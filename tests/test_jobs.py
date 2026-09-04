import threading

from aide.channels.notify import Notifier
from aide.llm.base import LLMProvider, LLMResponse
from aide.scheduler import jobs
from aide.storage import connect, migrate


class FakeNotifier(Notifier):
    def __init__(self, ok=True):
        self.sent = []
        self.ok = ok

    def send(self, title, body, urgency="normal"):
        self.sent.append((title, body, urgency))
        return self.ok


class FakeLLM(LLMProvider):
    def complete(self, messages, *, fast=False, tools=None, purpose="chat"):
        return LLMResponse(text="Resumo curto.", model="fake")


def _deps(ctx, notifier=None):
    return jobs.JobDeps(config=ctx.config, llm=FakeLLM(),
                        notifier=notifier or FakeNotifier(), conn=ctx.conn)


def test_tick_entrega_lembrete_vencido(ctx, registry):
    registry.call("reminders.create", {"text": "X", "when": "2020-01-01T09:00",
                                       "repeat": "daily"}, ctx)
    notifier = FakeNotifier()
    assert jobs.tick_reminders(_deps(ctx, notifier)) == 1
    assert notifier.sent[0][0] == "Lembrete"


def test_tick_nao_marca_entregue_se_a_notificacao_falha(ctx, registry):
    registry.call("reminders.create", {"text": "X", "when": "2020-01-01T09:00",
                                       "repeat": "daily"}, ctx)
    assert jobs.tick_reminders(_deps(ctx, FakeNotifier(ok=False))) == 0
    pendentes = ctx.conn.execute(
        "SELECT COUNT(*) c FROM reminders WHERE status = 'pending'").fetchone()["c"]
    assert pendentes == 1


def test_eval_conditions_so_avisa_severidade_alta(ctx, registry):
    registry.call("tasks.create", {"title": "Velha"}, ctx)  # zumbi = severidade 3
    notifier = FakeNotifier()
    assert jobs.eval_conditions(_deps(ctx, notifier)) == 0
    assert notifier.sent == []


def test_eval_conditions_cobra_o_que_importa(ctx, registry):
    registry.call("tasks.create", {"title": "Boleto", "due": "2020-01-01T09:00"}, ctx)
    notifier = FakeNotifier()
    assert jobs.eval_conditions(_deps(ctx, notifier)) == 1
    titulo, corpo, urgencia = notifier.sent[0]
    assert titulo == "Precisa de você" and urgencia == "critical"
    assert "Boleto" in corpo


def test_briefing_vazio_nao_notifica(ctx):
    notifier = FakeNotifier()
    assert jobs.briefing_manha(_deps(ctx, notifier)) is False
    assert notifier.sent == []


def test_conexao_e_por_thread(tmp_path, ctx):
    """O APScheduler roda jobs em worker threads; sqlite recusa conexão de outra."""
    caminho = tmp_path / "j.db"
    migrate(connect(caminho))
    deps = jobs.JobDeps(config=ctx.config, llm=FakeLLM(), notifier=FakeNotifier(),
                        conn_factory=lambda: connect(caminho))

    vistas = []

    def trabalhar():
        vistas.append(deps.db())
        jobs.tick_reminders(deps)  # não pode levantar ProgrammingError

    principal = deps.db()
    t = threading.Thread(target=trabalhar)
    t.start()
    t.join()

    assert len(vistas) == 1
    assert vistas[0] is not principal


def test_sem_conexao_nem_fabrica_falha(ctx):
    deps = jobs.JobDeps(config=ctx.config, llm=FakeLLM(), notifier=FakeNotifier())
    try:
        deps.db()
    except RuntimeError as exc:
        assert "conn_factory" in str(exc)
    else:
        raise AssertionError("deveria ter falhado")


def test_agendamento_semanal_invalido_falha(ctx):
    try:
        jobs._semanal("sempre 19:00")
    except ValueError as exc:
        assert "domingo 19:00" in str(exc)
    else:
        raise AssertionError("deveria ter falhado")


