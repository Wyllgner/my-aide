"""Gasto recorrente: o que cai todo mês sem ninguém comprar de novo.

O cadastro gera lançamentos comuns em `expenses`, um por mês, com
`HORIZONTE_MESES` de antecedência. Assim o teto, o que está a cair e a tela de
um mês futuro contam a assinatura sem saber que ela existe. Ver a migration 016.
"""

from __future__ import annotations

import calendar
from datetime import datetime

from aide.core.context import now_in
from aide.tools.expenses import (
    FORMAS,
    formatar,
    ler_mes,
    normalizar_forma,
    parse_valor,
    resolver_categoria,
    tag_na_descricao,
)
from aide.tools.registry import ToolContext, registry

# o mês corrente e os 11 seguintes: dá para ver o ano que vem sem encher a busca
HORIZONTE_MESES = 12

# horário fixo: "dia 5" não diz a hora, e o lançamento precisa de uma
HORA_DO_LANCAMENTO = 9


def _mes_mais(mes: str, quantos: int) -> str:
    ano, numero = (int(x) for x in mes.split("-"))
    total = numero - 1 + quantos
    return f"{ano + total // 12:04d}-{total % 12 + 1:02d}"


def data_no_mes(mes: str, dia: int, agora: datetime) -> datetime:
    """Dia 31 em fevereiro cai no último dia dele, como a parcela."""
    ano, numero = (int(x) for x in mes.split("-"))
    return agora.replace(year=ano, month=numero, day=min(dia, calendar.monthrange(ano, numero)[1]),
                         hour=HORA_DO_LANCAMENTO, minute=0, second=0, microsecond=0)


def lancar_recorrentes(conn, agora: datetime) -> int:
    """Gera os meses que faltam até o horizonte. Chamar de novo não duplica nada,
    nem ressuscita o mês apagado: o índice único da migration cuida dos dois."""
    primeiro = agora.strftime("%Y-%m")
    gerados = 0
    for r in conn.execute("SELECT * FROM expense_recurring WHERE canceled_at IS NULL").fetchall():
        mes = r["start_month"]
        while mes <= _mes_mais(primeiro, HORIZONTE_MESES - 1):
            gerados += conn.execute(
                "INSERT OR IGNORE INTO expenses (cents, description, category, tag, spent_at,"
                " method, private, recurring_id, recurring_month)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["cents"], r["description"], r["category"], r["tag"],
                 data_no_mes(mes, r["day"], agora).isoformat(timespec="minutes"),
                 r["method"], r["private"], r["id"], mes)).rowcount
            mes = _mes_mais(mes, 1)
    return gerados


def _proxima(conn, recorrente_id: int, agora: datetime) -> str | None:
    linha = conn.execute(
        "SELECT MIN(spent_at) FROM expenses WHERE recurring_id = ? AND deleted_at IS NULL"
        " AND spent_at > ?", (recorrente_id, agora.isoformat(timespec="minutes"))).fetchone()
    return linha[0]


def _dados(conn, r, agora: datetime) -> dict:
    return {"id": r["id"], "description": r["description"], "valor": formatar(r["cents"]),
            "dia": r["day"], "category": r["category"], "tag": r["tag"],
            "method": r["method"], "desde": r["start_month"],
            "proxima": _proxima(conn, r["id"], agora)}


def _ativa(ctx: ToolContext, id: int):
    r = ctx.conn.execute("SELECT * FROM expense_recurring WHERE id = ? AND canceled_at IS NULL",
                         (id,)).fetchone()
    if r is None:
        raise ValueError(f"gasto recorrente {id} não existe")
    if r["private"] and not ctx.ver_privado:
        raise ValueError(f"gasto recorrente {id} é privado; ele não sai desta máquina")
    return r


def _dia(day) -> int:
    try:
        dia = int(day)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"dia {day!r} não é um número") from exc
    if not 1 <= dia <= 31:
        raise ValueError(f"o dia da cobrança vai de 1 a 31; recebido {dia}")
    return dia


