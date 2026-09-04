"""CLI do my-aide."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from aide import __version__
from aide.config import load_config
from aide.core.context import now_in
from aide.core.orchestrator import Orchestrator, record_usage
from aide.llm import build_provider
from aide.storage import connect, migrate
from aide.tools import registry
from aide.tools.registry import ToolContext

app = typer.Typer(help="Assessor pessoal local.", no_args_is_help=True)
console = Console()

PRIORITY_STYLE = {1: "red", 2: "white", 3: "dim", 4: "dim"}


def _open_db() -> tuple[object, sqlite3.Connection]:
    config = load_config()
    conn = connect(config.db_path)
    migrate(conn)
    return config, conn


def _ctx() -> tuple[object, sqlite3.Connection, ToolContext]:
    config, conn = _open_db()
    return config, conn, ToolContext(config=config, conn=conn, actor="cli")


def _confirm(name: str, args: dict) -> bool:
    console.print(f"[yellow]O assessor quer executar[/] {name} [dim]{args}[/]")
    return typer.confirm("autorizar?", default=False)


def _agent(config, conn) -> Orchestrator:
    llm = build_provider(config, usage_sink=record_usage(conn))
    return Orchestrator(config, conn, llm, confirm=_confirm)


def _fmt_due(due: str | None, now: datetime) -> tuple[str, str]:
    if not due:
        return "—", "dim"
    moment = datetime.fromisoformat(due)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=now.tzinfo)
    if moment < now:
        return moment.strftime("%d/%m %H:%M"), "red"
    if moment.date() == now.date():
        return moment.strftime("hoje %H:%M"), "yellow"
    return moment.strftime("%d/%m %H:%M"), "white"


def _print_tasks(rows: list[dict], config, title: str) -> None:
    if not rows:
        console.print("[dim]Nada por aqui.[/]")
        return

    now = now_in(config.timezone)
    table = Table(title=title, title_justify="left", box=None, padding=(0, 2, 0, 0))
    table.add_column("id", style="dim", justify="right")
    table.add_column("tarefa")
    table.add_column("prazo")
    table.add_column("", style="dim")

    for row in rows:
        due, style = _fmt_due(row.get("due_at"), now)
        marks = []
        if row.get("snooze_count"):
            marks.append(f"adiada {row['snooze_count']}x")
        if row.get("project"):
            marks.append(row["project"])
        table.add_row(
            str(row["id"]),
            f"[{PRIORITY_STYLE.get(row.get('priority'), 'white')}]{row['title']}[/]",
            f"[{style}]{due}[/]",
            " · ".join(marks),
        )
    console.print(table)


# ---------- setup ----------


@app.command()
def init() -> None:
    """Cria o banco e aplica as migrations."""
    config = load_config()
    conn = connect(config.db_path)
    applied = migrate(conn)
    console.print(f"[green]Aplicado:[/] {', '.join(applied)}" if applied
                  else "[dim]Banco já está atualizado.[/]")
    console.print(f"[dim]{config.db_path}[/]")


@app.command()
def doctor() -> None:
    """Confere se o ambiente está pronto."""
    config = load_config()
    key = config.llm.api_key
    checks = [
        ("config.yaml lido", True, config.timezone),
        ("OPENAI_API_KEY", bool(key), "definida" if key else "faltando — veja .env.example"),
        ("banco", config.db_path.exists(), str(config.db_path)),
        ("tools", bool(registry.names()), f"{len(registry.names())} registradas"),
    ]
    table = Table(show_header=False, box=None)
    for name, ok, detail in checks:
        table.add_row("[green]ok[/]" if ok else "[red]--[/]", name, f"[dim]{detail}[/]")
    console.print(table)


@app.command()
def tools() -> None:
    """Lista as tools registradas."""
    table = Table(box=None)
    table.add_column("tool", style="cyan")
    table.add_column("segurança", style="dim")
    table.add_column("descrição")
    for name in registry.names():
        tool = registry.get(name)
        table.add_row(name, tool.safety, tool.description.split(".")[0])
    console.print(table)


# ---------- tarefas ----------


@app.command()
def hoje() -> None:
    """O que precisa de você hoje."""
    config, _, ctx = _ctx()
    rows = registry.call("tasks.list", {"filter": "today"}, ctx).data
    _print_tasks(rows, config, "Hoje")


@app.command(name="ls")
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
    _print_tasks(result.data, config, filtro)


@app.command()
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


@app.command()
def done(task_id: int) -> None:
    """Conclui uma tarefa."""
    _, _, ctx = _ctx()
    result = registry.call("tasks.complete", {"id": task_id}, ctx)
    if not result.ok:
        console.print(f"[red]{result.error}[/]")
        raise typer.Exit(1)
    console.print(f"[green]feito[/] #{task_id} {result.data['title']}")


# ---------- conversa ----------


@app.command()
def ask(text: str) -> None:
    """Faz uma pergunta e imprime a resposta."""
    config, conn = _open_db()
    console.print(_agent(config, conn).ask(text))


@app.command()
def chat() -> None:
    """Conversa contínua. Ctrl-C ou 'sair' para encerrar."""
    config, conn = _open_db()
    agent = _agent(config, conn)
    console.print(f"[dim]sessão {agent.session_id} · 'sair' para encerrar[/]")

    while True:
        try:
            text = console.input("[bold cyan]› [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not text:
            continue
        if text.lower() in {"sair", "exit", "quit"}:
            break
        console.print(agent.ask(text))


@app.command()
def usage(days: int = 7) -> None:
    """Quanto o assessor consumiu de LLM nos últimos dias."""
    _, conn = _open_db()
    rows = conn.execute(
        "SELECT model, purpose, COUNT(*) n,"
        "       SUM(input_tokens) inp, SUM(output_tokens) outp"
        "  FROM llm_usage WHERE ts >= datetime('now', ?)"
        " GROUP BY model, purpose ORDER BY inp + outp DESC",
        (f"-{days} days",),
    ).fetchall()

    if not rows:
        console.print("[dim]Nenhuma chamada registrada.[/]")
        return

    table = Table(title=f"Uso de LLM — {days} dias", box=None)
    for col in ("modelo", "uso", "chamadas", "entrada", "saída"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["model"], r["purpose"] or "-", str(r["n"]), str(r["inp"]), str(r["outp"]))
    console.print(table)


@app.command()
def version() -> None:
    """Mostra a versão."""
    console.print(__version__)


if __name__ == "__main__":
    app()
