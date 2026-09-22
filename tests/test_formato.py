"""Como uma mensagem é escrita, e por que cada canal recebe uma versão.

O erro que este módulo existe para evitar: alinhar coluna pensando no terminal
e mandar o mesmo texto para o celular, onde a fonte é proporcional e a coluna
vira bagunça.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aide.channels import formato
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


# ---------- resposta de conversa no Telegram ----------

def test_a_lista_de_tarefas_ganha_relevo():
    """O modelo escreve texto puro porque a mesma frase vai para um terminal;
    quem sabe que o destino é o Telegram é o formatador."""
    from aide.channels.formato import conversa_para_telegram

    saida = conversa_para_telegram(
        "Suas tarefas abertas:\n#10 Marcar reunião com o contador (04/09, há 12 dias)")
    assert "Suas tarefas abertas:" in saida
    assert "`#10`" in saida
    assert "*Marcar reunião com o contador*" in saida
    assert "_04/09, há 12 dias_" in saida


def test_linha_sem_id_passa_inteira():
    from aide.channels.formato import conversa_para_telegram

    assert conversa_para_telegram("Você tem 5 tarefas abertas.") == "Você tem 5 tarefas abertas."


def test_item_sem_prazo_nao_inventa_travessao():
    from aide.channels.formato import conversa_para_telegram

    saida = conversa_para_telegram("#14 Pagar o condomínio")
    assert saida == "`#14` *Pagar o condomínio*"


def test_titulo_com_caractere_de_markdown_e_escapado():
    """Sem escapar, um título com _ quebra a formatação da mensagem inteira."""
    from aide.channels.formato import conversa_para_telegram

    saida = conversa_para_telegram("#7 relatorio_final (hoje)")
    assert r"relatorio\_final" in saida


def test_texto_livre_tambem_e_escapado():
    from aide.channels.formato import conversa_para_telegram

    assert r"\*" in conversa_para_telegram("isso é *importante*")


@pytest.mark.parametrize("iso,esperado", [
    ("2026-09-16T21:47-04:00", "hoje"),
    ("2026-09-15T10:00-04:00", "ontem"),
    ("2026-09-13T10:00-04:00", "há 3 dias"),
    ("2026-09-04T10:00-04:00", "04/09"),
])
def test_data_curta_diz_o_dia_sem_a_hora(iso, esperado):
    """Para uma nota, saber que foi ontem basta; '16/09 (hoje 21:47)' diz duas
    vezes a mesma coisa e come a linha."""
    from aide.channels.formato import data_curta

    assert data_curta(iso, AGORA) == esperado


def test_data_curta_aceita_vazio():
    from aide.channels.formato import data_curta

    assert data_curta(None, AGORA) == ""


# ---------- número, plural e carimbo do banco ----------

def test_numero_separa_milhar_com_ponto():
    """`f"{n:,}"` escreveria 654,638 — número inglês ao lado de R$ escrito certo."""
    assert formato.numero(654638) == "654.638"
    assert formato.numero(0) == "0"
    assert formato.numero(-1500) == "-1.500"


def test_dolar_mantem_o_simbolo_em_ingles_e_o_numero_em_portugues():
    assert formato.dolar(0.1369) == "US$ 0,1369"
    assert formato.dolar(4.2, casas=2) == "US$ 4,20"
    assert formato.dolar(1234.5) == "US$ 1.234,5000"


@pytest.mark.parametrize("quantos,esperado", [
    (0, "0 lançamentos"), (1, "1 lançamento"), (2, "2 lançamentos"),
    (1200, "1.200 lançamentos"),
])
def test_plural_escreve_o_que_se_fala(quantos, esperado):
    """"lançamento(s)" é o programador aparecendo no meio da frase."""
    assert formato.plural(quantos, "lançamento") == esperado


def test_plural_aceita_a_forma_irregular():
    assert formato.plural(2, "mensagem", "mensagens") == "2 mensagens"
    assert formato.plural(1, "mensagem", "mensagens") == "1 mensagem"


def test_carimbo_do_banco_vira_hora_local():
    """`datetime('now')` é UTC ingênuo: cru, ele adianta a hora em 4 e vira o dia."""
    local = formato.de_utc("2026-09-22 00:29:30", AGORA)
    assert local.strftime("%d/%m %H:%M") == "21/09 20:29"


def test_carimbo_com_fuso_e_respeitado():
    assert formato.de_utc("2026-09-21T09:00-04:00", AGORA).hour == 9


def test_carimbo_ilegivel_nao_explode():
    """Vem do banco; uma linha estranha não pode derrubar a tela inteira."""
    assert formato.de_utc("nada disso", AGORA) is None
    assert formato.de_utc(None, AGORA) is None


def test_decimal_e_o_dolar_sem_simbolo():
    assert formato.decimal(0.1369) == "0,1369"
    assert formato.decimal(12345.6, casas=2) == "12.345,60"


def test_titulo_longo_nao_emenda_no_prazo():
    """"Enviar versão final do artigo no20/09" — cortado sem aviso e sem espaço."""
    saida = para_terminal(Mensagem("Bom dia", [Secao("Atrasadas", [
        Item("Enviar versão final do artigo no BRWeb", ref="#15", marca="20/09 (ontem)")])]))
    linha = next(l for l in saida.splitlines() if "#15" in l)
    assert "…" in linha
    assert "no20/09" not in linha
    assert linha.endswith("20/09 (ontem)")


def test_titulo_curto_fica_inteiro_e_alinhado():
    saida = para_terminal(Mensagem("Bom dia", [Secao("Hoje", [
        Item("Pagar o IPVA", ref="#4", marca="hoje"),
        Item("Renovar a CNH", ref="#8", marca="amanhã")])]))
    linhas = [l for l in saida.splitlines() if l.startswith("  #")]
    assert "…" not in saida
    # a marca começa na mesma coluna nas duas linhas: é isso que faz a lista
    # ser escaneável de cima a baixo
    assert linhas[0].index("hoje") == linhas[1].index("amanhã")


def test_plural_de_frase_concorda_inteira():
    """"2 nota reindexadas" e "2 tarefa abertas" eram o que saía antes."""
    assert formato.plural(2, "nota reindexada") == "2 notas reindexadas"
    assert formato.plural(1, "nota reindexada") == "1 nota reindexada"
    assert formato.plural(3, "tarefa aberta") == "3 tarefas abertas"
