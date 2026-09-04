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
