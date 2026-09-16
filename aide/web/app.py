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
    from fastapi.responses import HTMLResponse, Response

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

        `auditar=False` porque abrir uma tela não é um acontecimento: a trilha
        registra o que mudou, e aqui nada muda. Vale enquanto não houver rota
        de escrita, e é isso que `test_nenhuma_rota_escreve` protege.
        """
        return ToolContext(config=config, conn=conn_factory(), actor="web",
                           ver_privado=True, auditar=False)

    app.state.contexto = contexto

    def saldo_atual() -> dict | None:
        """O rodapé da lateral. Falhar aqui não pode derrubar a página inteira."""
        from aide.llm import custo as calculo

        try:
            return calculo.saldo_estimado(conn_factory(), config)
        except Exception:
            log.warning("não consegui ler o saldo para a lateral", exc_info=True)
            return None

    def render(corpo: str, ativo: str) -> str:
        from aide.web.paginas import pagina

        return pagina(corpo, ativo=ativo, saldo=saldo_atual())

    app.state.render = render

    @app.get("/saude")
    def saude() -> dict:
        return {"ok": True, "escutando": ENDERECO}

    @app.get("/app.css")
    def folha_de_estilo() -> Response:
        from aide.web.estilo import CSS

        return Response(CSS, media_type="text/css",
                        headers={"cache-control": "max-age=300"})

    # Uma rota por tela. As que ainda não têm conteúdo respondem a moldura com
    # um aviso — assim a navegação inteira já é navegável e testável.
    from aide.core.context import now_in
    from aide.tools import registry as toolbelt
    from aide.web import telas as conteudo
    from aide.web.paginas import TELAS, cabecalho, em_breve

    # Cada tela é uma função (ctx, registry, agora) -> html. A que ainda não
    # existe cai no aviso dentro da moldura, em vez de deixar a rota em 404.
    MONTADORES = {"painel": conteudo.painel, "hoje": conteudo.hoje,
                  "calendario": conteudo.calendario, "gastos": conteudo.gastos,
                  "custo": conteudo.custo, "conversas": conteudo.conversas,
                  "ferramentas": conteudo.ferramentas, "auditoria": conteudo.auditoria, "notas": conteudo.notas,
                  "memoria": conteudo.memoria, "pessoas": conteudo.pessoas,
                  "fila": conteudo.fila}

    def _registrar(tela):
        @app.get(tela.caminho, response_class=HTMLResponse, name=tela.slug)
        def ver(periodo: str = "mes", sessao: str | None = None,
                ator: str | None = None, nota: int | None = None,
                busca: str | None = None) -> str:
            montar = MONTADORES.get(tela.slug)
            if montar is None:
                return render(cabecalho(tela.rotulo) + em_breve(tela.rotulo), tela.slug)
            ctx = contexto()
            agora = now_in(config.timezone)
            # o período é query string: continua sendo GET, e o histórico do
            # navegador guarda o recorte que você estava olhando
            extra = {}
            if tela.slug == "gastos":
                extra = {"periodo": periodo}
            elif tela.slug == "conversas":
                extra = {"sessao": sessao}
            elif tela.slug == "auditoria":
                extra = {"ator": ator}
            elif tela.slug == "notas":
                extra = {"nota": nota, "busca": busca}
            return render(montar(ctx, toolbelt, agora, **extra), tela.slug)

    for tela in TELAS:
        _registrar(tela)

    return app
