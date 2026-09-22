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

from aide.channels.formato import plural

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


Rule = Callable[..., list[Finding]]
_RULES: list[tuple[str, Rule]] = []


def rule(name: str) -> Callable[[Rule], Rule]:
    def decorator(fn: Rule) -> Rule:
        _RULES.append((name, fn))
        return fn

    return decorator


def _rows(conn, sql: str, params: tuple = ()) -> list:
    return conn.execute(sql, params).fetchall()


@rule("atrasadas")
def atrasadas(conn, now: datetime, config=None) -> list[Finding]:
    rows = _rows(
        conn,
        "SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
        " AND due_at IS NOT NULL AND due_at < ? ORDER BY due_at",
        (now.isoformat(timespec="minutes"),),
    )
    if not rows:
        return []

    # Diferença de datas, não de instantes: `timedelta.days` trunca, então um
    # prazo de anteontem às 23h virava "há 1 dia" — e a tabela de tarefas, que
    # compara datas, dizia "há 2 dias" sobre a mesma linha.
    dias = [(r, (now.date() - _no_fuso(r["due_at"], now).date()).days) for r in rows]
    return [
        Finding(
            rule="atrasadas",
            severity=1 if d >= 3 else 2,
            summary=f"#{r['id']} {r['title']} {_venceu(d)}",
            refs=[r["id"]],
        )
        for r, d in dias
    ]


def _no_fuso(iso: str, now: datetime) -> datetime:
    """Converte para o fuso de agora. `replace(tzinfo=...)` mentiria sobre o
    prazo gravado noutro fuso — e existem seis deles no banco, de quando a
    config dizia −03."""
    momento = datetime.fromisoformat(iso)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=now.tzinfo)
    return momento.astimezone(now.tzinfo)


def _venceu(dias: int) -> str:
    if dias <= 0:
        return "venceu hoje"
    if dias == 1:
        return "venceu ontem"
    return f"venceu há {dias} dias"


@rule("adiada_demais")
def adiada_demais(conn, now: datetime, config=None) -> list[Finding]:
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
def projeto_parado(conn, now: datetime, config=None) -> list[Finding]:
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
                    f"{PROJETO_PARADO_DIAS} dias ({plural(r['n'], 'tarefa aberta')})",
            refs=[],
        )
        for r in rows
    ]


@rule("zumbi")
def zumbi(conn, now: datetime, config=None) -> list[Finding]:
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
def contato_atrasado(conn, now: datetime, config=None) -> list[Finding]:
    rows = _rows(
        conn,
        "SELECT id, name, last_contact_at, cadence_days FROM people"
        " WHERE cadence_days IS NOT NULL AND last_contact_at IS NOT NULL",
    )
    achados = []
    for r in rows:
        dias = (now.date() - _no_fuso(r["last_contact_at"], now).date()).days
        if dias > r["cadence_days"]:
            achados.append(Finding(
                rule="contato_atrasado",
                severity=3,
                summary=f"faz {plural(dias, 'dia')} que você não fala com {r['name']}",
                refs=[r["id"]],
            ))
    return achados


# ---------- dinheiro ----------
#
# As duas regras abaixo são a primeira vez que o assessor olha gasto sozinho.
# Até aqui o dinheiro só respondia quando perguntado, o que faz dele um
# caderno; cobrar por condição é o que faz dele assessor.

# piso do gasto atípico: abaixo disto é ruído, e a conta de "3x a mediana"
# transforma um café caro em cobrança
PISO_ATIPICO_CENTAVOS = 5000
# quantos lançamentos são precisos para a mediana significar alguma coisa
AMOSTRA_MINIMA = 8
FATOR_ATIPICO = 3


