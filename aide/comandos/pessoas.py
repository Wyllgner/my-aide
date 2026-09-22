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
        texto = ("hoje" if dias == 0 else "ontem" if dias == 1
                 else formato.plural(dias, "dia") if dias is not None else "nunca")
        cor = "red" if p["atrasado"] else "white"
        table.add_row(p["name"], p["relation"] or "",
                      f"[{cor}]{texto}[/]",
                      f"a cada {formato.plural(p['cadence_days'], 'dia')}"
                      if p["cadence_days"] else "sem cobrança")
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

    # "ok Pedro" não dizia o que mudou; o que interessa é quando ele volta a
    # cobrar, que é a razão de registrar o contato
    p = next((x for x in registry.call("people.list", {}, ctx).data
              if x["id"] == resultado.data["id"]), None)
    recado = ""
    if p and p.get("cadence_days"):
        recado = (f" [dim]· cobro de novo em "
                  f"{formato.plural(p['cadence_days'], 'dia')}[/]")
    console.print(f"[green]contato de hoje registrado com[/] "
                  f"{resultado.data['name']}{recado}")


@app.command(rich_help_panel="Agenda e pessoas")
def pessoa(nome: str,
           relacao: str = typer.Option(None, "--relacao", "-r",
                                       help="amigo, família, trabalho, cliente..."),
           cadencia: int = typer.Option(None, "--cadencia", "-c",
                                        help="De quantos em quantos dias você quer ser cobrado."),
           esquecer: bool = typer.Option(False, "--esquecer",
                                         help="Para de acompanhar essa pessoa.")) -> None:
    """Passa a acompanhar alguém, ou muda o combinado com quem já é acompanhado.

    Cadastrar pessoa só existia por conversa e por MCP, então do terminal dava
    para registrar um contato com `myaide falei` mas não criar a pessoa: o
    comando falhava dizendo que não a conhecia, e não havia como ensinar.
    """
    _, _, ctx = _ctx()

    if esquecer:
        resultado = registry.call("people.remove", {"name": nome}, ctx)
        if not resultado.ok:
            console.print(f"[red]{resultado.error}[/]")
            raise typer.Exit(1)
        console.print(f"[green]não acompanho mais[/] {nome}")
        return

    args = {"name": nome}
    if relacao:
        args["relation"] = relacao
    if cadencia is not None:
        args["cadence_days"] = cadencia

    resultado = registry.call("people.add", args, ctx)
    # já registrado não é erro de quem digitou: é a intenção de mudar o combinado
    if not resultado.ok and "já está registrado" in (resultado.error or ""):
        resultado = registry.call("people.update", args, ctx)
        verbo = "atualizado"
    else:
        verbo = "registrado"

    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)

    p = resultado.data
    detalhes = [p["relation"]] if p.get("relation") else []
    detalhes.append(f"a cada {formato.plural(p['cadence_days'], 'dia')}"
                    if p.get("cadence_days") else "sem cobrança")
    console.print(f"[green]{verbo}[/] {p['name']} [dim]· {' · '.join(detalhes)}[/]")
