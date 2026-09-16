"""Como uma mensagem é escrita, e por que cada canal recebe uma versão.

O erro que este módulo existe para evitar: alinhar coluna pensando no terminal
e mandar o mesmo texto para o celular, onde a fonte é proporcional e a coluna
vira bagunça.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aide.channels.formato import (
    Item,
    Mensagem,
    Secao,
    atraso,
    escapar,
    para_desktop,
    para_telegram,
    para_terminal,
    quando,
)

TZ = ZoneInfo("America/Porto_Velho")
AGORA = datetime(2026, 9, 16, 17, 0, tzinfo=TZ)


# ---------- datas ----------

@pytest.mark.parametrize("iso,esperado", [
    ("2026-09-16T09:00-04:00", "16/09 (hoje 09:00)"),
    ("2026-09-17T14:00-04:00", "17/09 (amanhã 14:00)"),
    ("2026-09-15T15:00-04:00", "15/09 (ontem)"),
    ("2026-09-04T08:00-04:00", "04/09 (há 12 dias)"),
    ("2026-09-19T10:00-04:00", "19/09 (sábado 10:00)"),
    ("2026-09-30T10:00-04:00", "30/09 (em 14 dias)"),
])
def test_data_traz_o_dia_e_a_leitura_humana(iso, esperado):
    """As duas coisas: a data sozinha obriga a contar de cabeça, o relativo
    sozinho perde a referência."""
    assert quando(iso, AGORA) == esperado


def test_data_converte_para_o_fuso_de_hoje():
    """08:00 em São Paulo são 07:00 aqui; mostrar '08:00' faria você se atrasar."""
    assert quando("2026-09-17T08:00-03:00", AGORA) == "17/09 (amanhã 07:00)"


def test_sem_prazo_e_um_estado(): 
    assert quando(None, AGORA) == "sem prazo"


def test_data_ilegivel_nao_derruba_a_mensagem():
    assert quando("qualquer coisa", AGORA) == "qualquer coisa"


@pytest.mark.parametrize("iso,esperado", [
    ("2026-09-04T08:00-04:00", "12 dias"),
    ("2026-09-15T08:00-04:00", "1 dia"),
    ("2026-09-16T08:00-04:00", "hoje"),
])
def test_atraso_cabe_numa_coluna_estreita(iso, esperado):
    assert atraso(iso, AGORA) == esperado


# ---------- a mensagem ----------

@pytest.fixture
def mensagem():
    return Mensagem(
        titulo="Bom dia",
        secoes=[
            Secao("Atrasadas", [Item("Pagar o IPVA", "#4", "10/09 (há 6 dias)")]),
            Secao("Hoje", [Item("Boleto da luz", "#5", "16/09 (hoje 09:00)")]),
            Secao("Vazia", []),
        ],
        rodape="1 atrasada · 1 para hoje",
    )


def test_secao_vazia_nao_aparece(mensagem):
    for render in (para_terminal, para_desktop, para_telegram):
        assert "Vazia" not in render(mensagem)


def test_mensagem_sem_item_nenhum_e_vazia():
    assert Mensagem("X", [Secao("A", [])]).vazia
    assert not Mensagem("X", [Secao("A", [Item("y")])]).vazia


def test_terminal_alinha_em_coluna(mensagem):
    linhas = para_terminal(mensagem).splitlines()
    itens = [linha for linha in linhas if "(" in linha]
    # a marca começa na mesma coluna em todas as linhas: é o que deixa escanear
    assert len({linha.index("(") for linha in itens}) == 1
    assert "ATRASADAS" in para_terminal(mensagem)


def test_desktop_nao_alinha_e_nao_repete_o_titulo(mensagem):
    """A notificação já mostra o título no cabeçalho, e a fonte é proporcional:
    coluna viraria bagunça e o título gastaria uma das poucas linhas visíveis."""
    saida = para_desktop(mensagem)
    assert not saida.startswith("Bom dia")
    assert "   " not in saida  # sem preenchimento de coluna
    assert "Pagar o IPVA — 10/09 (há 6 dias)" in saida


def test_telegram_usa_markdown_em_vez_de_coluna(mensagem):
    saida = para_telegram(mensagem)
    assert "*Bom dia*" in saida
    assert "*Atrasadas*" in saida
    assert "• #4 Pagar o IPVA" in saida
    assert "   " not in saida


def test_telegram_escapa_o_que_quebraria_a_formatacao():
    """Um título com _ ou * estragaria a mensagem inteira, não só a linha dele."""
    saida = para_telegram(Mensagem("X", [Secao("S", [Item("relatório_final *urgente*")])]))
    assert r"relatório\_final \*urgente\*" in saida


def test_escapar_deixa_o_texto_normal_em_paz():
    assert escapar("Pagar o IPVA") == "Pagar o IPVA"
