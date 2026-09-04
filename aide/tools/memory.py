"""Memória: o que o assessor sabe sobre você.

Perfil vai inteiro no prompt de toda conversa — por isso é pequeno e curado.
Episódica é datada e recuperada por busca.

Escrever é sempre uma tool explícita. Salvar automático enche o banco de lixo
em uma semana, e depois não há como saber o que é verdade.
"""

from __future__ import annotations

from aide.core.context import now_in
from aide.tools.registry import ToolContext, registry

LIMITE_PERFIL = 60


def _vigentes(conn, kind: str | None = None, incluir_privadas: bool = True):
    sql = "SELECT id, kind, key, value, confidence, created_at FROM memory" \
          " WHERE superseded_by IS NULL"
    params: list = []
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if not incluir_privadas:
        sql += " AND private = 0"
    sql += " ORDER BY created_at DESC"
    return conn.execute(sql, params).fetchall()


@registry.register(
    name="memory.save",
    description=(
        "Guarda um fato sobre a pessoa. Use 'profile' para o que é estável — "
        "preferências, rotina, pessoas próximas — e 'episodic' para o que "
        "aconteceu numa data. Só guarde o que vai ser útil daqui a meses; "
        "não guarde o assunto da conversa atual."
    ),
    parameters={
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["profile", "episodic"]},
            "key": {"type": "string",
                    "description": "Identificador curto e estável, ex. 'horario_academia'."},
            "value": {"type": "string"},
            "confidence": {"type": "number",
                           "description": "0 a 1. Use abaixo de 1 quando a pessoa não confirmou."},
            "private": {"type": "boolean",
                        "description": "Se verdadeiro, nunca entra no contexto enviado ao modelo."},
        },
        "required": ["kind", "key", "value"],
    },
)
def save(ctx: ToolContext, kind: str, key: str, value: str,
         confidence: float = 1.0, private: bool = False) -> dict:
    key = key.strip().lower().replace(" ", "_")
    if not key or not value.strip():
        raise ValueError("key e value não podem ser vazios")
    if not 0 < confidence <= 1:
        raise ValueError("confidence deve estar entre 0 e 1")

    if kind == "profile":
        total = ctx.conn.execute(
            "SELECT COUNT(*) c FROM memory WHERE kind = 'profile' AND superseded_by IS NULL"
        ).fetchone()["c"]
        anterior = ctx.conn.execute(
            "SELECT id FROM memory WHERE kind = 'profile' AND key = ? AND superseded_by IS NULL",
            (key,),
        ).fetchone()
        if total >= LIMITE_PERFIL and anterior is None:
            raise ValueError(
                f"o perfil já tem {total} fatos, que é o teto — ele vai inteiro em "
                "todo prompt. Use memory.forget em algo obsoleto, ou salve como 'episodic'."
            )

    cur = ctx.conn.execute(
        "INSERT INTO memory (kind, key, value, confidence, private) VALUES (?, ?, ?, ?, ?)",
        (kind, key, value.strip(), confidence, int(private)),
    )
    novo = cur.lastrowid

    # o fato antigo não some: vira histórico apontando para o novo
    substituidos = ctx.conn.execute(
        "UPDATE memory SET superseded_by = ? WHERE kind = ? AND key = ?"
        " AND id != ? AND superseded_by IS NULL",
        (novo, kind, key, novo),
    ).rowcount

    return {"id": novo, "kind": kind, "key": key, "value": value.strip(),
            "substituiu": substituidos}


@registry.register(
    name="memory.search",
    description="Procura no que já foi guardado sobre a pessoa.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "kind": {"type": "string", "enum": ["profile", "episodic"]},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
    },
)
def search(ctx: ToolContext, query: str, kind: str | None = None,
           limit: int = 8) -> list[dict]:
    termos = [t for t in query.lower().split() if len(t) > 2]
    achados = []
    for row in _vigentes(ctx.conn, kind, incluir_privadas=False):
        alvo = f"{row['key']} {row['value']}".lower()
        pontos = sum(1 for t in termos if t in alvo)
        if pontos:
            achados.append((pontos, dict(row)))
    achados.sort(key=lambda par: par[0], reverse=True)
    return [item for _, item in achados[:limit]]


@registry.register(
    name="memory.list",
    description="Lista o perfil — tudo que o assessor considera estável sobre a pessoa.",
    parameters={
        "type": "object",
        "properties": {"kind": {"type": "string", "enum": ["profile", "episodic"]}},
        "required": [],
    },
)
def list_memory(ctx: ToolContext, kind: str = "profile") -> list[dict]:
    return [dict(r) for r in _vigentes(ctx.conn, kind)]


@registry.register(
    name="memory.forget",
    description="Esquece um fato. O registro vira histórico, não some de vez.",
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "kind": {"type": "string", "enum": ["profile", "episodic"]},
        },
        "required": ["key"],
    },
    safety="confirm",
)
def forget(ctx: ToolContext, key: str, kind: str = "profile") -> dict:
    key = key.strip().lower().replace(" ", "_")
    marcador = ctx.conn.execute(
        "INSERT INTO memory (kind, key, value, confidence)"
        " VALUES (?, ?, '[esquecido]', 1.0)", (kind, key)
    ).lastrowid
    apagados = ctx.conn.execute(
        "UPDATE memory SET superseded_by = ? WHERE kind = ? AND key = ?"
        " AND id != ? AND superseded_by IS NULL",
        (marcador, kind, key, marcador),
    ).rowcount
    ctx.conn.execute("UPDATE memory SET superseded_by = id WHERE id = ?", (marcador,))

    if not apagados:
        raise ValueError(f"não havia nada guardado em {kind}/{key}")
    return {"kind": kind, "key": key, "esquecidos": apagados}


def buscar_episodios(conn, query: str, limite: int = 5) -> list[dict]:
    """Memória episódica no formato que notes.search devolve.

    Privadas ficam de fora, como em todo caminho que alimenta o modelo.
    """
    termos = [t for t in query.lower().split() if len(t) > 2]
    if not termos:
        return []

    achados = []
    for row in _vigentes(conn, "episodic", incluir_privadas=False):
        alvo = f"{row['key']} {row['value']}".lower()
        pontos = sum(1 for t in termos if t in alvo)
        if pontos:
            achados.append((pontos, {
                "id": row["id"],
                "title": row["key"].replace("_", " "),
                "trecho": row["value"],
                "tipo": "histórico",
            }))
    achados.sort(key=lambda par: par[0], reverse=True)
    return [item for _, item in achados[:limite]]


# ---------- usado pelo contexto, não é tool ----------

def perfil_para_prompt(conn, config) -> str:
    """As linhas de perfil que vão no system prompt. Privadas ficam de fora."""
    linhas = []
    for row in _vigentes(conn, "profile", incluir_privadas=False):
        marca = "" if row["confidence"] >= 1 else f" (incerto: {row['confidence']:.1f})"
        linhas.append(f"- {row['key']}: {row['value']}{marca}")
    return "\n".join(linhas)


def registrar_episodio(conn, config, texto: str, chave: str | None = None) -> int:
    agora = now_in(config.timezone)
    chave = chave or f"episodio_{agora.strftime('%Y%m%d_%H%M')}"
    cur = conn.execute(
        "INSERT INTO memory (kind, key, value) VALUES ('episodic', ?, ?)", (chave, texto)
    )
    return cur.lastrowid
