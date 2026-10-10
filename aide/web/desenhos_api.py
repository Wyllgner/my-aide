"""As rotas dos desenhos: abrir, salvar, criar e apagar um `.excalidraw`.

As mesmas defesas das notas (`notas_api.py`): `seguranca.py` recusa a escrita
que não veio desta página, e `desenhos.resolver` recusa todo caminho que não
seja um desenho comum dentro do vault. O conteúdo é conferido por
`desenhos.validar` antes de chegar ao disco.

Toda escrita entra na auditoria com `actor="web"`: o caminho e, quando muda,
a marcação de privado — nunca o desenho, que pode ter texto privado dentro.
"""

from __future__ import annotations

import json
from pathlib import Path

from aide.storage import desenhos, vault
from aide.web.notas_api import versao


def instalar(app) -> None:
    from fastapi import Body, HTTPException, Query
    from fastapi.responses import JSONResponse

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
                "privada": desenhos.privado(dados)}

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
                "texto": no_disco, "versao": atual, "privada": desenhos.privado(dados)})
        antes = desenhos.privado(ler(arquivo)[1])
        # explícito, para o gravar não ler e validar o arquivo de novo
        dados = desenhos.gravar(arquivo, texto, privada=antes if privada is None else privada)
        depois = desenhos.privado(dados)
        auditar("desenhos.salvar", caminho, **({"privada": depois} if depois != antes else {}))
        return {"caminho": caminho, "versao": versao(arquivo), "privada": depois}

    @app.post("/api/desenhos/arquivo", status_code=201)
    def criar(caminho: str = Body(..., embed=True)) -> dict:
        arquivo = local(caminho)
        try:
            desenhos.criar(arquivo)
        except FileExistsError:
            raise HTTPException(409, "já existe um desenho com esse nome") from None
        auditar("desenhos.criar", caminho)
        return {"caminho": caminho, "versao": versao(arquivo), "privada": False}

    @app.delete("/api/desenhos/arquivo")
    def apagar(caminho: str = Query(...)) -> dict:
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "desenho não encontrado")
        destino = vault.para_lixeira(raiz(), arquivo)
        auditar("desenhos.apagar", caminho)
        return {"caminho": caminho, "lixeira": destino.name if destino else None}

    @app.post("/api/desenhos/mover")
    def mover(de: str = Body(...), para: str = Body(...)) -> dict:
        """Renomeia ou muda de pasta, nunca por cima de outro arquivo. Os links
        para o desenho ainda não são reescritos aqui (vem com os links)."""
        origem, destino = local(de), local(para)
        if not origem.is_file():
            raise HTTPException(404, "desenho não encontrado")
        if destino.exists():
            raise HTTPException(409, "já existe um desenho com esse nome")
        try:
            vault.mover(origem, destino)
        except FileExistsError:
            raise HTTPException(409, "já existe um desenho com esse nome") from None
        auditar("desenhos.mover", de, para=para)
        return {"caminho": para, "versao": versao(destino)}

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
