"""Briefings: o assessor falando primeiro.

Montagem determinística. A estrutura — o que vence, o que atrasou, o que já
foi — sempre saiu de SQL; o que a LLM fazia era reescrever aquilo em prosa. No
formato de lista com coluna a prosa não entra, então a chamada por dia deixou
de existir: mais barato, instantâneo e sem chance de inventar um item que não
está nos dados.

A mensagem sai como `Mensagem`, e cada canal a renderiza do seu jeito — ver
`aide/channels/formato.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aide.channels.formato import Item, Mensagem, Secao, quando
from aide.scheduler import rules

LIMITE_ITENS = 6


@dataclass
class Briefing:
    mensagem: Mensagem
    urgency: str = "normal"

    @property
    def title(self) -> str:
        return self.mensagem.titulo

    @property
    def vazio(self) -> bool:
        return self.mensagem.vazia


def _itens(conn, sql: str, params: tuple, agora: datetime,
           marca=None, limite: int = LIMITE_ITENS) -> list[Item]:
    linhas = conn.execute(sql, params).fetchall()
    itens = [
        Item(texto=r["title"], ref=f"#{r['id']}",
             marca=marca(r, agora) if marca else quando(r["due_at"], agora))
        for r in linhas[:limite]
    ]
    if len(linhas) > limite:
        itens.append(Item(texto=f"e mais {len(linhas) - limite}"))
    return itens


ABERTAS = ("SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL"
           " AND status = 'open' AND private = 0")


def montar_manha(conn, agora: datetime, config=None) -> Briefing:
    inicio = agora.replace(hour=0, minute=0).isoformat(timespec="minutes")
    fim = agora.replace(hour=23, minute=59).isoformat(timespec="minutes")

    atrasadas = _itens(conn, f"{ABERTAS} AND due_at < ? ORDER BY due_at",
                       (inicio,), agora)
    hoje = _itens(conn, f"{ABERTAS} AND due_at BETWEEN ? AND ? ORDER BY due_at",
                  (inicio, fim), agora)
    lembretes = [
        Item(texto=r["text"], marca=quando(r["fire_at"], agora))
        for r in conn.execute(
            "SELECT text, fire_at FROM reminders WHERE status = 'pending'"
            " AND fire_at <= ? ORDER BY fire_at LIMIT ?", (fim, LIMITE_ITENS)).fetchall()
    ]
    decidir = [
        Item(texto=f.summary) for f in rules.evaluate(conn, agora, config=config)
        if f.rule in {"adiada_demais", "zumbi"}
    ][:LIMITE_ITENS]

    mensagem = Mensagem(
        titulo="Bom dia",
        secoes=[Secao("Atrasadas", atrasadas), Secao("Hoje", hoje),
                Secao("Lembretes", lembretes), Secao("Precisa decidir", decidir)],
        rodape=_rodape([(len(atrasadas), "atrasada", "atrasadas"),
                        (len(hoje), "para hoje", "para hoje")]),
    )
    return Briefing(mensagem, urgency="critical" if atrasadas else "normal")


def montar_noite(conn, agora: datetime, config=None) -> Briefing:
    amanha = agora + timedelta(days=1)

    feitas = _itens(
        conn,
        "SELECT id, title, due_at FROM tasks WHERE completed_at >= ? AND private = 0"
        " ORDER BY completed_at", (_inicio_utc(agora),), agora, marca=lambda r, a: "")
    ficaram = _itens(conn, f"{ABERTAS} AND due_at < ? ORDER BY due_at",
                     (agora.isoformat(timespec="minutes"),), agora)
    amanha_itens = _itens(
        conn, f"{ABERTAS} AND due_at BETWEEN ? AND ? ORDER BY due_at",
        (amanha.replace(hour=0, minute=0).isoformat(timespec="minutes"),
         amanha.replace(hour=23, minute=59).isoformat(timespec="minutes")), agora)

    mensagem = Mensagem(
        titulo="Fechando o dia",
        secoes=[Secao("Feito hoje", feitas), Secao("Ficou para trás", ficaram),
                Secao("Amanhã", amanha_itens)],
        rodape=_rodape([(len(feitas), "concluída", "concluídas"),
                        (len(amanha_itens), "para amanhã", "para amanhã")]),
    )
    return Briefing(mensagem)


def montar_semanal(conn, agora: datetime, config=None) -> Briefing:
    atencao = [Item(texto=f.summary)
               for f in rules.evaluate(conn, agora, config=config)][:10]
    sem_prazo = _itens(conn, f"{ABERTAS} AND due_at IS NULL ORDER BY created_at",
                       (), agora, marca=lambda r, a: "", limite=10)

    mensagem = Mensagem(
        titulo="Revisão da semana",
        secoes=[Secao("Precisa de atenção", atencao),
                Secao("Abertas sem prazo", sem_prazo)],
        rodape=_rodape([(len(atencao), "ponto", "pontos"),
                        (len(sem_prazo), "sem prazo", "sem prazo")]),
    )
    return Briefing(mensagem)


def _inicio_utc(agora: datetime) -> str:
    """Meia-noite de hoje no formato em que o SQLite grava `completed_at`.

    `due_at` guarda ISO local com fuso; `completed_at` vem de `datetime('now')`,
    que é UTC com espaço no lugar do T. Comparar um com o outro é comparação de
    texto: " " vem antes de "T", então a condição nunca casava e tarefa
    concluída simplesmente não aparecia no briefing da noite.
    """
    return agora.replace(hour=0, minute=0).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _rodape(partes: list[tuple[int, str, str]]) -> str:
    """'4 atrasadas · 1 para hoje'. O que é zero não aparece."""
    escritas = [f"{n} {singular if n == 1 else plural}"
                for n, singular, plural in partes if n]
    return " · ".join(escritas)


MONTADORES = {"manha": montar_manha, "noite": montar_noite, "semanal": montar_semanal}


def gerar(conn, config, llm, agora: datetime, tipo: str = "manha") -> Briefing:
    """`llm` continua na assinatura: quem chama não precisa saber que saiu de cena."""
    if tipo not in MONTADORES:
        raise ValueError(f"briefing desconhecido: {tipo}")
    return MONTADORES[tipo](conn, agora, config)
