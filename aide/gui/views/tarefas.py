"""Hoje e Atrasadas: a lista que você olha todo dia."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidgetItem, QPushButton, QWidget

from aide.gui import theme
from aide.gui.views.base import VisaoBase, formatar_prazo


class VisaoTarefas(VisaoBase):
    def __init__(self, modelo, filtro: str = "today", titulo: str = "Hoje",
                 vazio: str = "Nada para hoje.", com_captura: bool = True):
        self.titulo = titulo
        self.vazio = vazio
        self.filtro = filtro
        super().__init__(modelo)

        if com_captura:
            self.layout_principal.insertWidget(1, self._barra_captura())

        # dois cliques concluem: é a ação que você mais repete
        self.lista.itemDoubleClicked.connect(self._concluir)

    def _barra_captura(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 4, 20, 12)

        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Nova tarefa e Enter")
        self.entrada.returnPressed.connect(self._criar)
        linha.addWidget(self.entrada)

        botao = QPushButton("Adicionar")
        botao.clicked.connect(self._criar)
        linha.addWidget(botao)
        return caixa

    def _criar(self) -> None:
        texto = self.entrada.text().strip()
        if not texto:
            return

        args = {"title": texto}
        # digitar na visão "Hoje" quer dizer "para hoje": sem prazo, a tarefa
        # sairia da lista no mesmo instante em que foi criada
        if self.filtro == "today":
            args["due"] = self.modelo.momento().hoje_ate

        ok, erro = self.modelo.chamar("tasks.create", args)
        if not ok:
            self.mostrar_vazio(True, erro)
            return
        self.entrada.clear()
        self.recarregar()

    def _concluir(self, item: QListWidgetItem) -> None:
        task_id = item.data(Qt.UserRole)
        if task_id:
            self.modelo.chamar("tasks.complete", {"id": task_id})
            self.recarregar()

    def recarregar(self) -> None:
        ok, dados = self.modelo.chamar("tasks.list", {"filter": self.filtro})
        self.lista.clear()
        if not ok:
            self.mostrar_vazio(True, str(dados))
            return

        momento = self.modelo.momento()
        for tarefa in dados:
            prazo, cor = formatar_prazo(tarefa["due_at"], momento)
            marcas = []
            if tarefa.get("project"):
                marcas.append(tarefa["project"])
            if tarefa.get("snooze_count"):
                marcas.append(f"adiada {tarefa['snooze_count']}x")

            item = QListWidgetItem(
                f"{tarefa['title']}\n{prazo}" + (f"  ·  {' · '.join(marcas)}" if marcas else "")
            )
            item.setData(Qt.UserRole, tarefa["id"])
            item.setToolTip("clique duplo para concluir")
            if tarefa.get("priority") == 1:
                item.setForeground(QColor(theme.TOKENS["danger"]))
            elif cor != theme.TOKENS["text"]:
                item.setForeground(QColor(cor))
            self.lista.addItem(item)

        self.mostrar_vazio(not dados)