@rule("orcamento_categoria")
def orcamento_categoria(conn, now: datetime, config=None) -> list[Finding]:
    """Categoria que passou (ou está perto de passar) do teto do mês.

    Sem teto declarado em `config.yaml` esta regra não diz nada: o assessor não
    tem opinião própria sobre quanto é muito, e inventar um número seria cobrar
    por um limite que você nunca combinou.

    O gasto privado entra na soma e nunca no texto. Somar é o que mantém o total
    verdadeiro; nomear entregaria pelo aviso o que a listagem esconde.
    """
    tetos = getattr(getattr(config, "gastos", None), "tetos_centavos", None)
    if not tetos:
        return []

    inicio = now.replace(day=1, hour=0, minute=0).isoformat(timespec="minutes")
    fim = now.isoformat(timespec="minutes")
    gasto = {
        (r["category"] or "").lower(): r["total"]
        for r in _rows(conn,
                       "SELECT lower(category) category, SUM(cents) total FROM expenses"
                       " WHERE deleted_at IS NULL AND spent_at BETWEEN ? AND ?"
                       " GROUP BY lower(category)", (inicio, fim))
    }

    avisar_em = getattr(config.gastos, "avisar_em", 0.8)
    achados = []
    for categoria, teto in sorted(tetos.items()):
        total = gasto.get(categoria, 0)
        if not teto or total < teto * avisar_em:
            continue
        fracao = total / teto
        if total > teto:
            # só o que passou é urgente. Conta fixa lançada no valor exato do
            # teto — aluguel de 700 com teto de 700 — não é notícia, e cobrar
            # "passou em R$ 0,00" todo mês ensinaria você a ignorar o aviso.
            severidade = 1
            recado = f" — passou em {_reais(total - teto)}"
        elif total == teto:
            severidade = 2
            recado = " — bateu o teto exato"
        else:
            severidade = 2
            recado = f" ({fracao * 100:.0f}% do teto, e o mês ainda não acabou)"

        achados.append(Finding(
            rule="orcamento_categoria",
            severity=severidade,
            summary=f"{categoria}: {_reais(total)} dos {_reais(teto)} do mês{recado}",
            refs=[],
        ))
    return achados


@rule("gasto_atipico")
def gasto_atipico(conn, now: datetime, config=None) -> list[Finding]:
    """Um lançamento muito acima do que você costuma gastar.

    Compara com a mediana dos últimos 90 dias, não com a média: uma compra
    grande puxa a média e esconde a seguinte. Exige amostra mínima e um piso em
    reais, senão nos primeiros dias de uso todo lançamento é atípico.

    Só olha os últimos 3 dias, porque cobrar hoje um gasto de três semanas atrás
    não deixa nada a decidir. E pula o que está marcado como privado: este aviso
    diz a descrição em voz alta, inclusive no Telegram.
    """
    historico = [r["cents"] for r in _rows(
        conn,
        "SELECT cents FROM expenses WHERE deleted_at IS NULL AND private = 0"
        " AND spent_at >= ? ORDER BY cents",
        ((now - timedelta(days=90)).isoformat(timespec="minutes"),),
    )]
    if len(historico) < AMOSTRA_MINIMA:
        return []

    mediana = historico[len(historico) // 2]
    limite = max(mediana * FATOR_ATIPICO, PISO_ATIPICO_CENTAVOS)

    recentes = _rows(
        conn,
        "SELECT id, cents, description, category, spent_at FROM expenses"
        " WHERE deleted_at IS NULL AND private = 0 AND spent_at >= ? AND cents > ?"
        " ORDER BY cents DESC",
        ((now - timedelta(days=3)).isoformat(timespec="minutes"), limite),
    )
    return [
        Finding(
            rule="gasto_atipico",
            severity=3,
            summary=(f"{_reais(r['cents'])} em {r['description']} é bem acima do seu "
                     f"normal ({_reais(mediana)} por lançamento)"),
            refs=[r["id"]],
        )
        for r in recentes
    ]


def _reais(centavos: int) -> str:
    """Mesmo formato do resto do controle de gastos, e a partir dos centavos
    inteiros: converter para float aqui traria de volta o erro que a tabela
    inteira existe para evitar."""
    from aide.tools.expenses import formatar

    return formatar(centavos)


def evaluate(conn, now: datetime, only: list[str] | None = None,
             config=None) -> list[Finding]:
    """Roda todas as regras. Uma regra quebrada não derruba as outras.

    `config` é opcional porque nem toda regra depende dela; a de orçamento
    depende, e sem config ela se cala em vez de inventar um teto.
    """
    achados: list[Finding] = []
    for name, fn in _RULES:
        if only and name not in only:
            continue
        try:
            achados.extend(fn(conn, now, config))
        except Exception:
            # uma regra quebrada não pode derrubar o daemon nem calar as outras
            log.exception("regra %s falhou", name)
    return sorted(achados, key=lambda f: f.severity)


def rule_names() -> list[str]:
    return [name for name, _ in _RULES]
