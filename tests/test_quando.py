"""Ler data escrita por gente, sem gastar API.

O que não casa volta None de propósito: adivinhar errado um horário é pior que
recusar, porque o lembrete que não chega só é notado quando já não serve.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from aide.core.quando import interpretar

TZ = ZoneInfo("America/Porto_Velho")
# segunda-feira, 21 de setembro de 2026, 14:00
AGORA = datetime(2026, 9, 21, 14, 0, tzinfo=TZ)


@pytest.mark.parametrize("texto,esperado", [
    ("20h", "2026-09-21 20:00"),
    ("20:00", "2026-09-21 20:00"),
    ("9h30", "2026-09-22 09:30"),          # 9h30 já passou hoje
    ("hoje 18h", "2026-09-21 18:00"),
    ("amanhã 9h", "2026-09-22 09:00"),
    ("amanha", "2026-09-22 09:00"),        # dia sem hora começa às 9
    ("depois de amanhã 7h", "2026-09-23 07:00"),
    ("quinta 20h", "2026-09-24 20:00"),
    ("segunda 8h", "2026-09-28 08:00"),    # hoje é segunda: a próxima
    ("25/09 10h", "2026-09-25 10:00"),
    ("25/09", "2026-09-25 09:00"),
    ("2026-12-31T23:30", "2026-12-31 23:30"),
])
def test_formas_que_se_digita_no_dia_a_dia(texto, esperado):
    assert interpretar(texto, AGORA).strftime("%Y-%m-%d %H:%M") == esperado


def test_hora_que_ja_passou_vira_amanha():
    """"me lembra às 8h" dito às 23h quer dizer amanhã, não um horário que foi."""
    noite = AGORA.replace(hour=23)
    assert interpretar("8h", noite).day == 22


def test_data_curta_ja_passada_e_do_ano_que_vem():
    dezembro = datetime(2026, 12, 10, 9, 0, tzinfo=TZ)
    assert interpretar("05/01 10h", dezembro).year == 2027


@pytest.mark.parametrize("texto", ["", "   ", "logo", "quando der", "35h", "99/99"])
def test_o_que_nao_reconhece_volta_none(texto):
    assert interpretar(texto, AGORA) is None


def test_resultado_nasce_com_fuso():
    """Sem fuso, a comparação com agora explode e o lembrete grava hora errada."""
    assert interpretar("20h", AGORA).tzinfo is not None
    assert interpretar("2026-12-31T23:30", AGORA).tzinfo is not None
