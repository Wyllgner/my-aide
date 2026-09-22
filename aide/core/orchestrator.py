"""Orquestrador: monta o contexto e roda o loop de tool-calling."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from collections.abc import Callable

from aide.channels import passos
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
                 actor: str = "cli", embedder=None,
                 progresso: Callable[[str], None] | None = None):
        self.config = config
        self.conn = conn
        self.llm = llm
        self.registry = registry or tool_registry
        self.session_id = session_id or uuid.uuid4().hex[:12]
        # devolve True para autorizar uma tool marcada 'confirm'
        self.confirm = confirm
        self.actor = actor
        self.embedder = embedder
        # Recebe uma frase por passo ("olhando suas tarefas"). Quem chama decide
        # o que fazer com ela: spinner no terminal, "digitando" no Telegram.
        # Silêncio durante o trabalho é o que faz alguém mandar a mesma coisa
        # duas vezes, achando que não chegou.
        self.progresso = progresso

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

    def corrigir_ultima_resposta(self, texto: str) -> None:
        """Substitui a última fala do assistente pelo que foi mesmo enviado.

        Um canal pode trocar a resposta antes de entregá-la — o Telegram faz
        isso ao perguntar "tem certeza?" no lugar do texto do modelo. Se o
        histórico guardar a versão descartada, o modelo lê nas voltas seguintes
        uma fala que ele nunca disse, e aprende com ela. Foi assim que ele
        passou a responder "não foi possível apagar" sem sequer tentar: estava
        imitando um erro que só existia no transcrito.
        """
        linha = self.conn.execute(
            "SELECT id FROM messages WHERE session_id = ? AND role = 'assistant'"
            " ORDER BY id DESC LIMIT 1", (self.session_id,)).fetchone()
        if linha:
            self.conn.execute("UPDATE messages SET content = ? WHERE id = ?",
                              (texto, linha["id"]))

    def _save(self, message: Message) -> int:
        """Devolve o id: a volta inteira é atribuída à mensagem que a abriu."""
        cursor = self.conn.execute(
            "INSERT INTO messages (session_id, role, content, tool_calls) VALUES (?, ?, ?, ?)",
            (self.session_id, message.role, message.content,
             json.dumps(message.tool_calls) if message.tool_calls else None),
        )
        return cursor.lastrowid

    # ---------- loop ----------

    def ask(self, text: str) -> str:
        turno = self._save(Message(role="user", content=text))
        messages = context.build(self.config, self.history(), conn=self.conn)
        schemas = self.registry.schemas()
        ctx = ToolContext(config=self.config, conn=self.conn, actor=self.actor,
                          embedder=self.embedder)

        # O conteúdo vai em DEBUG, não em INFO. O daemon roda sob systemd, e o
        # que sai em INFO acaba no journal — uma segunda cópia da sua conversa,
        # fora do banco 0600 e sem passar pela marca de `private`. Em INFO fica
        # só o que serve para acompanhar o serviço; `--log-level DEBUG` traz o
        # resto quando você estiver depurando.
        log.info("[%s] mensagem recebida (%s caracteres)", self.actor, len(text))
        log.debug("[%s] pergunta: %s", self.actor, text)

        for _ in range(MAX_ITERATIONS):
            self._avisar(passos.PENSANDO)
            response = self.llm.complete(messages, tools=schemas, purpose="chat",
                                         sessao=self.session_id, turno=turno)

            if not response.tool_calls:
                reply = response.text.strip()
                log.info("[%s] respondido (%s caracteres)", self.actor, len(reply))
                log.debug("[%s] resposta: %s", self.actor, reply)
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

    def _avisar(self, frase: str) -> None:
        """Um passo nunca pode derrubar a conversa: se quem escuta falhar, o
        trabalho segue e o aviso é o que se perde."""
        if self.progresso is None:
            return
        try:
            self.progresso(frase)
        except Exception:
            log.debug("aviso de progresso falhou", exc_info=True)

    def _run_call(self, call: dict, ctx: ToolContext) -> Message:
        fn = call.get("function", {})
        name = fn.get("name", "")
        raw_args = fn.get("arguments") or "{}"
        self._avisar(passos.descrever(name))

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

        result = self.registry.call(name, args, ctx)
        resumo = result.to_json()
        # nome e desfecho em INFO; argumentos e retorno podem carregar o que a
        # pessoa escreveu, então descem para DEBUG. A trilha completa continua
        # na tabela `audit`, que vive dentro do banco fechado.
        log.info("[%s] tool %s -> %s", ctx.actor, name,
                 "ok" if result.ok else "ERRO")
        log.debug("[%s] tool %s(%s) -> %s", ctx.actor, name, args, resumo[:300])
        return Message(role="tool", tool_call_id=call.get("id"), content=resumo)


def record_usage(conn_or_factory):
    """Sink de uso para o provider: grava cada chamada em llm_usage.

    Aceita uma conexão ou uma função que devolve uma — o daemon chama de
    dentro de worker threads, onde a conexão do processo principal não vale.
    """

    def sink(model, purpose, input_tokens, output_tokens, latency_ms,
             sessao=None, turno=None):
        # sqlite3.Connection tem __call__, então callable() não serve para
        # distinguir uma conexão de uma fábrica de conexões.
        conn = (conn_or_factory if isinstance(conn_or_factory, sqlite3.Connection)
                else conn_or_factory())
        conn.execute(
            "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens,"
            " latency_ms, session_id, turn_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (model, purpose, input_tokens, output_tokens, latency_ms, sessao, turno),
        )

    return sink
