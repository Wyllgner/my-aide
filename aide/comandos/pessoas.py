"""Agenda e pessoas — os dois lados do que envolve outra gente."""

from __future__ import annotations

import typer
from rich.table import Table

from aide.comandos.base import _ctx, app, console
from aide.tools import registry


@app.command()
def agenda(dias: int = typer.Option(7, "--dias", "-d"),
           sincronizar: bool = typer.Option(False, "--sync", "-s")) -> None:
    """Compromissos do calendário assinado."""
    config, conn, ctx = _ctx()

    if sincronizar:
        from aide.tools.events import sincronizar as puxar

        try:
            resultado = puxar(conn, config)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc
        console.print(f"[dim]{resultado['importados']} evento(s) importado(s)[/]")

    eventos = registry.call("events.list", {"dias": dias}, ctx).data
    if not eventos:
        console.print("[dim]Nada na agenda.[/]"
                      + ("" if config.calendar_url else "  (nenhum calendário configurado)"))
        return

    table = Table(box=None)
    table.add_column("quando")
    table.add_column("compromisso")
    table.add_column("onde", style="dim")
    for e in eventos:
        dia, _, hora = e["start_at"].partition("T")
        table.add_row(f"{dia[8:10]}/{dia[5:7]} {hora[:5]}", e["title"], e["location"] or "")
    console.print(table)

    conflitos = registry.call("events.conflicts", {"dias": dias}, ctx).data
    for c in conflitos:
        console.print(f"[red]conflito:[/] {c['a']}  ×  {c['b']}")


@app.command()
def pessoas(atrasados: bool = typer.Option(False, "--atrasados", "-a")) -> None:
    """Com quem você combinou de manter contato."""
    _, _, ctx = _ctx()
    linhas = registry.call("people.list", {"atrasados": atrasados}, ctx).data
    if not linhas:
        console.print("[dim]Ninguém registrado.[/]" if not atrasados
                      else "[green]Ninguém em atraso.[/]")
        return

    table = Table(box=None)
    table.add_column("pessoa")
    table.add_column("relação", style="dim")
    table.add_column("sem falar")
    table.add_column("combinado", style="dim")
    for p in linhas:
        dias = p["dias_sem_falar"]
        texto = f"{dias}d" if dias is not None else "—"
        cor = "red" if p["atrasado"] else "white"
        table.add_row(p["name"], p["relation"] or "",
                      f"[{cor}]{texto}[/]",
                      f"a cada {p['cadence_days']}d" if p["cadence_days"] else "sem cobrança")
    console.print(table)


@app.command()
def falei(nome: str, nota: str = typer.Argument(None)) -> None:
    """Registra que você falou com alguém agora."""
    _, _, ctx = _ctx()
    args = {"name": nome}
    if nota:
        args["note"] = nota
    resultado = registry.call("people.touch", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)
    console.print(f"[green]ok[/] {resultado.data['name']}")


