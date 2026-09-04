"""Registro central de tools.

O artefato mais importante do projeto: dele saem as ferramentas do loop interno,
o servidor MCP (etapa 6) e a documentação. Nada escreve no banco sem passar aqui.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

Safety = Literal["safe", "confirm"]


@dataclass
class ToolContext:
    """O que um handler recebe além dos argumentos."""

    config: Any
    conn: sqlite3.Connection
    actor: str = "cli"
    # opcional: sem ele a busca funciona só por palavra-chave
    embedder: Any = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    safety: Safety = "safe"

    @property
    def api_name(self) -> str:
        """A OpenAI só aceita [a-zA-Z0-9_-] em nome de tool; o ponto é interno."""
        return self.name.replace(".", "_")

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.api_name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None

    def to_json(self) -> str:
        payload = {"ok": self.ok}
        if self.ok:
            payload["data"] = self.data
        else:
            payload["error"] = self.error
        return json.dumps(payload, ensure_ascii=False, default=str)


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, parameters: dict[str, Any],
                 safety: Safety = "safe") -> Callable:
        def decorator(fn: Callable) -> Callable:
            if name in self._tools:
                raise ValueError(f"tool duplicada: {name}")
            self._tools[name] = Tool(name, description, parameters, fn, safety)
            return fn

        return decorator

    def get(self, name: str) -> Tool | None:
        """Aceita tanto `tasks.create` quanto o `tasks_create` que a API devolve."""
        tool = self._tools.get(name)
        if tool is not None:
            return tool
        return next((t for t in self._tools.values() if t.api_name == name), None)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai() for t in self._tools.values()]

    def call(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(False, error=f"tool desconhecida: {name}")
        name = tool.name

        unknown = set(args) - set(tool.parameters.get("properties", {}))
        if unknown:
            return ToolResult(False, error=f"argumentos inesperados: {sorted(unknown)}")

        missing = set(tool.parameters.get("required", [])) - set(args)
        if missing:
            return ToolResult(False, error=f"argumentos faltando: {sorted(missing)}")

        try:
            result = ToolResult(True, data=tool.handler(ctx, **args))
        except ValueError as exc:
            result = ToolResult(False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - o loop precisa continuar vivo
            result = ToolResult(False, error=f"{type(exc).__name__}: {exc}")

        self._audit(ctx, name, args, result)
        return result

    @staticmethod
    def _audit(ctx: ToolContext, name: str, args: dict, result: ToolResult) -> None:
        summary = result.error if not result.ok else json.dumps(
            result.data, ensure_ascii=False, default=str
        )[:400]
        ctx.conn.execute(
            "INSERT INTO audit (actor, tool, args_json, result_summary, ok)"
            " VALUES (?, ?, ?, ?, ?)",
            (ctx.actor, name, json.dumps(args, ensure_ascii=False, default=str),
             summary, int(result.ok)),
        )


registry = Registry()
