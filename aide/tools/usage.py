"""Quanto a própria OpenAI está custando.

Saldo da conta não está aqui porque a OpenAI não expõe por API — os endpoints
de billing exigem a sessão do navegador e recusam chave de API. O que existe é
o gasto, e o quanto dele já comeu o orçamento do `config.yaml`.
"""

from __future__ import annotations

from aide.core.context import now_in
from aide.llm import custo as calculo
from aide.tools.registry import ToolContext, registry


@registry.register(
    name="usage.cost",
    description=(
        "Quanto a API da OpenAI custou no período e quanto ainda cabe no "
        "orçamento do mês. Use para 'quanto você já me custou', 'quanto gastei "
        "de API', 'ainda tenho crédito?'. Não é o saldo da conta: a OpenAI não "
        "expõe saldo por API, então diga isso se perguntarem por saldo."
    ),
    parameters={
        "type": "object",
        "properties": {
            "dias": {"type": "integer",
                     "description": "Janela em dias. Sem isto, o mês corrente."},
        },
        "required": [],
    },
)
def cost(ctx: ToolContext, dias: int | None = None) -> dict:
    agora = now_in(ctx.config.timezone)
    if dias:
        gasto = calculo.estimar(ctx.conn, ctx.config, dias=dias)
        desde = agora.replace(hour=0, minute=0)
    else:
        gasto = calculo.mes_corrente(ctx.conn, ctx.config, agora)
        desde = agora.replace(day=1, hour=0, minute=0)

    gasto = calculo.com_custo_real(gasto, ctx.config, desde)
    sobra = calculo.restante(gasto, ctx.config.llm.orcamento_mensal_usd)

    resposta = {
        "periodo": gasto.desde,
        "estimado_usd": round(gasto.estimado_usd, 4),
        "chamadas": gasto.chamadas,
        "por_modelo": [
            {"modelo": m["model"], "chamadas": m["chamadas"],
             "usd": round(m["usd"], 4) if m["usd"] is not None else None}
            for m in gasto.por_modelo
        ],
        "saldo_da_conta": (
            "indisponível: a OpenAI não expõe saldo por API, só pelo painel"
        ),
    }
    if gasto.real_usd is not None:
        resposta["real_usd"] = round(gasto.real_usd, 4)
    if gasto.erro_real:
        resposta["custo_real"] = f"indisponível ({gasto.erro_real})"
    if sobra:
        resposta["orcamento_mensal_usd"] = sobra["orcamento"]
        resposta["ainda_cabe_usd"] = round(sobra["sobra"], 2)
        resposta["usado_do_orcamento"] = f"{sobra['fracao'] * 100:.0f}%"
    else:
        resposta["orcamento"] = "não definido em config.yaml (llm.orcamento_mensal_usd)"
    return resposta
