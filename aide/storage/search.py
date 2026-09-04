"""Busca nas notas.

Palavra-chave por FTS5. A camada semântica (embeddings) entra por cima disto,
fundida por reciprocal rank fusion.
"""

from __future__ import annotations

import re

# Só letras e números viram termo de busca. Tudo o mais — aspas, parênteses,
# operadores — é sintaxe para o FTS5 e viraria erro vindo de uma pergunta.
_TERMO = re.compile(r"\w+", re.UNICODE)


def preparar_consulta(texto: str) -> str:
    """Transforma a frase do usuário numa consulta FTS5 segura."""
    termos = [t for t in _TERMO.findall(texto) if len(t) > 1]
    if not termos:
        return ""
    # OR para não exigir todos os termos; o rank cuida da ordem
    return " OR ".join(f'"{t}"' for t in termos)


def indexar(conn, note_id: int, title: str, body: str) -> None:
    conn.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
    conn.execute(
        "INSERT INTO notes_fts (rowid, title, body) VALUES (?, ?, ?)",
        (note_id, title, body),
    )


def remover_do_indice(conn, note_id: int) -> None:
    conn.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))


def buscar_texto(conn, consulta: str, limite: int = 10,
                 incluir_privadas: bool = True) -> list[dict]:
    fts = preparar_consulta(consulta)
    if not fts:
        return []

    sql = (
        "SELECT n.id, n.title, n.tags, n.private,"
        "       snippet(notes_fts, 1, '', '', ' … ', 12) AS trecho,"
        "       bm25(notes_fts) AS score"
        "  FROM notes_fts JOIN notes n ON n.id = notes_fts.rowid"
        " WHERE notes_fts MATCH ? AND n.deleted_at IS NULL"
    )
    if not incluir_privadas:
        sql += " AND n.private = 0"
    sql += " ORDER BY score LIMIT ?"

    try:
        rows = conn.execute(sql, (fts, limite)).fetchall()
    except Exception:  # noqa: BLE001 - consulta malformada não pode derrubar o assessor
        return []
    return [dict(r) for r in rows]
