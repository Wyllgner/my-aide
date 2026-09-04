"""Orquestrador. Etapa 1: conversa sem tools, persistindo a sessão."""

from __future__ import annotations

import json
import sqlite3
import uuid

from aide.core import context
from aide.llm.base import LLMProvider, Message


class Orchestrator:
    def __init__(self, config, conn: sqlite3.Connection, llm: LLMProvider,
                 session_id: str | None = None):
        self.config = config
        self.conn = conn
        self.llm = llm
        self.session_id = session_id or uuid.uuid4().hex[:12]

    def history(self) -> list[Message]:
        rows = self.conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (self.session_id,),
        ).fetchall()
        return [Message(role=r["role"], content=r["content"] or "") for r in rows]

    def _save(self, role: str, content: str, tool_calls: list | None = None) -> None:
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls) VALUES (?, ?, ?, ?)",
            (self.session_id, role, content, json.dumps(tool_calls) if tool_calls else None),
        )

    def ask(self, text: str) -> str:
        self._save("user", text)
        messages = context.build(self.config, self.history())
        response = self.llm.complete(messages, purpose="chat")
        self._save("assistant", response.text, response.tool_calls)
        return response.text


def record_usage(conn: sqlite3.Connection):
    """Sink de uso para o provider: grava cada chamada em llm_usage."""

    def sink(model, purpose, input_tokens, output_tokens, latency_ms):
        conn.execute(
            "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens, latency_ms)"
            " VALUES (?, ?, ?, ?, ?)",
            (model, purpose, input_tokens, output_tokens, latency_ms),
        )

    return sink
