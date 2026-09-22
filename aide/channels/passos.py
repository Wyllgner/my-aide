"""O que o assessor está fazendo agora, em palavras.

Nasceu de uma reclamação concreta: você manda uma mensagem, o modelo pensa,
chama três tools, e no meio disso a tela não diz nada. Sem sinal, não há como
saber se deu erro, se está lento ou se a mensagem nem chegou, e a reação natural
é mandar de novo, que faz o assessor trabalhar duas vezes.

O texto é o mesmo em todo canal; o que muda é como cada um mostra: o terminal
gira um spinner, o Telegram mostra "digitando" e, se demorar muito, manda uma
linha dizendo em que passo está.
"""

from __future__ import annotations

# tool -> o que ela está fazendo, no gerúndio
FRASES = {
    "tasks.list": "olhando suas tarefas",
    "tasks.create": "criando a tarefa",
    "tasks.update": "ajustando a tarefa",
    "tasks.complete": "concluindo a tarefa",
    "tasks.snooze": "adiando a tarefa",
    "tasks.drop": "descartando a tarefa",
    "notes.search": "procurando nas suas notas",
    "notes.list": "olhando suas notas",
    "notes.read": "lendo a nota",
    "notes.create": "guardando a nota",
    "notes.append": "acrescentando à nota",
    "notes.delete": "apagando a nota",
    "memory.search": "procurando no que já guardei",
    "memory.list": "lembrando do que sei sobre você",
    "memory.save": "guardando isso sobre você",
    "memory.forget": "esquecendo isso",
    "expenses.add": "anotando o gasto",
    "expenses.list": "olhando os lançamentos",
    "expenses.summary": "somando os gastos",
    "expenses.delete": "apagando o gasto",
    "events.list": "olhando a agenda",
    "events.conflicts": "procurando choque de horário",
    "people.list": "vendo com quem você combinou de falar",
    "people.add": "registrando a pessoa",
    "people.touch": "marcando o contato",
    "people.update": "atualizando o combinado",
    "people.remove": "deixando de acompanhar",
    "reminders.create": "criando o lembrete",
    "reminders.list": "olhando seus lembretes",
    "reminders.cancel": "cancelando o lembrete",
    "work_orders.list": "olhando a fila de trabalho",
    "work_orders.create": "enfileirando o trabalho",
    "work_orders.claim": "assumindo o trabalho",
    "work_orders.complete": "fechando o trabalho",
    "work_orders.drop": "descartando o trabalho",
    "usage.cost": "somando o custo",
    "usage.set_balance": "anotando o saldo",
    "time.now": "vendo que dia é hoje",
}

PENSANDO = "pensando"


def descrever(nome: str) -> str:
    """Frase para uma tool, aceitando o `notes_delete` que o modelo devolve.

    Tool sem frase própria cai numa forma genérica em vez de sumir: um passo que
    não aparece é exatamente o silêncio que este módulo existe para tirar.
    """
    from aide.tools import alvo

    canonico = alvo.canonico(nome)
    if canonico in FRASES:
        return FRASES[canonico]
    familia = canonico.split(".")[0].replace("_", " ")
    return f"mexendo em {familia}" if familia else "trabalhando nisso"
