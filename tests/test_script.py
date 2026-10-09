"""O /app.js no que dá para conferir sem navegador: as regras de texto.

Roda o trecho do próprio script no Node; sem Node, pula.
"""

import json
import re
import shutil
import subprocess

import pytest

from aide.storage import vault
from aide.web.script import JS

node = shutil.which("node")
pytestmark = pytest.mark.skipif(node is None, reason="sem node")


def _front(texto: str):
    """O que a FRONT do script acha em `texto`: (miolo, resto) ou None."""
    regex = re.search(r"var FRONT = (/.*/);", JS).group(1)
    codigo = (f"const FRONT = {regex}; const t = {json.dumps(texto)};"
              "const m = t.match(FRONT);"
              "console.log(JSON.stringify(m ? [m[1] || '', t.slice(m[0].length)] : null));")
    saida = subprocess.run([node, "-e", codigo], capture_output=True, text=True, check=True)
    return json.loads(saida.stdout)


@pytest.mark.parametrize("texto", [
    "---\ntitle: x\n---\n\ncorpo",
    "---\n---\ncorpo",
    "---\ntitle: a --- b\n---\ncorpo\n---\nfim",
    "---\nnunca fecha",
    "----\nnão é",
    "---\ntitle: x\n---x\nprivate: true\n---\ncorpo",
    "sem frontmatter",
])
def test_o_script_ve_o_frontmatter_igual_ao_servidor(texto):
    """Se discordarem, marcar "privada" na página cria um segundo bloco ou
    escreve a linha onde o servidor não lê."""
    meta, corpo = vault.separar(texto)
    achado = _front(texto)
    if achado is None:
        assert meta == {} and corpo == texto.strip()
    else:
        miolo, resto = achado
        assert vault.separar(f"---\n{miolo}\n---\n{resto}" if miolo else f"---\n---\n{resto}") \
            == (meta, corpo)
        assert resto.strip() == corpo


@pytest.mark.parametrize("linha, marcada", [
    ("- [ ] comprar", "- [x] comprar"),
    ("  * [x] feita", "  * [ ] feita"),
    ("1. [ ] numerada", "1. [x] numerada"),
    ("3) [X] outra", "3) [ ] outra"),
])
def test_a_regra_de_tarefa_do_script_troca_so_a_caixa(linha, marcada):
    regex = re.search(r"var TAREFA = (/.*/);", JS).group(1)
    codigo = (f"const T = {regex}; const l = {json.dumps(linha)}; const m = T.exec(l);"
              "console.log(l.replace(T, '$1' + (m[2] === ' ' ? 'x' : ' ') + '$3'));")
    saida = subprocess.run([node, "-e", codigo], capture_output=True, text=True, check=True)
    assert saida.stdout.rstrip("\n") == marcada


# ---------- cores no editor ----------

def _realcar(texto: str) -> str:
    """Roda o colorizador do próprio script no Node."""
    inicio = JS.index("  function esc(t)")
    fim = JS.index("  var pedidoRealce")
    codigo = (JS[inicio:fim] + f"\nconsole.log(JSON.stringify(realcar({json.dumps(texto)})));")
    saida = subprocess.run([node, "-e", codigo], capture_output=True, text=True, check=True)
    return json.loads(saida.stdout)


def _sem_marcacao(html: str) -> str:
    import html as h

    return h.unescape(re.sub(r"<[^>]+>", "", html))


@pytest.mark.parametrize("texto", [
    "# Título\n\n**forte** e *itálico* e `código` e [[Link|apelido]] e [x](http://a.b)",
    "---\ntitle: x\n---\n\n- [ ] tarefa\n> citação\n```\n**não**\n```\n#tag",
    '<img src=x onerror=alert(1)> & "aspas" <script>',
    "", "linha\n", "a\n\n\nb",
])
def test_o_realce_preserva_o_texto_caractere_a_caractere(texto):
    """A cópia colorida fica por baixo do campo: se um caractere mudar, o texto
    desalinha do cursor."""
    assert _sem_marcacao(_realcar(texto)) == texto + "\n "


def test_texto_da_nota_nunca_vira_html_no_realce():
    html = _realcar('<img src=x onerror=alert(1)><script>alert(2)</script>')
    assert "<img" not in html and "<script" not in html
    assert set(re.findall(r"<(\w+)", html)) <= {"span"}


def test_marcas_recebem_cores():
    html = _realcar("# Título\n**forte** [[Link]] `x`")
    assert '<span class="r-titulo">Título</span>' in html
    assert '<span class="r-forte">forte</span>' in html
    assert '<span class="r-link">Link</span>' in html
    assert '<span class="r-codigo">`x`</span>' in html


def test_dentro_de_codigo_nada_colore():
    html = _realcar("```\n**não** [[nada]]\n```")
    assert "r-forte" not in html and "r-link" not in html
