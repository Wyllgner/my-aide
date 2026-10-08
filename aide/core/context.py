"""Montagem do prompt: system + estado atual + histórico da sessão."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aide.llm.base import Message

PROMPTS_DIR = Path(__file__).parent / "prompts"


def now_in(timezone: str) -> datetime:
    return datetime.now(ZoneInfo(timezone))


def profile_prompt(conn, config) -> Message | None:
    """O perfil vai inteiro em toda conversa — é o que faz o assessor te conhecer."""
    from aide.tools.memory import perfil_para_prompt

    perfil = perfil_para_prompt(conn, config)
    if not perfil:
        return None
    return Message(
        role="system",
        content="O que você já sabe sobre a pessoa (não pergunte de novo):\n" + perfil,
    )


CATEGORIAS_PADRAO = ("alimentação", "transporte", "mercado", "saúde", "casa",
                     "lazer", "assinatura")


def system_prompt(config, conn=None) -> Message:
    from aide.channels.formato import por_extenso

    agora = now_in(config.timezone)
    template = (PROMPTS_DIR / "system.md").read_text()
    text = template.format(
        user_name=config.user_name or "seu usuário",
        # `%A` segue o locale da máquina, que aqui é C: o modelo lia "Monday" no
        # meio de um prompt em português e respondia o dia da semana em inglês
        now=f"{por_extenso(agora)} de {agora.year}, {agora.strftime('%H:%M')}",
        timezone=config.timezone,
        categorias=_categorias(config, conn),
        tags=_tags(conn),
    )
    return Message(role="system", content=text)


def _categorias(config, conn=None) -> str:
    """As categorias que a pessoa declarou teto para, quando existirem.

    Sem isto o modelo inventava o nome ("transporte" quando o teto é "uber") e a
    regra de orçamento, que casa por nome exato, não encontrava nada: o teto
    ficava declarado e mudo.
    """
    from aide.tools.expenses import tetos_em_vigor

    declaradas = tuple(tetos_em_vigor(conn, config))
    return ", ".join(declaradas or CATEGORIAS_PADRAO)


def _tags(conn) -> str:
    """"farmácia → pessoal, lanche → pessoal". Sem a lista o modelo lançaria
    "10 em farmácia" com categoria inventada e sem a tag."""
    from aide.tools.expenses import _chave, tags_em_vigor, tags_usadas

    tags = tags_em_vigor(conn)
    cadastradas = (", ".join(f"{nome} → {categoria}" for nome, categoria in tags.values())
                   or "nenhuma cadastrada ainda")
    # as soltas também: sem elas "57 em alimentação do casal" saía sem a tag
    # casal, porque o modelo não sabia que ela existia
    soltas = "; ".join(
        f"{categoria}: {', '.join(t for t in nomes if _chave(t) not in tags)}"
        for categoria, nomes in tags_usadas(conn).items()
        if any(_chave(t) not in tags for t in nomes))
    return f"{cadastradas}. Já usadas sem cadastro: {soltas}" if soltas else cadastradas


def state_snapshot(conn, config) -> Message | None:
    """Tarefas abertas, para o modelo não recriar o que já existe.

    Não é só o dia: o modelo precisa enxergar o que está em aberto, senão
    "adia o IPVA" vira uma tarefa nova. Itens `private` ficam de fora — nunca
    vão para o provedor.
    """
    now = now_in(config.timezone)
    today = now.replace(hour=23, minute=59).isoformat(timespec="minutes")
    rows = conn.execute(
        "SELECT id, title, due_at, priority, project, snooze_count FROM tasks"
        " WHERE deleted_at IS NULL AND status = 'open' AND private = 0"
        " ORDER BY due_at IS NULL, due_at LIMIT 40",
    ).fetchall()

    if not rows:
        return None

    lines = []
    for r in rows:
        marks = []
        if r["due_at"]:
            marks.append(r["due_at"])
            if r["due_at"] < now.isoformat():
                marks.append("ATRASADA")
            elif r["due_at"] <= today:
                marks.append("hoje")
        else:
            marks.append("sem prazo")
        if r["project"]:
            marks.append(r["project"])
        if r["snooze_count"]:
            marks.append(f"adiada {r['snooze_count']}x")
        lines.append(f"#{r['id']} {r['title']} — {' · '.join(marks)}")

    return Message(
        role="system",
        content=(
            "Tarefas abertas agora (esta é a lista completa; use estes ids ao "
            "adiar, concluir ou alterar, e NÃO crie tarefa nova para algo que "
            "já está aqui):\n" + "\n".join(lines)
        ),
    )


def build(config, history: list[Message], conn=None) -> list[Message]:
    messages = [system_prompt(config, conn)]
    if conn is not None:
        perfil = profile_prompt(conn, config)
        if perfil:
            messages.append(perfil)
        snapshot = state_snapshot(conn, config)
        if snapshot:
            messages.append(snapshot)
    messages.extend(history[-config.history_messages :])
    return messages
