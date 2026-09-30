"""Controle de gastos.

Um lançamento é valor + descrição + quando. O resto — categoria, forma de
pagamento — é opcional, porque exigir classificação na hora de registrar é o
que faz as pessoas pararem de registrar. A forma que não foi dita é débito, e
`expenses.update` corrige depois.

O valor mora em centavos inteiros. Ver a migration 006.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from aide.core.context import now_in
from aide.tools.registry import ToolContext, registry

CAMPOS = "id, cents, description, category, spent_at, method"

# "10,50 almoço com a KA" — valor na frente, resto é descrição.
_LANCAMENTO = re.compile(r"^\s*(?:R\$\s*)?([\d.,]+)\s+(.*\S)\s*$", re.IGNORECASE)

# "10 reais almoço": a moeda dita em palavra fica entre o valor e a descrição,
# e sem tirá-la o almoço vira "reais almoço".
_MOEDA_ESCRITA = re.compile(r"^(?:reais?|conto?s?|pila|pau|mangos?|brl)\b[\s,]*",
                            re.IGNORECASE)


# O número, com os separadores que ele possa ter. Tudo em volta é palavra.
_NUMERO = re.compile(r"\d[\d.,]*")


def parse_valor(texto: str) -> int:
    """Texto em centavos. Aceita o jeito brasileiro e o jeito de máquina.

    Pega o número de dentro da frase em vez de exigir que ela seja só o
    número. A descrição da tool promete "o valor como a pessoa falou", e ela
    recusava "10 reais" — quebrando a própria promessa e obrigando a pessoa a
    repetir o valor num formato que o programa aceitasse.

    Uma frase com dois números é recusada de propósito: em "10 reais e 50
    centavos" adivinhar qual é o valor erraria calado, e num lançamento de
    dinheiro errar calado é o pior desfecho.

    A ambiguidade que sobra é uma: um ponto sozinho. Em "10.50" ele separa
    centavos, em "1.234" separa milhar. Decide pelo número de casas depois
    dele, que é como um humano lê.
    """
    bruto = str(texto).strip()
    if not bruto:
        raise ValueError("valor vazio")

    negativo = bruto.lstrip().startswith("-")
    achados = _NUMERO.findall(bruto)
    if not achados:
        raise ValueError(f"não achei nenhum valor em {texto!r}")
    if len(achados) > 1:
        raise ValueError(
            f"achei mais de um número em {texto!r}; diga só o valor, como \"10,50\"")

    limpo = achados[0]

    if "," in limpo and "." in limpo:
        # 1.234,56 — ponto é milhar, vírgula é decimal
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "," in limpo:
        limpo = limpo.replace(",", ".")
    elif limpo.count(".") == 1 and len(limpo.split(".")[1]) == 3:
        # 1.234 tem cara de milhar, não de 1 real e 234 centavos
        limpo = limpo.replace(".", "")

    if limpo.count(".") > 1:
        raise ValueError(f"não entendi o valor {texto!r}")

    try:
        reais = float(limpo)
    except ValueError as exc:
        raise ValueError(f"não entendi o valor {texto!r}") from exc

    if negativo or reais < 0:
        raise ValueError("gasto não é negativo; registre o valor gasto")
    # round e não int(): 19.99 * 100 dá 1998.9999... em binário
    return round(reais * 100)


def parse_lancamento(texto: str) -> tuple[int, str]:
    """"10,50 almoço com a KA" -> (1050, "almoço com a KA")."""
    casou = _LANCAMENTO.match(texto or "")
    if not casou:
        raise ValueError(
            f"não consegui separar valor e descrição em {texto!r}. "
            'Escreva o valor na frente, como "10,50 almoço com a KA".'
        )
    descricao = _MOEDA_ESCRITA.sub("", casou.group(2).strip()).strip()
    if not descricao:
        raise ValueError(
            f"faltou dizer o que foi o gasto em {texto!r}. "
            'Escreva assim: "10,50 almoço com a KA".'
        )
    return parse_valor(casou.group(1)), descricao


def formatar(cents: int) -> str:
    """1050 -> 'R$ 10,50'. 123456 -> 'R$ 1.234,56'."""
    sinal = "-" if cents < 0 else ""
    inteiro, centavos = divmod(abs(cents), 100)
    # o Python separa milhar com vírgula; trocar direto por ponto comeria
    # também a vírgula dos centavos, então o milhar passa por um marcador
    milhar = f"{inteiro:,}".replace(",", "\x00").replace("\x00", ".")
    return f"{sinal}R$ {milhar},{centavos:02d}"


# ---------- débito ou crédito ----------

FORMAS = ("debito", "credito")

# O jeito que a pessoa fala -> o que vai para o banco. Pix e dinheiro saem da
# conta na hora, então contam como débito.
_FORMAS_DITAS = {
    "debito": "debito", "débito": "debito", "pix": "debito", "dinheiro": "debito",
    "credito": "credito", "crédito": "credito", "cartao de credito": "credito",
    "cartão de crédito": "credito",
}


def normalizar_forma(texto: str | None) -> str:
    """"Crédito" -> "credito". Nada dito -> "debito"."""
    if texto is None or not str(texto).strip():
        return "debito"
    forma = _FORMAS_DITAS.get(str(texto).strip().lower())
    if forma is None:
        raise ValueError(f"forma de pagamento {texto!r} não existe; use débito ou crédito")
    return forma


def por_extenso(forma: str | None) -> str:
    return "crédito" if forma == "credito" else "débito"


# ---------- períodos ----------

PERIODOS = ("hoje", "ontem", "semana", "mes", "ano", "sempre")


def intervalo(periodo: str, agora: datetime) -> tuple[str, str]:
    """Começo e fim do período, em ISO local. `semana` começa na segunda."""
    inicio_do_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = agora.replace(hour=23, minute=59, second=59)

    if periodo == "hoje":
        inicio = inicio_do_dia
    elif periodo == "ontem":
        inicio = inicio_do_dia - timedelta(days=1)
        fim = inicio.replace(hour=23, minute=59, second=59)
    elif periodo == "semana":
        inicio = inicio_do_dia - timedelta(days=inicio_do_dia.weekday())
    elif periodo == "mes":
        inicio = inicio_do_dia.replace(day=1)
    elif periodo == "ano":
        inicio = inicio_do_dia.replace(month=1, day=1)
    elif periodo == "sempre":
        inicio = inicio_do_dia.replace(year=1970, month=1, day=1)
    else:
        raise ValueError(f"período desconhecido: {periodo!r}. Use: {', '.join(PERIODOS)}")

    return inicio.isoformat(timespec="minutes"), fim.isoformat(timespec="minutes")


def _linha(r) -> dict:
    dados = dict(r)
    dados["valor"] = formatar(dados["cents"])
    dados["method"] = dados["method"] or "debito"
    return dados


def _filtro_privado(ctx: ToolContext) -> str:
    return "" if ctx.ver_privado else " AND private = 0"


# ---------- tools ----------


@registry.register(
    name="expenses.add",
    description=(
        "Registra um gasto. Use sempre que a pessoa mencionar que gastou, "
        "pagou ou comprou algo com um valor — 'almocei 32 reais', "
        "'gastei 150 no mercado', '10,50 café'. Não crie tarefa para isso."
    ),
    parameters={
        "type": "object",
        "properties": {
            "amount": {
                "type": "string",
                "description": "Valor em reais, como a pessoa falou: '10,50', '32', 'R$ 1.234,56'.",
            },
            "description": {"type": "string", "description": "O que foi. Curto."},
            "category": {
                "type": "string",
                "description": (
                    "Opcional, minúsculo e curto: alimentação, transporte, mercado, "
                    "saúde, casa, lazer, assinatura. Deduza do que foi gasto."
                ),
            },
            "when": {"type": "string", "description": "ISO 8601. Padrão: agora."},
            "method": {
                "type": "string", "enum": list(FORMAS),
                "description": "debito ou credito. Se a pessoa não disse, deixe de fora: vira debito.",
            },
            "private": {"type": "boolean", "description": "Não sai desta máquina."},
        },
        "required": ["amount", "description"],
    },
)
def add(ctx: ToolContext, amount: str, description: str, category: str | None = None,
        when: str | None = None, method: str | None = None, private: bool = False) -> dict:
    cents = parse_valor(amount)
    if not description.strip():
        raise ValueError("todo gasto precisa de uma descrição")

    quando = when or now_in(ctx.config.timezone).isoformat(timespec="minutes")
    try:
        quando = datetime.fromisoformat(quando).isoformat(timespec="minutes")
    except ValueError as exc:
        raise ValueError(f"when precisa ser ISO 8601. Recebido: {when!r}") from exc

    cur = ctx.conn.execute(
        "INSERT INTO expenses (cents, description, category, spent_at, method, private)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (cents, description.strip(), (category or None) and category.strip().lower(),
         quando, normalizar_forma(method), int(private)),
    )
    return _linha(ctx.conn.execute(
        f"SELECT {CAMPOS} FROM expenses WHERE id = ?", (cur.lastrowid,)).fetchone())


@registry.register(
    name="expenses.list",
    description="Lista os gastos de um período, do mais recente para o mais antigo.",
    parameters={
        "type": "object",
        "properties": {
            "periodo": {"type": "string", "enum": list(PERIODOS),
                        "description": "Padrão: mes."},
            "category": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": [],
    },
)
def list_expenses(ctx: ToolContext, periodo: str = "mes", category: str | None = None,
                  limit: int = 50) -> list[dict]:
    de, ate = intervalo(periodo, now_in(ctx.config.timezone))
    sql = (f"SELECT {CAMPOS} FROM expenses WHERE deleted_at IS NULL"
           " AND spent_at BETWEEN ? AND ?" + _filtro_privado(ctx))
    params: list = [de, ate]
    if category:
        sql += " AND category = ?"
        params.append(category.strip().lower())
    sql += " ORDER BY spent_at DESC LIMIT ?"
    params.append(limit)
    return [_linha(r) for r in ctx.conn.execute(sql, params).fetchall()]


@registry.register(
    name="expenses.summary",
    description=(
        "Quanto foi gasto num período, com o total por categoria. É a tool para "
        "'quanto gastei esse mês', 'quanto foi de mercado', 'gastei muito hoje'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "periodo": {"type": "string", "enum": list(PERIODOS),
                        "description": "Padrão: mes."},
            "category": {"type": "string"},
        },
        "required": [],
    },
)
def summary(ctx: ToolContext, periodo: str = "mes", category: str | None = None) -> dict:
    de, ate = intervalo(periodo, now_in(ctx.config.timezone))
    onde = ("WHERE deleted_at IS NULL AND spent_at BETWEEN ? AND ?"
            + _filtro_privado(ctx))
    params: list = [de, ate]
    if category:
        onde += " AND category = ?"
        params.append(category.strip().lower())

    total, quantos = ctx.conn.execute(
        f"SELECT COALESCE(SUM(cents), 0), COUNT(*) FROM expenses {onde}", params
    ).fetchone()

    por_categoria = [
        {"category": r[0] or "sem categoria", "cents": r[1],
         "valor": formatar(r[1]), "quantos": r[2]}
        for r in ctx.conn.execute(
            f"SELECT category, SUM(cents), COUNT(*) FROM expenses {onde}"
            " GROUP BY category ORDER BY SUM(cents) DESC", params
        ).fetchall()
    ]

    # débito sempre aparece, mesmo zerado: é o que sai da conta este mês, e
    # "crédito R$ 300" sozinho não diz se o resto foi débito ou se não houve
    por_forma = {forma: 0 for forma in FORMAS}
    for forma, cents in ctx.conn.execute(
        f"SELECT COALESCE(method, 'debito'), SUM(cents) FROM expenses {onde}"
        " GROUP BY 1", params
    ).fetchall():
        por_forma[forma] = por_forma.get(forma, 0) + cents

    return {
        "periodo": periodo, "de": de, "ate": ate,
        "total_cents": total, "total": formatar(total), "quantos": quantos,
        "media": formatar(round(total / quantos)) if quantos else formatar(0),
        "por_categoria": por_categoria,
        "por_forma": [{"method": forma, "cents": cents, "valor": formatar(cents)}
                      for forma, cents in por_forma.items()],
    }


@registry.register(
    name="expenses.update",
    description=(
        "Corrige um gasto já lançado: débito virou crédito, valor errado, "
        "categoria trocada. Passe só o que muda."
    ),
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "method": {"type": "string", "enum": list(FORMAS)},
            "amount": {"type": "string", "description": "Novo valor, como a pessoa falou."},
            "description": {"type": "string"},
            "category": {"type": "string"},
            "when": {"type": "string", "description": "ISO 8601."},
        },
        "required": ["id"],
    },
)
def update(ctx: ToolContext, id: int, method: str | None = None, amount: str | None = None,
           description: str | None = None, category: str | None = None,
           when: str | None = None) -> dict:
    row = ctx.conn.execute(
        "SELECT private FROM expenses WHERE id = ? AND deleted_at IS NULL", (id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"gasto {id} não existe")
    if row["private"] and not ctx.ver_privado:
        raise ValueError(f"gasto {id} é privado; ele não sai desta máquina")

    sets, params = [], []
    if method is not None:
        sets.append("method = ?")
        params.append(normalizar_forma(method))
    if amount is not None:
        sets.append("cents = ?")
        params.append(parse_valor(amount))
    if description is not None:
        if not description.strip():
            raise ValueError("todo gasto precisa de uma descrição")
        sets.append("description = ?")
        params.append(description.strip())
    if category is not None:
        sets.append("category = ?")
        params.append(category.strip().lower() or None)
    if when is not None:
        try:
            quando = datetime.fromisoformat(when).isoformat(timespec="minutes")
        except ValueError as exc:
            raise ValueError(f"when precisa ser ISO 8601. Recebido: {when!r}") from exc
        sets.append("spent_at = ?")
        params.append(quando)

    if not sets:
        raise ValueError("nada para alterar")

    ctx.conn.execute(f"UPDATE expenses SET {', '.join(sets)} WHERE id = ?", (*params, id))
    return _linha(ctx.conn.execute(
        f"SELECT {CAMPOS} FROM expenses WHERE id = ?", (id,)).fetchone())


@registry.register(
    name="expenses.delete",
    description="Apaga um gasto lançado por engano.",
    parameters={"type": "object", "properties": {"id": {"type": "integer"}},
                "required": ["id"]},
    safety="confirm",
)
def delete(ctx: ToolContext, id: int) -> dict:
    row = ctx.conn.execute(
        f"SELECT {CAMPOS}, private FROM expenses WHERE id = ? AND deleted_at IS NULL", (id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"gasto {id} não existe")
    if row["private"] and not ctx.ver_privado:
        raise ValueError(f"gasto {id} é privado; ele não sai desta máquina")
    ctx.conn.execute("UPDATE expenses SET deleted_at = datetime('now') WHERE id = ?", (id,))
    # devolve o que era: com {"id": 8, "deleted": true} a única coisa que o
    # modelo podia repetir de volta era o número, e "apaguei o 8" não confirma
    # nada para quem pediu
    return {"id": id, "deleted": True, "description": row["description"],
            "valor": formatar(row["cents"]), "category": row["category"]}
