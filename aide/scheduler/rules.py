"""Regras de condição: o que faz o assessor te procurar sem você pedir.

Cada regra é uma função determinística sobre o SQLite. Nenhuma LLM decide se
algo deve ser cobrado — ela só escreve a frase depois. É isso que separa este
projeto de um cron: um cron dispara por hora, isto dispara por estado.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

SNOOZE_LIMITE = 3
PROJETO_PARADO_DIAS = 14
ZUMBI_DIAS = 30


@dataclass
class Finding:
    """Algo que merece a sua atenção agora."""

    rule: str
    severity: int  # 1 alta, 2 média, 3 baixa
    summary: str
    refs: list[int]

    def __str__(self) -> str:
        return self.summary


Rule = Callable[[object, datetime], list[Finding]]
_RULES: list[tuple[str, Rule]] = []


def rule(name: str) -> Callable[[Rule], Rule]:
    def decorator(fn: Rule) -> Rule:
        _RULES.append((name, fn))
        return fn

    return decorator


def _rows(conn, sql: str, params: tuple = ()) -> list:
    return conn.execute(sql, params).fetchall()


@rule("atrasadas")
def atrasadas(conn, now: datetime) -> list[Finding]:
    rows = _rows(
        conn,
        "SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
        " AND due_at IS NOT NULL AND due_at < ? ORDER BY due_at",
        (now.isoformat(timespec="minutes"),),
    )
    if not rows:
        return []

    dias = [(r, (now - datetime.fromisoformat(r["due_at"]).replace(tzinfo=now.tzinfo)).days)
            for r in rows]
    return [
        Finding(
            rule="atrasadas",
            severity=1 if d >= 3 else 2,
            summary=f"#{r['id']} {r['title']} venceu há {d} dia(s)" if d
                    else f"#{r['id']} {r['title']} venceu hoje",
            refs=[r["id"]],
        )
        for r, d in dias
    ]


@rule("adiada_demais")
def adiada_demais(conn, now: datetime) -> list[Finding]:
    """Adiar três vezes é a tarefa dizendo que não vai acontecer."""
    rows = _rows(
        conn,
        "SELECT id, title, snooze_count FROM tasks WHERE deleted_at IS NULL"
        " AND status = 'open' AND snooze_count >= ? ORDER BY snooze_count DESC",
        (SNOOZE_LIMITE,),
    )
    return [
        Finding(
            rule="adiada_demais",
            severity=1,
            summary=f"#{r['id']} {r['title']} já foi adiada {r['snooze_count']}x "
                    "— ainda importa, ou descarta?",
            refs=[r["id"]],
        )
        for r in rows
    ]


@rule("projeto_parado")
def projeto_parado(conn, now: datetime) -> list[Finding]:
    limite = (now - timedelta(days=PROJETO_PARADO_DIAS)).isoformat(timespec="minutes")
    rows = _rows(
        conn,
        "SELECT project, COUNT(*) n, MAX(COALESCE(last_touched_at, created_at)) ultimo"
        "  FROM tasks WHERE deleted_at IS NULL AND status = 'open' AND project IS NOT NULL"
        " GROUP BY project HAVING ultimo < ?",
        (limite,),
    )
    return [
        Finding(
            rule="projeto_parado",
            severity=3,
            summary=f"projeto '{r['project']}' está parado há mais de "
                    f"{PROJETO_PARADO_DIAS} dias ({r['n']} tarefa(s) abertas)",
            refs=[],
        )
        for r in rows
    ]


@rule("zumbi")
def zumbi(conn, now: datetime) -> list[Finding]:
    """Criada faz tempo, sem prazo, nunca tocada. Provavelmente morreu."""
    limite = (now - timedelta(days=ZUMBI_DIAS)).isoformat(timespec="minutes")
    rows = _rows(
        conn,
        "SELECT id, title FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
        " AND due_at IS NULL AND created_at < ?"
        " AND COALESCE(last_touched_at, created_at) < ? ORDER BY created_at",
        (limite, limite),
    )
    return [
        Finding(
            rule="zumbi",
            severity=3,
            summary=f"#{r['id']} {r['title']} está parada há mais de {ZUMBI_DIAS} dias sem prazo",
            refs=[r["id"]],
        )
        for r in rows
    ]


@rule("contato_atrasado")
def contato_atrasado(conn, now: datetime) -> list[Finding]:
    rows = _rows(
        conn,
        "SELECT id, name, last_contact_at, cadence_days FROM people"
        " WHERE cadence_days IS NOT NULL AND last_contact_at IS NOT NULL",
    )
    achados = []
    for r in rows:
        ultimo = datetime.fromisoformat(r["last_contact_at"]).replace(tzinfo=now.tzinfo)
        dias = (now - ultimo).days
        if dias > r["cadence_days"]:
            achados.append(Finding(
                rule="contato_atrasado",
                severity=3,
                summary=f"faz {dias} dias que você não fala com {r['name']}",
                refs=[r["id"]],
            ))
    return achados


def evaluate(conn, now: datetime, only: list[str] | None = None) -> list[Finding]:
    """Roda todas as regras. Uma regra quebrada não derruba as outras."""
    achados: list[Finding] = []
    for name, fn in _RULES:
        if only and name not in only:
            continue
        try:
            achados.extend(fn(conn, now))
        except Exception:
            # uma regra quebrada não pode derrubar o daemon nem calar as outras
            log.exception("regra %s falhou", name)
    return sorted(achados, key=lambda f: f.severity)


def rule_names() -> list[str]:
    return [name for name, _ in _RULES]
