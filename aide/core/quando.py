"""Ler uma data escrita por gente, sem gastar API.

O modelo já sabe interpretar "quinta às 20h", mas fazê-lo no terminal custa uma
chamada, exige rede e demora. Para o punhado de formas que se digita no dia a
dia, uma tabela de casos resolve, e resolve igual todas as vezes.

Deliberadamente não tenta ser esperto: o que não casa volta como `None`, e quem
chamou diz o que aceita. Adivinhar errado um horário é pior do que recusar, já
que o lembrete que não chega só é notado quando já não serve.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

DIAS_DA_SEMANA = {
    "segunda": 0, "segunda-feira": 0, "seg": 0,
    "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1, "ter": 1,
    "quarta": 2, "quarta-feira": 2, "qua": 2,
    "quinta": 3, "quinta-feira": 3, "qui": 3,
    "sexta": 4, "sexta-feira": 4, "sex": 4,
    "sábado": 5, "sabado": 5, "sab": 5,
    "domingo": 6, "dom": 6,
}

# "20h", "20h30", "20:00", "9 h"
_HORA = re.compile(r"(?:^|\s)(\d{1,2})\s*(?:h|:)\s*(\d{2})?(?:\s|$)")
# "25/09", "25/09/2026", "25-09"
_DATA = re.compile(r"(?:^|\s)(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?:\s|$)")


def interpretar(texto: str, agora: datetime) -> datetime | None:
    """Devolve o momento que o texto descreve, ou None se não reconhecer.

    Aceita ISO ("2026-09-25T09:00"), hora sozinha ("20h", que é hoje se ainda
    não passou e amanhã se passou), dia relativo ("hoje", "amanhã", "depois de
    amanhã"), dia da semana ("quinta") e data curta ("25/09").
    """
    bruto = (texto or "").strip().lower()
    if not bruto:
        return None

    try:
        momento = datetime.fromisoformat(bruto)
    except ValueError:
        pass
    else:
        return momento if momento.tzinfo else momento.replace(tzinfo=agora.tzinfo)

    hora, minuto = _hora_em(bruto)
    dia = _dia_em(bruto, agora)

    if dia is None and hora is None:
        return None

    if dia is None:
        # hora sozinha: hoje, a não ser que já tenha passado. "me lembra às 8h"
        # dito às 23h quer dizer amanhã, não um horário que já foi.
        alvo = agora.replace(hour=hora, minute=minuto or 0, second=0, microsecond=0)
        return alvo if alvo > agora else alvo + timedelta(days=1)

    if hora is None:
        # dia sem hora: 9h é o começo do dia de quem tem compromisso, e é a
        # hora que o briefing da manhã já assume
        hora, minuto = 9, 0

    return dia.replace(hour=hora, minute=minuto or 0, second=0, microsecond=0)


def _hora_em(texto: str) -> tuple[int | None, int | None]:
    casou = _HORA.search(texto)
    if not casou:
        return None, None
    hora = int(casou.group(1))
    minuto = int(casou.group(2) or 0)
    if hora > 23 or minuto > 59:
        return None, None
    return hora, minuto


def _dia_em(texto: str, agora: datetime) -> datetime | None:
    if "depois de amanhã" in texto or "depois de amanha" in texto:
        return agora + timedelta(days=2)
    if "amanhã" in texto or "amanha" in texto:
        return agora + timedelta(days=1)
    if "hoje" in texto:
        return agora

    casou = _DATA.search(texto)
    if casou:
        dia, mes, ano = casou.group(1), casou.group(2), casou.group(3)
        try:
            alvo = agora.replace(day=int(dia), month=int(mes))
        except ValueError:
            return None
        if ano:
            alvo = alvo.replace(year=int(ano) + 2000 if len(ano) == 2 else int(ano))
        elif alvo.date() < agora.date():
            # "25/09" em dezembro é do ano que vem; ninguém agenda para trás
            alvo = alvo.replace(year=alvo.year + 1)
        return alvo

    for palavra, indice in DIAS_DA_SEMANA.items():
        if re.search(rf"(?:^|\s){re.escape(palavra)}(?:\s|$)", texto):
            adiante = (indice - agora.weekday()) % 7 or 7
            return agora + timedelta(days=adiante)
    return None
