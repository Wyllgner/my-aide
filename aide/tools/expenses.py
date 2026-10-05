"""Controle de gastos.

Um lançamento é valor + descrição + quando. O resto — categoria, forma de
pagamento — é opcional, porque exigir classificação na hora de registrar é o
que faz as pessoas pararem de registrar. A forma que não foi dita é débito, e
`expenses.update` corrige depois.

O valor mora em centavos inteiros. Ver a migration 006.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import datetime, timedelta

from aide.core.context import now_in
from aide.tools.registry import ToolContext, registry

CAMPOS = ("id, cents, description, category, tag, spent_at, method,"
          " installment_group, installment, installments")

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


# ---------- parcelas ----------

# Nenhuma loja parcela em mais que isso; um número maior é engano de digitação
# ou de leitura, e lançaria anos de parcelas de uma vez.
MAX_PARCELAS = 48


def somar_meses(quando: datetime, meses: int) -> datetime:
    """31/01 + 1 mês = 28/02 (ou 29): a parcela cai no último dia do mês curto."""
    total = quando.month - 1 + meses
    ano, mes = quando.year + total // 12, total % 12 + 1
    dia = min(quando.day, calendar.monthrange(ano, mes)[1])
    return quando.replace(year=ano, month=mes, day=dia)


def dividir(cents: int, parcelas: int) -> list[int]:
    """1000 em 3 -> [334, 333, 333]. A sobra vai na primeira, como na fatura."""
    base, sobra = divmod(cents, parcelas)
    return [base + sobra] + [base] * (parcelas - 1)


def _parcelas(installments) -> int:
    try:
        n = int(installments)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"quantidade de parcelas {installments!r} não é um número") from exc
    if n < 1 or n > MAX_PARCELAS:
        raise ValueError(f"parcelas vai de 1 a {MAX_PARCELAS}; recebido {n}")
    return n


# ---------- tetos ----------


def tetos_em_vigor(conn, config) -> dict[str, int]:
    """Teto de cada categoria, em centavos: o config, com o que foi mudado por cima.

    Todo lugar que olha teto — a cobrança, a página, o prompt, a tool — passa
    por aqui, senão o teto mudado pelo Telegram valeria numa tela e não na outra.
    """
    tetos = dict(getattr(getattr(config, "gastos", None), "tetos_centavos", None) or {})
    if conn is None:
        return tetos
    for r in conn.execute("SELECT category, cents FROM expense_caps").fetchall():
        if r[1] is None:
            tetos.pop(r[0], None)
        else:
            tetos[r[0]] = r[1]
    return tetos


# ---------- tags ----------


def _chave(texto: str) -> str:
    """"Farmácia" -> "farmacia". A tag é achada do jeito que for escrita."""
    sem_acento = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def tags_em_vigor(conn) -> dict[str, tuple[str, str]]:
    """chave -> (tag como foi escrita, categoria a que pertence)."""
    if conn is None:
        return {}
    return {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT key, tag, category FROM expense_tags ORDER BY category, tag").fetchall()}


def resolver_categoria(conn, category: str | None, tag: str | None) -> tuple[str | None, str | None]:
    """Categoria e tag de um lançamento, com a tag puxando a categoria dela.

    Quem decide a categoria de uma tag conhecida é o cadastro, não o modelo: se
    ele mandar "farmácia" como categoria, ou "farmácia" com categoria "saúde",
    o gasto vai para `pessoal` do mesmo jeito. Senão o teto de pessoal ficaria
    furado sempre que o modelo errasse a dedução.
    """
    categoria = (category or "").strip().lower() or None
    tags = tags_em_vigor(conn)

    if tag and tag.strip():
        conhecida = tags.get(_chave(tag))
        if conhecida:
            return conhecida[1], conhecida[0]
        # tag solta, sem cadastro: vale como etiqueta, sem mexer na categoria
        return categoria, tag.strip().lower()

    if categoria and _chave(categoria) in tags:
        nome, mae = tags[_chave(categoria)]
        return mae, nome
    return categoria, None


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
    if dados.get("installments"):
        dados["parcela"] = f'{dados["installment"]}/{dados["installments"]}'
    else:
        for chave in ("installment_group", "installment", "installments"):
            dados.pop(chave, None)
    return dados


def _filtro_privado(ctx: ToolContext) -> str:
    return "" if ctx.ver_privado else " AND private = 0"


# ---------- tools ----------


@registry.register(
    name="expenses.add",
    description=(
        "Registra um gasto. Use sempre que a pessoa mencionar que gastou, "
        "pagou ou comprou algo com um valor — 'almocei 32 reais', "
        "'gastei 150 no mercado', '10,50 café'. Não crie tarefa para isso. "
        "Compra parcelada vira uma parcela por mês, cada uma no mês em que cai. "
        "Se a pessoa disse que parcelou mas não disse em quantas vezes, não "
        "chame ainda: pergunte em quantas parcelas foi."
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
            "tag": {
                "type": "string",
                "description": (
                    "Opcional: de onde foi, dentro da categoria (farmácia, lanche). Se a "
                    "tag estiver cadastrada, a categoria dela é posta sozinha."
                ),
            },
            "when": {"type": "string", "description": "ISO 8601. Padrão: agora."},
            "method": {
                "type": "string", "enum": list(FORMAS),
                "description": "debito ou credito. Se a pessoa não disse, deixe de fora: vira debito.",
            },
            "private": {"type": "boolean", "description": "Não sai desta máquina."},
            "in_installments": {
                "type": "boolean",
                "description": "true quando a pessoa disse que foi parcelado, mesmo sem dizer em quantas vezes.",
            },
            "installments": {
                "type": "integer",
                "description": "Em quantas parcelas: '10x' -> 10. Só o que a pessoa disse; nunca chute.",
            },
            "amount_is_installment": {
                "type": "boolean",
                "description": (
                    "true quando o valor dito é o de cada parcela ('10x de 50'); "
                    "false ou ausente quando é o total da compra ('500 em 10x')."
                ),
            },
        },
        "required": ["amount", "description"],
    },
)
def add(ctx: ToolContext, amount: str, description: str, category: str | None = None,
        when: str | None = None, method: str | None = None, private: bool = False,
        tag: str | None = None, in_installments: bool = False,
        installments: int | None = None, amount_is_installment: bool = False) -> dict:
    cents = parse_valor(amount)
    if not description.strip():
        raise ValueError("todo gasto precisa de uma descrição")

    quando = when or now_in(ctx.config.timezone).isoformat(timespec="minutes")
    try:
        inicio = datetime.fromisoformat(quando)
    except ValueError as exc:
        raise ValueError(f"when precisa ser ISO 8601. Recebido: {when!r}") from exc

    if installments is None and (in_installments or amount_is_installment):
        # lançar à vista o que foi parcelado poria a compra inteira num mês só;
        # o erro volta para o modelo, que pergunta em vez de chutar
        raise ValueError("foi parcelado, mas não sei em quantas vezes; "
                         "pergunte à pessoa em quantas parcelas foi antes de lançar")
    parcelas = _parcelas(installments) if installments is not None else 1

    categoria, etiqueta = resolver_categoria(ctx.conn, category, tag)
    # parcelado sem forma dita é crédito: débito não parcela
    forma = normalizar_forma(method if method or parcelas == 1 else "credito")
    valores = [cents] * parcelas if amount_is_installment else dividir(cents, parcelas)

    ids = []
    for n, valor in enumerate(valores, start=1):
        cur = ctx.conn.execute(
            "INSERT INTO expenses (cents, description, category, tag, spent_at, method,"
            " private, installment_group, installment, installments)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (valor, description.strip(), categoria, etiqueta,
             somar_meses(inicio, n - 1).isoformat(timespec="minutes"), forma, int(private),
             ids[0] if ids else None, n if parcelas > 1 else None,
             parcelas if parcelas > 1 else None),
        )
        ids.append(cur.lastrowid)
    if parcelas > 1:
        # a primeira não sabia o próprio id antes de existir
        ctx.conn.execute("UPDATE expenses SET installment_group = ? WHERE id = ?",
                         (ids[0], ids[0]))

    primeira = _linha(ctx.conn.execute(
        f"SELECT {CAMPOS} FROM expenses WHERE id = ?", (ids[0],)).fetchone())
    if parcelas > 1:
        total = sum(valores)
        primeira["total"] = formatar(total)
        primeira["ultima_parcela"] = somar_meses(inicio, parcelas - 1).strftime("%m/%Y")
    return primeira


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

    por_tag: dict[str | None, list[dict]] = {}
    for r in ctx.conn.execute(
        f"SELECT category, tag, SUM(cents) FROM expenses {onde} AND tag IS NOT NULL"
        " GROUP BY category, tag ORDER BY SUM(cents) DESC", params
    ).fetchall():
        por_tag.setdefault(r[0], []).append({"tag": r[1], "cents": r[2], "valor": formatar(r[2])})

    por_categoria = [
        {"category": r[0] or "sem categoria", "cents": r[1],
         "valor": formatar(r[1]), "quantos": r[2], "tags": por_tag.get(r[0], [])}
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
    name="expenses.budgets",
    description=(
        "Os tetos de gasto por categoria que a pessoa declarou, com quanto já foi "
        "usado no mês e quanto sobra. É a tool para 'quais meus limites', 'quanto "
        "posso gastar de uber', 'estourei algum teto'."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def budgets(ctx: ToolContext) -> dict:
    # a mesma conta da página e da cobrança: as três precisam dizer o mesmo
    # número. Sem esta tool o modelo só via o gasto, e respondia "você não
    # definiu limites" com os tetos declarados no config.
    from aide.web.consultas import tetos_do_mes

    linhas = tetos_do_mes(ctx.conn, ctx.config, now_in(ctx.config.timezone))
    if not linhas:
        return {"tetos": [], "aviso": "nenhum teto declarado; defina com expenses.set_budget"}
    return {"tetos": [
        {"categoria": linha["categoria"], "teto": formatar(linha["teto"]),
         "gasto": formatar(linha["gasto"]), "sobra": formatar(linha["teto"] - linha["gasto"]),
         "usado": f'{linha["gasto"] / linha["teto"] * 100:.0f}%' if linha["teto"] else "—"}
        for linha in linhas
    ]}


@registry.register(
    name="expenses.set_budget",
    description=(
        "Define, muda ou tira o teto mensal de uma categoria. 'aumenta o uber pra "
        "80', 'põe teto de 300 em mercado', 'tira o teto de dates'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "Minúsculo, como nos gastos."},
            "amount": {"type": "string", "description": "Novo teto por mês, como a pessoa falou."},
            "remove": {"type": "boolean", "description": "true para tirar o teto."},
        },
        "required": ["category"],
    },
)
def set_budget(ctx: ToolContext, category: str, amount: str | None = None,
               remove: bool = False) -> dict:
    categoria = category.strip().lower()
    if not categoria:
        raise ValueError("diga de qual categoria é o teto")
    antes = tetos_em_vigor(ctx.conn, ctx.config).get(categoria)

    if remove:
        if antes is None:
            raise ValueError(f"{categoria} não tem teto")
        cents = None
    else:
        if amount is None:
            raise ValueError("diga o valor do teto, ou remove=true para tirá-lo")
        cents = parse_valor(amount)
        if cents == 0:
            raise ValueError("teto zero cobraria qualquer gasto; para tirar o teto, use remove")

    ctx.conn.execute(
        "INSERT INTO expense_caps (category, cents) VALUES (?, ?)"
        " ON CONFLICT (category) DO UPDATE SET cents = excluded.cents,"
        " updated_at = datetime('now')", (categoria, cents))
    return {"categoria": categoria,
            "antes": formatar(antes) if antes is not None else "sem teto",
            "agora": formatar(cents) if cents is not None else "sem teto"}


@registry.register(
    name="expenses.add_tag",
    description=(
        "Cadastra uma tag dentro de uma categoria: 'cria a tag farmácia em pessoal'. "
        "Daí em diante '10 em farmácia' vai para pessoal com a tag farmácia, e "
        "consome o teto de pessoal. Cadastrar de novo muda a categoria da tag."
    ),
    parameters={
        "type": "object",
        "properties": {
            "tag": {"type": "string"},
            "category": {"type": "string", "description": "A categoria que ela consome."},
        },
        "required": ["tag", "category"],
    },
)
def add_tag(ctx: ToolContext, tag: str, category: str) -> dict:
    nome, categoria = tag.strip().lower(), category.strip().lower()
    if not nome or not categoria:
        raise ValueError("diga a tag e a categoria dela, como: farmácia em pessoal")
    if _chave(nome) == _chave(categoria):
        raise ValueError("a tag não pode ter o mesmo nome da categoria")
    if _chave(categoria) in tags_em_vigor(ctx.conn):
        raise ValueError(f"{categoria} já é uma tag; tag dentro de tag não soma em teto nenhum")
    antes = tags_em_vigor(ctx.conn).get(_chave(nome))
    ctx.conn.execute(
        "INSERT INTO expense_tags (key, tag, category) VALUES (?, ?, ?)"
        " ON CONFLICT (key) DO UPDATE SET tag = excluded.tag, category = excluded.category",
        (_chave(nome), nome, categoria))
    resposta = {"tag": nome, "category": categoria}
    if antes and antes[1] != categoria:
        # os gastos antigos ficam na categoria de antes: foram contados naquele
        # teto, e mudá-los agora reescreveria um mês que já fechou
        resposta["antes"] = antes[1]
    return resposta


@registry.register(
    name="expenses.tags",
    description="As tags cadastradas, agrupadas pela categoria que cada uma consome.",
    parameters={"type": "object", "properties": {}, "required": []},
)
def list_tags(ctx: ToolContext) -> dict:
    grupos: dict[str, list[str]] = {}
    for nome, categoria in tags_em_vigor(ctx.conn).values():
        grupos.setdefault(categoria, []).append(nome)
    return {"por_categoria": grupos}


@registry.register(
    name="expenses.remove_tag",
    description=("Descadastra uma tag. Os gastos que já têm a tag continuam com ela; "
                 "só os novos deixam de ir sozinhos para a categoria."),
    parameters={"type": "object", "properties": {"tag": {"type": "string"}},
                "required": ["tag"]},
)
def remove_tag(ctx: ToolContext, tag: str) -> dict:
    conhecida = tags_em_vigor(ctx.conn).get(_chave(tag))
    if conhecida is None:
        raise ValueError(f"a tag {tag!r} não está cadastrada")
    ctx.conn.execute("DELETE FROM expense_tags WHERE key = ?", (_chave(tag),))
    return {"tag": conhecida[0], "category": conhecida[1], "removida": True}


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
            "tag": {"type": "string", "description": "\"\" tira a tag."},
            "when": {"type": "string", "description": "ISO 8601."},
        },
        "required": ["id"],
    },
)
def update(ctx: ToolContext, id: int, method: str | None = None, amount: str | None = None,
           description: str | None = None, category: str | None = None,
           when: str | None = None, tag: str | None = None) -> dict:
    row = ctx.conn.execute(
        "SELECT private, category, tag FROM expenses WHERE id = ? AND deleted_at IS NULL", (id,)
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
    if category is not None or tag is not None:
        if tag is not None and not tag.strip():
            # tirar a tag deixa a categoria onde está
            categoria, etiqueta = (category.strip().lower() or None
                                   if category is not None else row["category"]), None
        else:
            categoria, etiqueta = resolver_categoria(
                ctx.conn,
                category if category is not None else row["category"],
                tag if tag is not None else (None if category is not None else row["tag"]))
        sets += ["category = ?", "tag = ?"]
        params += [categoria, etiqueta]
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
    description=("Apaga um gasto lançado por engano. Numa compra parcelada, "
                 "apaga todas as parcelas dela."),
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
    grupo = row["installment_group"]
    if grupo:
        # parcela não se apaga sozinha: a compra lançada por engano é a compra
        # inteira, e sobrar 9 de 10 parcelas é pior que não ter nenhuma
        apagadas = ctx.conn.execute(
            "UPDATE expenses SET deleted_at = datetime('now')"
            " WHERE installment_group = ? AND deleted_at IS NULL", (grupo,)).rowcount
        return {"id": id, "deleted": True, "description": row["description"],
                "valor": formatar(row["cents"]), "category": row["category"],
                "parcelas_apagadas": apagadas}
    ctx.conn.execute("UPDATE expenses SET deleted_at = datetime('now') WHERE id = ?", (id,))
    # devolve o que era: com {"id": 8, "deleted": true} a única coisa que o
    # modelo podia repetir de volta era o número, e "apaguei o 8" não confirma
    # nada para quem pediu
    return {"id": id, "deleted": True, "description": row["description"],
            "valor": formatar(row["cents"]), "category": row["category"]}
