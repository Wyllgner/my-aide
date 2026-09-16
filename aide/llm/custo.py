"""Quanto o assessor custa, e quanto ainda cabe no mês.

Saldo da conta não entra aqui porque não dá: os endpoints de billing da OpenAI
exigem *session key* — a sessão do navegador — e recusam chave de API com 403.
O que existe é:

1. a estimativa local, dos tokens registrados em `llm_usage` vezes os preços do
   `config.yaml`. Funciona sempre e sem credencial nova;
2. o custo real, pela Admin API da OpenAI, que precisa de uma **chave de admin**
   com escopo `api.usage.read` (a chave normal não tem). Opcional.

"Quanto ainda tenho" só é respondível contra um orçamento que você define, e é
isso que `restante` faz.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

log = logging.getLogger(__name__)

URL_CUSTOS = "https://api.openai.com/v1/organization/costs"


@dataclass
class Ancora:
    """Um saldo lido no painel, com a data em que foi lido."""

    usd: float
    em: str


@dataclass
class Gasto:
    """Um período fechado. `real` só existe com chave de admin."""

    desde: str
    estimado_usd: float
    chamadas: int
    por_modelo: list[dict]
    sem_preco: list[str]
    real_usd: float | None = None
    erro_real: str | None = None


def estimar(conn, config, dias: int = 30) -> Gasto:
    linhas = conn.execute(
        "SELECT model, COUNT(*) n, SUM(input_tokens) i, SUM(output_tokens) o"
        f"  FROM llm_usage WHERE ts >= datetime('now','-{int(dias)} days')"
        " GROUP BY model ORDER BY i + o DESC"
    ).fetchall()

    total, chamadas, por_modelo, sem_preco = 0.0, 0, [], []
    for r in linhas:
        chamadas += r["n"]
        preco = config.llm.precos.get(r["model"])
        if preco:
            custo = (r["i"] / 1_000_000) * preco[0] + (r["o"] / 1_000_000) * preco[1]
            total += custo
        else:
            custo = None
            sem_preco.append(r["model"])
        por_modelo.append({"model": r["model"], "chamadas": r["n"],
                           "entrada": r["i"], "saida": r["o"], "usd": custo})

    return Gasto(desde=f"{dias} dias", estimado_usd=total, chamadas=chamadas,
                 por_modelo=por_modelo, sem_preco=sem_preco)


def mes_corrente(conn, config, agora: datetime) -> Gasto:
    """Do dia 1 até agora — é o recorte que a cobrança da OpenAI usa."""
    inicio = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    dias = (agora - inicio).days + 1
    gasto = estimar(conn, config, dias=dias)
    gasto.desde = inicio.strftime("%d/%m")
    return gasto


def restante(gasto: Gasto, orcamento: float | None) -> dict | None:
    """O mais perto de 'quanto ainda tenho' que dá para responder honestamente."""
    if not orcamento:
        return None
    usado = gasto.real_usd if gasto.real_usd is not None else gasto.estimado_usd
    sobra = orcamento - usado
    return {
        "orcamento": orcamento,
        "usado": usado,
        "sobra": sobra,
        "fracao": min(usado / orcamento, 1.0) if orcamento else 0.0,
        "estimado": gasto.real_usd is None,
    }


# ---------- custo real, via Admin API ----------


def custo_real(admin_key: str, desde: datetime, ate: datetime | None = None) -> float:
    """Soma os custos que a OpenAI de fato registrou no período.

    Precisa de chave de admin com escopo `api.usage.read`. A chave normal da
    API recebe 403 — não é o mesmo tipo de credencial.
    """
    params = f"?start_time={int(desde.astimezone(UTC).timestamp())}&limit=180"
    if ate:
        params += f"&end_time={int(ate.astimezone(UTC).timestamp())}"

    req = urllib.request.Request(
        URL_CUSTOS + params, headers={"Authorization": f"Bearer {admin_key}"})
    with urllib.request.urlopen(req, timeout=30) as resposta:
        dados = json.loads(resposta.read())

    total = 0.0
    for balde in dados.get("data", []):
        for item in balde.get("results", []):
            total += float((item.get("amount") or {}).get("value") or 0)
    return total


def com_custo_real(gasto: Gasto, config, desde: datetime) -> Gasto:
    """Acrescenta o número real ao estimado, se houver chave de admin.

    Falha em silêncio de propósito: o assessor não pode parar de responder
    quanto custa só porque a OpenAI está fora do ar ou a chave expirou.
    """
    chave = getattr(config.llm, "admin_key", None)
    if not chave:
        return gasto
    try:
        gasto.real_usd = custo_real(chave, desde)
    except urllib.error.HTTPError as exc:
        corpo = exc.read(300).decode(errors="replace")
        if "api.usage.read" in corpo:
            gasto.erro_real = "a chave de admin não tem o escopo api.usage.read"
        else:
            gasto.erro_real = f"a OpenAI recusou ({exc.code})"
        log.warning("custo real indisponível: %s", gasto.erro_real)
    except Exception as exc:  # nunca derrubar o relatório de custo
        gasto.erro_real = f"não consegui consultar ({type(exc).__name__})"
        log.warning("custo real indisponível", exc_info=True)
    return gasto


# ---------- saldo ancorado ----------


def anotar_saldo(conn, usd: float, quando: str, source: str = "manual") -> Ancora:
    """Guarda o saldo que você leu no painel. Em centavos, como todo dinheiro aqui."""
    if usd < 0:
        raise ValueError("saldo não é negativo")
    conn.execute(
        "INSERT INTO api_balance (cents, noted_at, source) VALUES (?, ?, ?)",
        (round(usd * 100), quando, source))
    return Ancora(usd=usd, em=quando)


def ultima_ancora(conn) -> Ancora | None:
    linha = conn.execute(
        "SELECT cents, noted_at FROM api_balance ORDER BY noted_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if linha is None:
        return None
    return Ancora(usd=linha["cents"] / 100, em=linha["noted_at"])


def gasto_desde(conn, config, desde: str) -> float:
    """Estimativa do que foi consumido depois da âncora."""
    linhas = conn.execute(
        "SELECT model, SUM(input_tokens) i, SUM(output_tokens) o FROM llm_usage"
        " WHERE ts >= ? GROUP BY model", (_para_utc_sqlite(desde),)).fetchall()
    total = 0.0
    for r in linhas:
        preco = config.llm.precos.get(r["model"])
        if preco:
            total += (r["i"] / 1_000_000) * preco[0] + (r["o"] / 1_000_000) * preco[1]
    return total


def _para_utc_sqlite(iso_local: str) -> str:
    """`llm_usage.ts` vem de datetime('now'): UTC, com espaço no lugar do T.

    Comparar com ISO local aqui daria o mesmo bug silencioso que o briefing da
    noite teve — texto, e " " ordena antes de "T".
    """
    momento = datetime.fromisoformat(iso_local)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def saldo_estimado(conn, config) -> dict | None:
    """Quanto deve restar: a última âncora menos o gasto desde ela.

    É estimativa, e o nome diz isso. Ela só é boa enquanto os preços do
    `config.yaml` estiverem certos e nada gastar a chave por fora — por isso o
    resultado carrega há quanto tempo a âncora foi feita, para você saber
    quando reancorar.
    """
    ancora = ultima_ancora(conn)
    if ancora is None:
        return None

    consumido = gasto_desde(conn, config, ancora.em)
    dias = max((datetime.now(UTC) - datetime.fromisoformat(ancora.em)
                .replace(tzinfo=datetime.fromisoformat(ancora.em).tzinfo or UTC)).days, 0)
    return {
        "ancora_usd": ancora.usd,
        "ancora_em": ancora.em,
        "dias_desde": dias,
        "gasto_desde": consumido,
        "saldo_usd": ancora.usd - consumido,
        "fracao_usada": min(consumido / ancora.usd, 1.0) if ancora.usd else 0.0,
    }
