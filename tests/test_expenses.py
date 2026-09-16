"""Gastos: registrar por texto solto e perguntar depois."""

from datetime import datetime, timedelta

import pytest

from aide.core.context import now_in
from aide.tools.expenses import formatar, intervalo, parse_lancamento, parse_valor

# ---------- dinheiro ----------

@pytest.mark.parametrize("texto,centavos", [
    ("10,50", 1050),
    ("R$ 10,50", 1050),
    ("r$10,50", 1050),
    ("32", 3200),
    ("12,5", 1250),
    ("0,99", 99),
    ("19,99", 1999),        # o clássico que o float erra
    ("1.234,56", 123456),
    ("1500", 150000),
    ("10.50", 1050),        # ponto com 2 casas: decimal
    ("1.234", 123400),      # ponto com 3 casas: milhar
    (" 7 ", 700),
])
def test_entende_o_valor(texto, centavos):
    assert parse_valor(texto) == centavos


@pytest.mark.parametrize("texto", ["", "abc", "1,2,3", "10..50"])
def test_recusa_valor_sem_sentido(texto):
    with pytest.raises(ValueError):
        parse_valor(texto)


def test_recusa_valor_negativo():
    with pytest.raises(ValueError, match="negativo"):
        parse_valor("-10")


def test_centavos_sao_exatos():
    """O motivo de guardar inteiro: 0,1 + 0,2 em float não dá 0,3."""
    assert parse_valor("0,10") + parse_valor("0,20") == parse_valor("0,30")
    assert sum(parse_valor("19,99") for _ in range(100)) == parse_valor("1999,00")


@pytest.mark.parametrize("centavos,texto", [
    (1050, "R$ 10,50"), (99, "R$ 0,99"), (5, "R$ 0,05"),
    (123456, "R$ 1.234,56"), (100000000, "R$ 1.000.000,00"), (0, "R$ 0,00"),
])
def test_formata_como_se_escreve_no_brasil(centavos, texto):
    assert formatar(centavos) == texto


# ---------- "10,50 almoço com a KA" ----------

@pytest.mark.parametrize("texto,centavos,descricao", [
    ("10,50 almoço com a KA", 1050, "almoço com a KA"),
    ("R$ 32 uber pro aeroporto", 3200, "uber pro aeroporto"),
    ("1.234,56 notebook novo", 123456, "notebook novo"),
    ("15 café", 1500, "café"),
])
def test_separa_valor_da_descricao(texto, centavos, descricao):
    assert parse_lancamento(texto) == (centavos, descricao)


def test_sem_descricao_explica_o_formato():
    with pytest.raises(ValueError, match="10,50 almoço"):
        parse_lancamento("10,50")


# ---------- tools ----------

def test_registra_e_devolve_formatado(ctx, registry):
    gasto = registry.call("expenses.add", {
        "amount": "10,50", "description": "almoço com a KA",
        "category": "Alimentação"}, ctx)
    assert gasto.ok
    assert gasto.data["cents"] == 1050
    assert gasto.data["valor"] == "R$ 10,50"
    assert gasto.data["category"] == "alimentação"  # normalizado


def test_exige_descricao(ctx, registry):
    assert not registry.call("expenses.add", {"amount": "10", "description": "  "}, ctx).ok


def test_soma_o_periodo(ctx, registry):
    for valor in ("10,50", "32", "187,90"):
        registry.call("expenses.add", {"amount": valor, "description": "x"}, ctx)

    resumo = registry.call("expenses.summary", {"periodo": "hoje"}, ctx).data
    assert resumo["total_cents"] == 1050 + 3200 + 18790
    assert resumo["total"] == "R$ 230,40"
    assert resumo["quantos"] == 3
    assert resumo["media"] == "R$ 76,80"


def test_agrupa_por_categoria_do_maior_para_o_menor(ctx, registry):
    registry.call("expenses.add", {"amount": "10", "description": "a",
                                   "category": "alimentação"}, ctx)
    registry.call("expenses.add", {"amount": "200", "description": "b",
                                   "category": "mercado"}, ctx)
    registry.call("expenses.add", {"amount": "5", "description": "c"}, ctx)

    categorias = registry.call("expenses.summary", {"periodo": "hoje"}, ctx).data["por_categoria"]
    assert [c["category"] for c in categorias] == ["mercado", "alimentação", "sem categoria"]
    assert categorias[0]["valor"] == "R$ 200,00"


def test_filtra_por_categoria(ctx, registry):
    registry.call("expenses.add", {"amount": "10", "description": "a",
                                   "category": "mercado"}, ctx)
    registry.call("expenses.add", {"amount": "99", "description": "b",
                                   "category": "lazer"}, ctx)

    resumo = registry.call("expenses.summary",
                           {"periodo": "hoje", "category": "mercado"}, ctx).data
    assert resumo["total"] == "R$ 10,00"


def test_gasto_de_ontem_fica_fora_de_hoje(ctx, registry):
    ontem = (now_in(ctx.config.timezone) - timedelta(days=1)).isoformat(timespec="minutes")
    registry.call("expenses.add", {"amount": "50", "description": "ontem",
                                   "when": ontem}, ctx)
    registry.call("expenses.add", {"amount": "10", "description": "hoje"}, ctx)

    assert registry.call("expenses.summary", {"periodo": "hoje"}, ctx).data["total"] == "R$ 10,00"
    assert registry.call("expenses.summary", {"periodo": "ontem"}, ctx).data["total"] == "R$ 50,00"
    assert registry.call("expenses.summary", {"periodo": "mes"}, ctx).data["total"] == "R$ 60,00"


def test_periodo_desconhecido_diz_quais_valem(ctx, registry):
    erro = registry.call("expenses.summary", {"periodo": "década"}, ctx)
    assert not erro.ok
    assert "hoje" in erro.error


def test_semana_comeca_na_segunda():
    agora = datetime(2026, 9, 16, 15, 0)  # quarta
    de, _ = intervalo("semana", agora)
    assert de.startswith("2026-09-14")  # segunda


def test_periodo_vazio_nao_quebra(ctx, registry):
    resumo = registry.call("expenses.summary", {"periodo": "ontem"}, ctx).data
    assert resumo["total"] == "R$ 0,00"
    assert resumo["quantos"] == 0
    assert resumo["media"] == "R$ 0,00"


def test_lista_do_mais_recente_para_o_mais_antigo(ctx, registry):
    agora = now_in(ctx.config.timezone)
    for i, desc in enumerate(["antigo", "recente"]):
        registry.call("expenses.add", {
            "amount": "10", "description": desc,
            "when": (agora - timedelta(hours=5 - i * 4)).isoformat(timespec="minutes")}, ctx)

    lista = registry.call("expenses.list", {"periodo": "hoje"}, ctx).data
    assert [g["description"] for g in lista] == ["recente", "antigo"]


def test_apagar_e_tool_de_confirmacao(registry):
    """Apagar gasto não pode acontecer sem alguém dizer sim — nem por MCP."""
    assert registry.get("expenses.delete").safety == "confirm"


def test_apagado_some_da_conta(ctx, registry):
    gasto = registry.call("expenses.add", {"amount": "10", "description": "engano"}, ctx).data
    registry.call("expenses.delete", {"id": gasto["id"]}, ctx)
    assert registry.call("expenses.summary", {"periodo": "hoje"}, ctx).data["quantos"] == 0
