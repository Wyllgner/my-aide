"""Montagem do prompt: system + estado atual + histórico da sessão."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aide.llm.base import Message

PROMPTS_DIR = Path(__file__).parent / "prompts"


def now_in(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def system_prompt(config) -> Message:
    template = (PROMPTS_DIR / "system.md").read_text()
    text = template.format(
        user_name=config.user_name or "seu usuário",
        now=now_in(config.timezone).strftime("%A, %d/%m/%Y %H:%M"),
        timezone=config.timezone,
    )
    return Message(role="system", content=text)


def state_snapshot(conn, config) -> Message | None:
    """Tarefas abertas, para o modelo não recriar o que já existe.

    Não é só o dia: o modelo precisa enxergar o que está em aberto, senão
    "adia o IPVA" vira uma tarefa nova. Itens `private` ficam de fora — nunca
    vão para o provedor.
    """
    now = now_in(config.timezone)
    today = now.replace(hour=23, minute=59).isoformat(timespec="minutes")
    rows = conn.execute(
        "SELECT id, title, due_at, priority, project, snooze_count FROM tasks"
        " WHERE deleted_at IS NULL AND status = 'open' AND private = 0"
        " ORDER BY due_at IS NULL, due_at LIMIT 40",
    ).fetchall()

    if not rows:
        return None

    lines = []
    for r in rows:
        marks = []
        if r["due_at"]:
            marks.append(r["due_at"])
            if r["due_at"] < now.isoformat():
                marks.append("ATRASADA")
            elif r["due_at"] <= today:
                marks.append("hoje")
        else:
            marks.append("sem prazo")
        if r["project"]:
            marks.append(r["project"])
        if r["snooze_count"]:
            marks.append(f"adiada {r['snooze_count']}x")
        lines.append(f"#{r['id']} {r['title']} — {' · '.join(marks)}")

    return Message(
        role="system",
        content=(
            "Tarefas abertas agora (esta é a lista completa; use estes ids ao "
            "adiar, concluir ou alterar, e NÃO crie tarefa nova para algo que "
            "já está aqui):\n" + "\n".join(lines)
        ),
    )


def build(config, history: list[Message], conn=None) -> list[Message]:
    messages = [system_prompt(config)]
    if conn is not None:
        snapshot = state_snapshot(conn, config)
        if snapshot:
            messages.append(snapshot)
    messages.extend(history[-config.history_messages :])
    return messages
