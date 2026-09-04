"""CLI do my-aide."""

from __future__ import annotations

import sqlite3

import typer
from rich.console import Console
from rich.table import Table

from aide import __version__
from aide.config import load_config
from aide.core.orchestrator import Orchestrator, record_usage
from aide.llm import build_provider
from aide.storage import connect, migrate

app = typer.Typer(help="Assessor pessoal local.", no_args_is_help=True)
console = Console()


def _open_db() -> tuple[object, sqlite3.Connection]:
    config = load_config()
    conn = connect(config.db_path)
    migrate(conn)
    return config, conn


@app.command()
def init() -> None:
    """Cria o banco e aplica as migrations."""
    config = load_config()
    conn = connect(config.db_path)
    applied = migrate(conn)
    if applied:
        console.print(f"[green]Aplicado:[/] {', '.join(applied)}")
    else:
        console.print("[dim]Banco já está atualizado.[/]")
    console.print(f"[dim]{config.db_path}[/]")


@app.command()
def doctor() -> None:
    """Confere se o ambiente está pronto."""
    config = load_config()
    checks = [
        ("config.yaml lido", True, config.timezone),
        ("OPENAI_API_KEY", bool(config.llm.api_key), "definida" if config.llm.api_key else "faltando — veja .env.example"),
        ("banco", config.db_path.exists(), str(config.db_path)),
        ("vault", config.vault_dir.exists(), str(config.vault_dir)),
    ]
    table = Table(show_header=False, box=None)
    for name, ok, detail in checks:
        table.add_row("[green]ok[/]" if ok else "[red]--[/]", name, f"[dim]{detail}[/]")
    console.print(table)


@app.command()
def ask(text: str) -> None:
    """Faz uma pergunta e imprime a resposta."""
    config, conn = _open_db()
    llm = build_provider(config, usage_sink=record_usage(conn))
    console.print(Orchestrator(config, conn, llm).ask(text))


@app.command()
def chat() -> None:
    """Conversa contínua. Ctrl-C ou 'sair' para encerrar."""
    config, conn = _open_db()
    llm = build_provider(config, usage_sink=record_usage(conn))
    agent = Orchestrator(config, conn, llm)
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

    table = Table(title=f"Uso de LLM — {days} dias")
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
