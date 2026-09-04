"""Conversa: uma visão como as outras, não o app inteiro.

A chamada à LLM sai numa thread: com ela na thread da interface, a janela
congela por segundos a cada mensagem.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aide.gui import theme


class Trabalhador(QObject):
    respondeu = Signal(str)
    falhou = Signal(str)

    def __init__(self, agente, texto: str):
        super().__init__()
        self.agente = agente
        self.texto = texto

    def executar(self) -> None:
        try:
            self.respondeu.emit(self.agente.ask(self.texto))
        except Exception as exc:  # noqa: BLE001 - a janela não pode morrer com a rede
            self.falhou.emit(f"Não consegui responder: {exc}")


class VisaoConversa(QWidget):
    titulo = "Conversa"

    def __init__(self, modelo, criar_agente):
        super().__init__()
        self.modelo = modelo
        self.criar_agente = criar_agente
        self.agente = None
        self.thread: QThread | None = None
        self.setObjectName("painel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        cabecalho = QLabel("Conversa")
        cabecalho.setObjectName("cabecalho")
        layout.addWidget(cabecalho)

        self.transcricao = QTextEdit()
        self.transcricao.setReadOnly(True)
        layout.addWidget(self.transcricao)

        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 12, 20, 16)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Fale normalmente: 'adia o dentista pra sexta'")
        self.entrada.returnPressed.connect(self.enviar)
        linha.addWidget(self.entrada)
        self.botao = QPushButton("Enviar")
        self.botao.clicked.connect(self.enviar)
        linha.addWidget(self.botao)
        layout.addWidget(caixa)

    # ---------- envio ----------

    def _escrever(self, quem: str, texto: str, cor: str) -> None:
        self.transcricao.append(
            f'<p style="margin:6px 0"><b style="color:{cor}">{quem}</b><br>{texto}</p>'
        )

    def enviar(self) -> None:
        texto = self.entrada.text().strip()
        if not texto or self.thread is not None:
            return

        self._escrever("você", texto, theme.TOKENS["accent"])
        self.entrada.clear()
        self._ocupado(True)

        if self.agente is None:
            self.agente = self.criar_agente()

        self.thread = QThread()
        self.trabalhador = Trabalhador(self.agente, texto)
        self.trabalhador.moveToThread(self.thread)
        self.thread.started.connect(self.trabalhador.executar)
        self.trabalhador.respondeu.connect(self._responder)
        self.trabalhador.falhou.connect(self._erro)
        self.thread.start()

    def _ocupado(self, ocupado: bool) -> None:
        self.botao.setEnabled(not ocupado)
        self.botao.setText("..." if ocupado else "Enviar")
        self.entrada.setEnabled(not ocupado)

    def _encerrar_thread(self) -> None:
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
        self._ocupado(False)
        self.entrada.setFocus()

    def _responder(self, texto: str) -> None:
        self._escrever("assessor", texto, theme.TOKENS["ok"])
        self._encerrar_thread()

    def _erro(self, texto: str) -> None:
        self._escrever("erro", texto, theme.TOKENS["danger"])
        self._encerrar_thread()

    def recarregar(self) -> None:
        """A conversa não se recarrega — o histórico é a própria tela."""
