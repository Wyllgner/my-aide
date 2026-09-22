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
    sem arquivo é acusada, e o arquivo sem linha é adotado. Antes a varredura
    percorria só as linhas, então um `.md` escrito no editor nunca era achado e
    um arquivo de nota apagada ficava no vault invisível para sempre.
    """
    from pathlib import Path

    from aide.storage import vault
    from aide.storage.search import indexar

    config, conn, ctx = _ctx()
    vault_dir = Path(config.vault_dir)

    def _indexar(note_id: int, titulo: str, corpo: str) -> None:
        indexar(conn, note_id, titulo, corpo)
        if not ctx.embedder:
            return
        try:
            vetor = ctx.embedder.embed_one(f"{titulo}\n\n{corpo}")
        except Exception:  # noqa: BLE001
            return
        if vetor:
            from aide.storage.search import guardar_vetor

            guardar_vetor(conn, "note", note_id, f"{titulo}\n\n{corpo}", vetor,
                          ctx.embedder.modelo)

    vivas = {Path(r["path"]).resolve(): r for r in conn.execute(
        "SELECT id, title, path FROM notes WHERE deleted_at IS NULL")}
    apagadas = {Path(r["path"]).resolve() for r in conn.execute(
        "SELECT path FROM notes WHERE deleted_at IS NOT NULL")}

    reindexadas = adotadas = recolhidas = sumidas = 0

    for caminho in vault.arquivos(vault_dir):
        real = caminho.resolve()
        if real in vivas:
            row = vivas[real]
            _indexar(row["id"], row["title"], vault.corpo_de(caminho))
            reindexadas += 1
            continue
        if real in apagadas:
            # a nota foi apagada, mas o arquivo ficou: recolhe para a lixeira, que
            # é onde o apagar de hoje já o põe
            destino = vault.para_lixeira(vault_dir, caminho)
            console.print(f"[yellow]recolhido para a lixeira:[/] {destino}")
            recolhidas += 1
            continue
        # arquivo que o banco não conhece: alguém escreveu no editor, e o vault
        # é a fonte da verdade, então ele entra
        meta, corpo = vault.ler(caminho)
        titulo = meta.get("title") or caminho.stem
        cur = conn.execute(
            "INSERT INTO notes (title, path, tags) VALUES (?, ?, ?)",
            (titulo, str(caminho), (meta.get("tags") or "").strip("[]") or None))
        _indexar(cur.lastrowid, titulo, corpo)
        console.print(f"[green]adotada:[/] #{cur.lastrowid} {titulo}")
        adotadas += 1

    for real, row in vivas.items():
        if not real.exists():
            console.print(f"[red]sumiu:[/] {row['path']} [dim](#{row['id']} {row['title']})[/]")
            sumidas += 1

    partes = [f"[green]{formato.plural(reindexadas, 'nota reindexada')}[/]"]
    if adotadas:
        partes.append(f"[green]{formato.plural(adotadas, 'adotada')}[/]")
    if recolhidas:
        partes.append(f"[yellow]{formato.plural(recolhidas, 'recolhida')} "
                      f"para a lixeira[/]")
    if sumidas:
        partes.append(
            f"[red]{formato.plural(sumidas, 'arquivo sumido')}[/]")
    console.print(" · ".join(partes))
