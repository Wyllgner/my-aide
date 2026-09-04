"""Tools de lembretes: avisos com hora marcada, sem virar tarefa."""

from __future__ import annotations

from datetime import datetime

from aide.core.context import now_in
from aide.tools.registry import ToolContext, registry

REPEAT_RULES = {"daily", "weekdays", "weekly", "monthly", "yearly"}


def _parse_dt(value: str, field: str) -> str:
    try:
        return datetime.fromisoformat(value).isoformat(timespec="minutes")
    except ValueError as exc:
        raise ValueError(
            f"{field} precisa ser ISO 8601 (ex. 2026-09-05T09:00). Recebido: {value!r}"
        ) from exc


@registry.register(
    name="reminders.create",
    description=(
        "Cria um lembrete para uma hora marcada. Use quando a pessoa quer ser "
        "avisada num momento — não quando há algo a fazer com prazo (isso é tarefa)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "when": {"type": "string", "description": "Quando avisar, em ISO 8601."},
            "repeat": {"type": "string", "enum": sorted(REPEAT_RULES),
                       "description": "Deixe vazio para lembrete único."},
        },
        "required": ["text", "when"],
    },
)
def create(ctx: ToolContext, text: str, when: str, repeat: str | None = None) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("texto vazio")
    if repeat and repeat not in REPEAT_RULES:
        raise ValueError(f"repeat deve ser um de {sorted(REPEAT_RULES)}")

    fire_at = _parse_dt(when, "when")
    if fire_at < now_in(ctx.config.timezone).isoformat(timespec="minutes") and not repeat:
        raise ValueError(f"{fire_at} já passou; escolha um horário futuro")

    cur = ctx.conn.execute(
        "INSERT INTO reminders (text, fire_at, repeat_rule) VALUES (?, ?, ?)",
        (text, fire_at, repeat),
    )
    return {"id": cur.lastrowid, "text": text, "fire_at": fire_at, "repeat": repeat}


@registry.register(
    name="reminders.list",
    description="Lista lembretes pendentes.",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer"}},
        "required": [],
    },
)
def list_reminders(ctx: ToolContext, limit: int = 50) -> list[dict]:
    rows = ctx.conn.execute(
        "SELECT id, text, fire_at, repeat_rule FROM reminders"
        " WHERE status = 'pending' ORDER BY fire_at LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


@registry.register(
    name="reminders.cancel",
    description="Cancela um lembrete pendente.",
    parameters={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
)
def cancel(ctx: ToolContext, id: int) -> dict:
    row = ctx.conn.execute(
        "SELECT text, status FROM reminders WHERE id = ?", (id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"lembrete {id} não existe")
    if row["status"] != "pending":
        raise ValueError(f"lembrete {id} não está pendente (está {row['status']})")

    ctx.conn.execute("UPDATE reminders SET status = 'cancelled' WHERE id = ?", (id,))
    return {"id": id, "text": row["text"], "status": "cancelled"}


# ---------- usado pelo scheduler, não é tool ----------

def _next_occurrence(fire_at: datetime, rule: str) -> datetime:
    from datetime import timedelta

    if rule == "daily":
        return fire_at + timedelta(days=1)
    if rule == "weekdays":
        nxt = fire_at + timedelta(days=1)
        while nxt.weekday() >= 5:  # sábado e domingo
            nxt += timedelta(days=1)
        return nxt
    if rule == "weekly":
        return fire_at + timedelta(weeks=1)
    if rule == "monthly":
        month = fire_at.month + 1
        year = fire_at.year + (month > 12)
        month = 1 if month > 12 else month
        # dia 31 em mês curto cai para o último dia possível
        for day in range(fire_at.day, 27, -1):
            try:
                return fire_at.replace(year=year, month=month, day=day)
            except ValueError:
                continue
        return fire_at.replace(year=year, month=month, day=28)
    if rule == "yearly":
        try:
            return fire_at.replace(year=fire_at.year + 1)
        except ValueError:  # 29 de fevereiro
            return fire_at.replace(year=fire_at.year + 1, day=28)
    raise ValueError(f"regra de repetição desconhecida: {rule}")


def due(conn, now: datetime) -> list[dict]:
    """Lembretes pendentes cuja hora já chegou."""
    rows = conn.execute(
        "SELECT id, text, fire_at, repeat_rule FROM reminders"
        " WHERE status = 'pending' AND fire_at <= ? ORDER BY fire_at",
        (now.isoformat(timespec="minutes"),),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_delivered(conn, reminder: dict) -> str | None:
    """Fecha o lembrete. Se repete, agenda a próxima ocorrência e devolve a data."""
    conn.execute(
        "UPDATE reminders SET status = 'delivered', delivered_at = datetime('now')"
        " WHERE id = ?", (reminder["id"],)
    )
    if not reminder.get("repeat_rule"):
        return None

    nxt = _next_occurrence(
        datetime.fromisoformat(reminder["fire_at"]), reminder["repeat_rule"]
    ).isoformat(timespec="minutes")
    conn.execute(
        "INSERT INTO reminders (text, fire_at, repeat_rule) VALUES (?, ?, ?)",
        (reminder["text"], nxt, reminder["repeat_rule"]),
    )
    return nxt
