"""A ponte entre a GUI e o core.

A GUI nunca escreve no banco direto: chama tools do registry, igual às outras
portas. Assim a auditoria, a validação e as regras de confirmação valem aqui
também — e uma tool nova aparece na interface sem código de persistência novo.
"""

from __future__ import annotations

from dataclasses import dataclass

from aide.core.context import now_in
from aide.storage import connect, migrate
from aide.tools import registry as tool_registry
from aide.tools.registry import ToolContext


@dataclass
class Momento:
    agora_iso: str
    hoje_ate: str


class Modelo:
    def __init__(self, config, conn=None, registry=None, embedder=None):
        self.config = config
        self.conn = conn or self._abrir(config)
        self.registry = registry or tool_registry
        self.embedder = embedder

    @staticmethod
    def _abrir(config):
        conn = connect(config.db_path)
        migrate(conn)
        return conn

    @property
    def ctx(self) -> ToolContext:
        return ToolContext(config=self.config, conn=self.conn, actor="gui",
                           embedder=self.embedder)

    def momento(self) -> Momento:
        agora = now_in(self.config.timezone)
        return Momento(
            agora_iso=agora.isoformat(timespec="minutes"),
            hoje_ate=agora.replace(hour=23, minute=59).isoformat(timespec="minutes"),
        )

    def chamar(self, tool: str, args: dict | None = None):
        """Devolve (ok, dado_ou_erro)."""
        resultado = self.registry.call(tool, args or {}, self.ctx)
        return resultado.ok, (resultado.data if resultado.ok else resultado.error)

    # ---------- consultas que a sidebar usa ----------

    def contadores(self) -> dict[str, int]:
        momento = self.momento()

        def conta(sql, p=()):
            return self.conn.execute(sql, p).fetchone()["c"]

        return {
            "hoje": conta(
                "SELECT COUNT(*) c FROM tasks WHERE deleted_at IS NULL AND status='open'"
                " AND (due_at <= ? OR (due_at IS NULL AND priority = 1))",
                (momento.hoje_ate,)),
            "atrasadas": conta(
                "SELECT COUNT(*) c FROM tasks WHERE deleted_at IS NULL AND status='open'"
                " AND due_at IS NOT NULL AND due_at < ?", (momento.agora_iso,)),
            "fila": conta("SELECT COUNT(*) c FROM work_orders WHERE status='open'"),
            "notas": conta("SELECT COUNT(*) c FROM notes WHERE deleted_at IS NULL"),
        }

    def projetos(self) -> list[tuple[str, int]]:
        linhas = self.conn.execute(
            "SELECT project, COUNT(*) c FROM tasks WHERE deleted_at IS NULL"
            " AND status='open' AND project IS NOT NULL GROUP BY project ORDER BY project"
        ).fetchall()
        return [(r["project"], r["c"]) for r in linhas]
