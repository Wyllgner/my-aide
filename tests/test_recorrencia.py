"""O que se repete, e quando volta.

O defeito de origem: `recurrence` era aceito, guardado e nunca lido. Concluir a
tarefa do aluguel só a fechava, e a falta aparecia no mês em que a cobrança não
veio. Estes testes existem para que isso não volte calado.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aide.core import recorrencia

TZ = ZoneInfo("America/Porto_Velho")


def _em(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=TZ)


@pytest.mark.parametrize("regra,de,para", [
    ("daily", "2026-09-21T09:00", "2026-09-22T09:00"),
    ("weekly", "2026-09-21T09:00", "2026-09-28T09:00"),
    ("monthly", "2026-10-10T09:00", "2026-11-10T09:00"),
    ("yearly", "2026-09-21T09:00", "2027-09-21T09:00"),
    # sexta pula o fim de semana
    ("weekdays", "2026-09-25T09:00", "2026-09-28T09:00"),
    ("weekdays", "2026-09-21T09:00", "2026-09-22T09:00"),
])
def test_proxima_ocorrencia(regra, de, para):
    assert recorrencia.proxima(_em(de), regra) == _em(para)


@pytest.mark.parametrize("de,para", [
    ("2026-01-31T09:00", "2026-02-28T09:00"),   # mês curto: cai no último dia
    ("2026-03-31T09:00", "2026-04-30T09:00"),
    ("2028-01-31T09:00", "2028-02-29T09:00"),   # ano bissexto
    ("2026-12-15T09:00", "2027-01-15T09:00"),   # vira o ano
])
def test_mensal_respeita_o_tamanho_do_mes(de, para):
    """O código antigo descia num `range(dia, 27, -1)`, vazio para todo dia menor
    que 28: o mensal do dia 10 voltava no dia 28, sem erro nenhum."""
    assert recorrencia.proxima(_em(de), "monthly") == _em(para)


def test_mensal_do_dia_10_volta_no_dia_10():
    assert recorrencia.proxima(_em("2026-10-10T09:00"), "monthly").day == 10


@pytest.mark.parametrize("escrito,canonico", [
    ("todo mês", "monthly"), ("mensal", "monthly"), ("1st of month", "monthly"),
    ("todo dia", "daily"), ("diario", "daily"), ("every day", "daily"),
    ("dias úteis", "weekdays"), ("every weekday", "weekdays"),
    ("toda semana", "weekly"), ("todo ano", "yearly"),
    ("MENSAL", "monthly"), ("  monthly  ", "monthly"),
])
def test_aceita_como_se_escreve_de_um_lado_e_do_outro(escrito, canonico):
    """O modelo manda em inglês, você digita em português, o banco guarda um só."""
    assert recorrencia.normalizar(escrito) == canonico


@pytest.mark.parametrize("texto", ["", None, "quando der", "de vez em quando", "every fortnight"])
def test_o_que_nao_conhece_nao_e_guardado(texto):
    """Guardar "quando der" numa coluna de recorrência é prometer uma repetição
    que nunca vai acontecer."""
    assert recorrencia.normalizar(texto) is None


def test_regra_desconhecida_levanta_em_vez_de_chutar():
    with pytest.raises(ValueError, match="desconhecida"):
        recorrencia.proxima(_em("2026-09-21T09:00"), "quando der")
