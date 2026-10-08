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
from aide.storage.reconciliacao import esquecer, sincronizar

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

    def auditar(acao: str, caminho: str, ok: bool = True) -> None:
        conn = app.state.conn_factory()
        conn.execute(
            "INSERT INTO audit (actor, tool, args_json, result_summary, ok)"
            " VALUES ('web', ?, ?, ?, ?)",
            (acao, json.dumps({"caminho": caminho}, ensure_ascii=False),
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

    @app.post("/api/notas/pasta", status_code=201)
    def criar_pasta(caminho: str = Body(..., embed=True)) -> dict:
        pasta = local(caminho, pasta=True)
        try:
            vault.criar_pasta(pasta)
        except FileExistsError:
            raise HTTPException(409, "já existe uma pasta com esse nome") from None
        auditar("notas.criar_pasta", caminho)
        return {"caminho": caminho}

    @app.delete("/api/notas/arquivo")
    def apagar(caminho: str = Query(...)) -> dict:
        arquivo = local(caminho)
        if not arquivo.is_file():
            raise HTTPException(404, "nota não encontrada")
        esquecer(app.state.conn_factory(), raiz() / caminho)
        destino = vault.para_lixeira(raiz(), arquivo)
        auditar("notas.apagar", caminho)
        return {"caminho": caminho, "lixeira": destino.name if destino else None}
