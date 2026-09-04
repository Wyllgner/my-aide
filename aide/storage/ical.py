"""Leitura de feed iCalendar (.ics).

Integração, não calendário próprio: o Google Calendar (e o Apple, e o Outlook)
publicam um endereço iCal secreto por agenda. Assinar esse endereço dá acesso
de leitura sem OAuth, sem app registrado e sem dependência nova.

Parser pequeno de propósito — VEVENT com DTSTART/DTEND/SUMMARY é tudo que
precisamos. Recorrência (RRULE) não é expandida; ver `LIMITACOES`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

LIMITACOES = (
    "eventos recorrentes (RRULE) aparecem só na primeira ocorrência; "
    "para o dia a dia isso basta, e evita reimplementar o iCalendar inteiro"
)

_DESDOBRA = re.compile(r"\r?\n[ \t]")
_DATA_HORA = "%Y%m%dT%H%M%S"
_DATA = "%Y%m%d"


def _desdobrar(texto: str) -> list[str]:
    """O iCal quebra linhas longas com espaço no começo da continuação."""
    return _DESDOBRA.sub("", texto).replace("\r\n", "\n").split("\n")


def _valor(linha: str) -> tuple[str, dict[str, str], str]:
    nome_bruto, _, valor = linha.partition(":")
    partes = nome_bruto.split(";")
    params = {}
    for p in partes[1:]:
        chave, _, v = p.partition("=")
        params[chave.upper()] = v
    return partes[0].upper(), params, valor


def _parse_data(valor: str, params: dict[str, str], tz: ZoneInfo) -> datetime | None:
    valor = valor.strip()
    try:
        if valor.endswith("Z"):
            return datetime.strptime(valor[:-1], _DATA_HORA).replace(
                tzinfo=ZoneInfo("UTC")).astimezone(tz)
        if params.get("VALUE") == "DATE" or len(valor) == 8:
            return datetime.strptime(valor, _DATA).replace(tzinfo=tz)
        fuso = ZoneInfo(params["TZID"]) if params.get("TZID") else tz
        return datetime.strptime(valor, _DATA_HORA).replace(tzinfo=fuso).astimezone(tz)
    except (ValueError, KeyError):
        return None


def _texto(valor: str) -> str:
    return (valor.replace(r"\,", ",").replace(r"\;", ";")
            .replace("\\n", " ").replace("\\N", " ").strip())


def parse(conteudo: str, timezone: str = "UTC") -> list[dict]:
    """Extrai os VEVENT do feed."""
    tz = ZoneInfo(timezone)
    eventos: list[dict] = []
    atual: dict | None = None

    for linha in _desdobrar(conteudo):
        if linha.startswith("BEGIN:VEVENT"):
            atual = {}
            continue
        if linha.startswith("END:VEVENT"):
            if atual and atual.get("start_at") and atual.get("title"):
                eventos.append(atual)
            atual = None
            continue
        if atual is None or ":" not in linha:
            continue

        nome, params, valor = _valor(linha)
        if nome == "SUMMARY":
            atual["title"] = _texto(valor)
        elif nome == "DTSTART":
            momento = _parse_data(valor, params, tz)
            if momento:
                atual["start_at"] = momento.isoformat(timespec="minutes")
                atual["dia_inteiro"] = params.get("VALUE") == "DATE"
        elif nome == "DTEND":
            momento = _parse_data(valor, params, tz)
            if momento:
                atual["end_at"] = momento.isoformat(timespec="minutes")
        elif nome == "LOCATION":
            atual["location"] = _texto(valor)
        elif nome == "UID":
            atual["external_id"] = valor.strip()

    return sorted(eventos, key=lambda e: e["start_at"])


def baixar(url: str, timeout: int = 30) -> str:
    import urllib.request

    if not url.startswith(("http://", "https://", "webcal://")):
        raise ValueError("o endereço do calendário precisa ser http(s) ou webcal")
    url = url.replace("webcal://", "https://", 1)

    req = urllib.request.Request(url, headers={"User-Agent": "my-aide/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resposta:
        return resposta.read().decode("utf-8", errors="replace")


def conflitos(eventos: list[dict]) -> list[tuple[dict, dict]]:
    """Pares que se sobrepõem no tempo. Evento de dia inteiro não conta."""
    marcados = [e for e in eventos if e.get("end_at") and not e.get("dia_inteiro")]
    achados = []
    for i, a in enumerate(marcados):
        for b in marcados[i + 1:]:
            if b["start_at"] < a["end_at"] and a["start_at"] < b["end_at"]:
                achados.append((a, b))
    return achados


def proximos(eventos: list[dict], agora: datetime, dias: int = 7) -> list[dict]:
    limite = (agora + timedelta(days=dias)).isoformat(timespec="minutes")
    agora_iso = agora.isoformat(timespec="minutes")
    return [e for e in eventos if agora_iso <= e["start_at"] <= limite]
