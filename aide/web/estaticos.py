"""O CSS e o JavaScript das telas, guardados em aide/web/static/.

Arquivo de verdade, e nao string dentro de um modulo Python: o editor
reconhece a linguagem e o diff mostra so a linha que mudou.
"""

from __future__ import annotations

from pathlib import Path

PASTA = Path(__file__).parent / "static"


def ler(nome: str) -> str:
    return (PASTA / nome).read_text(encoding="utf-8")


# A ordem vale: a folha depende dela. O responsivo sobrepoe o que veio antes,
# e ".botao:disabled" (em arquivos.css) sobrepoe o ".botao" de notas.css.
PARTES_CSS = ["base.css", "layout.css", "notas.css", "editor.css",
              "vault.css", "responsivo.css", "desenho.css", "arquivos.css", "telas.css"]


def folha() -> str:
    return "".join(ler(f"css/{nome}") for nome in PARTES_CSS)


# As partes que o js/app.js importa, uma por assunto. Lista fechada pelo mesmo
# motivo das fontes em app.py: o nome que chega na URL nunca vira caminho.
PARTES_NOTAS = ["comum.js", "realce.js", "atalhos.js", "arvore.js", "criar.js",
                "abrir-rapido.js", "quebrados.js", "pastas.js", "grafo.js",
                "editor.js"]


def notas() -> str:
    """O script das notas inteiro, entrada e partes. Para quem pergunta se o
    script faz alguma coisa (os testes), e nao para servir: o navegador pede
    cada arquivo pela rota dele."""
    return ler("js/app.js") + "".join(ler(f"js/notas/{nome}") for nome in PARTES_NOTAS)
