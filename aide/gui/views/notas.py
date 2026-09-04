"""Notas: lista e busca híbrida."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidgetItem, QTextEdit, QWidget

from aide.gui import theme
from aide.gui.views.base import VisaoBase


class VisaoNotas(VisaoBase):
    titulo = "Notas"
    vazio = "Nenhuma nota ainda."

    def __init__(self, modelo):
        super().__init__(modelo)
        self.layout_principal.insertWidget(1, self._barra_busca())

        self.leitura = QTextEdit()
        self.leitura.setReadOnly(True)
        self.leitura.setVisible(False)
        self.layout_principal.addWidget(self.leitura)

        self.lista.itemClicked.connect(self._abrir)

    def _barra_busca(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 4, 20, 12)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por significado, não só palavra")
        self.busca.returnPressed.connect(self.recarregar)
        linha.addWidget(self.busca)
        return caixa

    def _abrir(self, item: QListWidgetItem) -> None:
        nota_id = item.data(Qt.UserRole)
        if not nota_id:
            return
        ok, nota = self.modelo.chamar("notes.read", {"id": nota_id})
        self.leitura.setVisible(True)
        self.leitura.setPlainText(nota["body"] if ok else str(nota))

    def recarregar(self) -> None:
        termo = self.busca.text().strip()
        if termo:
            ok, dados = self.modelo.chamar("notes.search", {"query": termo, "limit": 15})
            sem_resultado = f"Nada encontrado para {termo!r}."
        else:
            ok, dados = self.modelo.chamar("notes.list", {"limit": 30})
            sem_resultado = None

        self.lista.clear()
        self.leitura.setVisible(False)
        if not ok:
            self.mostrar_vazio(True, str(dados))
            return

        for nota in dados:
            rotulo = nota["title"]
            if nota.get("tags"):
                rotulo += f"\n{nota['tags']}"
            item = QListWidgetItem(rotulo)
            item.setData(Qt.UserRole, nota["id"])
            if nota.get("tags"):
                item.setForeground(QColor(theme.TOKENS["text_muted"]))
            self.lista.addItem(item)

        self.mostrar_vazio(not dados, sem_resultado)
