"""CLI do my-aide.

Ponto de montagem: os comandos vivem em `aide/comandos/`, um módulo por
assunto. Importar cada um aqui é o que os registra no `app` — o decorador
`@app.command()` só roda quando o módulo é carregado.
"""

from __future__ import annotations

from importlib import import_module

from aide.comandos.base import app, console

# Um módulo por assunto, e a ordem importa duas vezes: ela registra os comandos
# (o `@app.command()` só roda quando o módulo carrega) e, porque cada comando
# declara seu painel, ela também é a ordem em que os painéis saem no --help. O
# que se usa todo dia vem primeiro; instalação, por último.
_MODULOS = tuple(import_module(f"aide.comandos.{nome}") for nome in (
    "tarefas", "lembretes", "conversa", "notas", "gastos", "pessoas",
    "relatorios", "fila", "daemon", "setup",
))

__all__ = ["app", "console"]
