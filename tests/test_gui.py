"""GUI sem tela: QT_QPA_PLATFORM=offscreen roda no CI e aqui."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel

from aide.gui import theme
from aide.gui.app import JanelaPrincipal
from aide.gui.modelo import Modelo


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def modelo(ctx):
    return Modelo(ctx.config, conn=ctx.conn)


@pytest.fixture
def janela(qapp, modelo):
    return JanelaPrincipal(modelo, {"hoje": QLabel("hoje"), "conversa": QLabel("chat")})


def test_a_gui_escreve_pelo_registry_nao_pelo_banco(modelo):
    """Mesma auditoria e validação das outras portas."""
    ok, _ = modelo.chamar("tasks.create", {"title": "Da GUI"})
    assert ok
    registrado = modelo.conn.execute(
        "SELECT actor, tool FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    assert registrado["actor"] == "gui"
    assert registrado["tool"] == "tasks.create"


def test_erro_de_tool_volta_tratado(modelo):
    ok, erro = modelo.chamar("tasks.complete", {"id": 999})
    assert not ok
    assert "não existe" in erro


def test_contadores_refletem_o_estado(modelo, registry, ctx):
    assert modelo.contadores()["atrasadas"] == 0
    registry.call("tasks.create", {"title": "Velha", "due": "2020-01-01T09:00"}, ctx)
    assert modelo.contadores()["atrasadas"] == 1


def test_contador_ignora_concluida(modelo, registry, ctx):
    tarefa = registry.call("tasks.create", {"title": "X", "due": "2020-01-01T09:00"},
                           ctx).data
    registry.call("tasks.complete", {"id": tarefa["id"]}, ctx)
    assert modelo.contadores()["atrasadas"] == 0


def test_projetos_agrupam(modelo, registry, ctx):
    registry.call("tasks.create", {"title": "A", "project": "casa"}, ctx)
    registry.call("tasks.create", {"title": "B", "project": "casa"}, ctx)
    registry.call("tasks.create", {"title": "C", "project": "obra"}, ctx)
    assert modelo.projetos() == [("casa", 2), ("obra", 1)]


def test_sidebar_esconde_contador_zero(janela):
    """Zero não é informação, é ruído."""
    rotulos = [janela.sidebar.lista.item(i).text()
               for i in range(janela.sidebar.lista.count())]
    assert "Fila" in rotulos          # sem número
    assert not any(r.endswith("0") for r in rotulos)


def test_sidebar_mostra_contador_quando_ha_pendencia(janela, registry, ctx):
    registry.call("tasks.create", {"title": "X", "due": "2020-01-01T09:00"}, ctx)
    janela.atualizar()
    rotulos = [janela.sidebar.lista.item(i).text()
               for i in range(janela.sidebar.lista.count())]
    assert any(r.startswith("Atrasadas") and r.strip().endswith("1") for r in rotulos)


def test_troca_de_visao(janela):
    janela.mostrar("conversa")
    assert janela.pilha.currentWidget().text() == "chat"
    janela.mostrar("hoje")
    assert janela.pilha.currentWidget().text() == "hoje"


def test_visao_desconhecida_e_ignorada(janela):
    atual = janela.pilha.currentWidget()
    janela.mostrar("nao_existe")
    assert janela.pilha.currentWidget() is atual


def test_cor_do_prazo_marca_estado():
    agora, hoje = "2026-09-03T10:00", "2026-09-03T23:59"
    assert theme.cor_do_prazo("2026-09-01T09:00", agora, hoje) == theme.TOKENS["danger"]
    assert theme.cor_do_prazo("2026-09-03T18:00", agora, hoje) == theme.TOKENS["warn"]
    assert theme.cor_do_prazo("2026-12-01T09:00", agora, hoje) == theme.TOKENS["text"]
    assert theme.cor_do_prazo(None, agora, hoje) == theme.TOKENS["text_muted"]


def test_folha_de_estilo_resolve_todos_os_tokens():
    """Placeholder não substituído vira regra CSS inválida, e o Qt ignora calado."""
    import re

    folha = theme.folha_de_estilo()
    assert re.search(r"\{[a-z_]+\}", folha) is None

    # warn/danger/ok não entram na folha de propósito: são cor de *estado*,
    # aplicadas item a item por cor_do_prazo, não estilo do widget
    estruturais = {k: v for k, v in theme.TOKENS.items()
                   if k not in {"warn", "danger", "ok"}}
    for nome, cor in estruturais.items():
        assert cor in folha, nome


# ---------- visões ----------

from aide.gui.views import VisaoFila, VisaoNotas, VisaoProjetos, VisaoTarefas
from aide.gui.views.base import formatar_prazo


def test_hoje_lista_e_conclui_com_clique_duplo(qapp, modelo, registry, ctx):
    registry.call("tasks.create", {"title": "Boleto", "due": "2020-01-01T09:00"}, ctx)
    visao = VisaoTarefas(modelo)
    visao.recarregar()
    assert visao.lista.count() == 1

    visao._concluir(visao.lista.item(0))
    assert visao.lista.count() == 0
    status = ctx.conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()["status"]
    assert status == "done"


def test_captura_cria_tarefa(qapp, modelo):
    visao = VisaoTarefas(modelo)
    visao.entrada.setText("Comprar pão")
    visao._criar()
    assert visao.entrada.text() == ""
    assert visao.lista.count() == 1


def test_captura_vazia_nao_cria_nada(qapp, modelo):
    visao = VisaoTarefas(modelo)
    visao.entrada.setText("   ")
    visao._criar()
    assert modelo.conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 0


def test_estado_vazio_aparece_quando_nao_ha_nada(qapp, modelo):
    visao = VisaoTarefas(modelo)
    visao.recarregar()
    assert visao.aviso_vazio.isVisible() or not visao.lista.isVisible()


def test_atrasadas_usa_outro_filtro(qapp, modelo, registry, ctx):
    registry.call("tasks.create", {"title": "Futura", "due": "2030-01-01T09:00"}, ctx)
    visao = VisaoTarefas(modelo, filtro="overdue", titulo="Atrasadas")
    visao.recarregar()
    assert visao.lista.count() == 0


def test_projetos_agrupa_com_cabecalho(qapp, modelo, registry, ctx):
    registry.call("tasks.create", {"title": "A", "project": "casa"}, ctx)
    registry.call("tasks.create", {"title": "B", "project": "casa"}, ctx)
    visao = VisaoProjetos(modelo)
    visao.recarregar()
    # 1 cabeçalho + 2 tarefas
    assert visao.lista.count() == 3
    assert "casa" in visao.lista.item(0).text()


def test_notas_lista_e_abre(qapp, modelo, registry, ctx, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Carro", "body": "trocar o óleo"}, ctx)
    visao = VisaoNotas(modelo)
    visao.recarregar()
    assert visao.lista.count() == 1

    visao._abrir(visao.lista.item(0))
    assert "trocar o óleo" in visao.leitura.toPlainText()


def test_busca_sem_resultado_avisa_o_termo(qapp, modelo, registry, ctx, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Carro", "body": "óleo"}, ctx)
    visao = VisaoNotas(modelo)
    visao.busca.setText("astrofísica")
    visao.recarregar()
    assert "astrofísica" in visao.aviso_vazio.text()


def test_fila_mostra_status_e_resultado(qapp, modelo, registry, ctx):
    ordem = registry.call("work_orders.create", {"goal": "Organizar fiscais"}, ctx).data
    registry.call("work_orders.complete", {"id": ordem["id"],
                                           "result_summary": "42 arquivos"}, ctx)
    visao = VisaoFila(modelo)
    visao.recarregar()
    texto = visao.lista.item(0).text()
    assert "Organizar fiscais" in texto and "done" in texto and "42 arquivos" in texto


def test_formatar_prazo(modelo):
    momento = modelo.momento()
    hoje = momento.agora_iso[:10]
    assert formatar_prazo(f"{hoje}T18:00", momento)[0] == "hoje 18:00"
    assert formatar_prazo("2026-12-25T09:00", momento)[0] == "25/12 09:00"
    assert formatar_prazo(None, momento)[0] == "sem prazo"


def test_tarefa_criada_em_hoje_aparece_em_hoje(qapp, modelo):
    """Sem prazo, a tarefa sumiria da lista no instante em que foi criada."""
    visao = VisaoTarefas(modelo)
    visao.entrada.setText("Comprar pão")
    visao._criar()
    assert visao.lista.count() == 1
    assert "hoje" in visao.lista.item(0).text()


# ---------- conversa, bandeja e montagem ----------

from aide.gui.views.conversa import VisaoConversa


class AgenteFake:
    def __init__(self, resposta="feito", erro=None):
        self.resposta = resposta
        self.erro = erro
        self.perguntas = []

    def ask(self, texto):
        self.perguntas.append(texto)
        if self.erro:
            raise self.erro
        return self.resposta


def _conversa(modelo, agente):
    return VisaoConversa(modelo, lambda: agente)


def test_conversa_envia_e_mostra_resposta(qapp, modelo):
    agente = AgenteFake("Criei a tarefa.")
    visao = _conversa(modelo, agente)
    visao.entrada.setText("me lembra do IPVA")
    visao.enviar()
    visao.thread.wait(5000)
    qapp.processEvents()

    assert agente.perguntas == ["me lembra do IPVA"]
    assert "Criei a tarefa." in visao.transcricao.toPlainText()


def test_conversa_nao_congela_a_janela(qapp, modelo):
    """A chamada à LLM sai da thread da interface."""
    import threading

    thread_da_ui = threading.get_ident()
    vistas = []

    class Espia(AgenteFake):
        def ask(self, texto):
            vistas.append(threading.get_ident())
            return "ok"

    visao = _conversa(modelo, Espia())
    visao.entrada.setText("oi")
    visao.enviar()
    visao.thread.wait(5000)
    qapp.processEvents()

    assert vistas and vistas[0] != thread_da_ui


def test_falha_da_llm_nao_derruba_a_janela(qapp, modelo):
    visao = _conversa(modelo, AgenteFake(erro=RuntimeError("sem rede")))
    visao.entrada.setText("oi")
    visao.enviar()
    visao.thread.wait(5000)
    qapp.processEvents()

    assert "sem rede" in visao.transcricao.toPlainText()
    assert visao.botao.isEnabled()  # voltou a aceitar mensagem


def test_conversa_ignora_mensagem_vazia(qapp, modelo):
    agente = AgenteFake()
    visao = _conversa(modelo, agente)
    visao.entrada.setText("   ")
    visao.enviar()
    assert agente.perguntas == []


def test_bandeja_resume_o_estado(qapp, modelo, registry, ctx):
    from aide.gui.tray import Bandeja

    registry.call("tasks.create", {"title": "X", "due": "2020-01-01T09:00"}, ctx)
    bandeja = Bandeja(modelo, janela=None, ao_sair=lambda: None)
    assert "atrasada" in bandeja.acao_resumo.text()
    assert "my-aide" in bandeja.toolTip()


def test_montagem_completa_do_app(qapp, ctx, monkeypatch):
    """Prova que todas as visões constroem juntas, sem entrar no loop."""
    from aide.gui import main as gui_main

    monkeypatch.setattr(gui_main, "__name__", "aide.gui.main")
    _, janela, _bandeja = gui_main.construir(config=ctx.config, app=qapp)
    assert janela.ordem == ["hoje", "atrasadas", "projetos", "notas", "fila", "conversa"]
    for chave in janela.ordem:
        janela.mostrar(chave)


def test_navegacao_por_codigo_move_a_selecao(janela):
    """A bandeja e o relógio navegam sem clique; a sidebar tem de acompanhar."""
    janela.mostrar("conversa")
    linha = janela.sidebar.lista.currentRow()
    assert janela.sidebar.chaves[linha] == "conversa"
