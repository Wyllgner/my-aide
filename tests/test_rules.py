from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aide.scheduler import rules

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 3, 10, 0, tzinfo=TZ)


def _achados(conn, nome):
    return [f for f in rules.evaluate(conn, AGORA) if f.rule == nome]


def test_atrasada_e_encontrada(ctx, registry):
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-08-30T09:00"}, ctx)
    achados = _achados(ctx.conn, "atrasadas")
    assert len(achados) == 1
    assert "venceu há 4 dia" in achados[0].summary


def test_tarefa_no_prazo_nao_aparece(ctx, registry):
    registry.call("tasks.create", {"title": "Futuro", "due": "2026-09-30T09:00"}, ctx)
    assert _achados(ctx.conn, "atrasadas") == []


def test_concluida_nao_e_cobrada(ctx, registry):
    task = registry.call("tasks.create", {"title": "X", "due": "2026-08-01T09:00"}, ctx).data
    registry.call("tasks.complete", {"id": task["id"]}, ctx)
    assert _achados(ctx.conn, "atrasadas") == []


def test_tres_adiamentos_viram_pergunta(ctx, registry):
    task = registry.call("tasks.create", {"title": "Dentista", "due": "2026-09-10T09:00"}, ctx).data
    for _ in range(2):
        registry.call("tasks.snooze", {"id": task["id"], "until": "2026-09-20T09:00"}, ctx)
    assert _achados(ctx.conn, "adiada_demais") == []

    registry.call("tasks.snooze", {"id": task["id"], "until": "2026-09-25T09:00"}, ctx)
    achados = _achados(ctx.conn, "adiada_demais")
    assert len(achados) == 1
    assert "ainda importa" in achados[0].summary
    assert achados[0].severity == 1


def test_projeto_parado(ctx, registry):
    registry.call("tasks.create", {"title": "X", "project": "abandonado"}, ctx)
    antigo = (AGORA - timedelta(days=20)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET last_touched_at = ?, created_at = ?", (antigo, antigo))
    achados = _achados(ctx.conn, "projeto_parado")
    assert len(achados) == 1 and "abandonado" in achados[0].summary


def test_projeto_ativo_nao_aparece(ctx, registry):
    registry.call("tasks.create", {"title": "X", "project": "vivo"}, ctx)
    assert _achados(ctx.conn, "projeto_parado") == []


def test_zumbi_precisa_ser_antiga_e_sem_prazo(ctx, registry):
    registry.call("tasks.create", {"title": "Velha"}, ctx)
    registry.call("tasks.create", {"title": "Com prazo", "due": "2026-12-01T09:00"}, ctx)
    antigo = (AGORA - timedelta(days=40)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET created_at = ?, last_touched_at = ?", (antigo, antigo))
    achados = _achados(ctx.conn, "zumbi")
    assert [f.refs[0] for f in achados] == [1]


def test_contato_atrasado(ctx):
    antigo = (AGORA - timedelta(days=30)).isoformat(timespec="minutes")
    ctx.conn.execute(
        "INSERT INTO people (name, last_contact_at, cadence_days) VALUES (?, ?, ?)",
        ("Fulano", antigo, 21),
    )
    achados = _achados(ctx.conn, "contato_atrasado")
    assert len(achados) == 1 and "Fulano" in achados[0].summary


def test_contato_em_dia_nao_aparece(ctx):
    recente = (AGORA - timedelta(days=2)).isoformat(timespec="minutes")
    ctx.conn.execute(
        "INSERT INTO people (name, last_contact_at, cadence_days) VALUES (?, ?, ?)",
        ("Ciclano", recente, 21),
    )
    assert _achados(ctx.conn, "contato_atrasado") == []


def test_banco_vazio_nao_gera_ruido(ctx):
    assert rules.evaluate(ctx.conn, AGORA) == []


def test_regra_quebrada_nao_derruba_as_outras(ctx, registry, monkeypatch):
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-08-30T09:00"}, ctx)

    def explode(conn, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(rules, "_RULES", [("quebrada", explode), *rules._RULES])
    achados = rules.evaluate(ctx.conn, AGORA)
    assert any(f.rule == "atrasadas" for f in achados)


def test_ordena_por_severidade(ctx, registry):
    registry.call("tasks.create", {"title": "Velha"}, ctx)
    antigo = (AGORA - timedelta(days=40)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET created_at = ?, last_touched_at = ?", (antigo, antigo))
    registry.call("tasks.create", {"title": "Boleto", "due": "2026-08-25T09:00"}, ctx)
    achados = rules.evaluate(ctx.conn, AGORA)
    assert [f.severity for f in achados] == sorted(f.severity for f in achados)


def test_atraso_e_contado_em_dias_de_calendario(ctx):
    """`timedelta.days` trunca: um prazo de anteontem à noite dizia "há 1 dia",
    enquanto a tabela de tarefas dizia "há 2 dias" sobre a mesma linha."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Porto_Velho")
    agora = datetime(2026, 9, 21, 8, 0, tzinfo=tz)
    anteontem = (agora - timedelta(days=2)).replace(hour=23, minute=0)
    ctx.conn.execute("INSERT INTO tasks (title, status, due_at) VALUES (?, 'open', ?)",
                     ("prazo da noite", anteontem.isoformat(timespec="minutes")))

    achado = rules.evaluate(ctx.conn, agora, only=["atrasadas"])[0]
    assert "venceu há 2 dias" in achado.summary


def test_atraso_de_um_dia_se_escreve_ontem(ctx):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Porto_Velho")
    agora = datetime(2026, 9, 21, 8, 0, tzinfo=tz)
    ctx.conn.execute("INSERT INTO tasks (title, status, due_at) VALUES (?, 'open', ?)",
                     ("de ontem", "2026-09-20T09:00-04:00"))

    achado = rules.evaluate(ctx.conn, agora, only=["atrasadas"])[0]
    assert "venceu ontem" in achado.summary
    assert "dia(s)" not in achado.summary


def test_prazo_gravado_em_outro_fuso_e_convertido(ctx):
    """Seis prazos no banco foram gravados com −03; `replace(tzinfo=)` os movia."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Porto_Velho")
    # 21/09 00:30 em São Paulo é ainda 20/09 às 23:30 aqui
    agora = datetime(2026, 9, 21, 8, 0, tzinfo=tz)
    ctx.conn.execute("INSERT INTO tasks (title, status, due_at) VALUES (?, 'open', ?)",
                     ("virada do dia", "2026-09-21T00:30-03:00"))

    achado = rules.evaluate(ctx.conn, agora, only=["atrasadas"])[0]
    assert "venceu ontem" in achado.summary