@registry.register(
    name="expenses.add_recurring",
    description=(
        "Cadastra um gasto que cai todo mês: assinatura, conta fixa. 'o claude é "
        "110 todo dia 5'. Lança um gasto por mês, que consome o teto do mês em que "
        "cai. Para compra com número de vezes, use expenses.add com installments. "
        "Se a pessoa não disse o dia da cobrança, não chame ainda: pergunte."
    ),
    parameters={
        "type": "object",
        "properties": {
            "amount": {"type": "string", "description": "Valor de cada mês, como a pessoa falou."},
            "description": {"type": "string", "description": "O que é. Curto: 'claude', 'aluguel'."},
            "day": {"type": "integer", "description": "Dia da cobrança, de 1 a 31. Nunca chute."},
            "category": {"type": "string"},
            "tag": {"type": "string"},
            "method": {"type": "string", "enum": list(FORMAS)},
            "private": {"type": "boolean", "description": "Não sai desta máquina."},
            "start_month": {
                "type": "string",
                "description": ("AAAA-MM do primeiro lançamento. Padrão: o mês atual. Se o deste "
                                "mês já foi lançado à mão, use o mês seguinte."),
            },
        },
        "required": ["amount", "description", "day"],
    },
)
def add_recurring(ctx: ToolContext, amount: str, description: str, day: int,
                  category: str | None = None, tag: str | None = None,
                  method: str | None = None, private: bool = False,
                  start_month: str | None = None) -> dict:
    cents = parse_valor(amount)
    nome = description.strip()
    if not nome:
        raise ValueError("todo gasto recorrente precisa de uma descrição")
    if cents == 0:
        raise ValueError("gasto recorrente de R$ 0,00 não lança nada")
    dia = _dia(day)

    agora = now_in(ctx.config.timezone)
    inicio = ler_mes(start_month, agora)
    if inicio < agora.strftime("%Y-%m"):
        # os meses que passaram podem já ter sido lançados à mão, e gerá-los
        # contaria a mesma cobrança duas vezes sem ninguém perceber
        raise ValueError("o primeiro mês não pode ser passado; "
                         "lance os meses antigos com expenses.add")

    # só entre as que quem chama pode ver: a recusa não pode confirmar um privado
    filtro = "" if ctx.ver_privado else " AND private = 0"
    repetida = ctx.conn.execute(
        "SELECT id FROM expense_recurring WHERE canceled_at IS NULL AND lower(description) = ?"
        + filtro, (nome.lower(),)).fetchone()
    if repetida:
        raise ValueError(f"já existe o gasto recorrente {nome} (#{repetida['id']})")

    categoria, etiqueta = resolver_categoria(ctx.conn, category, tag)
    if etiqueta is None:
        etiqueta = tag_na_descricao(ctx.conn, categoria, nome)
    novo = ctx.conn.execute(
        "INSERT INTO expense_recurring (cents, description, category, tag, method, private,"
        " day, start_month) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (cents, nome, categoria, etiqueta, normalizar_forma(method), int(private), dia, inicio)
    ).lastrowid
    lancar_recorrentes(ctx.conn, agora)

    r = ctx.conn.execute("SELECT * FROM expense_recurring WHERE id = ?", (novo,)).fetchone()
    return _dados(ctx.conn, r, agora)


@registry.register(
    name="expenses.recurring",
    description="Os gastos que caem todo mês: 'quais minhas assinaturas', 'o que é fixo'.",
    parameters={"type": "object", "properties": {}, "required": []},
)
def list_recurring(ctx: ToolContext) -> list[dict]:
    agora = now_in(ctx.config.timezone)
    filtro = "" if ctx.ver_privado else " AND private = 0"
    return [_dados(ctx.conn, r, agora) for r in ctx.conn.execute(
        f"SELECT * FROM expense_recurring WHERE canceled_at IS NULL{filtro}"
        " ORDER BY day, id").fetchall()]


