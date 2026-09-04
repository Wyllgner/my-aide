from datetime import datetime
from zoneinfo import ZoneInfo

from aide.llm.base import LLMProvider, LLMResponse
from aide.scheduler import briefing

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 3, 7, 30, tzinfo=TZ)


class SpyLLM(LLMProvider):
    def __init__(self, text="Hoje: pagar boleto."):
        self.text = text
        self.calls = []

    def complete(self, messages, *, fast=False, tools=None, purpose="chat"):
        self.calls.append({"fast": fast, "purpose": purpose, "prompt": messages[-1].content})
        return LLMResponse(text=self.text, model="fake")


def test_sem_dados_nao_chama_a_llm(ctx):
    llm = SpyLLM()
    resultado = briefing.gerar(ctx.conn, ctx.config, llm, AGORA, "manha")
    assert resultado.vazio
    assert llm.calls == []


def test_briefing_usa_o_modelo_barato(ctx, registry):
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-09-03T09:00"}, ctx)
    llm = SpyLLM()
    briefing.gerar(ctx.conn, ctx.config, llm, AGORA, "manha")
    assert llm.calls[0]["fast"] is True
    assert llm.calls[0]["purpose"] == "briefing_manha"


def test_prompt_leva_os_dados_reais(ctx, registry):
    registry.call("tasks.create", {"title": "Boleto da internet", "due": "2026-09-03T09:00"}, ctx)
    llm = SpyLLM()
    briefing.gerar(ctx.conn, ctx.config, llm, AGORA, "manha")
    assert "Boleto da internet" in llm.calls[0]["prompt"]
    assert "vence hoje" in llm.calls[0]["prompt"]


def test_atrasada_eleva_a_urgencia(ctx, registry):
    registry.call("tasks.create", {"title": "Velha", "due": "2026-08-20T09:00"}, ctx)
    resultado = briefing.gerar(ctx.conn, ctx.config, SpyLLM(), AGORA, "manha")
    assert resultado.urgency == "critical"


def test_sem_novidades_conta_como_vazio(ctx, registry):
    registry.call("tasks.create", {"title": "X", "due": "2026-09-03T09:00"}, ctx)
    resultado = briefing.gerar(ctx.conn, ctx.config, SpyLLM("SEM NOVIDADES"), AGORA, "manha")
    assert resultado.vazio


def test_noite_separa_feito_de_pendente(ctx, registry):
    feita = registry.call("tasks.create", {"title": "Feita", "due": "2026-09-03T09:00"}, ctx).data
    registry.call("tasks.complete", {"id": feita["id"]}, ctx)
    registry.call("tasks.create", {"title": "Pendente", "due": "2026-09-03T08:00"}, ctx)
    dados = briefing.coletar_noite(ctx.conn, AGORA.replace(hour=21, minute=30))
    assert any("Feita" in x for x in dados["concluídas hoje"])
    assert any("Pendente" in x for x in dados["ficaram para trás"])


def test_tipo_invalido_falha(ctx):
    try:
        briefing.gerar(ctx.conn, ctx.config, SpyLLM(), AGORA, "xpto")
    except ValueError as exc:
        assert "desconhecido" in str(exc)
    else:
        raise AssertionError("deveria ter falhado")
