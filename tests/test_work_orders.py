def test_cria_e_lista(ctx, registry):
    criada = registry.call("work_orders.create", {
        "goal": "Organizar as notas fiscais de agosto",
        "context": "Estão soltas na pasta Downloads",
        "refs": ["~/Downloads"],
        "done_criteria": "Uma pasta por mês, renomeadas",
    }, ctx)
    assert criada.ok
    assert criada.data["refs"] == ["~/Downloads"]
    assert registry.call("work_orders.list", {}, ctx).data[0]["goal"].startswith("Organizar")


def test_objetivo_vazio_e_recusado(ctx, registry):
    assert not registry.call("work_orders.create", {"goal": "   "}, ctx).ok


def test_fila_ordena_por_prioridade(ctx, registry):
    registry.call("work_orders.create", {"goal": "normal", "priority": 2}, ctx)
    registry.call("work_orders.create", {"goal": "urgente", "priority": 1}, ctx)
    fila = registry.call("work_orders.list", {}, ctx).data
    assert [o["goal"] for o in fila] == ["urgente", "normal"]


def test_assumir_tira_da_fila_aberta(ctx, registry):
    ordem = registry.call("work_orders.create", {"goal": "X"}, ctx).data
    assert registry.call("work_orders.claim", {"id": ordem["id"], "by": "cowork"}, ctx).ok
    assert registry.call("work_orders.list", {"status": "open"}, ctx).data == []
    assumidas = registry.call("work_orders.list", {"status": "claimed"}, ctx).data
    assert assumidas[0]["claimed_by"] == "cowork"


def test_nao_da_para_assumir_duas_vezes(ctx, registry):
    """Sem isto, dois executores fariam o mesmo trabalho."""
    ordem = registry.call("work_orders.create", {"goal": "X"}, ctx).data
    registry.call("work_orders.claim", {"id": ordem["id"], "by": "a"}, ctx)
    segunda = registry.call("work_orders.claim", {"id": ordem["id"], "by": "b"}, ctx)
    assert not segunda.ok
    assert "com a" in segunda.error


def test_completar_guarda_o_resultado(ctx, registry):
    ordem = registry.call("work_orders.create", {"goal": "X"}, ctx).data
    fechada = registry.call("work_orders.complete", {
        "id": ordem["id"], "result_summary": "42 notas renomeadas em ~/fiscal/2026-08"
    }, ctx)
    assert fechada.data["status"] == "done"
    assert "42 notas" in fechada.data["result_summary"]


def test_completar_sem_resumo_e_recusado(ctx, registry):
    """O resumo é o que faz o trabalho externo virar memória daqui."""
    ordem = registry.call("work_orders.create", {"goal": "X"}, ctx).data
    assert not registry.call("work_orders.complete", {"id": ordem["id"],
                                                      "result_summary": " "}, ctx).ok


def test_nao_completa_duas_vezes(ctx, registry):
    ordem = registry.call("work_orders.create", {"goal": "X"}, ctx).data
    registry.call("work_orders.complete", {"id": ordem["id"], "result_summary": "feito"}, ctx)
    assert not registry.call("work_orders.complete", {"id": ordem["id"],
                                                      "result_summary": "de novo"}, ctx).ok


def test_descartar(ctx, registry):
    ordem = registry.call("work_orders.create", {"goal": "X"}, ctx).data
    fechada = registry.call("work_orders.drop", {"id": ordem["id"], "reason": "mudou"}, ctx)
    assert fechada.data["status"] == "dropped"
    assert "mudou" in fechada.data["result_summary"]


def test_ordem_inexistente(ctx, registry):
    assert not registry.call("work_orders.claim", {"id": 999}, ctx).ok
