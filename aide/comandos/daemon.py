"""O daemon e o bot: o assessor rodando sem você abrir nada."""

from __future__ import annotations

import logging

import typer
from rich.table import Table

from aide.channels import build_notifier
from aide.comandos.base import _embedder, _open_db, app, console, load_config
from aide.core.orchestrator import record_usage
from aide.llm import build_provider
from aide.scheduler.jobs import JOBS, JobDeps, build_scheduler
from aide.storage import connect
from aide.tools import registry


def _deps(por_thread: bool = False) -> JobDeps:
    """`por_thread` para o daemon: cada worker do scheduler abre a sua conexão."""
    config, conn = _open_db()
    notifier = build_notifier(config)
    if por_thread:
        deps = JobDeps(config=config, llm=None, notifier=notifier,
                       conn_factory=lambda: connect(config.db_path))
        deps.llm = build_provider(config, usage_sink=record_usage(deps.db))
        deps.embedder = _embedder(config, deps.db)
        return deps
    return JobDeps(config=config, llm=build_provider(config, usage_sink=record_usage(conn)),
                   notifier=notifier, conn=conn, embedder=_embedder(config, conn))


def _start_bot(config, deps):
    """Sobe o bot do Telegram junto do daemon, se estiver configurado."""
    if not config.telegram.usable:
        return None

    from aide.channels.telegram_bot import TelegramBot

    # deps.db (sem parênteses): a conexão é resolvida na thread que usar
    bot = TelegramBot(config, deps.conn_factory, deps.llm, registry,
                      embedder=deps.embedder)
    bot.start()
    console.print(f"[green]telegram no ar[/] [dim]chats {list(config.telegram.allowed_chat_ids)}[/]")
    return bot


@app.command()
def serve(log_level: str = typer.Option("INFO", "--log-level")) -> None:
    """Roda o daemon: lembretes, cobranças, briefings e o bot do Telegram."""
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


