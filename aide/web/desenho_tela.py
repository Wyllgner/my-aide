"""A tela de um desenho: o Excalidraw em tela cheia, com uma barra em cima.

Fica fora da moldura das telas (sem a lateral): o desenho precisa do espaço
todo. O servidor só monta a casca — o caminho vai num atributo, escapado — e o
`/desenho.js` busca o desenho pela API e monta o editor.

O link de volta só aponta para uma nota do vault: `de` vem da URL, e um link
de volta que aceitasse qualquer endereço levaria para fora do site.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import quote

from aide.storage import desenhos, vault
from aide.web.icones import icone


def _voltar(raiz: Path, de: str | None) -> str:
    """/notas?arquivo=<de> se `de` for uma nota que existe; senão, /notas."""
    if de:
        try:
            if vault.resolver(raiz, de).is_file():
                return "/notas?arquivo=" + quote(de, safe="/")
        except vault.ForaDoVault:
            pass
    return "/notas"


def pagina(caminho: str, voltar: str) -> str:
    nome = Path(caminho).name.removesuffix(desenhos.EXTENSAO)
    pasta = str(Path(caminho).parent)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(nome)} · my-aide</title>
<link rel="stylesheet" href="/app.css">
<link rel="stylesheet" href="/vendor/excalidraw/excalidraw.css">
<script type="module" src="/desenho.js"></script>
</head>
<body class="desenho-corpo">
<header class="desenho-barra">
  <a class="botao" href="{escape(voltar)}">{icone("notas", 16)}<span>Notas</span></a>
  <div class="desenho-nome">
    {f'<span class="desenho-pasta">{escape(pasta)}/</span>' if pasta != "." else ""}<strong>{escape(nome)}</strong>
  </div>
  <span id="desenho-estado" class="desenho-estado" role="status" aria-live="polite">abrindo…</span>
</header>
<div id="desenho" class="desenho-editor" data-caminho="{escape(caminho)}"></div>
</body>
</html>
"""


def _erro(status: int, mensagem: str):
    from fastapi.responses import HTMLResponse

    return HTMLResponse(status_code=status, content=f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Desenho · my-aide</title>
<link rel="stylesheet" href="/app.css"></head>
<body><main style="padding:32px"><p>{escape(mensagem)}</p>
<p><a href="/notas">Voltar para as notas</a></p></main></body></html>""")


def instalar(app) -> None:
    from fastapi import Query
    from fastapi.responses import HTMLResponse, Response

    config = app.state.config

    @app.get("/desenho", response_class=HTMLResponse)
    def tela(caminho: str = Query(...), de: str | None = Query(None)):
        raiz = Path(config.vault_dir)
        try:
            arquivo = desenhos.resolver(raiz, caminho)
        except vault.ForaDoVault:
            return _erro(400, "Esse caminho não é de um desenho do vault.")
        if not arquivo.is_file():
            return _erro(404, "Desenho não encontrado: ele foi apagado ou movido.")
        return pagina(caminho, _voltar(raiz, de))

    @app.get("/desenho.js")
    def script() -> Response:
        from aide.web.desenho_script import JS

        return Response(JS, media_type="text/javascript", headers={"cache-control": "no-cache"})
