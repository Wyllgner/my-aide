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
