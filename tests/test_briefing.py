"""Briefings: o que o assessor manda sem você pedir.

A montagem é determinística. A estrutura sempre saiu de SQL; a LLM só
reescrevia aquilo em prosa, e no formato de lista não há prosa — então a
chamada por dia saiu de cena. Estes testes fixam isso: se alguém devolver a
LLM para cá, o teste do modelo intocado quebra.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from aide.channels.formato import para_terminal
from aide.llm.base import LLMProvider
from aide.scheduler import briefing

TZ = ZoneInfo("America/Porto_Velho")
AGORA = datetime(2026, 9, 3, 7, 30, tzinfo=TZ)


class LLMIntocada(LLMProvider):
    """Se o briefing a chamar, o teste quebra — e é para quebrar."""

    def complete(self, messages, *, fast=False, tools=None, purpose="chat", **extra):
        raise AssertionError("briefing não deve chamar a LLM: a montagem é determinística")


def gerar(ctx, tipo="manha", agora=AGORA):
    return briefing.gerar(ctx.conn, ctx.config, LLMIntocada(), agora, tipo)


def texto(resultado):
    return para_terminal(resultado.mensagem)


def test_briefing_nao_custa_chamada_de_llm(ctx, registry):
    """Roda três vezes por dia, todo dia. Sem prosa, não há o que pedir a ela."""
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-09-03T09:00"}, ctx)
    assert "Boleto" in texto(gerar(ctx))


def test_sem_dados_nao_manda_nada(ctx):
    assert gerar(ctx).vazio


def test_leva_os_dados_reais(ctx, registry):
    registry.call("tasks.create", {"title": "Boleto da internet",
                                   "due": "2026-09-03T09:00"}, ctx)
    saida = texto(gerar(ctx))
    assert "Boleto da internet" in saida
    assert "HOJE" in saida


def test_atrasada_aparece_com_ha_quantos_dias(ctx, registry):
    registry.call("tasks.create", {"title": "Velha", "due": "2026-08-20T09:00"}, ctx)
    saida = texto(gerar(ctx))
    assert "ATRASADAS" in saida
    assert "há 14 dias" in saida


def test_atrasada_eleva_a_urgencia(ctx, registry):
    registry.call("tasks.create", {"title": "Velha", "due": "2026-08-20T09:00"}, ctx)
    assert gerar(ctx).urgency == "critical"
    assert briefing.montar_manha(ctx.conn, AGORA).urgency == "critical"


def test_sem_atraso_a_urgencia_e_normal(ctx, registry):
    registry.call("tasks.create", {"title": "Hoje", "due": "2026-09-03T09:00"}, ctx)
    assert gerar(ctx).urgency == "normal"


def test_tarefa_privada_nao_entra_no_briefing(ctx, registry):
    """O briefing vai para o desktop e para o Telegram — privado não atravessa."""
    registry.call("tasks.create", {"title": "TERAPIA", "due": "2026-09-03T09:00",
                                   "private": True}, ctx)
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-09-03T09:00"}, ctx)
    saida = texto(gerar(ctx))
    assert "TERAPIA" not in saida
    assert "Boleto" in saida


def test_lista_longa_e_cortada(ctx, registry):
    """Uma mensagem com trinta linhas não é lida; ela é fechada."""
    # títulos distintos: "Tarefa 1" e "Tarefa 2" seriam barradas como duplicata
    for nome in ("Boleto", "Dentista", "Mercado", "Oficina", "Faxina",
                 "Contador", "Academia", "Passaporte", "Vacina", "Seguro"):
        registry.call("tasks.create", {"title": nome, "due": "2026-08-20T09:00"}, ctx)
    saida = texto(gerar(ctx))
    assert "e mais 4" in saida


def test_rodape_conta_o_que_importa(ctx, registry):
    registry.call("tasks.create", {"title": "Atrasada", "due": "2026-08-20T09:00"}, ctx)
    registry.call("tasks.create", {"title": "Hoje", "due": "2026-09-03T09:00"}, ctx)
    assert "1 atrasada · 1 para hoje" in texto(gerar(ctx))


def test_rodape_omite_o_que_e_zero(ctx, registry):
    registry.call("tasks.create", {"title": "Hoje", "due": "2026-09-03T09:00"}, ctx)
    rodape = gerar(ctx).mensagem.rodape
    assert rodape == "1 para hoje"


def test_noite_separa_feito_de_pendente(ctx, registry):
    feita = registry.call("tasks.create", {"title": "Feita", "due": "2026-09-03T09:00"}, ctx).data
    registry.call("tasks.complete", {"id": feita["id"]}, ctx)
    registry.call("tasks.create", {"title": "Pendente", "due": "2026-09-03T08:00"}, ctx)

    saida = texto(gerar(ctx, "noite", AGORA.replace(hour=21, minute=30)))
    assert "FEITO HOJE" in saida and "Feita" in saida
    assert "FICOU PARA TRÁS" in saida and "Pendente" in saida


def test_noite_mostra_o_de_amanha(ctx, registry):
    registry.call("tasks.create", {"title": "Dentista", "due": "2026-09-04T14:00"}, ctx)
    saida = texto(gerar(ctx, "noite", AGORA.replace(hour=21, minute=30)))
    assert "AMANHÃ" in saida
    assert "amanhã 14:00" in saida


def test_semanal_junta_o_que_pede_atencao(ctx, registry):
    registry.call("tasks.create", {"title": "Sem prazo"}, ctx)
    saida = texto(gerar(ctx, "semanal"))
    assert "ABERTAS SEM PRAZO" in saida
    assert "Sem prazo" in saida


def test_tipo_invalido_falha(ctx):
    try:
        gerar(ctx, "xpto")
    except ValueError as exc:
        assert "desconhecido" in str(exc)
    else:
        raise AssertionError("deveria ter falhado")


def test_titulo_de_cada_briefing(ctx, registry):
    registry.call("tasks.create", {"title": "X", "due": "2026-09-03T09:00"}, ctx)
    assert gerar(ctx, "manha").title == "Bom dia"
    assert gerar(ctx, "noite", AGORA.replace(hour=21)).title == "Fechando o dia"
    assert gerar(ctx, "semanal").title == "Revisão da semana"
