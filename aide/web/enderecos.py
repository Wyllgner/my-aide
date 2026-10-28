"""Os endereços das telas do vault, num lugar só.

Três telas levam um caminho na URL: `/notas?arquivo=`, `/notas?tag=` e
`/desenho?caminho=`. Cada módulo montava o seu, sempre com
`quote(..., safe="/")` — a barra de pasta fica legível na barra de endereço, e
um `quote` esquecido quebra caminho com espaço ou acento. Do lado do navegador
o mesmo endereço sai de `js/notas/comum.js`.
"""

from __future__ import annotations

from urllib.parse import quote


def _valor(caminho: str) -> str:
    # safe="/": "Projetos/Casa.md" continua assim no endereco, e nao
    # "Projetos%2FCasa.md"
    return quote(caminho, safe="/")


def nota(caminho: str) -> str:
    return "/notas?arquivo=" + _valor(caminho)


def desenho(caminho: str, de: str | None = None) -> str:
    """`de` é a nota aberta: o "Notas" da tela do desenho volta para ela."""
    url = "/desenho?caminho=" + _valor(caminho)
    return url + "&de=" + _valor(de) if de else url


def tag(nome: str, aberta: str | None = None) -> str:
    """A lista de notas com a tag, sem fechar a nota que está aberta."""
    url = "/notas?tag=" + _valor(nome)
    return url + "&arquivo=" + _valor(aberta) if aberta else url
