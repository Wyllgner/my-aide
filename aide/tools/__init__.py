"""Importar este pacote registra todas as tools."""

from aide.tools import (  # noqa: F401
    clock,
    events,
    expenses,
    memory,
    notes,
    people,
    reminders,
    tasks,
    usage,
    work_orders,
)
from aide.tools.registry import Registry, Tool, ToolContext, ToolResult, registry

__all__ = ["Registry", "Tool", "ToolContext", "ToolResult", "registry"]
