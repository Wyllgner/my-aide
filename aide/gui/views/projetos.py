"""Projetos: agrupamento por frente de trabalho."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from aide.gui.views.base import VisaoBase, formatar_prazo


class VisaoProjetos(VisaoBase):
    titulo = "Projetos"
    vazio = "Nenhuma tarefa com projeto ainda."

    def recarregar(self) -> None:
        self.lista.clear()
        projetos = self.modelo.projetos()
        if not projetos:
            self.mostrar_vazio(True)
            return

        momento = self.modelo.momento()
        for nome, total in projetos:
            cabecalho = QListWidgetItem(f"{nome}   ({total})")
            cabecalho.setFlags(Qt.NoItemFlags)
            self.lista.addItem(cabecalho)

            ok, tarefas = self.modelo.chamar(
                "tasks.list", {"filter": "all", "project": nome, "limit": 10})
            for tarefa in tarefas if ok else []:
                prazo, _cor = formatar_prazo(tarefa["due_at"], momento)
                item = QListWidgetItem(f"    {tarefa['title']}\n    {prazo}")
                item.setData(Qt.UserRole, tarefa["id"])
                self.lista.addItem(item)

        self.mostrar_vazio(False)
