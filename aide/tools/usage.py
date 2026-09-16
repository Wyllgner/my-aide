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
        "Quanto a API da OpenAI custou e quanto de saldo deve restar. Use para "
        "'quanto você já me custou', 'quanto gastei de API', 'quanto ainda tenho "
        "de crédito'. O saldo é estimado a partir do último valor anotado do "
        "painel; diga que é estimativa ao responder."
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
    }

    saldo = calculo.saldo_estimado(ctx.conn, ctx.config)
    if saldo:
        resposta["saldo_estimado_usd"] = round(saldo["saldo_usd"], 2)
        resposta["saldo_anotado_usd"] = saldo["ancora_usd"]
        resposta["saldo_anotado_ha_dias"] = saldo["dias_desde"]
        resposta["sobre_o_saldo"] = (
            "estimativa: o saldo anotado no painel menos o gasto calculado desde "
            "então. A OpenAI não expõe saldo por API. Se a âncora tiver mais de "
            "um mês, sugira conferir no painel e rodar `myaide saldo <valor>`."
        )
    else:
        resposta["saldo_da_conta"] = (
            "não sei: a OpenAI não expõe saldo por API e nenhum foi anotado. "
            "Sugira `myaide saldo <valor>` com o que o painel mostra."
        )
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


@registry.register(
    name="usage.set_balance",
    description=(
        "Anota o saldo da API que a pessoa leu no painel da OpenAI. Use quando "
        "ela disser quanto tem — 'tenho 4,22 na API', 'meu saldo é 10 dólares'. "
        "A partir daí o saldo estimado parte desse número."
    ),
    parameters={
        "type": "object",
        "properties": {
            "usd": {"type": "string",
                    "description": "Em dólares, como a pessoa falou: '4.22', '4,22', '10'."},
        },
        "required": ["usd"],
    },
)
def set_balance(ctx: ToolContext, usd: str) -> dict:
    from aide.tools.expenses import parse_valor

    valor = parse_valor(usd) / 100
    agora = now_in(ctx.config.timezone)
    calculo.anotar_saldo(ctx.conn, valor, agora.isoformat(timespec="minutes"))
    return {"saldo_anotado_usd": valor, "em": agora.isoformat(timespec="minutes"),
            "nota": "daqui em diante o saldo estimado desconta o gasto a partir deste valor"}
