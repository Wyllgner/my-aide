"""O que o assessor está fazendo agora, em palavras.

Nasceu de uma reclamação concreta: você manda uma mensagem, o modelo pensa,
chama três tools, e no meio disso a tela não diz nada. Sem sinal, não há como
saber se deu erro, se está lento ou se a mensagem nem chegou, e a reação natural
é mandar de novo, que faz o assessor trabalhar duas vezes.

Cada passo tem **duas** formas, porque a lista do Telegram mostra as duas ao
mesmo tempo: o que está acontecendo agora ("vendo o que você tem pra hoje") e o
que já terminou ("vi o que você tem pra hoje"). Sem o passado, um passo concluído
continuaria escrito como se estivesse em andamento.

As frases dizem o assunto por extenso, e não o nome da tool: quem lê não tem por
que saber que existe uma `tasks.list`. Decisão do dono, depois de ver a primeira
versão: "olhando suas tarefas" era curto mas seco, e a lista parecia log.
"""

from __future__ import annotations

# tool -> (o que está fazendo, o que já fez)
FRASES = {
    "tasks.list": ("vendo o que você tem pra hoje", "vi o que você tem pra hoje"),
    "tasks.create": ("criando a tarefa", "criei a tarefa"),
    "tasks.update": ("mudando a tarefa", "mudei a tarefa"),
    "tasks.complete": ("marcando como concluída", "marquei como concluída"),
    "tasks.snooze": ("adiando a tarefa", "adiei a tarefa"),
    "tasks.drop": ("descartando a tarefa", "descartei a tarefa"),
    "notes.search": ("procurando nas suas notas", "procurei nas suas notas"),
    "notes.list": ("vendo suas notas", "vi suas notas"),
    "notes.read": ("lendo a nota inteira", "li a nota inteira"),
    "notes.create": ("guardando a nota no vault", "guardei a nota no vault"),
    "notes.append": ("acrescentando à nota", "acrescentei à nota"),
    "notes.delete": ("apagando a nota", "apaguei a nota"),
    "memory.search": ("procurando no que já sei sobre você",
                      "procurei no que já sei sobre você"),
    "memory.list": ("lembrando do que sei sobre você", "lembrei do que sei sobre você"),
    "memory.save": ("guardando isso sobre você", "guardei isso sobre você"),
    "memory.forget": ("esquecendo isso", "esqueci isso"),
    "expenses.add": ("anotando o gasto", "anotei o gasto"),
    "expenses.list": ("vendo seus lançamentos", "vi seus lançamentos"),
    "expenses.summary": ("somando seus gastos do mês", "somei seus gastos do mês"),
    "expenses.delete": ("apagando o gasto", "apaguei o gasto"),
    "events.list": ("vendo seus compromissos", "vi seus compromissos"),
    "events.conflicts": ("procurando choque de horário", "procurei choque de horário"),
    "people.list": ("vendo com quem você combinou de falar",
                    "vi com quem você combinou de falar"),
    "people.add": ("passando a acompanhar essa pessoa", "passei a acompanhar essa pessoa"),
    "people.touch": ("marcando que você falou com ela", "marquei que você falou com ela"),
    "people.update": ("mudando o combinado com ela", "mudei o combinado com ela"),
    "people.remove": ("deixando de acompanhar essa pessoa",
                      "deixei de acompanhar essa pessoa"),
    "reminders.create": ("criando o lembrete", "criei o lembrete"),
    "reminders.list": ("vendo seus lembretes", "vi seus lembretes"),
    "reminders.cancel": ("cancelando o lembrete", "cancelei o lembrete"),
    "work_orders.list": ("vendo a fila de trabalho", "vi a fila de trabalho"),
    "work_orders.create": ("pondo isso na fila de trabalho", "pus isso na fila de trabalho"),
    "work_orders.claim": ("assumindo o trabalho", "assumi o trabalho"),
    "work_orders.complete": ("fechando o trabalho", "fechei o trabalho"),
    "work_orders.drop": ("descartando o trabalho", "descartei o trabalho"),
    "usage.cost": ("somando quanto a API custou", "somei quanto a API custou"),
    "usage.set_balance": ("anotando seu saldo", "anotei seu saldo"),
    "time.now": ("vendo que dia é hoje", "vi que dia é hoje"),
}

PENSANDO = "pensando"

# ⏳ para o que está em andamento, ✓ para o que terminou. São os dois estados que
# a lista precisa distinguir, e cor não existe no Telegram.
AGORA = "⏳"
PRONTO = "✓"


def fazendo(nome: str) -> str:
    """O passo em andamento, aceitando o `notes_delete` que o modelo devolve."""
    return _frase(nome, 0)


def feito(nome: str) -> str:
    """O mesmo passo, já terminado."""
    return _frase(nome, 1)


def _frase(nome: str, indice: int) -> str:
    """Tool sem frase própria cai numa forma genérica em vez de sumir: um passo
    que não aparece é exatamente o silêncio que este módulo existe para tirar."""
    from aide.tools import alvo

    canonico = alvo.canonico(nome)
    par = FRASES.get(canonico)
    if par:
        return par[indice]
    assunto = canonico.split(".")[0].replace("_", " ")
    return (f"mexendo em {assunto}", f"mexi em {assunto}")[indice] if assunto else "trabalhando"
