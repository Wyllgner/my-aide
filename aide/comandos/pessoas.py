"""Agenda e pessoas — os dois lados do que envolve outra gente."""

from __future__ import annotations

import typer
from rich.table import Table

from aide.channels import formato
from aide.comandos.base import _ctx, app, console, now_in
from aide.tools import registry


@app.command(rich_help_panel="Agenda e pessoas")
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
        console.print(f"[dim]{formato.plural(resultado['importados'], 'evento')} "
                      f"importados[/]")

    eventos = registry.call("events.list", {"dias": dias}, ctx).data
    if not eventos:
        # dizer só "nada na agenda" faz parecer que o dia está livre, quando o
        # que existe é assessor sem calendário nenhum para olhar
        if not config.calendar_url:
            console.print("[dim]Nenhum calendário configurado.[/] Cole o endereço "
                          "secreto em iCal da sua agenda em [bold]calendar.ics_url[/] "
                          "(config.local.yaml) e rode [bold]myaide agenda --sync[/].")
        else:
            console.print(f"[dim]Nada na agenda nos próximos "
                          f"{formato.plural(dias, 'dia')}.[/]")
        return

    table = Table(box=None)
    table.add_column("quando")
    table.add_column("compromisso")
    table.add_column("onde", style="dim")
    agora = now_in(config.timezone)
    for e in eventos:
        table.add_row(formato.quando(e["start_at"], agora), e["title"], e["location"] or "")
    console.print(table)

    conflitos = registry.call("events.conflicts", {"dias": dias}, ctx).data
    for c in conflitos:
        console.print(f"[red]conflito:[/] {c['a']}  ×  {c['b']}")


@app.command(rich_help_panel="Agenda e pessoas")
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


@app.command(rich_help_panel="Agenda e pessoas")
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


