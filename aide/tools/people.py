"""Pessoas: quem você não pode deixar cair no esquecimento.

A regra `contato_atrasado` já existia em rules.py sem nada para alimentá-la.
Isto fecha o circuito: você diz com quem quer manter contato e de quanto em
quanto tempo, e o assessor cobra quando o silêncio passar do combinado.
"""

from __future__ import annotations

from aide.core.context import now_in
from aide.tools.registry import ToolContext, registry

CAMPOS = "id, name, relation, last_contact_at, cadence_days, created_at"


def _pessoa(ctx: ToolContext, nome_ou_id):
    if isinstance(nome_ou_id, int) or str(nome_ou_id).isdigit():
        row = ctx.conn.execute(
            f"SELECT {CAMPOS} FROM people WHERE id = ?", (int(nome_ou_id),)
        ).fetchone()
    else:
        row = ctx.conn.execute(
            f"SELECT {CAMPOS} FROM people WHERE name LIKE ? ORDER BY name LIMIT 1",
            (f"%{nome_ou_id}%",),
        ).fetchone()
    if row is None:
        raise ValueError(f"não conheço ninguém chamado {nome_ou_id!r}")
    return row


@registry.register(
    name="people.add",
    description=(
        "Registra alguém com quem a pessoa quer manter contato regular. "
        "Use quando ela disser que não quer perder o contato com alguém, ou "
        "que quer falar com fulano a cada tantas semanas."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "relation": {"type": "string",
                         "description": "Ex.: irmão, ex-chefe, amigo da facul."},
            "cadence_days": {"type": "integer",
                             "description": "A cada quantos dias falar. Sem isto, não cobra."},
            "last_contact": {"type": "string",
                             "description": "Último contato em ISO 8601. Padrão: agora."},
        },
        "required": ["name"],
    },
)
def add(ctx: ToolContext, name: str, relation: str | None = None,
        cadence_days: int | None = None, last_contact: str | None = None) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("nome vazio")
    if cadence_days is not None and cadence_days < 1:
        raise ValueError("cadence_days precisa ser pelo menos 1")

    ja = ctx.conn.execute(
        "SELECT id, name FROM people WHERE lower(name) = lower(?)", (name,)
    ).fetchone()
    if ja:
        raise ValueError(
            f"{ja['name']} já está registrado (#{ja['id']}). Use people.update."
        )

    quando = last_contact or now_in(ctx.config.timezone).isoformat(timespec="minutes")
    cur = ctx.conn.execute(
        "INSERT INTO people (name, relation, cadence_days, last_contact_at)"
        " VALUES (?, ?, ?, ?)",
        (name, relation, cadence_days, quando),
    )
    return dict(_pessoa(ctx, cur.lastrowid))


@registry.register(
    name="people.touch",
    description=(
        "Marca que a pessoa falou com alguém agora. Use quando ela mencionar "
        "que conversou, encontrou ou ligou para alguém registrado."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nome ou parte dele."},
            "when": {"type": "string", "description": "ISO 8601. Padrão: agora."},
            "note": {"type": "string", "description": "O que foi conversado, se valer guardar."},
        },
        "required": ["name"],
    },
)
def touch(ctx: ToolContext, name: str, when: str | None = None,
          note: str | None = None) -> dict:
    row = _pessoa(ctx, name)
    quando = when or now_in(ctx.config.timezone).isoformat(timespec="minutes")
    ctx.conn.execute(
        "UPDATE people SET last_contact_at = ? WHERE id = ?", (quando, row["id"])
    )

    if note:
        # contato com conteúdo vira memória episódica, para a busca achar depois
        ctx.conn.execute(
            "INSERT INTO memory (kind, key, value) VALUES ('episodic', ?, ?)",
            (f"contato_{row['name'].lower().replace(' ', '_')}",
             f"{quando[:10]}: {note.strip()}"),
        )

    return {"id": row["id"], "name": row["name"], "last_contact_at": quando}


@registry.register(
    name="people.list",
    description="Lista as pessoas registradas e há quanto tempo você não fala com cada uma.",
    parameters={
        "type": "object",
        "properties": {"atrasados": {"type": "boolean",
                                     "description": "Só quem passou da cadência."}},
        "required": [],
    },
)
def list_people(ctx: ToolContext, atrasados: bool = False) -> list[dict]:
    agora = now_in(ctx.config.timezone)
    saida = []
    for row in ctx.conn.execute(f"SELECT {CAMPOS} FROM people ORDER BY name").fetchall():
        dado = dict(row)
        if row["last_contact_at"]:
            ultimo = row["last_contact_at"]
            dias = (agora - agora.fromisoformat(ultimo).replace(tzinfo=agora.tzinfo)).days
            dado["dias_sem_falar"] = dias
            dado["atrasado"] = bool(row["cadence_days"] and dias > row["cadence_days"])
        else:
            dado["dias_sem_falar"] = None
            dado["atrasado"] = False
        if atrasados and not dado["atrasado"]:
            continue
        saida.append(dado)
    return saida


@registry.register(
    name="people.update",
    description="Muda a relação ou a cadência de contato de alguém.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "relation": {"type": "string"},
            "cadence_days": {"type": "integer",
                             "description": "Use 0 para parar de cobrar."},
        },
        "required": ["name"],
    },
)
def update(ctx: ToolContext, name: str, relation: str | None = None,
           cadence_days: int | None = None) -> dict:
    row = _pessoa(ctx, name)
    sets, params = [], []
    if relation is not None:
        sets.append("relation = ?")
        params.append(relation)
    if cadence_days is not None:
        sets.append("cadence_days = ?")
        params.append(cadence_days or None)  # 0 vira NULL: para de cobrar
    if not sets:
        raise ValueError("nada para alterar")

    ctx.conn.execute(f"UPDATE people SET {', '.join(sets)} WHERE id = ?",
                     (*params, row["id"]))
    return dict(_pessoa(ctx, row["id"]))


@registry.register(
    name="people.remove",
    description="Para de acompanhar alguém.",
    parameters={"type": "object", "properties": {"name": {"type": "string"}},
                "required": ["name"]},
    safety="confirm",
)
def remove(ctx: ToolContext, name: str) -> dict:
    row = _pessoa(ctx, name)
    ctx.conn.execute("DELETE FROM people WHERE id = ?", (row["id"],))
    return {"id": row["id"], "name": row["name"], "status": "removido"}
