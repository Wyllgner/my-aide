"""Hora. A LLM nunca adivinha data — pergunta aqui."""

from __future__ import annotations

from aide.core.context import now_in
from aide.tools.registry import ToolContext, registry


@registry.register(
    name="time.now",
    description=(
        "Data e hora atuais no fuso do usuário. Use SEMPRE antes de calcular "
        "qualquer prazo relativo ('amanhã', 'sexta', 'daqui a duas semanas')."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def now(ctx: ToolContext) -> dict:
    moment = now_in(ctx.config.timezone)
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return {
        "iso": moment.isoformat(timespec="minutes"),
        "data": moment.strftime("%d/%m/%Y"),
        "hora": moment.strftime("%H:%M"),
        "dia_da_semana": dias[moment.weekday()],
        "timezone": ctx.config.timezone,
    }
