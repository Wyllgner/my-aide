"""Ponto de entrada do app."""

from __future__ import annotations

import signal
import sys


def construir(config=None, app=None):
    """Monta app, janela e bandeja — sem entrar no loop de eventos.

    Separado de `main` de propósito: montar é o que dá para testar; `exec()`
    bloqueia até a janela fechar.
    """
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from aide.cli import _embedder
    from aide.config import load_config
    from aide.core.orchestrator import Orchestrator, record_usage
    from aide.gui.app import JanelaPrincipal
    from aide.gui.modelo import Modelo
    from aide.gui.tray import Bandeja
    from aide.gui.views import VisaoFila, VisaoNotas, VisaoProjetos, VisaoTarefas
    from aide.gui.views.conversa import VisaoConversa
    from aide.llm import build_provider

    config = config or load_config()
    app = app or QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("my-aide")

    modelo = Modelo(config)
    modelo.embedder = _embedder(config, modelo.conn)

    def criar_agente():
        llm = build_provider(config, usage_sink=record_usage(modelo.conn))
        # sem confirmação interativa ainda: tool 'confirm' é recusada, como no bot
        return Orchestrator(config, modelo.conn, llm, actor="gui",
                            embedder=modelo.embedder, confirm=lambda *_: False)

    visoes = {
        "hoje": VisaoTarefas(modelo),
        "atrasadas": VisaoTarefas(modelo, filtro="overdue", titulo="Atrasadas",
                                  vazio="Nada atrasado.", com_captura=False),
        "projetos": VisaoProjetos(modelo),
        "notas": VisaoNotas(modelo),
        "fila": VisaoFila(modelo),
        "conversa": VisaoConversa(modelo, criar_agente),
    }

    janela = JanelaPrincipal(modelo, visoes)

    bandeja = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        bandeja = Bandeja(modelo, janela, app.quit)
        # fechar a janela some para a bandeja; o assessor continua ali
        app.setQuitOnLastWindowClosed(False)

    return app, janela, bandeja


def main() -> int:
    from PySide6.QtCore import QTimer

    app, janela, bandeja = construir()
    janela.show()

    relogios = []
    if bandeja:
        bandeja.show()
        relogio = QTimer()
        relogio.timeout.connect(bandeja.atualizar)
        relogio.start(60_000)
        relogios.append(relogio)

    # ctrl-c no terminal precisa de uma brecha para o Python processar o sinal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    respiro = QTimer()
    respiro.timeout.connect(lambda: None)
    respiro.start(200)
    relogios.append(respiro)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
