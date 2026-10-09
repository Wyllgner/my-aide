"""O registro de em que dias cada nota foi mexida (`note_activity`).

Quem escreve numa nota chama `registrar`: a página ao salvar, o assessor ao
criar ou acrescentar, e a reconciliação ao achar um arquivo mudado por fora
(Obsidian, editor de texto). Mover a nota leva o histórico junto.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path


def registrar(conn, vault_dir: Path, arquivo: Path, quando: datetime, origem: str) -> None:
    try:
        caminho = arquivo.resolve().relative_to(Path(vault_dir).resolve()).as_posix()
    except ValueError:
        return
    conn.execute(
        "INSERT INTO note_activity (caminho, dia, origem) VALUES (?, ?, ?)"
        " ON CONFLICT (caminho, dia) DO UPDATE SET vezes = vezes + 1",
        (caminho, quando.date().isoformat(), origem))


def mover(conn, de: str, para: str) -> None:
    """O histórico segue a nota renomeada ou movida."""
    # se a nota nova já tinha linha no mesmo dia, soma em vez de colidir
    conn.execute(
        "INSERT INTO note_activity (caminho, dia, vezes, origem)"
        " SELECT ?, dia, vezes, origem FROM note_activity WHERE caminho = ? AND true"
        " ON CONFLICT (caminho, dia) DO UPDATE SET vezes = vezes + excluded.vezes",
        (para, de))
    conn.execute("DELETE FROM note_activity WHERE caminho = ?", (de,))


def por_dia(conn, desde: date) -> set[tuple[str, str]]:
    """(caminho, dia) de tudo mexido desde `desde`."""
    return {(r[0], r[1]) for r in conn.execute(
        "SELECT caminho, dia FROM note_activity WHERE dia >= ?", (desde.isoformat(),))}
