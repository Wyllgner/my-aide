"""Tools de agenda.

A agenda é *lida* de um feed iCal, não construída aqui — ver ARQUITETURA.md
seção 5.3. O que este projeto acrescenta é o cruzamento: conflito de horário e
tarefa que vence no mesmo dia de um compromisso.
"""

from __future__ import annotations

from datetime import timedelta

from aide.core.context import now_in
from aide.storage import ical
from aide.tools.registry import ToolContext, registry


@registry.register(
    name="events.list",
    description=(
        "Compromissos da agenda nos próximos dias. A agenda vem de um "
        "calendário assinado (Google, Apple, Outlook), é só leitura."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dias": {"type": "integer", "description": "Janela a partir de hoje. Padrão 7."},
        },
        "required": [],
    },
)
def list_events(ctx: ToolContext, dias: int = 7) -> list[dict]:
    agora = now_in(ctx.config.timezone)
    limite = (agora + timedelta(days=dias)).isoformat(timespec="minutes")
    rows = ctx.conn.execute(
        "SELECT id, title, start_at, end_at, location FROM events"
        " WHERE deleted_at IS NULL AND start_at BETWEEN ? AND ? ORDER BY start_at",
        (agora.replace(hour=0, minute=0).isoformat(timespec="minutes"), limite),
    ).fetchall()
    return [dict(r) for r in rows]


@registry.register(
    name="events.conflicts",
    description="Compromissos que se sobrepõem no horário.",
    parameters={
        "type": "object",
        "properties": {"dias": {"type": "integer"}},
        "required": [],
    },
)
def conflicts(ctx: ToolContext, dias: int = 14) -> list[dict]:
    eventos = list_events(ctx, dias=dias)
    return [
        {"a": f"{a['title']} ({a['start_at']})", "b": f"{b['title']} ({b['start_at']})"}
        for a, b in ical.conflitos(eventos)
    ]


# ---------- sincronização, usada pelo scheduler e pela CLI ----------

def sincronizar(conn, config, url: str | None = None) -> dict:
    """Baixa o feed e substitui os eventos importados.

    Substitui em vez de mesclar: o feed é a fonte da verdade, e evento apagado
    lá tem de sumir aqui. Eventos criados localmente (source='local') ficam.
    """
    url = url or getattr(config, "calendar_url", None)
    if not url:
        raise ValueError(
            "nenhum calendário configurado. Ponha o endereço iCal secreto em "
            "config.yaml (calendar.ics_url) — no Google: Configurações da agenda "
            "> Endereço secreto no formato iCal."
        )

    eventos = ical.parse(ical.baixar(url), config.timezone)
    conn.execute("DELETE FROM events WHERE source = 'ical'")
    for evento in eventos:
        conn.execute(
            "INSERT INTO events (title, start_at, end_at, location, source, external_id)"
            " VALUES (?, ?, ?, ?, 'ical', ?)",
            (evento["title"], evento["start_at"], evento.get("end_at"),
             evento.get("location"), evento.get("external_id")),
        )
    return {"importados": len(eventos)}
