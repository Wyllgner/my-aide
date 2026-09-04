"""Tools de notas: o segundo cérebro.

O markdown no vault é a fonte da verdade; o SQLite indexa para a busca.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aide.core.context import now_in
from aide.storage import vault
from aide.storage.search import guardar_vetor, indexar, remover_do_indice
from aide.tools.registry import ToolContext, registry

log = logging.getLogger(__name__)


def _indexar_tudo(ctx: ToolContext, note_id: int, title: str, body: str) -> None:
    """Índice de palavra-chave sempre; o semântico só se houver embedder.

    A nota precisa ficar gravada mesmo sem rede ou sem chave da OpenAI — por
    isso a falha do embedding é registrada, não propagada.
    """
    indexar(ctx.conn, note_id, title, body)
    embedder = getattr(ctx, "embedder", None)
    if embedder is None:
        return
    try:
        vetor = embedder.embed_one(f"{title}\n\n{body}")
    except Exception:
        log.warning("não consegui gerar embedding da nota %s", note_id, exc_info=True)
        return
    if vetor:
        guardar_vetor(ctx.conn, "note", note_id, f"{title}\n\n{body}", vetor)


def _nota(ctx: ToolContext, id_ou_titulo):
    if isinstance(id_ou_titulo, int) or str(id_ou_titulo).isdigit():
        row = ctx.conn.execute(
            "SELECT * FROM notes WHERE id = ? AND deleted_at IS NULL", (int(id_ou_titulo),)
        ).fetchone()
    else:
        row = ctx.conn.execute(
            "SELECT * FROM notes WHERE title = ? AND deleted_at IS NULL"
            " ORDER BY updated_at DESC LIMIT 1", (str(id_ou_titulo),)
        ).fetchone()
    if row is None:
        raise ValueError(f"nota não encontrada: {id_ou_titulo}")
    return row


@registry.register(
    name="notes.create",
    description=(
        "Guarda uma nota no vault. Use para o que a pessoa quer registrar e "
        "reler depois — ideias, decisões, resumos — não para tarefas."
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"},
            "tags": {"type": "string", "description": "Separadas por vírgula."},
            "private": {"type": "boolean",
                        "description": "Se verdadeiro, nunca entra no contexto enviado ao modelo."},
        },
        "required": ["title", "body"],
    },
)
def create(ctx: ToolContext, title: str, body: str, tags: str | None = None,
           private: bool = False) -> dict:
    title = title.strip()
    if not title:
        raise ValueError("título vazio")
    if not body.strip():
        raise ValueError("nota vazia")

    agora = now_in(ctx.config.timezone)
    caminho = vault.caminho_para(Path(ctx.config.vault_dir), title, agora)
    vault.escrever(caminho, title, body, tags, agora)

    cur = ctx.conn.execute(
        "INSERT INTO notes (title, path, tags, private) VALUES (?, ?, ?, ?)",
        (title, str(caminho), tags, int(private)),
    )
    _indexar_tudo(ctx, cur.lastrowid, title, body)
    return {"id": cur.lastrowid, "title": title, "path": str(caminho)}


@registry.register(
    name="notes.append",
    description="Acrescenta texto a uma nota existente, datado.",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "title": {"type": "string", "description": "Alternativa ao id."},
            "body": {"type": "string"},
        },
        "required": ["body"],
    },
)
def append(ctx: ToolContext, body: str, id: int | None = None,
           title: str | None = None) -> dict:
    if id is None and title is None:
        raise ValueError("informe id ou title")

    row = _nota(ctx, id if id is not None else title)
    caminho = Path(row["path"])
    if not caminho.exists():
        raise ValueError(f"o arquivo da nota sumiu: {caminho}")

    agora = now_in(ctx.config.timezone)
    vault.acrescentar(caminho, body, agora)
    ctx.conn.execute("UPDATE notes SET updated_at = datetime('now') WHERE id = ?", (row["id"],))
    _indexar_tudo(ctx, row["id"], row["title"], vault.corpo_de(caminho))
    return {"id": row["id"], "title": row["title"]}


@registry.register(
    name="notes.read",
    description="Lê o conteúdo de uma nota.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer"}, "title": {"type": "string"}},
        "required": [],
    },
)
def read(ctx: ToolContext, id: int | None = None, title: str | None = None) -> dict:
    if id is None and title is None:
        raise ValueError("informe id ou title")

    row = _nota(ctx, id if id is not None else title)
    caminho = Path(row["path"])
    if not caminho.exists():
        raise ValueError(f"o arquivo da nota sumiu: {caminho}")
    return {"id": row["id"], "title": row["title"], "body": vault.corpo_de(caminho),
            "tags": row["tags"]}


@registry.register(
    name="notes.list",
    description="Lista as notas mais recentes.",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer"}, "tag": {"type": "string"}},
        "required": [],
    },
)
def list_notes(ctx: ToolContext, limit: int = 20, tag: str | None = None) -> list[dict]:
    sql = "SELECT id, title, tags, updated_at FROM notes WHERE deleted_at IS NULL"
    params: list = []
    if tag:
        sql += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in ctx.conn.execute(sql, params).fetchall()]


@registry.register(
    name="notes.search",
    description=(
        "Procura nas notas por significado e por palavra-chave. Use quando a "
        "pessoa perguntar o que já foi anotado ou dito sobre algum assunto."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
    },
)
def search(ctx: ToolContext, query: str, limit: int = 5) -> list[dict]:
    from aide.storage.search import buscar

    achados = buscar(ctx.conn, query, embedder=getattr(ctx, "embedder", None),
                     limite=limit, incluir_privadas=False)
    return [{k: v for k, v in a.items() if k != "score"} for a in achados]


@registry.register(
    name="notes.delete",
    description="Descarta uma nota. O arquivo no vault continua lá.",
    parameters={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    safety="confirm",
)
def delete(ctx: ToolContext, id: int) -> dict:
    row = _nota(ctx, id)
    ctx.conn.execute("UPDATE notes SET deleted_at = datetime('now') WHERE id = ?", (id,))
    remover_do_indice(ctx.conn, id)
    return {"id": id, "title": row["title"], "status": "removida do índice",
            "arquivo": row["path"]}
