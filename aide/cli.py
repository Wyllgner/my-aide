"""CLI do my-aide."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from aide import __version__
from aide.channels import build_notifier
from aide.config import load_config
from aide.core.context import now_in
from aide.core.orchestrator import Orchestrator, record_usage
from aide.llm import build_provider
from aide.scheduler import rules
from aide.scheduler.jobs import JOBS, JobDeps, build_scheduler
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
        ("telegram", config.telegram.usable,
         "configurado" if config.telegram.usable
         else "desligado (opcional — veja 'aide telegram-id')"),
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


# ---------- daemon ----------


def _deps(por_thread: bool = False) -> JobDeps:
    """`por_thread` para o daemon: cada worker do scheduler abre a sua conexão."""
    config, conn = _open_db()
    notifier = build_notifier(config)
    if por_thread:
        deps = JobDeps(config=config, llm=None, notifier=notifier,
                       conn_factory=lambda: connect(config.db_path))
        deps.llm = build_provider(config, usage_sink=record_usage(deps.db))
        return deps
    return JobDeps(config=config, llm=build_provider(config, usage_sink=record_usage(conn)),
                   notifier=notifier, conn=conn)


def _start_bot(config, deps):
    """Sobe o bot do Telegram junto do daemon, se estiver configurado."""
    if not config.telegram.usable:
        return None

    from aide.channels.telegram_bot import TelegramBot

    bot = TelegramBot(config, deps.conn_factory, deps.llm, registry)
    bot.start()
    console.print(f"[green]telegram no ar[/] [dim]chats {list(config.telegram.allowed_chat_ids)}[/]")
    return bot


@app.command()
def serve(log_level: str = typer.Option("INFO", "--log-level")) -> None:
    """Roda o daemon: lembretes, cobranças, briefings e o bot do Telegram."""
    import logging
    import signal
    import threading

    logging.basicConfig(level=log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config, _ = _open_db()
    deps = _deps(por_thread=True)
    scheduler = build_scheduler(deps)
    scheduler.start()
    bot = _start_bot(config, deps)

    table = Table(title="Jobs agendados", box=None, title_justify="left")
    table.add_column("job", style="cyan")
    table.add_column("próxima execução")
    for job in scheduler.get_jobs():
        table.add_row(job.id, str(job.next_run_time))
    console.print(table)

    parar = threading.Event()
    for sinal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sinal, lambda *_: parar.set())

    console.print("[dim]daemon no ar · ctrl-c para sair[/]")
    parar.wait()
    if bot:
        bot.stop()
    scheduler.shutdown(wait=False)
    console.print("[dim]encerrado[/]")


@app.command(name="telegram-id")
def telegram_id(espera: int = typer.Option(60, "--espera", "-t",
                                           help="segundos aguardando a mensagem")) -> None:
    """Descobre o chat id: rode isto e mande qualquer mensagem para o bot."""
    from aide.channels.telegram import TelegramClient, TelegramError

    # via load_config, que é quem carrega o .env — os.getenv sozinho não vê nada
    token = load_config().telegram.token
    if not token:
        console.print("[red]TELEGRAM_BOT_TOKEN não definida.[/] "
                      "Crie um bot com o @BotFather e ponha o token no .env")
        raise typer.Exit(1)

    client = TelegramClient(token)
    try:
        bot = client.me()
    except TelegramError as exc:
        console.print(f"[red]token não funcionou:[/] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"bot [cyan]@{bot['username']}[/] · mande uma mensagem para ele agora")
    try:
        updates = client.get_updates(timeout=espera)
    except TelegramError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    ids = {u.get("message", {}).get("chat", {}).get("id") for u in updates}
    ids.discard(None)
    if not ids:
        console.print("[yellow]nenhuma mensagem chegou.[/] Tente de novo.")
        raise typer.Exit(1)

    for chat_id in ids:
        console.print(f"[green]chat id:[/] {chat_id}")
    console.print("\n[dim]Ponha em config.yaml:[/]")
    console.print("[dim]telegram:[/]")
    console.print("[dim]  enabled: true[/]")
    console.print(f"[dim]  allowed_chat_ids: [{next(iter(ids))}][/]")


@app.command(name="job")
def rodar_job(nome: str = typer.Argument(..., help=" | ".join(JOBS))) -> None:
    """Roda um job do daemon agora, para testar."""
    if nome not in JOBS:
        console.print(f"[red]job desconhecido.[/] Use: {', '.join(JOBS)}")
        raise typer.Exit(1)
    resultado = JOBS[nome](_deps())
    console.print(f"[dim]{nome} → {resultado}[/]")


@app.command()
def checar() -> None:
    """Mostra o que as regras de condição estão vendo agora."""
    config, conn = _open_db()
    achados = rules.evaluate(conn, now_in(config.timezone))
    if not achados:
        console.print("[green]Nada pedindo atenção.[/]")
        return

    cores = {1: "red", 2: "yellow", 3: "dim"}
    table = Table(box=None, show_header=False)
    for f in achados:
        table.add_row(f"[{cores[f.severity]}]{f.rule}[/]", f.summary)
    console.print(table)


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
