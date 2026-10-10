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


def _citado_por(ligs: list) -> str:
    """As notas que levam a este desenho, numa lista que abre pela barra —
    o clique abre a nota já no link, como na lista de links quebrados."""
    from aide.channels import formato
    from aide.web.notas_tela import _onde_cita

    if not ligs:
        return ('<span class="desenho-citado vazio-curto"'
                ' title="escreva [[nome.excalidraw]] numa nota para ligar">'
                'nenhuma nota cita</span>')
    por_origem: dict[str, list] = {}
    for lig in ligs:
        por_origem.setdefault(lig.origem, []).append(lig)
    itens = "".join(_onde_cita(origem, por_origem[origem])
                    for origem in sorted(por_origem, key=str.casefold))
    rotulo = formato.plural(len(por_origem), "nota cita", "notas citam")
    return (f'<details class="desenho-citado" id="citado-por"><summary class="botao">'
            f'{icone("nota", 15)}<span>{escape(rotulo)}</span></summary>'
            f'<div class="desenho-citado-lista"><p class="eyebrow">Links para este desenho</p>'
            f'<ul class="quebrado-citacoes">{itens}</ul></div></details>')


def pagina(caminho: str, voltar: str, citado_por: str = "") -> str:
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
  <div class="desenho-nome" id="desenho-nome">
    {f'<span class="desenho-pasta">{escape(pasta)}/</span>' if pasta != "." else ""}<strong>{escape(nome)}</strong>
  </div>
  <form id="renomear-form" class="desenho-renomear" hidden>
    <input id="renomear-nome" value="{escape(caminho.removesuffix(desenhos.EXTENSAO))}"
      aria-label="novo nome do desenho (com a pasta, se quiser mudar de pasta)" autocomplete="off">
    <span class="dica">Enter renomeia · Esc cancela</span>
  </form>
  <button type="button" id="renomear" class="botao"
    title="renomear ou mudar de pasta; os links das notas acompanham">
    {icone("renomear", 15)}<span>renomear</span></button>
  {citado_por}
  <span id="desenho-estado" class="desenho-estado" role="status" aria-live="polite">abrindo…</span>
  <label class="privada" title="privado: o texto do desenho não vai para o modelo nem para a OpenAI">
    <input type="checkbox" id="privada" disabled>{icone("privada", 15)}<span>privado</span></label>
  <button type="button" id="apagar" class="botao botao-perigo"
    title="mandar para a lixeira do vault (pede um segundo clique)">
    {icone("lixeira", 15)}<span class="rotulo">apagar</span></button>
</header>
<div id="conflito" class="conflito desenho-conflito" hidden>
  <span>Este desenho mudou fora daqui desde que você abriu.</span>
  <button type="button" id="usar-disco" class="botao-fraco">ficar com o do disco</button>
  <button type="button" id="usar-meu" class="botao-fraco">manter o que eu desenhei</button>
</div>
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
        from aide.web import grafo

        citam = grafo.mapa(raiz).citam_desenho(caminho)
        return pagina(caminho, _voltar(raiz, de), _citado_por(citam))

    @app.get("/desenho.js")
    def script() -> Response:
        from aide.web.desenho_script import JS

        return Response(JS, media_type="text/javascript", headers={"cache-control": "no-cache"})
