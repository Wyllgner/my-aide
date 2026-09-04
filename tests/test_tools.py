from aide.core.context import state_snapshot


def test_cria_e_lista(ctx, registry):
    created = registry.call("tasks.create", {"title": "Pagar IPVA"}, ctx)
    assert created.ok
    listed = registry.call("tasks.list", {"filter": "all"}, ctx)
    assert [t["title"] for t in listed.data] == ["Pagar IPVA"]


def test_rejeita_prazo_que_nao_e_iso(ctx, registry):
    result = registry.call("tasks.create", {"title": "X", "due": "sexta"}, ctx)
    assert not result.ok
    assert "ISO 8601" in result.error


def test_bloqueia_tarefa_duplicada(ctx, registry):
    registry.call("tasks.create", {"title": "Pagar o IPVA"}, ctx)
    again = registry.call("tasks.create", {"title": "pagar ipva"}, ctx)
    assert not again.ok
    assert "já existe" in again.error
    forced = registry.call("tasks.create", {"title": "pagar ipva", "force": True}, ctx)
    assert forced.ok


def test_snooze_conta_adiamentos(ctx, registry):
    task = registry.call("tasks.create", {"title": "X", "due": "2026-09-04T09:00"}, ctx).data
    for _ in range(3):
        result = registry.call("tasks.snooze", {"id": task["id"], "until": "2026-09-11T09:00"}, ctx)
    assert result.data["snooze_count"] == 3


def test_completar_duas_vezes_falha(ctx, registry):
    task = registry.call("tasks.create", {"title": "X"}, ctx).data
    assert registry.call("tasks.complete", {"id": task["id"]}, ctx).ok
    assert not registry.call("tasks.complete", {"id": task["id"]}, ctx).ok


def test_valida_argumentos(ctx, registry):
    assert not registry.call("tasks.create", {}, ctx).ok
    assert not registry.call("tasks.create", {"title": "X", "xpto": 1}, ctx).ok
    assert not registry.call("tasks.inexistente", {}, ctx).ok


def test_toda_chamada_vira_auditoria(ctx, registry):
    registry.call("tasks.create", {"title": "X"}, ctx)
    registry.call("tasks.complete", {"id": 999}, ctx)
    rows = ctx.conn.execute("SELECT tool, ok FROM audit ORDER BY id").fetchall()
    assert [(r["tool"], r["ok"]) for r in rows] == [("tasks.create", 1), ("tasks.complete", 0)]


def test_nomes_de_tool_sao_validos_na_api(registry):
    import re
    for name in registry.names():
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", registry.get(name).api_name), name


def test_registry_aceita_nome_da_api(registry):
    assert registry.get("tasks_create") is registry.get("tasks.create")


def test_privada_nao_entra_no_contexto(ctx, registry):
    registry.call("tasks.create", {"title": "Segredo", "private": True}, ctx)
    registry.call("tasks.create", {"title": "Publica"}, ctx)
    snapshot = state_snapshot(ctx.conn, ctx.config)
    assert "Publica" in snapshot.content
    assert "Segredo" not in snapshot.content
