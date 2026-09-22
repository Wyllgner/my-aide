"""Notas, busca e memória."""

from __future__ import annotations

import sys

import typer
from rich.table import Table

from aide.channels import formato
from aide.comandos.base import _ctx, app, console
from aide.tools import registry


@app.command(rich_help_panel="Notas e memória")
def nota(titulo: str, corpo: str = typer.Argument(None),
         tags: str = typer.Option(None, "--tags", "-t")) -> None:
    """Guarda uma nota. Sem corpo, lê da entrada padrão."""

    texto = corpo if corpo is not None else sys.stdin.read()
    _, _, ctx = _ctx()
    args = {"title": titulo, "body": texto}
    if tags:
        args["tags"] = tags
    resultado = registry.call("notes.create", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)
    console.print(f"[green]#{resultado.data['id']}[/] {resultado.data['path']}")


@app.command(rich_help_panel="Notas e memória")
def notas(limite: int = typer.Option(20, "--limite", "-n")) -> None:
    """Lista as notas mais recentes."""
    _, _, ctx = _ctx()
    linhas = registry.call("notes.list", {"limit": limite}, ctx).data
    if not linhas:
        console.print("[dim]Nenhuma nota ainda.[/]")
        return
    table = Table(box=None)
    table.add_column("id", style="dim", justify="right")
    table.add_column("nota")
    table.add_column("tags", style="dim")
    for n in linhas:
        table.add_row(str(n["id"]), n["title"], n["tags"] or "")
    console.print(table)


@app.command(rich_help_panel="Notas e memória")
def buscar(consulta: str, limite: int = typer.Option(5, "--limite", "-n")) -> None:
    """Busca nas notas por significado e palavra-chave."""
    _, _, ctx = _ctx()
    achados = registry.call("notes.search", {"query": consulta, "limit": limite}, ctx).data
    if not achados:
        console.print("[dim]Nada encontrado.[/]")
        return
    for a in achados:
        console.print(f"[cyan]#{a['id']}[/] [bold]{a['title']}[/]")
        if a.get("trecho"):
            console.print(f"  [dim]{a['trecho'].strip()[:160]}[/]")


@app.command(rich_help_panel="Notas e memória")
def perfil() -> None:
    """Mostra o que o assessor sabe sobre você."""
    _, _, ctx = _ctx()
    fatos = registry.call("memory.list", {"kind": "profile"}, ctx).data
    if not fatos:
        console.print("[dim]Ele ainda não sabe nada sobre você.[/]")
        return
    table = Table(box=None, show_header=False)
    for f in fatos:
        confianca = "" if f["confidence"] >= 1 else " [dim](incerto)[/]"
        table.add_row(f"[cyan]{f['key']}[/]", f["value"] + confianca)
    console.print(table)


@app.command(rich_help_panel="Notas e memória")
def reindexar() -> None:
    """Reconstrói o índice a partir dos arquivos do vault.

    O markdown é a fonte da verdade, e aqui isso vale nos dois sentidos: a linha
    sem arquivo é acusada, e o arquivo sem linha é adotado. O mesmo trabalho que
    o daemon faz sozinho, mas reindexando tudo em vez de só o que mudou, que é o
    que serve depois de um banco corrompido.
    """
    from pathlib import Path

    from aide.storage.reconciliacao import reconciliar

    config, conn, ctx = _ctx()
    relato = reconciliar(conn, Path(config.vault_dir), embedder=ctx.embedder, forcar=True)

    for caminho in relato.recolhidas:
        console.print(f"[yellow]recolhido para a lixeira:[/] {caminho}")
    for note_id, titulo in relato.adotadas:
        console.print(f"[green]adotada:[/] #{note_id} {titulo}")
    for note_id, titulo, caminho in relato.sumidas:
        console.print(f"[red]sumiu:[/] {caminho} [dim](#{note_id} {titulo})[/]")

    partes = [f"[green]{formato.plural(len(relato.reindexadas), 'nota reindexada')}[/]"]
    if relato.adotadas:
        partes.append(f"[green]{formato.plural(len(relato.adotadas), 'adotada')}[/]")
    if relato.recolhidas:
        partes.append(f"[yellow]{formato.plural(len(relato.recolhidas), 'recolhida')} "
                      f"para a lixeira[/]")
    if relato.sumidas:
        partes.append(f"[red]{formato.plural(len(relato.sumidas), 'arquivo sumido')}[/]")
    console.print(" · ".join(partes))
