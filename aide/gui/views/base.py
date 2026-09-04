"""Peças comuns das visões."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget

from aide.gui import theme


class VisaoBase(QWidget):
    """Cabeçalho + lista + estado vazio. Toda visão herda isto."""

    titulo = ""
    subtitulo = ""
    vazio = "Nada por aqui."

    def __init__(self, modelo):
        super().__init__()
        self.modelo = modelo
        self.setObjectName("painel")

        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setContentsMargins(0, 0, 0, 0)
        self.layout_principal.setSpacing(0)

        self.cabecalho = QLabel(self.titulo)
        self.cabecalho.setObjectName("cabecalho")
        self.layout_principal.addWidget(self.cabecalho)

        if self.subtitulo:
            legenda = QLabel(self.subtitulo)
            legenda.setObjectName("subtitulo")
            self.layout_principal.addWidget(legenda)

        self.lista = QListWidget()
        self.lista.setObjectName("lista")
        self.layout_principal.addWidget(self.lista)

        self.aviso_vazio = QLabel(self.vazio)
        self.aviso_vazio.setObjectName("vazio")
        self.layout_principal.addWidget(self.aviso_vazio)

    def mostrar_vazio(self, vazio: bool, texto: str | None = None) -> None:
        self.aviso_vazio.setText(texto or self.vazio)
        self.aviso_vazio.setVisible(vazio)
        self.lista.setVisible(not vazio)

    def recarregar(self) -> None:
        raise NotImplementedError


def formatar_prazo(due_at: str | None, momento) -> tuple[str, str]:
    """Texto e cor do prazo. Cor aqui significa estado, não decoração."""
    cor = theme.cor_do_prazo(due_at, momento.agora_iso, momento.hoje_ate)
    if not due_at:
        return "sem prazo", cor
    dia, _, hora = due_at.partition("T")
    hora = hora[:5]
    if dia == momento.agora_iso[:10]:
        return f"hoje {hora}", cor
    _, mes, d = dia.split("-")
    return f"{d}/{mes} {hora}", cor