@registry.register(
    name="expenses.cancel_recurring",
    description=("Encerra um gasto recorrente: 'cancelei o claude'. Os meses que já caíram "
                 "ficam; os que estavam marcados para depois de hoje somem."),
    parameters={"type": "object", "properties": {"id": {"type": "integer"}},
                "required": ["id"]},
    safety="confirm",
)
def cancel_recurring(ctx: ToolContext, id: int) -> dict:
    r = _ativa(ctx, id)
    agora = now_in(ctx.config.timezone).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE expense_recurring SET canceled_at = datetime('now') WHERE id = ?",
                     (id,))
    removidos = ctx.conn.execute(
        "UPDATE expenses SET deleted_at = datetime('now') WHERE recurring_id = ?"
        " AND deleted_at IS NULL AND spent_at > ?", (id, agora)).rowcount
    return {"id": id, "description": r["description"], "canceled": True,
            "meses_removidos": removidos}


@registry.register(
    name="expenses.update_recurring",
    description=("Muda um gasto recorrente: 'o claude subiu pra 120', 'agora cai dia 10'. "
                 "Vale para os meses que ainda não caíram; os que já caíram ficam como "
                 "foram. Passe só o que muda."),
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "amount": {"type": "string", "description": "Novo valor, como a pessoa falou."},
            "description": {"type": "string"},
            "day": {"type": "integer", "description": "Novo dia da cobrança, de 1 a 31."},
            "category": {"type": "string"},
            "tag": {"type": "string", "description": "\"\" tira a tag."},
            "method": {"type": "string", "enum": list(FORMAS)},
        },
        "required": ["id"],
    },
)
def update_recurring(ctx: ToolContext, id: int, amount: str | None = None,
                     description: str | None = None, day: int | None = None,
                     category: str | None = None, tag: str | None = None,
                     method: str | None = None) -> dict:
    r = _ativa(ctx, id)
    mudancas: dict = {}
    if amount is not None:
        mudancas["cents"] = parse_valor(amount)
        if mudancas["cents"] == 0:
            raise ValueError("gasto recorrente de R$ 0,00 não lança nada; para encerrar, cancele")
    if description is not None:
        if not description.strip():
            raise ValueError("todo gasto recorrente precisa de uma descrição")
        mudancas["description"] = description.strip()
    if method is not None:
        mudancas["method"] = normalizar_forma(method)
    if category is not None or tag is not None:
        if tag is not None and not tag.strip():
            mudancas["category"] = (category.strip().lower() or None
                                    if category is not None else r["category"])
            mudancas["tag"] = None
        else:
            mudancas["category"], mudancas["tag"] = resolver_categoria(
                ctx.conn, category if category is not None else r["category"],
                tag if tag is not None else (None if category is not None else r["tag"]))
    novo_dia = _dia(day) if day is not None else None
    if not mudancas and novo_dia is None:
        raise ValueError("nada para alterar")

    agora = now_in(ctx.config.timezone)
    agora_iso = agora.isoformat(timespec="minutes")
    # os nomes vêm das chaves escritas acima, nunca de quem chamou
    if mudancas:
        trechos = ", ".join(f"{campo} = ?" for campo in mudancas)
        ctx.conn.execute(f"UPDATE expense_recurring SET {trechos} WHERE id = ?",
                         (*mudancas.values(), id))
        ctx.conn.execute(
            f"UPDATE expenses SET {trechos} WHERE recurring_id = ? AND deleted_at IS NULL"
            " AND spent_at > ?", (*mudancas.values(), id, agora_iso))
    if novo_dia is not None:
        ctx.conn.execute("UPDATE expense_recurring SET day = ? WHERE id = ?", (novo_dia, id))
        for linha in ctx.conn.execute(
                "SELECT id, recurring_month FROM expenses WHERE recurring_id = ?"
                " AND deleted_at IS NULL AND spent_at > ?", (id, agora_iso)).fetchall():
            ctx.conn.execute(
                "UPDATE expenses SET spent_at = ? WHERE id = ?",
                (data_no_mes(linha["recurring_month"], novo_dia, agora)
                 .isoformat(timespec="minutes"), linha["id"]))

    atual = ctx.conn.execute("SELECT * FROM expense_recurring WHERE id = ?", (id,)).fetchone()
    return _dados(ctx.conn, atual, agora)
