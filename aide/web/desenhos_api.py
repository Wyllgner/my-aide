"""As rotas dos desenhos: abrir, salvar, criar e apagar um `.excalidraw`.

As mesmas defesas das notas (`notas_api.py`): `seguranca.py` recusa a escrita
que não veio desta página, e `desenhos.resolver` recusa todo caminho que não
seja um desenho comum dentro do vault. O conteúdo é conferido por
`desenhos.validar` antes de chegar ao disco.

Toda escrita no vault entra na auditoria com `actor="web"`: o caminho e,
quando muda, a marcação de privado — nunca o desenho, que pode ter texto
privado dentro. A prévia em PNG não: é cache fora do vault (`previas.py`).
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from aide.storage import desenhos, previas, vault
from aide.web.notas_api import versao


def instalar(app) -> None:
    from fastapi import Body, HTTPException, Query, Request
    from fastapi.responses import FileResponse, JSONResponse

    config = app.state.config

    def raiz() -> Path:
        return Path(config.vault_dir)

    def local(caminho: str) -> Path:
        try:
            return desenhos.resolver(raiz(), caminho)
        except vault.ForaDoVault as erro:
            raise HTTPException(400, str(erro)) from None

    def auditar(acao: str, caminho: str, **extra) -> None:
        conn = app.state.conn_factory()
        conn.execute(
            "INSERT INTO audit (actor, tool, args_json, result_summary, ok)"
            " VALUES ('web', ?, ?, 'ok', 1)",
            (acao, json.dumps({"caminho": caminho, **extra}, ensure_ascii=False)))

    def dados_dir() -> Path:
        return Path(config.data_dir)

    def com_previa(caminho: str, arquivo: Path) -> dict:
        """A assinatura do arquivo como está no disco, e se já há prévia dela:
        a página gera a que falta depois de salvar ou ao abrir."""
        assinatura = previas.assinatura_do_arquivo(arquivo)
        return {"assinatura": assinatura,
                "previa": previas.achar(dados_dir(), caminho, assinatura) is not None}

    def ler(arquivo: Path) -> tuple[str, dict]:
        """O desenho do disco, ou o erro que a página sabe mostrar: um arquivo
        posto por fora pode ser grande demais, binário ou JSON torto."""
        if not arquivo.is_file():
            raise HTTPException(404, "desenho não encontrado")
        try:
            return desenhos.ler(arquivo)
        except desenhos.DesenhoInvalido as erro:
            raise HTTPException(422, f"o arquivo não abre como desenho: {erro}") from None

    @app.get("/api/desenhos/arquivo")
    def abrir(caminho: str = Query(...)) -> dict:
        arquivo = local(caminho)
        texto, dados = ler(arquivo)
        return {"caminho": caminho, "texto": texto, "versao": versao(arquivo),
                "privada": desenhos.privado_de_fato(dados_dir(), caminho, dados),
                **com_previa(caminho, arquivo)}

    @app.put("/api/desenhos/arquivo")
    def salvar(caminho: str = Body(...), texto: str = Body(...),
               versao_lida: str = Body(..., alias="versao"),
               privada: bool | None = Body(None)):
        """`privada` só vem quando a caixa mudou; sem ele, vale o que está no
        disco (o Excalidraw descarta a marcação ao serializar)."""
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "desenho não encontrado; ele foi apagado ou movido")
        try:
            desenhos.validar(texto)
        except desenhos.DesenhoInvalido as erro:
            raise HTTPException(400, str(erro)) from None
        atual = versao(arquivo)
        if atual != versao_lida:
            # devolve o que está no disco para a página decidir, sem escolher
            # sozinha qual das duas versões vale
            no_disco, dados = ler(arquivo)
            return JSONResponse(status_code=409, content={
                "erro": "o desenho mudou fora daqui desde que você abriu",
                "texto": no_disco, "versao": atual,
                "privada": desenhos.privado_de_fato(dados_dir(), caminho, dados)})
        # o registro conta: editado no Obsidian, o arquivo perdeu a marcação,
        # e este salvamento a devolve ao arquivo
        antes = desenhos.privado_de_fato(dados_dir(), caminho, ler(arquivo)[1])
        if privada is not None:
            # a caixa mudou: é a única porta para um desenho deixar de ser privado
            desenhos.marcar(dados_dir(), caminho, privada)
        # explícito, para o gravar não ler e validar o arquivo de novo
        dados = desenhos.gravar(arquivo, texto, privada=antes if privada is None else privada)
        depois = desenhos.privado(dados)
        auditar("desenhos.salvar", caminho, **({"privada": depois} if depois != antes else {}))
        # a assinatura é do que ficou no disco: com a marcação de privado
        # reposta, o texto gravado não é o que a página mandou
        return {"caminho": caminho, "versao": versao(arquivo), "privada": depois,
                **com_previa(caminho, arquivo)}

    @app.post("/api/desenhos/arquivo", status_code=201)
    def criar(caminho: str = Body(..., embed=True)) -> dict:
        arquivo = local(caminho)
        try:
            desenhos.criar(arquivo)
        except FileExistsError:
            raise HTTPException(409, "já existe um desenho com esse nome") from None
        auditar("desenhos.criar", caminho)
        # um desenho apagado com este nome deixa a marca: na dúvida, privado
        return {"caminho": caminho, "versao": versao(arquivo),
                "privada": desenhos.privado_de_fato(dados_dir(), caminho, {})}

    @app.delete("/api/desenhos/arquivo")
    def apagar(caminho: str = Query(...)) -> dict:
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "desenho não encontrado")
        destino = vault.para_lixeira(raiz(), arquivo)
        previas.limpar(dados_dir(), caminho)
        auditar("desenhos.apagar", caminho)
        return {"caminho": caminho, "lixeira": destino.name if destino else None}

    @app.post("/api/desenhos/mover")
    def mover(de: str = Body(...), para: str = Body(...)) -> dict:
        """Renomeia ou muda de pasta, nunca por cima de outro arquivo, e
        conserta os [[...excalidraw]] das notas que levavam a ele."""
        from aide.storage.reconciliacao import sincronizar
        from aide.web import renomear

        origem, destino = local(de), local(para)
        if not origem.is_file():
            raise HTTPException(404, "desenho não encontrado")
        if destino.exists():
            raise HTTPException(409, "já existe um desenho com esse nome")
        puladas: list[str] = []
        try:
            mudadas = renomear.mover_desenho(raiz(), de, para, puladas)
        except FileExistsError:
            raise HTTPException(409, "já existe um desenho com esse nome") from None
        conn = app.state.conn_factory()
        for nota in mudadas:
            sincronizar(conn, raiz() / nota)
        # no lugar novo, a próxima abertura gera a prévia de novo
        previas.limpar(dados_dir(), de)
        desenhos.mover_marcas(dados_dir(), de, para)
        auditar("desenhos.mover", de, para=para, links_atualizados=mudadas,
                links_nao_atualizados=puladas)
        return {"caminho": para, "versao": versao(destino), "links_atualizados": mudadas,
                "links_nao_atualizados": puladas}

    @app.get("/api/desenhos/link")
    def link(caminho: str = Query(...), alvo: str = Query(..., max_length=2000)) -> dict:
        """Para onde leva o link de um elemento do desenho: a nota ou o desenho
        do vault, resolvido como um [[link]] numa nota da mesma pasta. Se não
        existe, o caminho que ele pede, para a página oferecer criar."""
        from aide.storage import links
        from aide.web import markdown

        local(caminho)
        citacao = markdown.citacao_do_link(alvo)
        if citacao is None:
            raise HTTPException(422, "esse link não é de uma nota nem de um desenho do vault")
        arvore = vault.arvore(raiz())
        secao = citacao.secao
        if citacao.tipo == "wiki" and markdown.DESENHO.search(citacao.alvo):
            tipo = "desenho"
            destino = desenhos.indice(raiz(), arvore).resolver(citacao.alvo, caminho)
        else:
            tipo = "nota"
            env = {"origem": caminho, "indice": links.indice(raiz(), arvore)}
            if citacao.tipo == "md":
                destino, secao = markdown._nota_por_link_markdown(citacao.alvo, env)
            else:
                destino = citacao.destino(caminho, env["indice"])
        if destino is not None:
            href = (markdown.href_da_nota(destino, secao) if tipo == "nota"
                    else "/desenho?caminho=" + quote(destino, safe="/"))
            return {"tipo": tipo, "existe": True, "caminho": destino, "href": href}
        pedido = citacao.caminho_pedido(caminho)
        try:
            (vault.resolver if tipo == "nota" else desenhos.resolver)(raiz(), pedido)
        except vault.ForaDoVault:
            raise HTTPException(422, "esse link aponta para fora do vault") from None
        return {"tipo": tipo, "existe": False, "caminho": pedido}

    # ---------- a prévia em PNG, para ![[desenho.excalidraw]] numa nota ----------

    @app.get("/api/desenhos/previa")
    def previa(caminho: str = Query(...)):
        """A prévia da versão que está no disco; 404 se ela ainda não foi gerada.
        Imagem, com CSP fechada e sem cache: o desenho pode ser privado."""
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "desenho não encontrado")
        png = previas.achar(dados_dir(), caminho, previas.assinatura_do_arquivo(arquivo))
        if png is None:
            raise HTTPException(404, "sem prévia desta versão")
        return FileResponse(png, media_type="image/png", headers={
            "content-security-policy": "default-src 'none'", "cache-control": "no-store"})

    async def guardar_previa(request, caminho: str = Query(...),
                             assinatura: str = Query(...)):
        """O PNG que a página exportou. Só para a versão que está no disco: a
        assinatura tem de bater, senão é uma prévia velha (ou outra coisa)."""
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "desenho não encontrado")
        if not previas.ASSINATURA.fullmatch(assinatura):
            raise HTTPException(400, "assinatura inválida")
        if assinatura != previas.assinatura_do_arquivo(arquivo):
            raise HTTPException(409, "o desenho mudou; esta prévia é de outra versão")
        # contado enquanto chega: o limite vale mesmo sem Content-Length
        partes, total = [], 0
        async for pedaco in request.stream():
            total += len(pedaco)
            if total > previas.TAMANHO_MAXIMO:
                raise HTTPException(413, "prévia grande demais")
            partes.append(pedaco)
        try:
            previas.guardar(dados_dir(), caminho, assinatura, b"".join(partes))
        except previas.PreviaInvalida as erro:
            raise HTTPException(415, str(erro)) from None
        # de quebra, tira as prévias de desenhos que sumiram por fora
        previas.podar(dados_dir(), desenhos.indice(raiz()).por_caminho.values())
        return {"caminho": caminho, "assinatura": assinatura}

    # a anotação vira texto com o `from __future__`, e o Request daqui de
    # dentro não seria achado: como no anexo das notas
    guardar_previa.__annotations__["request"] = Request
    app.put("/api/desenhos/previa")(guardar_previa)

    # ---------- a biblioteca de formas (uma só, Biblioteca.excalidrawlib) ----------

    def versao_da_biblioteca() -> str:
        # "" enquanto o arquivo não existe: a primeira gravação cria
        try:
            caminho = desenhos.caminho_biblioteca(raiz())
        except vault.ForaDoVault as erro:
            raise HTTPException(400, str(erro)) from None
        return versao(caminho) if caminho.is_file() else ""

    def ler_biblioteca() -> str:
        try:
            return desenhos.ler_biblioteca(raiz())[0]
        except desenhos.DesenhoInvalido as erro:
            raise HTTPException(422, f"a biblioteca não abre: {erro}") from None
        except vault.ForaDoVault as erro:
            raise HTTPException(400, str(erro)) from None

    @app.get("/api/desenhos/biblioteca")
    def biblioteca() -> dict:
        return {"texto": ler_biblioteca(), "versao": versao_da_biblioteca()}

    @app.put("/api/desenhos/biblioteca")
    def salvar_biblioteca(texto: str = Body(...), versao_lida: str = Body(..., alias="versao")):
        """Com a versão lida, como os desenhos: outra aba pode ter guardado uma
        forma no meio, e gravar por cima a apagaria. No 409 a página junta as
        duas e manda de novo."""
        try:
            desenhos.validar_biblioteca(texto)
        except desenhos.DesenhoInvalido as erro:
            raise HTTPException(400, str(erro)) from None
        atual = versao_da_biblioteca()
        if atual != versao_lida:
            return JSONResponse(status_code=409, content={
                "erro": "a biblioteca mudou desde que você abriu",
                "texto": ler_biblioteca(), "versao": atual})
        desenhos.gravar_biblioteca(raiz(), texto)
        auditar("desenhos.biblioteca", desenhos.BIBLIOTECA)
        return {"versao": versao_da_biblioteca()}
