"""Tools de tarefas."""

from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher

from aide.core.context import now_in
from aide.tools.registry import ToolContext, registry

FIELDS = "id, title, notes, status, priority, project, tags, due_at, recurrence, snooze_count"
PRIORITIES = {1: "urgente", 2: "normal", 3: "baixa", 4: "algum dia"}


def _parse_dt(value: str | None, field: str) -> str | None:
    """Aceita ISO 8601. A LLM converte linguagem natural antes de chamar."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).isoformat(timespec="minutes")
    except ValueError as exc:
        raise ValueError(
            f"{field} precisa ser ISO 8601 (ex. 2026-09-05T09:00). Recebido: {value!r}"
        ) from exc


def _similar_open_task(ctx: ToolContext, title: str):
    """Acha uma tarefa aberta com título parecido.

    Rede de segurança contra o modelo recriar o que já existe em vez de adiar
    ou concluir. Não depende de o prompt ser obedecido.
    """
    alvo = title.strip().casefold()
    rows = ctx.conn.execute(
        "SELECT id, title FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
    ).fetchall()

    for row in rows:
        outro = row["title"].strip().casefold()
        if alvo in outro or outro in alvo:
            return row
        if SequenceMatcher(None, alvo, outro).ratio() >= 0.85:
            return row
    return None


def _row(r) -> dict:
    data = dict(r)
    data["priority_label"] = PRIORITIES.get(data.get("priority"), "?")
    return data


def _require(ctx: ToolContext, task_id: int):
    row = ctx.conn.execute(
        f"SELECT {FIELDS} FROM tasks WHERE id = ? AND deleted_at IS NULL", (task_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"tarefa {task_id} não existe")
    return row


@registry.register(
    name="tasks.create",
    description="Cria uma tarefa. Converta prazos relativos com time.now antes de chamar.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "O que precisa ser feito."},
            "due": {"type": "string", "description": "Prazo em ISO 8601, ex. 2026-09-05T09:00."},
            "priority": {"type": "integer", "enum": [1, 2, 3, 4],
                         "description": "1 urgente, 2 normal, 3 baixa, 4 algum dia."},
            "project": {"type": "string"},
            "tags": {"type": "string", "description": "Separadas por vírgula."},
            "notes": {"type": "string"},
            "recurrence": {"type": "string",
                           "description": "Ex.: 'every weekday', '1st of month'."},
            "private": {"type": "boolean",
                        "description": "Se verdadeiro, nunca entra no contexto enviado ao modelo."},
            "force": {"type": "boolean",
                      "description": "Cria mesmo havendo uma tarefa aberta parecida."},
        },
        "required": ["title"],
    },
)
def create(ctx: ToolContext, title: str, due: str | None = None, priority: int = 2,
           project: str | None = None, tags: str | None = None, notes: str | None = None,
           recurrence: str | None = None, private: bool = False, force: bool = False) -> dict:
    title = title.strip()
    if not title:
        raise ValueError("título vazio")

    if not force:
        existente = _similar_open_task(ctx, title)
        if existente is not None:
            raise ValueError(
                f"já existe a tarefa aberta #{existente['id']} \"{existente['title']}\". "
                "Use tasks.update, tasks.snooze ou tasks.complete nela. "
                "Se for mesmo outra coisa, chame de novo com force=true."
            )

    cur = ctx.conn.execute(
        "INSERT INTO tasks (title, notes, priority, project, tags, due_at, recurrence,"
        " private, last_touched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
        (title, notes, priority, project, tags, _parse_dt(due, "due"), recurrence, int(private)),
    )
    return _row(_require(ctx, cur.lastrowid))


@registry.register(
    name="tasks.list",
    description="Lista tarefas. 'today' inclui as atrasadas e as sem prazo marcadas urgentes.",
    parameters={
        "type": "object",
        "properties": {
            "filter": {"type": "string",
                       "enum": ["today", "overdue", "week", "inbox", "done", "all"]},
            "project": {"type": "string"},
            "query": {"type": "string", "description": "Busca no título."},
            "limit": {"type": "integer"},
        },
        "required": [],
    },
)
def list_tasks(ctx: ToolContext, filter: str = "today", project: str | None = None,
               query: str | None = None, limit: int = 50) -> list[dict]:
    now = now_in(ctx.config.timezone)
    end_of_day = now.replace(hour=23, minute=59).isoformat(timespec="minutes")
    where = ["deleted_at IS NULL"]
    params: list = []

    if filter == "done":
        where.append("status = 'done'")
    else:
        where.append("status = 'open'")

    if filter == "today":
        where.append("(due_at <= ? OR (due_at IS NULL AND priority = 1))")
        params.append(end_of_day)
    elif filter == "overdue":
        where.append("due_at < ?")
        params.append(now.isoformat(timespec="minutes"))
    elif filter == "week":
        where.append("due_at <= ?")
        params.append((now + timedelta(days=7)).isoformat(timespec="minutes"))
    elif filter == "inbox":
        where.append("due_at IS NULL AND project IS NULL")

    if project:
        where.append("project = ?")
        params.append(project)
    if query:
        where.append("title LIKE ?")
        params.append(f"%{query}%")

    rows = ctx.conn.execute(
        f"SELECT {FIELDS} FROM tasks WHERE {' AND '.join(where)}"
        " ORDER BY due_at IS NULL, due_at, priority LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [_row(r) for r in rows]


@registry.register(
    name="tasks.update",
    description="Altera campos de uma tarefa existente.",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "title": {"type": "string"},
            "due": {"type": "string", "description": "ISO 8601, ou string vazia para remover."},
            "priority": {"type": "integer", "enum": [1, 2, 3, 4]},
            "project": {"type": "string"},
            "tags": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["id"],
    },
)
def update(ctx: ToolContext, id: int, **fields) -> dict:
    _require(ctx, id)
    columns = {"title": "title", "priority": "priority", "project": "project",
               "tags": "tags", "notes": "notes"}
    sets, params = [], []

    for key, column in columns.items():
        if key in fields:
            sets.append(f"{column} = ?")
            params.append(fields[key])

    if "due" in fields:
        sets.append("due_at = ?")
        params.append(_parse_dt(fields["due"] or None, "due"))

    if not sets:
        raise ValueError("nada para alterar")

    sets.append("last_touched_at = datetime('now')")
    ctx.conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", (*params, id))
    return _row(_require(ctx, id))


@registry.register(
    name="tasks.complete",
    description="Marca uma tarefa como concluída.",
    parameters={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
)
def complete(ctx: ToolContext, id: int) -> dict:
    row = _require(ctx, id)
    if row["status"] == "done":
        raise ValueError(f"tarefa {id} já está concluída")
    ctx.conn.execute(
        "UPDATE tasks SET status = 'done', completed_at = datetime('now'),"
        " last_touched_at = datetime('now') WHERE id = ?", (id,)
    )
    return {"id": id, "title": row["title"], "status": "done"}


@registry.register(
    name="tasks.snooze",
    description=(
        "Adia uma tarefa para uma nova data. Cada adiamento é contado — o assessor "
        "usa isso depois para perguntar se a tarefa ainda importa."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "until": {"type": "string", "description": "Novo prazo em ISO 8601."},
        },
        "required": ["id", "until"],
    },
)
def snooze(ctx: ToolContext, id: int, until: str) -> dict:
    _require(ctx, id)
    ctx.conn.execute(
        "UPDATE tasks SET due_at = ?, snooze_count = snooze_count + 1,"
        " last_touched_at = datetime('now') WHERE id = ?",
        (_parse_dt(until, "until"), id),
    )
    return _row(_require(ctx, id))


@registry.register(
    name="tasks.drop",
    description="Descarta uma tarefa que não faz mais sentido.",
    parameters={
        "type": "object",
        "properties": {"id": {"type": "integer"}, "reason": {"type": "string"}},
        "required": ["id"],
    },
    safety="confirm",
)
def drop(ctx: ToolContext, id: int, reason: str | None = None) -> dict:
    row = _require(ctx, id)
    ctx.conn.execute(
        "UPDATE tasks SET status = 'dropped', notes = COALESCE(notes || char(10), '') || ?,"
        " last_touched_at = datetime('now') WHERE id = ?",
        (f"[descartada] {reason or ''}".strip(), id),
    )
    return {"id": id, "title": row["title"], "status": "dropped"}
