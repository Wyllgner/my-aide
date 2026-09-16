"""Sobe a aplicação numa thread, dentro do processo do daemon.

Um processo só continua sendo verdade: o banco tem um dono, e a página fica de
pé exatamente enquanto o assessor está.
"""

from __future__ import annotations

import logging
import threading

from aide.web.app import ENDERECO, PORTA_PADRAO, criar_app

log = logging.getLogger(__name__)


class ServidorWeb:
    def __init__(self, config=None, conn_factory=None, porta: int = PORTA_PADRAO):
        import uvicorn

        self.porta = porta
        self.app = criar_app(config, conn_factory)
        self._servidor = uvicorn.Server(uvicorn.Config(
            self.app,
            # ENDERECO é constante de propósito; ver aide/web/app.py
            host=ENDERECO, port=porta,
            log_level="warning", access_log=False,
        ))
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{ENDERECO}:{self.porta}"

    def start(self) -> threading.Thread:
        self._thread = threading.Thread(target=self._servidor.run,
                                        name="web", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._servidor.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
