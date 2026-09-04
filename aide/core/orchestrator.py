"""Orquestrador: monta o contexto e roda o loop de tool-calling."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from collections.abc import Callable

from aide.core import context
from aide.llm.base import LLMProvider, Message
from aide.tools import registry as tool_registry
from aide.tools.registry import ToolContext

log = logging.getLogger(__name__)

MAX_ITERATIONS = 8


class Orchestrator:
    def __init__(self, config, conn: sqlite3.Connection, llm: LLMProvider,
                 session_id: str | None = None, registry=None,
                 confirm: Callable[[str, dict], bool] | None = None,
                 actor: str = "cli"):
        self.config = config
        self.conn = conn
        self.llm = llm
        self.registry = registry or tool_registry
        self.session_id = session_id or uuid.uuid4().hex[:12]
        # devolve True para autorizar uma tool marcada 'confirm'
        self.confirm = confirm
        self.actor = actor

    # ---------- persistência ----------

    def history(self) -> list[Message]:
        rows = self.conn.execute(
            "SELECT role, content, tool_calls FROM messages WHERE session_id = ? ORDER BY id",
            (self.session_id,),
        ).fetchall()
        out = []
        for r in rows:
            # o par assistant-com-tool_calls + resultado fica fora do histórico:
            # remontá-lo pela metade quebra a API, e o que importa já está na
            # resposta final e no snapshot de estado.
            if r["role"] == "tool" or r["tool_calls"]:
                continue
            if not (r["content"] or "").strip():
                continue
            out.append(Message(role=r["role"], content=r["content"]))
        return out

    def _save(self, message: Message) -> None:
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls) VALUES (?, ?, ?, ?)",
            (self.session_id, message.role, message.content,
             json.dumps(message.tool_calls) if message.tool_calls else None),
        )

    # ---------- loop ----------

    def ask(self, text: str) -> str:
        self._save(Message(role="user", content=text))
        messages = context.build(self.config, self.history(), conn=self.conn)
        schemas = self.registry.schemas()
        ctx = ToolContext(config=self.config, conn=self.conn, actor=self.actor)

        for _ in range(MAX_ITERATIONS):
            response = self.llm.complete(messages, tools=schemas, purpose="chat")

            if not response.tool_calls:
                reply = response.text.strip()
                self._save(Message(role="assistant", content=reply))
                return reply

            call_msg = Message(role="assistant", content=response.text,
                               tool_calls=response.tool_calls)
            messages.append(call_msg)
            self._save(call_msg)

            for call in response.tool_calls:
                result_msg = self._run_call(call, ctx)
                messages.append(result_msg)
                self._save(result_msg)

        fallback = "Me embananei e dei voltas demais nessa. Pode reformular?"
        self._save(Message(role="assistant", content=fallback))
        return fallback

    def _run_call(self, call: dict, ctx: ToolContext) -> Message:
        fn = call.get("function", {})
        name = fn.get("name", "")
        raw_args = fn.get("arguments") or "{}"

        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args, error = {}, f"argumentos ilegíveis: {raw_args[:120]}"
            return Message(role="tool", tool_call_id=call.get("id"),
                           content=json.dumps({"ok": False, "error": error}))

        tool = self.registry.get(name)
        if tool and tool.safety == "confirm" and self.confirm and not self.confirm(name, args):
            payload = {"ok": False, "error": "o usuário não autorizou esta ação"}
            return Message(role="tool", tool_call_id=call.get("id"),
                           content=json.dumps(payload, ensure_ascii=False))

        log.debug("tool %s(%s)", name, args)
        result = self.registry.call(name, args, ctx)
        return Message(role="tool", tool_call_id=call.get("id"), content=result.to_json())


def record_usage(conn: sqlite3.Connection):
    """Sink de uso para o provider: grava cada chamada em llm_usage."""

    def sink(model, purpose, input_tokens, output_tokens, latency_ms):
        conn.execute(
            "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens, latency_ms)"
            " VALUES (?, ?, ?, ?, ?)",
            (model, purpose, input_tokens, output_tokens, latency_ms),
        )

    return sink
