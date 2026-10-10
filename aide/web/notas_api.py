"""As rotas de escrita das notas: as únicas da página que mudam alguma coisa.

Elas existem porque o vault virou o seu caderno, e caderno se escreve. O que
as protege fica em dois lugares, e os dois precisam valer:

- `seguranca.py` recusa a escrita que não veio desta página (Host, Origin e o
  cabeçalho `X-Aide`), antes de chegar aqui;
- `vault.resolver` recusa todo caminho que não seja, sem dúvida, uma nota ou
  pasta comum dentro do vault.

Toda escrita entra na auditoria com `actor="web"`: o caminho, nunca o texto,
porque a trilha não precisa de uma segunda cópia do que você escreveu.
"""

from __future__ import annotations

import json
from pathlib import Path

from aide.storage import atividade, vault
from aide.storage.reconciliacao import (
    esquecer,
    mover_no_indice,
    privado_para_o_arquivo,
    sincronizar,
)

# uma nota de 2 MB já é um livro; acima disso é engano, não anotação
TAMANHO_MAXIMO = 2 * 1024 * 1024


def versao(caminho: Path) -> str:
    """O que a página guarda ao abrir e devolve ao salvar. Se mudou no meio,
    alguém escreveu por fora — o assessor, o Obsidian — e salvar por cima
    apagaria o que ele escreveu."""
    return str(caminho.stat().st_mtime_ns)


