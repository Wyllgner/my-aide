"""A aplicação web.

**Só leitura.** Nenhuma rota altera dado: concluir tarefa, lançar gasto e
conversar continuam sendo CLI, Telegram ou MCP. Isso não é preguiça — é o que
dispensa confirmação, CSRF e o risco de um clique errado numa aba esquecida.

**Só nesta máquina.** A página mostra tudo, inclusive o que está marcado como
`private`, e não pede senha. Ela é segura exatamente enquanto escutar em
127.0.0.1, e por isso o endereço é constante no código, não opção de
configuração: endereço de escuta em arquivo é o tipo de coisa que se troca para
testar e se esquece de voltar — e aí a terapia, os gastos e as conversas ficam
na rede. Abrir para fora volta a ser uma decisão consciente, e nesse dia vem
autenticação junto.
"""

from __future__ import annotations

import logging

from aide.storage import connect, migrate
from aide.tools.registry import ToolContext

log = logging.getLogger(__name__)

# Constante, não configuração. Ver o docstring do módulo.
ENDERECO = "127.0.0.1"
PORTA_PADRAO = 8787


def criar_app(config=None, conn_factory=None):
    """Monta a aplicação. Recebe as dependências para poder ser testada."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    from aide.config import load_config

    config = config or load_config()

    if conn_factory is None:
        def conn_factory():
            conn = connect(config.db_path)
            migrate(conn)
            return conn

    app = FastAPI(title="my-aide", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.conn_factory = conn_factory

    def contexto() -> ToolContext:
        """`ver_privado=True`: é o dono, na máquina dele, e a porta é local.

        A mesma decisão do terminal. O que a sustenta é o bind — se um dia a
        página escutar fora daqui, isto precisa mudar junto.
        """
        return ToolContext(config=config, conn=conn_factory(), actor="web",
                           ver_privado=True)

    app.state.contexto = contexto

    @app.get("/saude")
    def saude() -> dict:
        return {"ok": True, "escutando": ENDERECO}

    @app.get("/", response_class=HTMLResponse)
    def raiz() -> str:
        from aide.web.paginas import esqueleto

        return esqueleto()

    return app
