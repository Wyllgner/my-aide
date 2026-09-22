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


# ---------- tasks.update ----------

def test_update_altera_campos(ctx, registry):
    tarefa = registry.call("tasks.create", {"title": "Rascunho"}, ctx).data
    atualizada = registry.call("tasks.update", {
        "id": tarefa["id"], "title": "Definitivo", "priority": 1,
        "project": "viagem", "tags": "carro", "notes": "levar documento",
    }, ctx)
    assert atualizada.ok
    assert atualizada.data["title"] == "Definitivo"
    assert atualizada.data["priority_label"] == "urgente"
    assert atualizada.data["project"] == "viagem"


def test_update_marca_que_a_tarefa_foi_tocada(ctx, registry):
    """`last_touched_at` não é enfeite: projeto_parado e zumbi dependem dele.

    Sem isto, mexer numa tarefa não a tirava da mira das regras e o assessor
    cobrava algo que você acabou de tratar.
    """
    def tocada_em():
        return ctx.conn.execute(
            "SELECT last_touched_at FROM tasks WHERE id = ?", (tarefa["id"],)
        ).fetchone()["last_touched_at"]

    tarefa = registry.call("tasks.create", {"title": "X"}, ctx).data
    # envelhece a marca: é o estado que faz as regras cobrarem
    ctx.conn.execute("UPDATE tasks SET last_touched_at = '2026-01-01 00:00' WHERE id = ?",
                     (tarefa["id"],))
    assert tocada_em() == "2026-01-01 00:00"

    registry.call("tasks.update", {"id": tarefa["id"], "notes": "andei nisso"}, ctx)
    assert tocada_em() > "2026-01-01 00:00"


def test_update_remove_o_prazo_com_string_vazia(ctx, registry):
    tarefa = registry.call(
        "tasks.create", {"title": "X", "due": "2026-09-20T09:00"}, ctx).data
    assert tarefa["due_at"]
    limpa = registry.call("tasks.update", {"id": tarefa["id"], "due": ""}, ctx)
    assert limpa.data["due_at"] is None


def test_update_rejeita_prazo_que_nao_e_iso(ctx, registry):
    tarefa = registry.call("tasks.create", {"title": "X"}, ctx).data
    erro = registry.call("tasks.update", {"id": tarefa["id"], "due": "amanhã"}, ctx)
    assert not erro.ok
    assert "ISO 8601" in erro.error


def test_update_sem_campo_nenhum_reclama(ctx, registry):
    tarefa = registry.call("tasks.create", {"title": "X"}, ctx).data
    vazio = registry.call("tasks.update", {"id": tarefa["id"]}, ctx)
    assert not vazio.ok
    assert "nada para alterar" in vazio.error


def test_update_em_tarefa_inexistente_falha(ctx, registry):
    assert not registry.call("tasks.update", {"id": 999, "title": "X"}, ctx).ok


def test_update_nao_ressuscita_tarefa_apagada(ctx, registry):
    tarefa = registry.call("tasks.create", {"title": "X"}, ctx).data
    ctx.conn.execute("UPDATE tasks SET deleted_at = datetime('now') WHERE id = ?",
                     (tarefa["id"],))
    assert not registry.call("tasks.update", {"id": tarefa["id"], "title": "Y"}, ctx).ok


# ---------- recorrência de tarefa ----------

def test_concluir_tarefa_que_se_repete_cria_a_proxima(ctx, registry):
    """Era o buraco: `recurrence` entrava no banco e ninguém lia de volta, então
    o aluguel concluído em setembro não voltava em outubro."""
    tarefa = registry.call("tasks.create", {"title": "pagar o aluguel",
                                            "due": "2026-10-10T09:00",
                                            "recurrence": "monthly"}, ctx).data

    feito = registry.call("tasks.complete", {"id": tarefa["id"]}, ctx).data
    assert feito["proxima"]["due_at"].startswith("2026-11-10")

    nova = registry.call("tasks.list", {"filter": "all"}, ctx).data
    assert any(t["title"] == "pagar o aluguel" and t["status"] == "open" for t in nova)


def test_a_proxima_herda_o_que_define_a_tarefa(ctx, registry):
    tarefa = registry.call("tasks.create", {
        "title": "revisar o backup", "due": "2026-10-01T08:00", "recurrence": "weekly",
        "priority": 1, "project": "casa", "tags": "infra", "notes": "conferir o restore",
    }, ctx).data
    proxima_id = registry.call("tasks.complete", {"id": tarefa["id"]}, ctx).data["proxima"]["id"]

    nova = next(t for t in registry.call("tasks.list", {"filter": "all"}, ctx).data
                if t["id"] == proxima_id)
    assert (nova["priority"], nova["project"], nova["tags"]) == (1, "casa", "infra")
    assert nova["recurrence"] == "weekly"


def test_tarefa_sem_recorrencia_nao_volta(ctx, registry):
    tarefa = registry.call("tasks.create", {"title": "coisa única"}, ctx).data
    assert "proxima" not in registry.call("tasks.complete", {"id": tarefa["id"]}, ctx).data


def test_recorrencia_desconhecida_e_recusada_na_criacao(ctx, registry):
    """Aceitar texto livre era prometer uma repetição que nunca aconteceria."""
    resultado = registry.call("tasks.create", {"title": "x", "recurrence": "quando der"}, ctx)
    assert not resultado.ok
    assert "monthly" in resultado.error


def test_renovar_tarefa_atrasada_nao_nasce_atrasada(ctx, registry):
    """Concluir hoje o que vencia em janeiro não pode criar algo já vencido."""
    from datetime import timedelta

    from aide.core.context import now_in

    agora = now_in(ctx.config.timezone)
    antiga = (agora - timedelta(days=90)).replace(hour=9, minute=0)
    tarefa = registry.call("tasks.create", {"title": "vistoria", "recurrence": "monthly",
                                            "due": antiga.isoformat(timespec="minutes")}, ctx).data

    proxima = registry.call("tasks.complete", {"id": tarefa["id"]}, ctx).data["proxima"]
    assert proxima["due_at"] >= agora.date().isoformat()


def test_recorrencia_antiga_em_texto_livre_nao_quebra(ctx, registry):
    """Linhas gravadas quando a coluna aceitava qualquer coisa continuam existindo."""
    cur = ctx.conn.execute(
        "INSERT INTO tasks (title, status, recurrence) VALUES ('velha', 'open', 'every fortnight')")
    feito = registry.call("tasks.complete", {"id": cur.lastrowid}, ctx)
    assert feito.ok
    assert "proxima" not in feito.data
