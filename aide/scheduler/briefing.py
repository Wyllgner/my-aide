"""Briefings: o assessor falando primeiro.

A decisão de disparar é do scheduler (determinística). A LLM entra só para
redigir — e no modelo barato, porque isso roda todo dia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from aide.llm.base import Message
from aide.scheduler import rules

PROMPTS_DIR = Path(__file__).parent.parent / "core" / "prompts"
SEM_NOVIDADES = "SEM NOVIDADES"


@dataclass
class Briefing:
    title: str
    body: str
    urgency: str = "normal"

    @property
    def vazio(self) -> bool:
        return not self.body.strip() or self.body.strip() == SEM_NOVIDADES


def _tarefas(conn, sql: str, params: tuple = ()) -> list[str]:
    return [
        f"#{r['id']} {r['title']}" + (f" (vence {r['due_at']})" if r["due_at"] else "")
        for r in conn.execute(sql, params).fetchall()
    ]


def coletar_manha(conn, now: datetime) -> dict[str, list[str]]:
    fim_do_dia = now.replace(hour=23, minute=59).isoformat(timespec="minutes")
    return {
        "vence hoje": _tarefas(
            conn,
            "SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
            " AND due_at BETWEEN ? AND ? ORDER BY due_at",
            (now.replace(hour=0, minute=0).isoformat(timespec="minutes"), fim_do_dia),
        ),
        "atrasadas": _tarefas(
            conn,
            "SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
            " AND due_at < ? ORDER BY due_at LIMIT 10",
            (now.replace(hour=0, minute=0).isoformat(timespec="minutes"),),
        ),
        "lembretes de hoje": [
            f"{r['fire_at']} {r['text']}"
            for r in conn.execute(
                "SELECT text, fire_at FROM reminders WHERE status = 'pending'"
                " AND fire_at <= ? ORDER BY fire_at", (fim_do_dia,)
            ).fetchall()
        ],
        "precisa de decisão": [f.summary for f in rules.evaluate(conn, now)
                               if f.rule in {"adiada_demais", "zumbi"}],
    }


def coletar_noite(conn, now: datetime) -> dict[str, list[str]]:
    inicio = now.replace(hour=0, minute=0).isoformat(timespec="minutes")
    amanha = now + timedelta(days=1)
    return {
        "concluídas hoje": _tarefas(
            conn,
            "SELECT id, title, due_at FROM tasks WHERE completed_at >= ? ORDER BY completed_at",
            (inicio,),
        ),
        "ficaram para trás": _tarefas(
            conn,
            "SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
            " AND due_at < ? ORDER BY due_at LIMIT 10",
            (now.isoformat(timespec="minutes"),),
        ),
        "amanhã": _tarefas(
            conn,
            "SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
            " AND due_at BETWEEN ? AND ? ORDER BY due_at",
            (amanha.replace(hour=0, minute=0).isoformat(timespec="minutes"),
             amanha.replace(hour=23, minute=59).isoformat(timespec="minutes")),
        ),
    }


def coletar_semanal(conn, now: datetime) -> dict[str, list[str]]:
    return {
        "precisa de atenção": [f.summary for f in rules.evaluate(conn, now)],
        "abertas sem prazo": _tarefas(
            conn,
            "SELECT id, title, due_at FROM tasks WHERE deleted_at IS NULL AND status = 'open'"
            " AND due_at IS NULL ORDER BY created_at LIMIT 15",
        ),
    }


def _formatar(dados: dict[str, list[str]]) -> str:
    blocos = [f"{titulo}:\n" + "\n".join(f"- {linha}" for linha in linhas)
              for titulo, linhas in dados.items() if linhas]
    return "\n\n".join(blocos)


def gerar(conn, config, llm, now: datetime, tipo: str = "manha") -> Briefing:
    coletores = {
        "manha": (coletar_manha, "briefing da manhã", "Bom dia", 6),
        "noite": (coletar_noite, "resumo da noite", "Fechando o dia", 5),
        "semanal": (coletar_semanal, "revisão semanal", "Revisão da semana", 10),
    }
    if tipo not in coletores:
        raise ValueError(f"briefing desconhecido: {tipo}")

    coletar, descricao, titulo, max_linhas = coletores[tipo]
    dados = coletar(conn, now)
    texto = _formatar(dados)

    if not texto:
        return Briefing(title=titulo, body="", urgency="low")

    prompt = (PROMPTS_DIR / "briefing.md").read_text().format(
        user_name=config.user_name or "seu usuário",
        tipo=descricao,
        max_linhas=max_linhas,
        agora=now.strftime("%d/%m/%Y %H:%M"),
        dados=texto,
    )
    # modelo barato: isto roda todo dia, e é resumo de dado já estruturado
    resposta = llm.complete([Message(role="user", content=prompt)],
                            fast=True, purpose=f"briefing_{tipo}")

    urgencia = "critical" if dados.get("atrasadas") else "normal"
    return Briefing(title=titulo, body=resposta.text.strip(), urgency=urgencia)
