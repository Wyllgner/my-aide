"""A aplicação web.

**Quase só leitura.** A única escrita é a das notas (`notas_api.py`), porque o
vault virou o caderno que se escreve aqui. O resto — concluir tarefa, lançar
gasto, conversar — continua sendo CLI, Telegram ou MCP. Escrita tem preço:
CSRF, DNS rebinding e o clique errado numa aba esquecida. `seguranca.py` paga
os dois primeiros para todas as rotas, e `test_so_as_notas_escrevem` impede
que uma rota de escrita nova apareça sem passar por essa decisão.

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
from aide.web import seguranca

log = logging.getLogger(__name__)

# Constante, não configuração. Ver o docstring do módulo.
ENDERECO = "127.0.0.1"
PORTA_PADRAO = 8787


def criar_app(config=None, conn_factory=None):
    """Monta a aplicação. Recebe as dependências para poder ser testada."""
    from fastapi import Cookie, FastAPI, Header, Query
    from fastapi.responses import HTMLResponse, Response

    from aide.config import load_config

    config = config or load_config()

    if conn_factory is None:
        def conn_factory():
            conn = connect(config.db_path)
            migrate(conn)
            return conn

    app = FastAPI(title="my-aide", docs_url=None, redoc_url=None, openapi_url=None)
    seguranca.instalar(app)
    app.state.config = config
    app.state.conn_factory = conn_factory

    def contexto() -> ToolContext:
        """`ver_privado=True`: é o dono, na máquina dele, e a porta é local.

        A mesma decisão do terminal. O que a sustenta é o bind e a checagem de
        Host de `seguranca.py` — se um dia a página escutar fora daqui, isto
        precisa mudar junto.

        `auditar=False` porque abrir uma tela não é um acontecimento: a trilha
        registra o que mudou. As rotas de nota, que mudam, não usam este
        contexto e auditam por conta própria.
        """
        return ToolContext(config=config, conn=conn_factory(), actor="web",
                           ver_privado=True, auditar=False)

    app.state.contexto = contexto

    from aide.web import notas_api

    notas_api.instalar(app)

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

    @app.get("/app.js")
    def script() -> Response:
        from aide.web.script import JS

        return Response(JS, media_type="text/javascript",
                        headers={"cache-control": "no-cache"})

    from pathlib import Path

    pasta_fontes = Path(__file__).parent / "fontes"
    # lista fechada, montada ao subir: o nome na URL nunca vira caminho
    fontes = {p.name: p for p in pasta_fontes.glob("*.woff2")}

    @app.get("/fontes/{nome}")
    def fonte(nome: str) -> Response:
        arquivo = fontes.get(nome)
        if arquivo is None:
            return Response("fonte não encontrada", status_code=404, media_type="text/plain")
        # o nome não muda sem o arquivo mudar de nome junto: cache longo
        return Response(arquivo.read_bytes(), media_type="font/woff2",
                        headers={"cache-control": "max-age=31536000, immutable"})

    # O Excalidraw compilado (deploy/excalidraw/build.sh). Mesma ideia das
    # fontes: só o que estava na pasta ao subir, e só estes tipos.
    pasta_vendor = Path(__file__).parent / "vendor"
    tipos_vendor = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2"}
    vendor = {p.relative_to(pasta_vendor).as_posix(): p for p in pasta_vendor.rglob("*")
              if p.suffix in tipos_vendor and p.is_file() and not p.is_symlink()}

    @app.get("/vendor/{caminho:path}")
    def arquivo_vendor(caminho: str, if_none_match: str = Header("")) -> Response:
        import hashlib

        arquivo = vendor.get(caminho)
        if arquivo is None:
            return Response("arquivo não encontrado", status_code=404, media_type="text/plain")
        # só partes/ tem a garantia do hash no nome (o esbuild põe). A entrada,
        # o CSS e algumas fontes (Assistant, Cascadia…) mantêm o nome entre
        # versões: o navegador confere sempre e recebe 304 se nada mudou.
        if caminho.startswith("excalidraw/partes/"):
            return Response(arquivo.read_bytes(), media_type=tipos_vendor[arquivo.suffix],
                            headers={"cache-control": "max-age=31536000, immutable"})
        conteudo = arquivo.read_bytes()
        etag = '"' + hashlib.sha256(conteudo).hexdigest()[:32] + '"'
        cabecalhos = {"cache-control": "no-cache", "etag": etag}
        if etag in if_none_match:
            return Response(status_code=304, headers=cabecalhos)
        return Response(conteudo, media_type=tipos_vendor[arquivo.suffix], headers=cabecalhos)

    @app.get("/app.css")
    def folha_de_estilo() -> Response:
        from aide.web.estilo import CSS

        return Response(CSS, media_type="text/css",
                        headers={"cache-control": "no-cache"})

    # Uma rota por tela. As que ainda não têm conteúdo respondem a moldura com
    # um aviso — assim a navegação inteira já é navegável e testável.
    from aide.core.context import now_in
    from aide.tools import registry as toolbelt
    from aide.web import notas_tela
    from aide.web import telas as conteudo
    from aide.web.paginas import TELAS, cabecalho, em_breve

    # Cada tela é uma função (ctx, registry, agora) -> html. A que ainda não
    # existe cai no aviso dentro da moldura, em vez de deixar a rota em 404.
    MONTADORES = {"painel": conteudo.painel, "hoje": conteudo.hoje,
                  "calendario": conteudo.calendario, "gastos": conteudo.gastos,
                  "custo": conteudo.custo, "conversas": conteudo.conversas,
                  "ferramentas": conteudo.ferramentas, "auditoria": conteudo.auditoria, "notas": notas_tela.tela,
                  "memoria": conteudo.memoria, "pessoas": conteudo.pessoas,
                  "fila": conteudo.fila}

    def _registrar(tela):
        @app.get(tela.caminho, response_class=HTMLResponse, name=tela.slug)
        def ver(periodo: str = "mes", sessao: str | None = None,
                ator: str | None = None, nota: int | None = None,
                arquivo: str | None = None, quebrados: bool = False, geral: bool = False,
                grafo: bool = False,
                busca: str | None = None, ano: int | None = None,
                mes: int | None = None, dia: int | None = None,
                # filtros da busca de gastos
                q: str = "", categoria: str = "", tag: str = "", forma: str = "",
                tipo: str = "", de: str = "", ate: str = "", ordem: str = "",
                valor_min: str = Query("", alias="min"),
                valor_max: str = Query("", alias="max"),
                # o modo da tela de notas, lembrado pelo /app.js
                notas_modo: str | None = Cookie(None)) -> str:
            montar = MONTADORES.get(tela.slug)
            if montar is None:
                return render(cabecalho(tela.rotulo) + em_breve(tela.rotulo), tela.slug)
            ctx = contexto()
            agora = now_in(config.timezone)
            # o período é query string: continua sendo GET, e o histórico do
            # navegador guarda o recorte que você estava olhando
            extra = {}
            if tela.slug == "gastos":
                extra = {"periodo": periodo, "filtros": {
                    "q": q, "categoria": categoria, "tag": tag, "forma": forma,
                    "tipo": tipo, "de": de, "ate": ate, "ordem": ordem,
                    "min": valor_min, "max": valor_max}}
            elif tela.slug == "conversas":
                extra = {"sessao": sessao}
            elif tela.slug == "auditoria":
                extra = {"ator": ator}
            elif tela.slug == "notas":
                extra = {"nota": nota, "busca": busca, "arquivo": arquivo, "modo": notas_modo,
                         "quebrados": quebrados, "geral": geral, "grafo_todo": grafo,
                         "tag": tag}
            elif tela.slug == "calendario":
                extra = {"ano": ano, "mes": mes, "dia": dia}
            return render(montar(ctx, toolbelt, agora, **extra), tela.slug)

    for tela in TELAS:
        _registrar(tela)

    return app
