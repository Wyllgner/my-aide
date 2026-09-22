"""Conversar com o assessor."""

from __future__ import annotations

from aide.comandos.base import _agent, _open_db, app, console


def _responder(agent, texto: str) -> None:
    """Mostra o que está acontecendo enquanto trabalha.

    Uma pergunta pode virar três chamadas de tool e vários segundos de espera.
    Sem sinal na tela não há como saber se travou, e a reação natural é apertar
    Ctrl-C ou perguntar de novo, que faz o assessor trabalhar duas vezes.

    O passo de tool vira **linha impressa**, não texto do spinner: no terminal a
    tool acaba em milissegundos, e um texto que vive menos que um quadro de
    animação nunca chega a ser pintado. Como linha, ele fica: no fim você lê o
    que o assessor consultou para responder. O spinner guarda a espera que
    realmente dura, que é a do modelo.
    """
    from aide.channels import passos

    with console.status("[dim]pensando[/]", spinner="dots") as spinner:
        def contar(frase: str) -> None:
            if frase == passos.PENSANDO:
                spinner.update("[dim]pensando[/]")
            else:
                console.print(f"[dim]· {frase}[/]")

        agent.progresso = contar
        try:
            resposta = agent.ask(texto)
        finally:
            agent.progresso = None
    console.print(resposta)


@app.command(rich_help_panel="Conversar")
def ask(text: str) -> None:
    """Faz uma pergunta e imprime a resposta."""
    config, conn = _open_db()
    _responder(_agent(config, conn), text)


@app.command(rich_help_panel="Conversar")
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
        _responder(agent, text)
