"""CLI do my-aide.

Ponto de montagem: os comandos vivem em `aide/comandos/`, um módulo por
assunto. Importar cada um aqui é o que os registra no `app` — o decorador
`@app.command()` só roda quando o módulo é carregado.

`_embedder` é reexportado porque a GUI o importa daqui desde antes da quebra.
"""

from __future__ import annotations

from aide.comandos import conversa, daemon, fila, notas, pessoas, relatorios, setup, tarefas
from aide.comandos.base import _embedder, app, console

# os módulos acima são importados pelo efeito colateral de registrar comandos;
# nomeá-los aqui é o que impede o linter de apagar o import e a CLI de ficar vazia.
_MODULOS = (setup, tarefas, notas, pessoas, fila, conversa, daemon, relatorios)

__all__ = ["_embedder", "app", "console"]
