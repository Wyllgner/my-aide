"""Ordens de trabalho: a fila que o executor externo consome.

O daemon detecta a necessidade e escreve a ordem; ele não executa trabalho
pesado. Quando você abre uma sessão com um executor de propósito geral (Cowork
e afins), ele lê a fila por MCP, faz o serviço e escreve o resultado de volta.

Isso existe porque só a sessão local enxerga este banco: tarefa agendada na
nuvem não alcança o `aide.db`.
"""

from __future__ import annotations

import json

from aide.tools.registry import ToolContext, registry

CAMPOS = ("id, goal, context, refs_json, done_criteria, priority, status,"
          " claimed_by, claimed_at, result_summary, created_at, completed_at")


def _linha(row) -> dict:
    dados = dict(row)
    if dados.get("refs_json"):
        try:
            dados["refs"] = json.loads(dados.pop("refs_json"))
        except json.JSONDecodeError:
            dados["refs"] = []
    else:
        dados.pop("refs_json", None)
        dados["refs"] = []
    return dados


def _exigir(ctx: ToolContext, ordem_id: int):
    row = ctx.conn.execute(
        f"SELECT {CAMPOS} FROM work_orders WHERE id = ?", (ordem_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"ordem {ordem_id} não existe")
    return row


@registry.register(
    name="work_orders.create",
    description=(
        "Enfileira um trabalho para um executor externo fazer depois. Use para "
        "o que exige mão de obra que este assessor não tem — mexer em muitos "
        "arquivos, pesquisar na web, editar planilha, processar documentos."
    ),
    parameters={
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "O que precisa ser feito, em uma frase."},
            "context": {"type": "string",
                        "description": "O que o executor precisa saber para começar."},
            "refs": {"type": "array", "items": {"type": "string"},
                     "description": "Caminhos, links ou ids relacionados."},
            "done_criteria": {"type": "string",
                              "description": "Como saber que terminou."},
            "priority": {"type": "integer", "enum": [1, 2, 3, 4]},
        },
        "required": ["goal"],
    },
)
def create(ctx: ToolContext, goal: str, context: str | None = None,
           refs: list[str] | None = None, done_criteria: str | None = None,
           priority: int = 2) -> dict:
    goal = goal.strip()
    if not goal:
        raise ValueError("objetivo vazio")

    cur = ctx.conn.execute(
        "INSERT INTO work_orders (goal, context, refs_json, done_criteria, priority)"
        " VALUES (?, ?, ?, ?, ?)",
        (goal, context, json.dumps(refs, ensure_ascii=False) if refs else None,
         done_criteria, priority),
    )
    return _linha(_exigir(ctx, cur.lastrowid))


@registry.register(
    name="work_orders.list",
    description=(
        "Lista a fila de trabalho. Chame isto no início de uma sessão para "
        "saber o que ficou pendente esperando por você."
    ),
    parameters={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["open", "claimed", "done", "dropped", "all"]},
            "limit": {"type": "integer"},
        },
        "required": [],
    },
)
def list_orders(ctx: ToolContext, status: str = "open", limit: int = 20) -> list[dict]:
    sql = f"SELECT {CAMPOS} FROM work_orders"
    params: list = []
    if status != "all":
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY priority, created_at LIMIT ?"
    params.append(limit)
    return [_linha(r) for r in ctx.conn.execute(sql, params).fetchall()]


@registry.register(
    name="work_orders.claim",
    description="Assume uma ordem antes de começar, para ninguém fazer duas vezes.",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "by": {"type": "string", "description": "Quem está assumindo."},
        },
        "required": ["id"],
    },
)
def claim(ctx: ToolContext, id: int, by: str | None = None) -> dict:
    row = _exigir(ctx, id)
    if row["status"] != "open":
        raise ValueError(
            f"ordem {id} está {row['status']}"
            + (f" (com {row['claimed_by']})" if row["claimed_by"] else "")
        )
    ctx.conn.execute(
        "UPDATE work_orders SET status = 'claimed', claimed_by = ?,"
        " claimed_at = datetime('now') WHERE id = ?",
        (by or ctx.actor, id),
    )
    return _linha(_exigir(ctx, id))


@registry.register(
    name="work_orders.complete",
    description=(
        "Fecha uma ordem com o resultado. O resumo fica no banco — é assim que "
        "o trabalho feito lá fora vira memória permanente aqui."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "result_summary": {"type": "string",
                               "description": "O que foi feito e onde ficou."},
        },
        "required": ["id", "result_summary"],
    },
)
def complete(ctx: ToolContext, id: int, result_summary: str) -> dict:
    row = _exigir(ctx, id)
    if row["status"] in {"done", "dropped"}:
        raise ValueError(f"ordem {id} já está {row['status']}")
    if not result_summary.strip():
        raise ValueError("resumo vazio: diga o que foi feito")

    ctx.conn.execute(
        "UPDATE work_orders SET status = 'done', result_summary = ?,"
        " completed_at = datetime('now') WHERE id = ?",
        (result_summary.strip(), id),
    )
    return _linha(_exigir(ctx, id))


@registry.register(
    name="work_orders.drop",
    description="Descarta uma ordem que não faz mais sentido.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer"}, "reason": {"type": "string"}},
        "required": ["id"],
    },
    safety="confirm",
)
def drop(ctx: ToolContext, id: int, reason: str | None = None) -> dict:
    row = _exigir(ctx, id)
    if row["status"] in {"done", "dropped"}:
        raise ValueError(f"ordem {id} já está {row['status']}")
    ctx.conn.execute(
        "UPDATE work_orders SET status = 'dropped', result_summary = ?,"
        " completed_at = datetime('now') WHERE id = ?",
        (f"[descartada] {reason or ''}".strip(), id),
    )
    return _linha(_exigir(ctx, id))
