"""Conversar com o assessor."""

from __future__ import annotations

from aide.comandos.base import _agent, _open_db, app, console


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


