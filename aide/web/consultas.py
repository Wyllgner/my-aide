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


def auditoria(conn, limite: int = 150, ator: str | None = None) -> list[dict]:
    sql = "SELECT ts, actor, tool, args_json, result_summary, ok FROM audit"
    params: list = []
    if ator:
        sql += " WHERE actor = ?"
        params.append(ator)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def atores_da_auditoria(conn) -> list[tuple[str, int]]:
    """Quem chamou o quê, no total — não só nas últimas linhas."""
    return [(r["actor"], r["n"]) for r in conn.execute(
        "SELECT actor, COUNT(*) n FROM audit GROUP BY actor ORDER BY n DESC").fetchall()]


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


def planejado_no_mes(conn, ano: int, mes: int, tz) -> dict[int, list[dict]]:
    """O que cada dia do mês tem marcado, agrupado por dia.

    Junta as três origens que têm data — tarefa com prazo, evento do feed e
    lembrete — porque é assim que o dia acontece: você não separa o que veio
    da agenda do que você anotou.
    """
    from calendar import monthrange
    from datetime import datetime

    primeiro = datetime(ano, mes, 1, tzinfo=tz)
    ultimo = datetime(ano, mes, monthrange(ano, mes)[1], 23, 59, tzinfo=tz)
    de, ate = primeiro.isoformat(timespec="minutes"), ultimo.isoformat(timespec="minutes")

    por_dia: dict[int, list[dict]] = {}

    def juntar(quando_iso: str, item: dict) -> None:
        try:
            dia = datetime.fromisoformat(quando_iso).astimezone(tz).day
        except ValueError:
            return
        por_dia.setdefault(dia, []).append(item)

    for r in conn.execute(
        "SELECT id, title, due_at, status FROM tasks WHERE deleted_at IS NULL"
        " AND due_at BETWEEN ? AND ? ORDER BY due_at", (de, ate)).fetchall():
        juntar(r["due_at"], {"tipo": "tarefa", "ref": f"#{r['id']}", "texto": r["title"],
                             "feito": r["status"] == "done", "quando": r["due_at"]})

    for r in conn.execute(
        "SELECT title, start_at, all_day FROM events WHERE deleted_at IS NULL"
        " AND start_at BETWEEN ? AND ? ORDER BY start_at", (de, ate)).fetchall():
        juntar(r["start_at"], {"tipo": "evento", "ref": "", "texto": r["title"],
                               "feito": False, "quando": r["start_at"],
                               "dia_inteiro": bool(r["all_day"])})

    for r in conn.execute(
        "SELECT text, fire_at FROM reminders WHERE status = 'pending'"
        " AND fire_at BETWEEN ? AND ? ORDER BY fire_at", (de, ate)).fetchall():
        juntar(r["fire_at"], {"tipo": "lembrete", "ref": "", "texto": r["text"],
                              "feito": False, "quando": r["fire_at"]})

    return por_dia


def gastos_por_dia(conn, de: str, ate: str, tz) -> list[tuple[str, float]]:
    """Centavos por dia do período. Dia sem gasto entra como zero."""
    from datetime import datetime, timedelta

    linhas = dict(conn.execute(
        "SELECT substr(spent_at, 1, 10) d, SUM(cents) FROM expenses"
        " WHERE deleted_at IS NULL AND spent_at BETWEEN ? AND ? GROUP BY d",
        (de, ate)).fetchall())

    inicio = datetime.fromisoformat(de).astimezone(tz).date()
    fim = datetime.fromisoformat(ate).astimezone(tz).date()
    dias = (fim - inicio).days + 1
    return [((inicio + timedelta(days=i)).strftime("%d"),
             linhas.get((inicio + timedelta(days=i)).isoformat(), 0))
            for i in range(max(dias, 1))]


def acumulado(pares: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """A mesma série somando — mostra o ritmo, que a barra diária esconde."""
    total = 0.0
    saida = []
    for rotulo, valor in pares:
        total += valor
        saida.append((rotulo, total))
    return saida


def custo_por_dia(conn, agora, dias: int = 14, precos: dict | None = None):
    """Custo estimado por dia, em dólares."""
    from datetime import timedelta

    desde = _utc(agora.replace(hour=0, minute=0) - timedelta(days=dias - 1))
    linhas = conn.execute(
        "SELECT date(ts) d, model, SUM(input_tokens) i, SUM(output_tokens) o"
        " FROM llm_usage WHERE ts >= ? GROUP BY d, model", (desde,)).fetchall()

    por_dia: dict[str, float] = {}
    for r in linhas:
        preco = (precos or {}).get(r["model"])
        if preco:
            por_dia[r["d"]] = por_dia.get(r["d"], 0.0) + (
                r["i"] / 1_000_000 * preco[0] + r["o"] / 1_000_000 * preco[1])
    return [(d.strftime("%d"), round(por_dia.get(d.strftime("%Y-%m-%d"), 0.0), 6))
            for d in serie_de_dias(agora, dias)]


def uso_por_finalidade(conn, limite: int = 6) -> list[tuple[str, int]]:
    return [(r["purpose"] or "sem rótulo", r["n"]) for r in conn.execute(
        "SELECT purpose, COUNT(*) n FROM llm_usage GROUP BY purpose"
        " ORDER BY n DESC LIMIT ?", (limite,)).fetchall()]
