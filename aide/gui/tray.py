"""Ícone de bandeja: o assessor visível sem a janela aberta."""

from __future__ import annotations

from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from aide.gui import theme

TAMANHO = 32


def _icone(atrasadas: int) -> QIcon:
    """Ponto colorido: cinza tranquilo, vermelho quando há atraso."""
    pixmap = QPixmap(TAMANHO, TAMANHO)
    pixmap.fill(QColor(0, 0, 0, 0))

    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.Antialiasing)
    cor = theme.TOKENS["danger"] if atrasadas else theme.TOKENS["accent"]
    pintor.setBrush(QColor(cor))
    pintor.setPen(QColor(cor))
    pintor.drawEllipse(4, 4, TAMANHO - 8, TAMANHO - 8)
    pintor.end()
    return QIcon(pixmap)


class Bandeja(QSystemTrayIcon):
    def __init__(self, modelo, janela, ao_sair):
        super().__init__(_icone(0))
        self.modelo = modelo
        self.janela = janela

        menu = QMenu()
        abrir = QAction("Abrir my-aide", menu)
        abrir.triggered.connect(self._abrir)
        menu.addAction(abrir)

        self.acao_resumo = QAction("carregando...", menu)
        self.acao_resumo.setEnabled(False)
        menu.addAction(self.acao_resumo)

        menu.addSeparator()
        sair = QAction("Sair", menu)
        sair.triggered.connect(ao_sair)
        menu.addAction(sair)

        self.setContextMenu(menu)
        self.activated.connect(self._clicou)
        self.atualizar()

    def _clicou(self, motivo) -> None:
        if motivo == QSystemTrayIcon.Trigger:
            self._abrir()

    def _abrir(self) -> None:
        self.janela.show()
        self.janela.raise_()
        self.janela.activateWindow()
        self.janela.atualizar()

    def atualizar(self) -> None:
        contadores = self.modelo.contadores()
        atrasadas = contadores.get("atrasadas", 0)
        hoje = contadores.get("hoje", 0)

        self.setIcon(_icone(atrasadas))
        resumo = f"{hoje} para hoje" + (f", {atrasadas} atrasada(s)" if atrasadas else "")
        self.acao_resumo.setText(resumo)
        self.setToolTip(f"my-aide — {resumo}")
