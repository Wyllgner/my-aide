"""Quanto a API custa, e por que 'saldo' não aparece em lugar nenhum.

Testado contra a API de verdade em 16/09/2026:
  /v1/dashboard/billing/credit_grants  -> 403, exige session key do navegador
  /v1/dashboard/billing/subscription   -> 403, idem
  /v1/organization/costs               -> 403, falta o escopo api.usage.read
A chave normal não lê saldo nem custo. Só uma chave de ADMIN lê custo.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aide.llm import custo as calculo

TZ = ZoneInfo("America/Porto_Velho")
AGORA = datetime(2026, 9, 16, 17, 0, tzinfo=TZ)


@pytest.fixture
def com_uso(ctx):
    def gravar(modelo, entrada, saida, quando="now"):
        ctx.conn.execute(
            "INSERT INTO llm_usage (ts, model, purpose, input_tokens, output_tokens)"
            f" VALUES (datetime('{quando}'), ?, 'chat', ?, ?)", (modelo, entrada, saida))

    gravar("gpt-5.6-luna", 1_000_000, 1_000_000)
    gravar("gpt-5-nano", 1_000_000, 0)
    return ctx


def test_estima_pelo_preco_do_config(com_uso):
    gasto = calculo.estimar(com_uso.conn, com_uso.config)
    # luna: 0,20 de entrada + 1,20 de saída = 1,40 ; nano: 0,05 de entrada
    assert round(gasto.estimado_usd, 4) == 1.45
    assert gasto.chamadas == 2


def test_modelo_sem_preco_aparece_em_vez_de_virar_zero(ctx):
    """Somar zero calado faria o total mentir para baixo, que é o pior erro aqui."""
    ctx.conn.execute(
        "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
        " VALUES ('modelo-novo', 'chat', 1000, 1000)")
    gasto = calculo.estimar(ctx.conn, ctx.config)
    assert gasto.sem_preco == ["modelo-novo"]
    assert gasto.estimado_usd == 0.0


def test_periodo_antigo_fica_fora(ctx):
    ctx.conn.execute(
        "INSERT INTO llm_usage (ts, model, purpose, input_tokens, output_tokens)"
        " VALUES (datetime('now','-40 days'), 'gpt-5-nano', 'chat', 1000000, 0)")
    assert calculo.estimar(ctx.conn, ctx.config, dias=30).chamadas == 0
    assert calculo.estimar(ctx.conn, ctx.config, dias=60).chamadas == 1


def test_mes_corrente_comeca_no_dia_um(com_uso):
    gasto = calculo.mes_corrente(com_uso.conn, com_uso.config, AGORA)
    assert gasto.desde == "01/09"


# ---------- orçamento ----------

def test_quanto_ainda_cabe(com_uso):
    gasto = calculo.estimar(com_uso.conn, com_uso.config)
    sobra = calculo.restante(gasto, orcamento=5.0)
    assert round(sobra["sobra"], 2) == 3.55
    assert sobra["estimado"] is True


def test_sem_orcamento_nao_inventa_resposta(com_uso):
    """Sem um teto declarado, 'quanto ainda tenho' não tem resposta honesta."""
    gasto = calculo.estimar(com_uso.conn, com_uso.config)
    assert calculo.restante(gasto, orcamento=0) is None
    assert calculo.restante(gasto, orcamento=None) is None


def test_estourar_o_orcamento_nao_passa_de_cem_por_cento(com_uso):
    gasto = calculo.estimar(com_uso.conn, com_uso.config)
    sobra = calculo.restante(gasto, orcamento=1.0)
    assert sobra["fracao"] == 1.0        # a barra não transborda
    assert round(sobra["sobra"], 2) < 0  # mas o número diz a verdade


def test_custo_real_tem_preferencia_sobre_a_estimativa(com_uso):
    gasto = calculo.estimar(com_uso.conn, com_uso.config)
    gasto.real_usd = 2.0
    sobra = calculo.restante(gasto, orcamento=5.0)
    assert sobra["usado"] == 2.0
    assert sobra["estimado"] is False


# ---------- a Admin API ----------

def test_sem_chave_de_admin_nao_tenta_a_rede(com_uso):
    """A fixture `sem_rede` derruba o teste se alguém chamar a API."""
    object.__setattr__(com_uso.config.llm, "admin_key", None)
    gasto = calculo.com_custo_real(
        calculo.estimar(com_uso.conn, com_uso.config), com_uso.config, AGORA)
    assert gasto.real_usd is None
    assert gasto.erro_real is None


def test_falta_de_escopo_e_explicada(com_uso, monkeypatch):
    """O erro mais provável: chave de admin criada sem api.usage.read."""
    import urllib.error

    def recusar(*a, **k):
        raise urllib.error.HTTPError(
            "u", 403, "Forbidden", {},
            __import__("io").BytesIO(b'{"error":{"message":"Missing scopes: api.usage.read"}}'))

    object.__setattr__(com_uso.config.llm, "admin_key", "sk-admin-x")
    monkeypatch.setattr("urllib.request.urlopen", recusar)

    gasto = calculo.com_custo_real(
        calculo.estimar(com_uso.conn, com_uso.config), com_uso.config, AGORA)
    assert "api.usage.read" in gasto.erro_real
    assert gasto.real_usd is None


def test_openai_fora_do_ar_nao_derruba_o_relatorio(com_uso, monkeypatch):
    def cair(*a, **k):
        raise OSError("sem rede")

    object.__setattr__(com_uso.config.llm, "admin_key", "sk-admin-x")
    monkeypatch.setattr("urllib.request.urlopen", cair)

    gasto = calculo.com_custo_real(
        calculo.estimar(com_uso.conn, com_uso.config), com_uso.config, AGORA)
    assert gasto.erro_real
    assert gasto.estimado_usd > 0  # a estimativa continua valendo


def test_custo_real_soma_os_baldes(monkeypatch):
    import io
    import json

    resposta = json.dumps({"data": [
        {"results": [{"amount": {"value": 1.5}}, {"amount": {"value": 0.25}}]},
        {"results": [{"amount": {"value": 0.25}}]},
        {"results": []},
    ]}).encode()

    class Fake(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Fake(resposta))
    assert calculo.custo_real("sk-admin-x", AGORA) == 2.0


# ---------- a tool ----------

def test_a_tool_diz_que_saldo_nao_existe(com_uso, registry):
    """Se ela não disser, o modelo inventa um saldo — e você confia nele."""
    resposta = registry.call("usage.cost", {}, com_uso).data
    assert "não expõe saldo" in resposta["saldo_da_conta"]
    assert resposta["estimado_usd"] > 0


def test_a_tool_informa_o_que_ainda_cabe(com_uso, registry):
    object.__setattr__(com_uso.config.llm, "orcamento_mensal_usd", 5.0)
    resposta = registry.call("usage.cost", {}, com_uso).data
    assert resposta["ainda_cabe_usd"] == 3.55
    assert resposta["usado_do_orcamento"] == "29%"


# ---------- saldo ancorado ----------

def test_sem_ancora_nao_ha_saldo(ctx):
    """Sem um número lido no painel, não há resposta honesta para 'quanto tenho'."""
    assert calculo.saldo_estimado(ctx.conn, ctx.config) is None


def test_saldo_e_a_ancora_menos_o_gasto_depois_dela(ctx):
    ctx.conn.execute(
        "INSERT INTO llm_usage (ts, model, purpose, input_tokens, output_tokens)"
        " VALUES (datetime('now','-2 days'), 'gpt-5.6-luna', 'chat', 1000000, 0)")
    calculo.anotar_saldo(ctx.conn, 4.22, "2026-09-16T17:00-04:00")
    # depois da âncora: 1M de entrada no luna = US$ 0,20
    ctx.conn.execute(
        "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
        " VALUES ('gpt-5.6-luna', 'chat', 1000000, 0)")

    saldo = calculo.saldo_estimado(ctx.conn, ctx.config)
    assert saldo["ancora_usd"] == 4.22
    assert round(saldo["gasto_desde"], 4) == 0.20
    assert round(saldo["saldo_usd"], 2) == 4.02


def test_gasto_anterior_a_ancora_nao_e_descontado(ctx):
    """A âncora já reflete o que foi gasto antes dela; descontar de novo cobraria duas vezes."""
    ctx.conn.execute(
        "INSERT INTO llm_usage (ts, model, purpose, input_tokens, output_tokens)"
        " VALUES (datetime('now','-5 days'), 'gpt-5.6-luna', 'chat', 5000000, 0)")
    calculo.anotar_saldo(ctx.conn, 4.22, "2026-09-16T17:00-04:00")

    assert calculo.saldo_estimado(ctx.conn, ctx.config)["gasto_desde"] == 0.0


def test_a_ancora_mais_recente_manda(ctx):
    calculo.anotar_saldo(ctx.conn, 10.0, "2026-09-01T10:00-04:00")
    calculo.anotar_saldo(ctx.conn, 4.22, "2026-09-16T17:00-04:00")
    assert calculo.saldo_estimado(ctx.conn, ctx.config)["ancora_usd"] == 4.22


def test_historico_de_ancoras_e_guardado(ctx):
    """Duas âncoras permitem conferir se a estimativa acompanha a cobrança real."""
    calculo.anotar_saldo(ctx.conn, 10.0, "2026-09-01T10:00-04:00")
    calculo.anotar_saldo(ctx.conn, 4.22, "2026-09-16T17:00-04:00")
    assert ctx.conn.execute("SELECT COUNT(*) c FROM api_balance").fetchone()["c"] == 2


def test_saldo_e_guardado_em_centavos_inteiros(ctx):
    calculo.anotar_saldo(ctx.conn, 4.22, "2026-09-16T17:00-04:00")
    assert ctx.conn.execute("SELECT cents FROM api_balance").fetchone()["cents"] == 422


def test_saldo_negativo_e_recusado(ctx):
    with pytest.raises(ValueError, match="negativo"):
        calculo.anotar_saldo(ctx.conn, -1, "2026-09-16T17:00-04:00")


def test_a_tool_diz_que_o_saldo_e_estimativa(ctx, registry):
    """Sem isso o modelo apresenta o número como se fosse o saldo real da conta."""
    calculo.anotar_saldo(ctx.conn, 4.22, "2026-09-16T17:00-04:00")
    resposta = registry.call("usage.cost", {}, ctx).data
    assert resposta["saldo_estimado_usd"] == 4.22
    assert "estimativa" in resposta["sobre_o_saldo"]


def test_a_tool_admite_nao_saber_o_saldo(ctx, registry):
    resposta = registry.call("usage.cost", {}, ctx).data
    assert "não sei" in resposta["saldo_da_conta"]
    assert "myaide saldo" in resposta["saldo_da_conta"]


def test_a_tool_anota_o_saldo_que_a_pessoa_falou(ctx, registry):
    """Pelo Telegram é assim que o número entra: falando."""
    assert registry.call("usage.set_balance", {"usd": "4,22"}, ctx).data["saldo_anotado_usd"] == 4.22
    assert registry.call("usage.cost", {}, ctx).data["saldo_estimado_usd"] == 4.22
