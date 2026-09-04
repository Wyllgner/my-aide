"""Identidade visual. Ver ARQUITETURA.md seção 8.3.

Tokens nomeados por função, não por cor: trocar `bg` e `text` é o que basta
para um tema escuro depois.

A regra que sustenta o resto: cor significa estado da tarefa, nunca decoração.
Se tudo for colorido, o vermelho de "atrasado" para de gritar.
"""

from __future__ import annotations

TOKENS = {
    "bg": "#FFFFFF",
    "bg_sidebar": "#F7F8FA",
    "bg_hover": "#F0F2F5",
    "border": "#E5E7EB",
    "text": "#1A1D21",
    "text_muted": "#6B7280",
    "accent": "#4F46E5",
    "accent_soft": "#EEF0FE",
    "warn": "#D97706",
    "danger": "#DC2626",
    "ok": "#059669",
}

FONTE = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

FOLHA = """
* {{ font-family: {fonte}; color: {text}; }}

QMainWindow, QWidget#painel {{ background: {bg}; }}

QWidget#sidebar {{
    background: {bg_sidebar};
    border-right: 1px solid {border};
}}
QLabel#marca {{
    font-size: 15px; font-weight: 600;
    padding: 16px 16px 12px 16px;
}}
QListWidget#navegacao {{
    background: transparent; border: none;
    font-size: 13px; padding: 4px 8px;
}}
QListWidget#navegacao::item {{
    height: 34px; padding-left: 8px; border-radius: 6px;
}}
QListWidget#navegacao::item:hover {{ background: {bg_hover}; }}
QListWidget#navegacao::item:selected {{
    background: {accent_soft}; color: {accent}; font-weight: 600;
}}

QLabel#cabecalho {{ font-size: 20px; font-weight: 600; padding: 18px 20px 8px; }}
QLabel#subtitulo {{ font-size: 12px; color: {text_muted}; padding: 0 20px 12px; }}
QLabel#vazio {{ color: {text_muted}; font-size: 13px; padding: 32px 20px; }}

QListWidget#lista {{
    background: {bg}; border: none; font-size: 13px;
    padding: 0 12px;
}}
QListWidget#lista::item {{
    border-bottom: 1px solid {border};
    padding: 10px 8px;
}}
QListWidget#lista::item:hover {{ background: {bg_hover}; }}
QListWidget#lista::item:selected {{ background: {accent_soft}; }}

QLineEdit {{
    background: {bg}; border: 1px solid {border}; border-radius: 8px;
    padding: 8px 12px; font-size: 13px;
}}
QLineEdit:focus {{ border-color: {accent}; }}

QTextEdit {{
    background: {bg}; border: 1px solid {border}; border-radius: 8px;
    padding: 8px; font-size: 13px;
}}

QPushButton {{
    background: {accent}; color: #FFFFFF; border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 13px; font-weight: 600;
}}
QPushButton:hover {{ background: #4338CA; }}
QPushButton:disabled {{ background: {border}; color: {text_muted}; }}
QPushButton#secundario {{
    background: transparent; color: {text}; border: 1px solid {border};
    font-weight: 400;
}}
QPushButton#secundario:hover {{ background: {bg_hover}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {border}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def folha_de_estilo() -> str:
    return FOLHA.format(fonte=FONTE, **TOKENS)


def cor_do_prazo(due_at: str | None, agora_iso: str, hoje_ate: str) -> str:
    """A única cor que a lista usa. Vermelho é escasso de propósito."""
    if not due_at:
        return TOKENS["text_muted"]
    if due_at < agora_iso:
        return TOKENS["danger"]
    if due_at <= hoje_ate:
        return TOKENS["warn"]
    return TOKENS["text"]
