"""Importar este pacote registra todas as tools."""

from aide.tools import (  # noqa: F401
    clock,
    memory,
    notes,
    reminders,
    tasks,
    work_orders,
)
from aide.tools.registry import Registry, Tool, ToolContext, ToolResult, registry

__all__ = ["Registry", "Tool", "ToolContext", "ToolResult", "registry"]
