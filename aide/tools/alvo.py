"""O que vai ser apagado, em palavras.

Uma confirmação que diz `notes.delete {'id': 7}` não é uma confirmação: para
responder "sim" com consciência é preciso saber o que é o 7, e quem pergunta é
que tem o banco na mão. Sem isto a única forma de conferir era abrir outra tela
antes de responder, e a pressa é justamente o que faz alguém apagar a coisa
errada.

Duas decisões moram aqui:

**Descreve antes de executar.** Depois de apagada a linha some, e o relato
viraria "apaguei o 7".

**Privado é dito como privado.** A descrição vai para onde a pergunta foi feita,
e no Telegram isso é rede de terceiro: o título de uma nota marcada como privada
não pode aparecer ali só porque o modelo pediu para apagá-la. Quem não pode ver
privado recebe a forma ("uma nota marcada como privada"), que é o suficiente
para decidir, sem o conteúdo.
"""

from __future__ import annotations

# tool -> (tabela, coluna que descreve, artigo)
_ALVOS = {
    "tasks.drop": ("tasks", "title", "a tarefa"),
    "notes.delete": ("notes", "title", "a nota"),
    "expenses.delete": ("expenses", "description", "o gasto"),
    "work_orders.drop": ("work_orders", "goal", "a ordem"),
}

VERBOS = {
    "memory.forget": "esquecer",
    "people.remove": "parar de acompanhar",
}


def verbo(nome: str) -> str:
    return VERBOS.get(nome, "apagar")


def descrever(conn, nome: str, args: dict, ver_privado: bool = False) -> str:
    """Uma frase curta sobre o alvo, do jeito que se fala."""
    if nome == "memory.forget":
        return _memoria(conn, args, ver_privado)
    if nome == "people.remove":
        return f'{args.get("name", "")}'.strip() or nome

    alvo = _ALVOS.get(nome)
    identificador = args.get("id")
    if alvo is None or not isinstance(identificador, int):
        return _sem_alvo(nome, args)

    tabela, coluna, artigo = alvo
    tem_privado = _tem_coluna(conn, tabela, "private")
    colunas = f"{coluna} AS descricao" + (", private" if tem_privado else "")
    linha = conn.execute(
        # tabela e coluna vêm do mapa fixo acima, nunca do modelo; o id é
        # parametrizado, como todo valor no projeto
        f"SELECT {colunas} FROM {tabela} WHERE id = ?", (identificador,)
    ).fetchone()
    if linha is None:
        return f"{artigo} #{identificador} (que não existe mais)"

    if tem_privado and linha["private"] and not ver_privado:
        return f"{artigo} #{identificador}, marcada como privada"

    texto = f'{artigo} #{identificador} "{linha["descricao"]}"'
    if tabela == "expenses":
        return f"{texto} {_valor(conn, identificador)}".rstrip()
    return texto


def _memoria(conn, args: dict, ver_privado: bool) -> str:
    chave = str(args.get("key", "")).strip().lower().replace(" ", "_")
    tipo = args.get("kind", "profile")
    linhas = conn.execute(
        "SELECT value, private FROM memory WHERE kind = ? AND key = ?"
        " AND superseded_by IS NULL", (tipo, chave)).fetchall()
    if not linhas:
        return f"o que estava guardado em {chave} (não havia nada)"
    if any(r["private"] for r in linhas) and not ver_privado:
        return f"{chave} (marcado como privado)"
    return f'{chave}: "{linhas[0]["value"]}"' + (
        f" e mais {len(linhas) - 1}" if len(linhas) > 1 else "")


def _valor(conn, identificador: int) -> str:
    from aide.tools.expenses import formatar

    linha = conn.execute("SELECT cents FROM expenses WHERE id = ?", (identificador,)).fetchone()
    return f"({formatar(linha['cents'])})" if linha else ""


def _sem_alvo(nome: str, args: dict) -> str:
    """Tool nova marcada `confirm` sem entrada aqui: mostra o que dá, em vez de
    fingir que descreveu. Melhor cru do que silenciosamente errado."""
    if args:
        return f"{nome} {args}"
    return nome


def _tem_coluna(conn, tabela: str, coluna: str) -> bool:
    return any(r["name"] == coluna
               for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall())