def instalar(app) -> None:
    from fastapi import Body, HTTPException, Query, Request
    from fastapi.responses import JSONResponse

    config = app.state.config

    def raiz() -> Path:
        return Path(config.vault_dir)

    def agora():
        from aide.core.context import now_in

        return now_in(config.timezone)

    def local(caminho: str, pasta: bool = False) -> Path:
        try:
            return vault.resolver(raiz(), caminho, pasta=pasta)
        except vault.ForaDoVault as erro:
            raise HTTPException(400, str(erro)) from None

    def auditar(acao: str, caminho: str, ok: bool = True, **extra) -> None:
        conn = app.state.conn_factory()
        conn.execute(
            "INSERT INTO audit (actor, tool, args_json, result_summary, ok)"
            " VALUES ('web', ?, ?, ?, ?)",
            (acao, json.dumps({"caminho": caminho, **extra}, ensure_ascii=False),
             "ok" if ok else "recusado", int(ok)))

    def texto_valido(texto) -> str:
        if not isinstance(texto, str):
            raise HTTPException(400, "texto precisa ser texto")
        if len(texto.encode()) > TAMANHO_MAXIMO:
            raise HTTPException(413, "nota grande demais")
        return texto

    def previa(texto: str, caminho: str) -> str:
        from aide.storage import anexos, links
        from aide.web import markdown

        return markdown.renderizar(texto, caminho, links.indice(raiz()), anexos.indice(raiz()))

    @app.get("/api/notas/anexo")
    def anexo(caminho: str = Query(...)):
        """Um anexo do vault, para a prévia mostrar. Só leitura, só os tipos da
        lista (sem SVG nem HTML), e com uma CSP própria e fechada: mesmo aberto
        sozinho numa aba, o arquivo não roda nada."""
        from fastapi.responses import FileResponse

        from aide.storage import anexos

        try:
            arquivo = anexos.resolver(raiz(), caminho)
        except vault.ForaDoVault as erro:
            raise HTTPException(400, str(erro)) from None
        if not arquivo.is_file():
            raise HTTPException(404, "anexo não encontrado")
        if arquivo.stat().st_size > anexos.TAMANHO_MAXIMO:
            raise HTTPException(413, "anexo grande demais")
        from urllib.parse import quote as citar

        return FileResponse(arquivo, media_type=anexos.tipo(caminho), headers={
            # o nome do arquivo vira o título da aba do PDF e o nome ao baixar
            "content-disposition": f"inline; filename*=UTF-8''{citar(arquivo.name)}",
            "content-security-policy": "default-src 'none'; img-src 'self'; media-src 'self';"
                                       " object-src 'self'; sandbox",
            "cache-control": "no-cache",
        })

    async def anexar(request, nota: str = Query(...), nome: str = Query("")):
        """Guarda no vault o arquivo do corpo do pedido — a captura colada com
        Ctrl+V, o arquivo arrastado ou escolhido — e devolve o `![[...]]` para
        a nota. Só os tipos da lista de anexos, nunca por cima de outro arquivo,
        e os bytes são contados enquanto chegam: o limite vale mesmo sem
        Content-Length."""
        from aide.storage import anexos

        if not local(nota).is_file():
            raise HTTPException(404, "nota não encontrada")
        try:
            nome_final = anexos.nome_para(nome, request.headers.get("content-type", ""), agora())
            relativo_pasta = anexos.pasta_para(raiz(), nota)
            pasta = (vault.resolver(raiz(), relativo_pasta, pasta=True)
                     if relativo_pasta else raiz().resolve())
            # o nome também passa pela trava de caminho, antes de existir
            anexos.resolver(raiz(), f"{relativo_pasta}/{nome_final}".lstrip("/"))
        except vault.ForaDoVault as erro:
            raise HTTPException(400, str(erro)) from None
        except ValueError as erro:
            raise HTTPException(415, str(erro)) from None

        caminho, arquivo = anexos.reservar(pasta, nome_final)
        total = 0
        try:
            with arquivo:
                async for pedaco in request.stream():
                    total += len(pedaco)
                    if total > anexos.TAMANHO_MAXIMO:
                        raise HTTPException(413, "anexo grande demais")
                    arquivo.write(pedaco)
            if not total:
                raise HTTPException(400, "arquivo vazio")
        except BaseException:
            caminho.unlink(missing_ok=True)
            raise
        relativo = vault.relativo_de(raiz(), caminho)
        auditar("notas.anexar", relativo, nota=nota, bytes=total)
        return {"caminho": relativo, "link": anexos.link_para(raiz(), nota, relativo)}

    # o módulo tem `from __future__ import annotations`, e o FastAPI resolveria
    # o nome "Request" nos globais, onde ele não está (fastapi é opcional e só
    # se importa aqui dentro): a anotação vai como objeto
    anexar.__annotations__["request"] = Request
    app.post("/api/notas/anexo", status_code=201)(anexar)

    @app.get("/api/notas/arquivo")
    def abrir(caminho: str = Query(...)) -> dict:
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "nota não encontrada")
        if arquivo.stat().st_size > TAMANHO_MAXIMO:
            raise HTTPException(413, "nota grande demais para abrir aqui")
        try:
            texto = arquivo.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "a nota não está em UTF-8") from None
        return {"caminho": caminho, "texto": texto, "versao": versao(arquivo)}

    @app.put("/api/notas/arquivo")
    def salvar(caminho: str = Body(...), texto: str = Body(...),
               versao_lida: str = Body(..., alias="versao")):
        arquivo = local(caminho)
        texto = texto_valido(texto)
        if not arquivo.is_file():
            raise HTTPException(404, "nota não encontrada; ela foi apagada ou movida")
        # aba aberta antes de o privado ir para o arquivo: a marca entra no
        # disco, a versão muda, e o conflito mostra a nota com ela
        privado_para_o_arquivo(app.state.conn_factory(), raiz() / caminho)
        atual = versao(arquivo)
        if atual != versao_lida:
            # devolve o que está no disco para a página mostrar, sem decidir
            # sozinha qual das duas versões vale
            no_disco = arquivo.read_text(encoding="utf-8")
            return JSONResponse(status_code=409, content={
                "erro": "a nota mudou fora daqui desde que você abriu",
                "texto": no_disco, "versao": atual, "html": previa(no_disco, caminho)})
        vault.gravar(arquivo, texto)
        conn = app.state.conn_factory()
        sincronizar(conn, raiz() / caminho)
        atividade.registrar(conn, raiz(), arquivo, agora(), "pagina")
        auditar("notas.salvar", caminho)
        # a prévia volta junto: é o mesmo texto, e assim a página não precisa
        # de um segundo pedido nem de um renderizador próprio
        return {"caminho": caminho, "versao": versao(arquivo), "html": previa(texto, caminho)}

    @app.post("/api/notas/arquivo", status_code=201)
    def criar(caminho: str = Body(..., embed=True)) -> dict:
        arquivo = local(caminho)
        try:
            vault.criar_nota(arquivo)
        except FileExistsError:
            raise HTTPException(409, "já existe uma nota com esse nome") from None
        conn = app.state.conn_factory()
        sincronizar(conn, raiz() / caminho)
        atividade.registrar(conn, raiz(), arquivo, agora(), "pagina")
        auditar("notas.criar", caminho)
        return {"caminho": caminho, "versao": versao(arquivo)}

    @app.post("/api/notas/mover")
    def mover(de: str = Body(...), para: str = Body(...)) -> dict:
        origem, destino = local(de), local(para)
        if not origem.is_file():
            raise HTTPException(404, "nota não encontrada")
        if destino.exists():
            raise HTTPException(409, "já existe uma nota com esse nome")
        from aide.web import renomear

        puladas: list[str] = []
        try:
            mudadas = renomear.mover(raiz(), de, para, puladas)
        except FileExistsError:
            raise HTTPException(409, "já existe uma nota com esse nome") from None
        conn = app.state.conn_factory()
        mover_no_indice(conn, raiz() / de, raiz() / para)
        atividade.mover(conn, de, para)
        for nota in mudadas:
            sincronizar(conn, raiz() / nota)
        # mover reescreve outras notas: a trilha diz quais
        auditar("notas.mover", f"{de} → {para}", links_atualizados=mudadas,
                links_nao_atualizados=puladas)
        return {"caminho": para, "versao": versao(destino), "links_atualizados": mudadas,
                "links_nao_atualizados": puladas}

    @app.post("/api/notas/ligar")
    def ligar(alvo: str = Body(...), para: str = Body(...)) -> dict:
        """Conserta um link quebrado apontando-o para uma nota que existe."""
        from aide.web import renomear

        if not local(para).is_file():
            raise HTTPException(404, "nota não encontrada")
        if not alvo.strip():
            raise HTTPException(400, "diga qual link consertar")
        puladas: list[str] = []
        mudadas = renomear.ligar(raiz(), alvo, para, puladas)
        conn = app.state.conn_factory()
        for nota in mudadas:
            sincronizar(conn, raiz() / nota)
        auditar("notas.ligar", f"{alvo} → {para}", links_atualizados=mudadas,
                links_nao_atualizados=puladas)
        return {"caminho": para, "links_atualizados": mudadas, "links_nao_atualizados": puladas}

    @app.post("/api/notas/mover-pasta")
    def mover_pasta(de: str = Body(...), para: str = Body(...)) -> dict:
        from aide.web import renomear

        origem, destino = local(de, pasta=True), local(para, pasta=True)
        if not origem.is_dir():
            raise HTTPException(404, "pasta não encontrada")
        if destino.exists():
            raise HTTPException(409, "já existe uma pasta ou nota com esse nome")
        puladas: list[str] = []
        try:
            movidas, mudadas = renomear.mover_pasta(raiz(), de, para, puladas)
        except FileExistsError:
            raise HTTPException(409, "já existe uma pasta ou nota com esse nome") from None
        except ValueError as erro:
            raise HTTPException(400, str(erro)) from None
        conn = app.state.conn_factory()
        for velho, novo in movidas.items():
            mover_no_indice(conn, raiz() / velho, raiz() / novo)
            atividade.mover(conn, velho, novo)
        for nota in mudadas:
            sincronizar(conn, raiz() / nota)
        auditar("notas.mover_pasta", f"{de} → {para}", links_atualizados=mudadas,
                links_nao_atualizados=puladas)
        return {"caminho": para, "notas_movidas": movidas, "links_atualizados": mudadas,
                "links_nao_atualizados": puladas}

    @app.post("/api/notas/pasta", status_code=201)
    def criar_pasta(caminho: str = Body(..., embed=True)) -> dict:
        pasta = local(caminho, pasta=True)
        try:
            vault.criar_pasta(pasta)
        except FileExistsError:
            raise HTTPException(409, "já existe uma pasta com esse nome") from None
        auditar("notas.criar_pasta", caminho)
        return {"caminho": caminho}

    @app.delete("/api/notas/pasta")
    def apagar_pasta(caminho: str = Query(...)) -> dict:
        """A pasta inteira vai para a `.trash`, com o que tem dentro — como no
        Obsidian, e como a nota sozinha: nada é destruído, voltar é um `mv`."""
        pasta = local(caminho, pasta=True)
        if not pasta.is_dir():
            raise HTTPException(404, "pasta não encontrada")
        conn = app.state.conn_factory()
        notas = [vault.relativo_de(raiz(), p) for p in pasta.rglob("*.md")]
        for nota in notas:
            esquecer(conn, raiz() / nota)
        # os desenhos vão junto; a trilha conta os dois
        desenhos = sum(1 for _ in pasta.rglob("*.excalidraw"))
        destino = vault.para_lixeira(raiz(), pasta)
        auditar("notas.apagar_pasta", caminho, notas=len(notas), desenhos=desenhos)
        return {"caminho": caminho, "lixeira": destino.name if destino else None,
                "notas": len(notas)}

    @app.delete("/api/notas/arquivo")
    def apagar(caminho: str = Query(...)) -> dict:
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "nota não encontrada")
        esquecer(app.state.conn_factory(), raiz() / caminho)
        destino = vault.para_lixeira(raiz(), arquivo)
        auditar("notas.apagar", caminho)
        return {"caminho": caminho, "lixeira": destino.name if destino else None}
