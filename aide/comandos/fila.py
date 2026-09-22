"""Fila de trabalho e a ponte MCP para o executor externo."""

from __future__ import annotations

import typer

from aide.comandos.base import _ctx, app, console
from aide.tools import registry


@app.command(rich_help_panel="Fila de trabalho")
def fila(status: str = typer.Argument("open", help="open|claimed|done|dropped|all")) -> None:
    """A fila de trabalho esperando por um executor externo."""
    _, _, ctx = _ctx()
    resultado = registry.call("work_orders.list", {"status": status, "limit": 30}, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)
    if not resultado.data:
        console.print("[dim]Fila vazia.[/]")
        return

    cores = {"open": "yellow", "claimed": "cyan", "done": "green", "dropped": "dim"}
    for o in resultado.data:
        cor = cores.get(o["status"], "white")
        console.print(f"[dim]#{o['id']}[/] [{cor}]{o['status']}[/] {o['goal']}")
        if o.get("context"):
            console.print(f"    [dim]{o['context']}[/]")
        if o.get("result_summary"):
            console.print(f"    [green]→[/] {o['result_summary']}")


@app.command(rich_help_panel="Fila de trabalho")
def enfileirar(objetivo: str,
               contexto: str = typer.Option(None, "--contexto", "-c"),
               criterio: str = typer.Option(None, "--criterio", "-k"),
               prioridade: int = typer.Option(2, "--prio", "-P")) -> None:
    """Põe um trabalho na fila para um executor externo fazer."""
    _, _, ctx = _ctx()
    args = {"goal": objetivo, "priority": prioridade}
    if contexto:
        args["context"] = contexto
    if criterio:
        args["done_criteria"] = criterio
    resultado = registry.call("work_orders.create", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)
    console.print(f"[green]#{resultado.data['id']}[/] enfileirada")


@app.command(name="mcp-config", rich_help_panel="Fila de trabalho")
def mcp_config() -> None:
    """Imprime a configuração para plugar um cliente MCP neste assessor."""
    import json
    import sys
    from pathlib import Path

    binario = str(Path(sys.executable).parent / "myaide-mcp")
    bloco = {"mcpServers": {"my-aide": {"command": binario, "args": []}}}
    console.print(json.dumps(bloco, indent=2))
    console.print("\n[dim]Cole em claude_desktop_config.json (ou no cliente MCP que usar).[/]")
    console.print("[dim]Linux: ~/.config/Claude/claude_desktop_config.json[/]")


