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

from aide.storage import vault
from aide.storage.reconciliacao import esquecer, mover_no_indice, sincronizar

# uma nota de 2 MB já é um livro; acima disso é engano, não anotação
TAMANHO_MAXIMO = 2 * 1024 * 1024


def versao(caminho: Path) -> str:
    """O que a página guarda ao abrir e devolve ao salvar. Se mudou no meio,
    alguém escreveu por fora — o assessor, o Obsidian — e salvar por cima
    apagaria o que ele escreveu."""
    return str(caminho.stat().st_mtime_ns)


def instalar(app) -> None:
    from fastapi import Body, HTTPException, Query
    from fastapi.responses import JSONResponse

    config = app.state.config

    def raiz() -> Path:
        return Path(config.vault_dir)

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
        from aide.storage import links
        from aide.web import markdown

        return markdown.renderizar(texto, caminho, links.indice(raiz()))

    @app.get("/api/notas/arquivo")
    def abrir(caminho: str = Query(...)) -> dict:
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "nota não encontrada")
        if arquivo.stat().st_size > TAMANHO_MAXIMO:
            raise HTTPException(413, "nota grande demais para abrir aqui")
        return {"caminho": caminho, "texto": arquivo.read_text(encoding="utf-8"),
                "versao": versao(arquivo)}

    @app.put("/api/notas/arquivo")
    def salvar(caminho: str = Body(...), texto: str = Body(...),
               versao_lida: str = Body(..., alias="versao")):
        arquivo = local(caminho)
        texto = texto_valido(texto)
        if not arquivo.is_file():
            raise HTTPException(404, "nota não encontrada; ela foi apagada ou movida")
        atual = versao(arquivo)
        if atual != versao_lida:
            # devolve o que está no disco para a página mostrar, sem decidir
            # sozinha qual das duas versões vale
            no_disco = arquivo.read_text(encoding="utf-8")
            return JSONResponse(status_code=409, content={
                "erro": "a nota mudou fora daqui desde que você abriu",
                "texto": no_disco, "versao": atual, "html": previa(no_disco, caminho)})
        vault.gravar(arquivo, texto)
        sincronizar(app.state.conn_factory(), raiz() / caminho)
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
        sincronizar(app.state.conn_factory(), raiz() / caminho)
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

        try:
            mudadas = renomear.mover(raiz(), de, para)
        except FileExistsError:
            raise HTTPException(409, "já existe uma nota com esse nome") from None
        conn = app.state.conn_factory()
        mover_no_indice(conn, raiz() / de, raiz() / para)
        for nota in mudadas:
            sincronizar(conn, raiz() / nota)
        # mover reescreve outras notas: a trilha diz quais
        auditar("notas.mover", f"{de} → {para}", links_atualizados=mudadas)
        return {"caminho": para, "versao": versao(destino), "links_atualizados": mudadas}

    @app.post("/api/notas/mover-pasta")
    def mover_pasta(de: str = Body(...), para: str = Body(...)) -> dict:
        from aide.web import renomear

        origem, destino = local(de, pasta=True), local(para, pasta=True)
        if not origem.is_dir():
            raise HTTPException(404, "pasta não encontrada")
        if destino.exists():
            raise HTTPException(409, "já existe uma pasta ou nota com esse nome")
        try:
            movidas, mudadas = renomear.mover_pasta(raiz(), de, para)
        except FileExistsError:
            raise HTTPException(409, "já existe uma pasta ou nota com esse nome") from None
        except ValueError as erro:
            raise HTTPException(400, str(erro)) from None
        conn = app.state.conn_factory()
        for velho, novo in movidas.items():
            mover_no_indice(conn, raiz() / velho, raiz() / novo)
        for nota in mudadas:
            sincronizar(conn, raiz() / nota)
        auditar("notas.mover_pasta", f"{de} → {para}", links_atualizados=mudadas)
        return {"caminho": para, "notas_movidas": movidas, "links_atualizados": mudadas}

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
        destino = vault.para_lixeira(raiz(), pasta)
        auditar("notas.apagar_pasta", caminho, notas=len(notas))
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
