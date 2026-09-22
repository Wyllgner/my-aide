"""O que se repete, e quando volta.

Nasceu de um defeito: `tasks.create` aceitava `recurrence` como texto livre, o
schema sugeria "every weekday" ao modelo, o valor ia para o banco e **nada em
lugar nenhum lia de volta**. Concluir a tarefa do aluguel só a fechava, e a
próxima não aparecia. O erro não dava sinal: ele aparecia no mês em que a
cobrança não veio.

Por isso duas coisas moram aqui juntas: a lista fechada de regras que o projeto
entende, para nenhuma ponta gravar o que ninguém sabe ler, e o cálculo da
próxima ocorrência, que lembretes e tarefas passam a compartilhar.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta

REGRAS = ("daily", "weekdays", "weekly", "monthly", "yearly")

# Como se escreve por aqui. O modelo manda em inglês, você digita em português,
# e o banco guarda uma forma só.
SINONIMOS = {
    "diario": "daily", "diária": "daily", "diaria": "daily", "diariamente": "daily",
    "todo dia": "daily", "every day": "daily",
    "dias-uteis": "weekdays", "dias úteis": "weekdays", "dia de semana": "weekdays",
    "every weekday": "weekdays", "weekday": "weekdays",
    "semanal": "weekly", "semanalmente": "weekly", "toda semana": "weekly",
    "every week": "weekly",
    "mensal": "monthly", "mensalmente": "monthly", "todo mês": "monthly",
    "todo mes": "monthly", "every month": "monthly", "1st of month": "monthly",
    "anual": "yearly", "anualmente": "yearly", "todo ano": "yearly",
    "every year": "yearly",
}

EM_PORTUGUES = {"daily": "todo dia", "weekdays": "dias úteis", "weekly": "toda semana",
                "monthly": "todo mês", "yearly": "todo ano"}


def normalizar(regra: str | None) -> str | None:
    """Devolve a regra canônica, ou None se não for nenhuma conhecida.

    Recusar é de propósito: guardar "quando der" numa coluna de recorrência é
    prometer uma repetição que nunca vai acontecer.
    """
    if not regra:
        return None
    limpo = regra.strip().lower()
    if limpo in REGRAS:
        return limpo
    return SINONIMOS.get(limpo)


def por_extenso(regra: str | None) -> str:
    return EM_PORTUGUES.get(regra or "", regra or "")


def proxima(momento: datetime, regra: str) -> datetime:
    """A próxima ocorrência depois de `momento`, preservando a hora."""
    canonica = normalizar(regra)
    if canonica is None:
        raise ValueError(f"regra de repetição desconhecida: {regra}")

    if canonica == "daily":
        return momento + timedelta(days=1)
    if canonica == "weekdays":
        seguinte = momento + timedelta(days=1)
        while seguinte.weekday() >= 5:  # sábado e domingo
            seguinte += timedelta(days=1)
        return seguinte
    if canonica == "weekly":
        return momento + timedelta(weeks=1)
    if canonica == "monthly":
        mes = momento.month + 1
        ano = momento.year + (mes > 12)
        mes = 1 if mes > 12 else mes
        # dia 31 em mês curto cai para o último dia que existe, e o calendário
        # sabe qual é. A versão anterior descia de tentativa em tentativa com um
        # `range(dia, 27, -1)`, que sai vazio para todo dia menor que 28: era por
        # isso que o mensal do dia 10 voltava no dia 28, sem erro nenhum.
        ultimo = monthrange(ano, mes)[1]
        return momento.replace(year=ano, month=mes, day=min(momento.day, ultimo))
    try:
        return momento.replace(year=momento.year + 1)
    except ValueError:  # 29 de fevereiro
        return momento.replace(year=momento.year + 1, day=28)
