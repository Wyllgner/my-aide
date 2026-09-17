"""Notas, busca e memória."""

from __future__ import annotations

import sys

import typer
from rich.table import Table

from aide.comandos.base import _ctx, app, console
from aide.tools import registry


@app.command()
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


@app.command()
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


@app.command()
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


@app.command()
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


@app.command()
def reindexar() -> None:
    """Reconstrói o índice a partir dos arquivos do vault.

    O markdown é a fonte da verdade: se o banco corromper, isto traz tudo de volta.
    """
    from pathlib import Path

    from aide.storage import vault
    from aide.storage.search import indexar

    _, conn, ctx = _ctx()
    linhas = conn.execute(
        "SELECT id, title, path FROM notes WHERE deleted_at IS NULL").fetchall()

    reindexadas = sumidas = 0
    for row in linhas:
        caminho = Path(row["path"])
        if not caminho.exists():
            console.print(f"[yellow]sumiu:[/] {caminho}")
            sumidas += 1
            continue
        corpo = vault.corpo_de(caminho)
        indexar(conn, row["id"], row["title"], corpo)
        if ctx.embedder:
            try:
                vetor = ctx.embedder.embed_one(f"{row['title']}\n\n{corpo}")
            except Exception:  # noqa: BLE001
                vetor = None
            if vetor:
                from aide.storage.search import guardar_vetor

                guardar_vetor(conn, "note", row["id"], f"{row['title']}\n\n{corpo}", vetor,
                              ctx.embedder.modelo)
        reindexadas += 1

    console.print(f"[green]{reindexadas} nota(s) reindexada(s)[/]"
                  + (f" · [yellow]{sumidas} arquivo(s) sumido(s)[/]" if sumidas else ""))