def test_agendamento_semanal_traduz_o_dia():
    assert jobs._semanal("domingo 19:00") == ("sun", 19, 0)
    assert jobs._semanal("terça 08:30") == ("tue", 8, 30)


def test_usage_sink_do_embedder_funciona_em_outra_thread(tmp_path, ctx):
    """O bot roda em thread própria; sink com conexão fixa derruba a busca semântica."""
    from aide.core.orchestrator import record_usage

    caminho = tmp_path / "e.db"
    migrate(connect(caminho))
    deps = jobs.JobDeps(config=ctx.config, llm=FakeLLM(), notifier=FakeNotifier(),
                        conn_factory=lambda: connect(caminho))
    sink = record_usage(deps.db)

    erros = []

    def de_outra_thread():
        try:
            sink("text-embedding-3-small", "embedding", 10, 0, 5)
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    t = threading.Thread(target=de_outra_thread)
    t.start()
    t.join()

    assert erros == []
    total = deps.db().execute("SELECT COUNT(*) c FROM llm_usage").fetchone()["c"]
    assert total == 1


def test_queue_work_enfileira_projeto_parado(ctx, registry):
    from datetime import timedelta

    registry.call("tasks.create", {"title": "X", "project": "parado"}, ctx)
    antigo = (jobs.JobDeps(config=ctx.config, llm=FakeLLM(), notifier=FakeNotifier(),
                           conn=ctx.conn).now - timedelta(days=30)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET last_touched_at = ?, created_at = ?", (antigo, antigo))

    assert jobs.queue_work(_deps(ctx)) == 1
    fila = registry.call("work_orders.list", {}, ctx).data
    assert "parado" in fila[0]["goal"]


def test_queue_work_nao_duplica(ctx, registry):
    """Rodando 2x por dia, sem essa checagem a fila enche de repetição."""
    from datetime import timedelta

    registry.call("tasks.create", {"title": "X", "project": "parado"}, ctx)
    antigo = (jobs.JobDeps(config=ctx.config, llm=FakeLLM(), notifier=FakeNotifier(),
                           conn=ctx.conn).now - timedelta(days=30)).isoformat(timespec="minutes")
    ctx.conn.execute("UPDATE tasks SET last_touched_at = ?, created_at = ?", (antigo, antigo))

    jobs.queue_work(_deps(ctx))
    assert jobs.queue_work(_deps(ctx)) == 0


def test_queue_work_ignora_projeto_ativo(ctx, registry):
    registry.call("tasks.create", {"title": "X", "project": "vivo"}, ctx)
    assert jobs.queue_work(_deps(ctx)) == 0


def _nota_no_vault(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    return registry.call("notes.create", {"title": "Carro", "body": "trocar o óleo"}, ctx).data


def test_reindex_pega_arquivo_editado_a_mao(ctx, registry, tmp_path):
    """Editar o .md no editor sem isto deixa a busca respondendo o texto antigo."""
    import os
    import time
    from pathlib import Path

    from aide.storage.search import buscar_texto

    nota = _nota_no_vault(ctx, registry, tmp_path)
    caminho = Path(nota["path"])
    caminho.write_text(caminho.read_text() + "\n\ntambém revisar a suspensão\n")
    # garante mtime posterior ao updated_at gravado
    futuro = time.time() + 60
    os.utime(caminho, (futuro, futuro))

    assert buscar_texto(ctx.conn, "suspensão") == []
    assert jobs.reindex_vault(_deps(ctx)) == 1
    assert buscar_texto(ctx.conn, "suspensão")


def test_reindex_ignora_arquivo_intocado(ctx, registry, tmp_path):
    _nota_no_vault(ctx, registry, tmp_path)
    assert jobs.reindex_vault(_deps(ctx)) == 0


def test_reindex_sobrevive_a_arquivo_sumido(ctx, registry, tmp_path):
    from pathlib import Path

    nota = _nota_no_vault(ctx, registry, tmp_path)
    Path(nota["path"]).unlink()
    assert jobs.reindex_vault(_deps(ctx)) == 0  # não levanta
