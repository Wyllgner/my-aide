"""Janela principal: sidebar fixa + painel.

A conversa é uma visão como as outras. O app é sobre o *estado*; o chat é uma
das formas de mexer nele — se o chat virasse a tela principal, seria só outro
chatbot.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aide.gui import theme

LARGURA_SIDEBAR = 220
INTERVALO_ATUALIZACAO_MS = 60_000


class Sidebar(QWidget):
    """Navegação com contador de pendência ao lado de cada visão."""

    SECOES = (
        ("hoje", "Hoje"),
        ("atrasadas", "Atrasadas"),
        ("projetos", "Projetos"),
        ("notas", "Notas"),
        ("fila", "Fila"),
        (None, None),          # separador
        ("conversa", "Conversa"),
    )

    def __init__(self, ao_trocar):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(LARGURA_SIDEBAR)
        # QWidget puro ignora 'background' de folha de estilo sem isto
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        marca = QLabel("my-aide")
        marca.setObjectName("marca")
        layout.addWidget(marca)

        self.lista = QListWidget()
        self.lista.setObjectName("navegacao")
        self.chaves: list[str] = []

        for chave, rotulo in self.SECOES:
            if chave is None:
                separador = QListWidgetItem()
                separador.setFlags(Qt.NoItemFlags)
                separador.setSizeHint(separador.sizeHint().expandedTo(
                    separador.sizeHint()))
                self.lista.addItem(separador)
                self.chaves.append("")
                continue
            self.lista.addItem(QListWidgetItem(rotulo))
            self.chaves.append(chave)

        self.lista.currentRowChanged.connect(
            lambda linha: ao_trocar(self.chaves[linha]) if self.chaves[linha] else None
        )
        layout.addWidget(self.lista)
        layout.addStretch()
        # sem selecionar aqui: o sinal dispararia antes de a janela existir

    def selecionar(self, chave: str) -> None:
        """Mantém a seleção em sincronia com navegação feita por código."""
        if chave in self.chaves:
            linha = self.chaves.index(chave)
            if self.lista.currentRow() != linha:
                self.lista.setCurrentRow(linha)

    def atualizar_contadores(self, contadores: dict[str, int]) -> None:
        """Número ao lado do rótulo. Zero não aparece — ruído não é informação."""
        rotulos = dict(s for s in self.SECOES if s[0])
        for linha, chave in enumerate(self.chaves):
            if not chave:
                continue
            item = self.lista.item(linha)
            total = contadores.get(chave)
            item.setText(f"{rotulos[chave]}   {total}" if total else rotulos[chave])


class JanelaPrincipal(QMainWindow):
    def __init__(self, modelo, visoes: dict):
        super().__init__()
        self.modelo = modelo
        self.visoes = visoes

        self.setWindowTitle("my-aide")
        self.resize(980, 640)
        self.setStyleSheet(theme.folha_de_estilo())

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(self.mostrar)
        layout.addWidget(self.sidebar)

        self.pilha = QStackedWidget()
        self.pilha.setObjectName("painel")
        self.ordem: list[str] = []
        for chave, visao in visoes.items():
            self.pilha.addWidget(visao)
            self.ordem.append(chave)
        layout.addWidget(self.pilha)

        self.setCentralWidget(central)
        self.sidebar.lista.setCurrentRow(0)

        # a lista fica velha sozinha: uma tarefa vence sem ninguém clicar em nada
        self.relogio = QTimer(self)
        self.relogio.timeout.connect(self.atualizar)
        self.relogio.start(INTERVALO_ATUALIZACAO_MS)

        self.atualizar()

    def mostrar(self, chave: str) -> None:
        if chave not in self.ordem:
            return
        self.pilha.setCurrentIndex(self.ordem.index(chave))
        self.sidebar.selecionar(chave)
        self.atualizar()

    def atualizar(self) -> None:
        self.sidebar.atualizar_contadores(self.modelo.contadores())
        atual = self.pilha.currentWidget()
        if hasattr(atual, "recarregar"):
            atual.recarregar()
