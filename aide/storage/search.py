"""Busca nas notas.

Palavra-chave por FTS5. A camada semântica (embeddings) entra por cima disto,
fundida por reciprocal rank fusion.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Só letras e números viram termo de busca. Tudo o mais — aspas, parênteses,
# operadores — é sintaxe para o FTS5 e viraria erro vindo de uma pergunta.
_TERMO = re.compile(r"\w+", re.UNICODE)

# Numa pergunta em linguagem natural ("problema no meu dente") as palavras
# funcionais casam com qualquer nota e afogam o termo que importa. Fora.
# ruff quer literal; a string é bem mais legível de manter que 60 aspas soltas
STOPWORDS = frozenset("""
a as o os um uma uns umas de do da dos das em no na nos nas por para pelo pela
com sem sob sobre entre ate até após apos e ou mas que se ao aos à às
meu minha meus minhas seu sua seus suas nosso nossa dele dela
eu tu ele ela nos vos eles elas voce você
foi ser sou sao são era eram esta está estao estão tem tinha ter havia
isso isto aquilo esse essa este esta aquele aquela
qual quais quando onde como porque quanto quem
mais menos muito pouco tudo nada algo alguns alguma
ja já nao não sim tambem também so só
""".split())  # noqa: SIM905 - a string é mais legível de manter que 60 literais


def preparar_consulta(texto: str) -> str:
    """Transforma a frase do usuário numa consulta FTS5 segura."""
    termos = [t for t in _TERMO.findall(texto.lower())
              if len(t) > 2 and t not in STOPWORDS]
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


# ---------- camada semântica ----------

K_RRF = 60  # constante usual do reciprocal rank fusion

# Cosseno abaixo disto é ruído. Sem piso, a busca semântica sempre devolve algo
# — a nota "menos distante" — e o assessor responde com convicção sobre algo
# que não tem relação com a pergunta. Melhor dizer que não achou.
#
# Calibrado medindo o text-embedding-3-small com perguntas reais:
#   acerto verdadeiro   0,53 a 0,56
#   ruído               0,16 a 0,37
# 0,45 separa os dois com folga. Se aparecer falso negativo, baixe; se voltar
# a responder sobre nota sem relação, suba.
PISO_SIMILARIDADE = 0.45


def guardar_vetor(conn, ref_type: str, ref_id: int, chunk: str, vetor: list[float]) -> None:
    from aide.llm.embeddings import empacotar

    conn.execute(
        "DELETE FROM embeddings WHERE ref_type = ? AND ref_id = ?", (ref_type, ref_id)
    )
    conn.execute(
        "INSERT INTO embeddings (ref_type, ref_id, chunk, vector) VALUES (?, ?, ?, ?)",
        (ref_type, ref_id, chunk[:2000], empacotar(vetor)),
    )


def buscar_semantico(conn, vetor: list[float], limite: int = 10,
                     incluir_privadas: bool = True,
                     piso: float = PISO_SIMILARIDADE) -> list[dict]:
    """Força bruta sobre todos os vetores.

    Com algumas milhares de notas isto roda em milissegundos; um índice
    aproximado só se pagaria numa ordem de grandeza acima.
    """
    from aide.llm.embeddings import desempacotar, similaridade

    sql = (
        "SELECT e.ref_id, e.chunk, e.vector, n.title, n.tags, n.private"
        "  FROM embeddings e JOIN notes n ON n.id = e.ref_id"
        " WHERE e.ref_type = 'note' AND n.deleted_at IS NULL"
    )
    if not incluir_privadas:
        sql += " AND n.private = 0"

    achados = []
    for row in conn.execute(sql).fetchall():
        score = similaridade(vetor, desempacotar(row["vector"]))
        if score < piso:
            continue
        achados.append({"id": row["ref_id"], "title": row["title"], "tags": row["tags"],
                        "trecho": row["chunk"][:200], "score": score})
    achados.sort(key=lambda a: a["score"], reverse=True)
    return achados[:limite]


def fundir(listas: list[list[dict]], limite: int = 10) -> list[dict]:
    """Reciprocal rank fusion.

    Junta rankings de escalas diferentes — bm25 (menor é melhor) e cosseno
    (maior é melhor) — usando só a posição, sem precisar normalizar nota.
    """
    pontos: dict[int, float] = {}
    itens: dict[int, dict] = {}

    for lista in listas:
        for posicao, item in enumerate(lista, start=1):
            pontos[item["id"]] = pontos.get(item["id"], 0.0) + 1.0 / (K_RRF + posicao)
            itens.setdefault(item["id"], item)

    ordenados = sorted(pontos.items(), key=lambda par: par[1], reverse=True)
    return [{**itens[nota_id], "rrf": round(score, 5)} for nota_id, score in ordenados[:limite]]


def buscar(conn, consulta: str, embedder=None, limite: int = 5,
           incluir_privadas: bool = True) -> list[dict]:
    """Busca híbrida: palavra-chave + semântica, fundidas por RRF.

    Sem embedder (ou se ele falhar) devolve só a busca textual — degradar é
    melhor do que não responder.
    """
    texto = buscar_texto(conn, consulta, limite=limite * 2,
                         incluir_privadas=incluir_privadas)
    if embedder is None:
        return texto[:limite]

    try:
        vetor = embedder.embed_one(consulta)
    except Exception:
        # busca sem a metade semântica ainda é busca; falhar calado é pior
        log.warning("embedding da consulta falhou; usando só palavra-chave", exc_info=True)
        return texto[:limite]

    if not vetor:
        return texto[:limite]

    semantico = buscar_semantico(conn, vetor, limite=limite * 2,
                                 incluir_privadas=incluir_privadas)
    return fundir([texto, semantico], limite=limite)
