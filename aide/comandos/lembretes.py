"""Lembretes pelo terminal.

Existiam só por conversa ou por MCP, o que quer dizer que criar um lembrete
dependia de rede e de uma chamada de API. Aqui o horário é lido por um parser
determinístico: "me lembra às 20h" não tem por que custar nada.
"""

from __future__ import annotations

import typer

from aide.channels import formato
from aide.comandos.base import _ctx, app, console, now_in
from aide.core.quando import interpretar
from aide.tools import registry
from aide.tools.reminders import REPEAT_RULES

REPETICOES = {
    "diario": "daily", "diariamente": "daily",
    "dias-uteis": "weekdays", "semanal": "weekly",
    "mensal": "monthly", "anual": "yearly",
}


@app.command(rich_help_panel="Tarefas")
def lembrete(texto: str,
             quando: str = typer.Option(..., "--quando", "-q",
                                        help='Ex. "20h", "amanhã 9h", "quinta 20h", "25/09 14h"'),
             repete: str = typer.Option(None, "--repete", "-r",
                                        help=" | ".join(sorted(REPETICOES)))) -> None:
    """Cria um lembrete para uma hora marcada."""
    config, _, ctx = _ctx()
    agora = now_in(config.timezone)

    momento = interpretar(quando, agora)
    if momento is None:
        console.print(f"[red]não entendi o horário {quando!r}.[/] Tente "
                      '"20h", "amanhã 9h", "quinta 20h" ou "25/09 14h".')
        raise typer.Exit(1)

    args = {"text": texto, "when": momento.isoformat(timespec="minutes")}
    if repete:
        regra = REPETICOES.get(repete, repete)
        if regra not in REPEAT_RULES:
            console.print(f"[red]repetição desconhecida: {repete}[/] "
                          f"Use uma de: {', '.join(sorted(REPETICOES))}.")
            raise typer.Exit(1)
        args["repeat"] = regra

    resultado = registry.call("reminders.create", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)

    linha = resultado.data
    # ecoar o horário entendido, e não o texto digitado: "quinta 20h" pode ser
    # lido como outra quinta, e o erro só aparece na hora em que nada chega
    marca = f" [dim]· {formato.quando(linha['fire_at'], agora)}[/]"
    if linha.get("repeat"):
        marca += f" [dim]· repete {repete}[/]"
    console.print(f"[green]#{linha['id']}[/] {linha['text']}{marca}")


@app.command(rich_help_panel="Tarefas")
def lembretes() -> None:
    """Os lembretes que ainda vão disparar."""
    from rich.table import Table

    config, _, ctx = _ctx()
    agora = now_in(config.timezone)
    linhas = registry.call("reminders.list", {}, ctx).data
    if not linhas:
        console.print("[dim]Nenhum lembrete pendente.[/]")
        return

    invertido = {v: k for k, v in REPETICOES.items()}
    table = Table(box=None, padding=(0, 2, 0, 0))
    table.add_column("id", style="dim", justify="right")
    table.add_column("lembrete")
    table.add_column("quando")
    table.add_column("", style="dim")
    for r in linhas:
        table.add_row(str(r["id"]), r["text"], formato.quando(r["fire_at"], agora),
                      invertido.get(r.get("repeat_rule") or "", ""))
    console.print(table)


@app.command(rich_help_panel="Tarefas")
def cancelar(lembrete_id: int) -> None:
    """Cancela um lembrete pendente."""
    _, _, ctx = _ctx()
    resultado = registry.call("reminders.cancel", {"id": lembrete_id}, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)
    console.print(f"[green]cancelado[/] #{lembrete_id} {resultado.data.get('text', '')}")
