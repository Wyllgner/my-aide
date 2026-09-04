"""Importar este pacote registra todas as tools."""

from aide.tools import clock, reminders, tasks  # noqa: F401
from aide.tools.registry import Registry, Tool, ToolContext, ToolResult, registry

__all__ = ["Registry", "Tool", "ToolContext", "ToolResult", "registry"]
