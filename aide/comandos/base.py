"""O que todo comando compartilha: o app, o console e a abertura do banco.

Fica separado porque é a única coisa que os módulos de comando importam uns
dos outros — sem isto cada um puxaria o vizinho e a quebra por assunto não
teria servido para nada.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from aide.channels import formato
from aide.config import load_config
from aide.core.context import now_in
from aide.core.orchestrator import Orchestrator, record_usage
from aide.llm import build_provider
from aide.storage import connect, migrate
from aide.tools.registry import ToolContext

app = typer.Typer(help="Assessor pessoal local.", no_args_is_help=True)
console = Console()


PRIORITY_STYLE = {1: "red", 2: "white", 3: "dim", 4: "dim"}


def _open_db() -> tuple[object, sqlite3.Connection]:
    config = load_config()
    conn = connect(config.db_path)
    migrate(conn)
    return config, conn


def _embedder(config, conn_or_factory):
    """Sem chave ou sem rede o assessor segue funcionando, só sem semântica.

    Aceita fábrica de conexão: no daemon o embedder é usado de outra thread, e
    uma conexão da thread principal faz o registro de uso explodir.
    """
    from aide.llm.embeddings import Embedder

    if not config.llm.api_key:
        return None
    try:
        return Embedder(config, usage_sink=record_usage(conn_or_factory))
    except Exception:  # noqa: BLE001
        return None


def _ctx() -> tuple[object, sqlite3.Connection, ToolContext]:
    config, conn = _open_db()
    # ver_privado só aqui: é o dono, no terminal dele, olhando a própria
    # máquina. Todo outro caminho — modelo, MCP, Telegram, GUI — fica no padrão.
    return config, conn, ToolContext(config=config, conn=conn, actor="cli",
                                     embedder=_embedder(config, conn),
                                     ver_privado=True)


def _confirm(name: str, args: dict) -> bool:
    console.print(f"[yellow]O assessor quer executar[/] {name} [dim]{args}[/]")
    return typer.confirm("autorizar?", default=False)


def _agent(config, conn) -> Orchestrator:
    llm = build_provider(config, usage_sink=record_usage(conn))
    return Orchestrator(config, conn, llm, confirm=_confirm,
                        embedder=_embedder(config, conn))


def _fmt_due(due: str | None, now: datetime) -> tuple[str, str]:
    if not due:
        return "—", "dim"
    moment = datetime.fromisoformat(due)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=now.tzinfo)
    # Converte para o fuso de hoje antes de mostrar. Um prazo gravado noutro
    # fuso — porque você mudou de cidade, ou porque veio de um feed iCal —
    # apareceria com a hora de lá, e você leria o horário errado achando que
    # está certo. A comparação abaixo sempre esteve correta: ela usa o instante.
    moment = moment.astimezone(now.tzinfo)
    # o texto vem do mesmo lugar que os briefings usam, para o prazo não ser
    # escrito de dois jeitos dependendo de onde você olha
    texto = formato.quando(due, now)
    if moment < now:
        return texto, "red"
    if moment.date() == now.date():
        return texto, "yellow"
    return texto, "white"


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


