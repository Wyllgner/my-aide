"""As leituras da interface.

A regra do projeto continua valendo inteira: **escrita só por tool**. Aqui não
há escrita nenhuma, e `messages` e `audit` não têm tool — então as consultas
de leitura vivem neste módulo, em vez de virarem tools que existiriam só para
a web.

Onde existe tool, a rota chama a tool: a auditoria registra `actor="web"` e
uma tool nova aparece na página sem código novo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _utc(momento: datetime) -> str:
    """`ts` e `created_at` vêm de datetime('now'): UTC, espaço no lugar do T."""
    return momento.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def serie_de_dias(agora: datetime, dias: int = 14) -> list[datetime]:
    inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    return [inicio - timedelta(days=d) for d in range(dias - 1, -1, -1)]


def chamadas_por_dia(conn, agora: datetime, dias: int = 14) -> list[tuple[str, int]]:
    """Chamadas de LLM por dia. Dia sem chamada entra como zero, não some."""
    desde = _utc(agora.replace(hour=0, minute=0) - timedelta(days=dias - 1))
    linhas = dict(conn.execute(
        "SELECT date(ts) d, COUNT(*) FROM llm_usage WHERE ts >= ? GROUP BY d", (desde,)
    ).fetchall())
    return [(d.strftime("%d"), linhas.get(d.strftime("%Y-%m-%d"), 0))
            for d in serie_de_dias(agora, dias)]


def tarefas_por_dia(conn, agora: datetime, dias: int = 14) -> list[tuple[str, int]]:
    desde = _utc(agora.replace(hour=0, minute=0) - timedelta(days=dias - 1))
    criadas = dict(conn.execute(
        "SELECT date(created_at) d, COUNT(*) FROM tasks WHERE created_at >= ? GROUP BY d",
        (desde,)).fetchall())
    return [(d.strftime("%d"), criadas.get(d.strftime("%Y-%m-%d"), 0))
            for d in serie_de_dias(agora, dias)]


def uso_das_ferramentas(conn, limite: int = 6) -> list[tuple[str, int]]:
    """Por família, que é como a pessoa pensa — não por tool individual."""
    return [(r["f"], r["n"]) for r in conn.execute(
        "SELECT substr(tool, 1, instr(tool, '.') - 1) f, COUNT(*) n FROM audit"
        " WHERE instr(tool, '.') > 0 GROUP BY f ORDER BY n DESC LIMIT ?", (limite,)
    ).fetchall()]


def mensagens_por_canal(conn) -> dict[str, int]:
    """O id de sessão do Telegram começa com 'tg'; o resto veio daqui."""
    linhas = dict(conn.execute(
        "SELECT CASE WHEN session_id LIKE 'tg%' THEN 'telegram' ELSE 'aqui' END c,"
        " COUNT(*) FROM messages GROUP BY c").fetchall())
    return {"aqui": linhas.get("aqui", 0), "telegram": linhas.get("telegram", 0)}


def conversas(conn, limite: int = 40) -> list[dict]:
    """Uma linha por sessão, com a primeira fala como título."""
    linhas = conn.execute(
        "SELECT session_id, COUNT(*) n, MIN(created_at) inicio, MAX(created_at) fim,"
        "  (SELECT content FROM messages m2 WHERE m2.session_id = m.session_id"
        "     AND m2.role = 'user' AND m2.content <> '' ORDER BY m2.id LIMIT 1) abertura"
        " FROM messages m GROUP BY session_id ORDER BY fim DESC LIMIT ?", (limite,)
    ).fetchall()
    return [{"sessao": r["session_id"], "mensagens": r["n"], "inicio": r["inicio"],
             "fim": r["fim"], "abertura": (r["abertura"] or "").strip(),
             "canal": "telegram" if r["session_id"].startswith("tg") else "aqui"}
            for r in linhas]


def mensagens(conn, sessao: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT role, content, tool_calls, created_at FROM messages"
        " WHERE session_id = ? ORDER BY id", (sessao,)).fetchall()]


def auditoria(conn, limite: int = 120) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT ts, actor, tool, args_json, result_summary, ok FROM audit"
        " ORDER BY id DESC LIMIT ?", (limite,)).fetchall()]


def contagens(conn, agora: datetime) -> dict:
    """Os números do topo do painel, numa consulta por linha."""
    def um(sql, p=()):
        linha = conn.execute(sql, p).fetchone()
        return linha[0] if linha else 0

    agora_iso = agora.isoformat(timespec="minutes")
    return {
        "abertas": um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL AND status='open'"),
        "atrasadas": um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL"
                        " AND status='open' AND due_at IS NOT NULL AND due_at < ?", (agora_iso,)),
        "notas": um("SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL"),
        "perfil": um("SELECT COUNT(*) FROM memory WHERE kind='profile' AND superseded_by IS NULL"),
        "pessoas": um("SELECT COUNT(*) FROM people"),
        "fila": um("SELECT COUNT(*) FROM work_orders WHERE status IN ('open','claimed')"),
        "lembretes": um("SELECT COUNT(*) FROM reminders WHERE status='pending'"),
        "chamadas": um("SELECT COUNT(*) FROM llm_usage"),
    }
