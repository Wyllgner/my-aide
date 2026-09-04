from datetime import datetime

from aide.tools import reminders


def test_cria_e_lista(ctx, registry):
    created = registry.call(
        "reminders.create", {"text": "Reunião", "when": "2027-01-05T09:00"}, ctx
    )
    assert created.ok
    assert registry.call("reminders.list", {}, ctx).data[0]["text"] == "Reunião"


def test_recusa_horario_passado(ctx, registry):
    result = registry.call("reminders.create", {"text": "X", "when": "2020-01-01T09:00"}, ctx)
    assert not result.ok
    assert "já passou" in result.error


def test_aceita_passado_se_repete(ctx, registry):
    assert registry.call(
        "reminders.create", {"text": "X", "when": "2020-01-01T09:00", "repeat": "daily"}, ctx
    ).ok


def test_recusa_repeticao_invalida(ctx, registry):
    result = registry.call(
        "reminders.create", {"text": "X", "when": "2027-01-05T09:00", "repeat": "sempre"}, ctx
    )
    assert not result.ok


def test_cancelar_duas_vezes_falha(ctx, registry):
    rid = registry.call("reminders.create", {"text": "X", "when": "2027-01-05T09:00"}, ctx).data["id"]
    assert registry.call("reminders.cancel", {"id": rid}, ctx).ok
    assert not registry.call("reminders.cancel", {"id": rid}, ctx).ok


def test_due_pega_so_o_que_venceu(ctx, registry):
    registry.call("reminders.create", {"text": "passado", "when": "2020-01-01T09:00",
                                       "repeat": "daily"}, ctx)
    registry.call("reminders.create", {"text": "futuro", "when": "2030-01-01T09:00"}, ctx)
    vencidos = reminders.due(ctx.conn, datetime(2026, 1, 1, 10, 0))
    assert [r["text"] for r in vencidos] == ["passado"]


def test_repetido_reagenda_a_proxima(ctx, registry):
    registry.call("reminders.create", {"text": "X", "when": "2026-09-03T09:00",
                                       "repeat": "daily"}, ctx)
    vencido = reminders.due(ctx.conn, datetime(2026, 9, 3, 10, 0))[0]
    assert reminders.mark_delivered(ctx.conn, vencido) == "2026-09-04T09:00"
    pendentes = registry.call("reminders.list", {}, ctx).data
    assert [r["fire_at"] for r in pendentes] == ["2026-09-04T09:00"]


def test_unico_nao_reagenda(ctx, registry):
    registry.call("reminders.create", {"text": "X", "when": "2027-01-05T09:00"}, ctx)
    unico = ctx.conn.execute("SELECT id, text, fire_at, repeat_rule FROM reminders").fetchone()
    assert reminders.mark_delivered(ctx.conn, dict(unico)) is None
    assert registry.call("reminders.list", {}, ctx).data == []


def test_weekdays_pula_o_fim_de_semana():
    sexta = datetime(2026, 9, 4, 9, 0)
    assert reminders._next_occurrence(sexta, "weekdays") == datetime(2026, 9, 7, 9, 0)


def test_mensal_ajusta_dia_31():
    assert reminders._next_occurrence(datetime(2026, 1, 31, 9, 0), "monthly").day == 28
