from datetime import timedelta

from aide.core.context import now_in
from aide.scheduler import rules


def _dias_atras(ctx, dias):
    return (now_in(ctx.config.timezone) - timedelta(days=dias)).isoformat(timespec="minutes")


def test_registra_pessoa(ctx, registry):
    resultado = registry.call("people.add", {"name": "Ana", "relation": "irmã",
                                             "cadence_days": 14}, ctx)
    assert resultado.ok
    assert resultado.data["cadence_days"] == 14


def test_nao_duplica_pessoa(ctx, registry):
    registry.call("people.add", {"name": "Ana"}, ctx)
    de_novo = registry.call("people.add", {"name": "ana"}, ctx)
    assert not de_novo.ok
    assert "já está registrado" in de_novo.error


def test_cadencia_invalida(ctx, registry):
    assert not registry.call("people.add", {"name": "X", "cadence_days": 0}, ctx).ok


def test_touch_zera_o_contador(ctx, registry):
    registry.call("people.add", {"name": "Ana", "cadence_days": 7,
                                 "last_contact": _dias_atras(ctx, 30)}, ctx)
    assert registry.call("people.list", {"atrasados": True}, ctx).data

    registry.call("people.touch", {"name": "Ana"}, ctx)
    assert registry.call("people.list", {"atrasados": True}, ctx).data == []


def test_touch_por_nome_parcial(ctx, registry):
    registry.call("people.add", {"name": "Ana Paula"}, ctx)
    assert registry.call("people.touch", {"name": "Paula"}, ctx).ok


def test_touch_com_nota_vira_memoria(ctx, registry):
    """Assim 'o que eu falei com a Ana?' tem o que buscar depois."""
    registry.call("people.add", {"name": "Ana"}, ctx)
    registry.call("people.touch", {"name": "Ana", "note": "vai mudar de emprego"}, ctx)
    achados = registry.call("memory.search", {"query": "Ana emprego"}, ctx).data
    assert any("emprego" in m["value"] for m in achados)


def test_pessoa_desconhecida(ctx, registry):
    assert not registry.call("people.touch", {"name": "Ninguém"}, ctx).ok


def test_lista_calcula_dias_sem_falar(ctx, registry):
    registry.call("people.add", {"name": "Ana", "cadence_days": 7,
                                 "last_contact": _dias_atras(ctx, 10)}, ctx)
    pessoa = registry.call("people.list", {}, ctx).data[0]
    assert pessoa["dias_sem_falar"] == 10
    assert pessoa["atrasado"] is True


def test_cadencia_zero_para_de_cobrar(ctx, registry):
    registry.call("people.add", {"name": "Ana", "cadence_days": 7,
                                 "last_contact": _dias_atras(ctx, 90)}, ctx)
    registry.call("people.update", {"name": "Ana", "cadence_days": 0}, ctx)
    assert registry.call("people.list", {"atrasados": True}, ctx).data == []


def test_alimenta_a_regra_de_cobranca(ctx, registry):
    """A regra contato_atrasado existia sem nada para alimentá-la."""
    registry.call("people.add", {"name": "Ana", "cadence_days": 21,
                                 "last_contact": _dias_atras(ctx, 40)}, ctx)
    achados = [f for f in rules.evaluate(ctx.conn, now_in(ctx.config.timezone))
               if f.rule == "contato_atrasado"]
    assert len(achados) == 1
    assert "Ana" in achados[0].summary


def test_remover(ctx, registry):
    registry.call("people.add", {"name": "Ana"}, ctx)
    assert registry.call("people.remove", {"name": "Ana"}, ctx).ok
    assert registry.call("people.list", {}, ctx).data == []
