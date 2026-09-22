"""Tarefas: o que precisa de você."""

from __future__ import annotations

import typer

from aide.comandos.base import _ctx, _print_tasks, app, console
from aide.tools import registry

# O filtro é o nome que a tool entende; o título é o que você lê. Sem este mapa
# a tabela saía encabeçada por "today" ou "inbox" no meio de uma tela em
# português — e "inbox" ainda não diz o que está vendo.
TITULOS = {
    "today": "Para hoje",
    "overdue": "Atrasadas",
    "week": "Nos próximos 7 dias",
    "inbox": "Sem prazo",
    "done": "Concluídas",
    "all": "Todas as tarefas",
}


@app.command(rich_help_panel="Tarefas")
def hoje() -> None:
    """O que precisa de você hoje."""
    config, _, ctx = _ctx()
    rows = registry.call("tasks.list", {"filter": "today"}, ctx).data
    _print_tasks(rows, config, "Hoje")


@app.command(name="ls", rich_help_panel="Tarefas")
def listar(filtro: str = typer.Argument("today", help="today|overdue|week|inbox|done|all"),
           projeto: str = typer.Option(None, "--projeto", "-p")) -> None:
    """Lista tarefas por filtro."""
    config, _, ctx = _ctx()
    args = {"filter": filtro}
    if projeto:
        args["project"] = projeto
    result = registry.call("tasks.list", args, ctx)
    if not result.ok:
        console.print(f"[red]{result.error}[/]")
        raise typer.Exit(1)
    _print_tasks(result.data, config, TITULOS.get(filtro, filtro))


@app.command(rich_help_panel="Tarefas")
def add(texto: str, prazo: str = typer.Option(None, "--prazo", "-d", help="ISO 8601"),
        prioridade: int = typer.Option(2, "--prio", "-P"),
        projeto: str = typer.Option(None, "--projeto", "-p")) -> None:
    """Cria uma tarefa direto, sem passar pela LLM."""
    _, _, ctx = _ctx()
    args = {"title": texto, "priority": prioridade}
    if prazo:
        args["due"] = prazo
    if projeto:
        args["project"] = projeto
    result = registry.call("tasks.create", args, ctx)
    if not result.ok:
        console.print(f"[red]{result.error}[/]")
        raise typer.Exit(1)
    console.print(f"[green]#{result.data['id']}[/] {result.data['title']}")


@app.command(rich_help_panel="Tarefas")
def done(task_id: int) -> None:
    """Conclui uma tarefa."""
    _, _, ctx = _ctx()
    result = registry.call("tasks.complete", {"id": task_id}, ctx)
    if not result.ok:
        console.print(f"[red]{result.error}[/]")
        raise typer.Exit(1)
    console.print(f"[green]feito[/] #{task_id} {result.data['title']}")


