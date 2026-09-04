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
