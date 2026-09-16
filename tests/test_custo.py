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
