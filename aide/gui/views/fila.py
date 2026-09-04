"""Fila: o que espera um executor externo."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QListWidgetItem

from aide.gui import theme
from aide.gui.views.base import VisaoBase

CORES = {"open": "text", "claimed": "accent", "done": "ok", "dropped": "text_muted"}


class VisaoFila(VisaoBase):
    titulo = "Fila de trabalho"
    subtitulo = "O que o assessor separou para um executor externo fazer."
    vazio = "Fila vazia."

    def recarregar(self) -> None:
        ok, dados = self.modelo.chamar("work_orders.list", {"status": "all", "limit": 30})
        self.lista.clear()
        if not ok:
            self.mostrar_vazio(True, str(dados))
            return

        for ordem in dados:
            linhas = [ordem["goal"], ordem["status"]]
            if ordem.get("result_summary"):
                linhas.append(ordem["result_summary"])
            item = QListWidgetItem("\n".join(linhas))
            item.setData(Qt.UserRole, ordem["id"])
            item.setForeground(QColor(theme.TOKENS[CORES.get(ordem["status"], "text")]))
            self.lista.addItem(item)

        self.mostrar_vazio(not dados)
