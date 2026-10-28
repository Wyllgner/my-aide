"""Os endereços das telas do vault, montados num lugar só."""

import ast
import pathlib
import re

from aide.web import enderecos


def test_a_barra_de_pasta_fica_legivel_e_o_resto_e_escapado():
    """`quote(safe="/")`: "Projetos/Casa" na barra de endereço, não
    "Projetos%2FCasa" — e o espaço e o acento vão escapados."""
    assert enderecos.nota("Projetos/Casa.md") == "/notas?arquivo=Projetos/Casa.md"
    assert enderecos.nota("Pé de café.md") == "/notas?arquivo=P%C3%A9%20de%20caf%C3%A9.md"


def test_o_desenho_leva_a_nota_de_onde_veio_quando_ha_uma():
    assert enderecos.desenho("P/Planta.excalidraw") == "/desenho?caminho=P/Planta.excalidraw"
    assert enderecos.desenho("P/Planta.excalidraw", "Inbox/Ideia.md") == (
        "/desenho?caminho=P/Planta.excalidraw&de=Inbox/Ideia.md")
    # sem origem (None ou ""), nada de "&de=" vazio pendurado no endereço
    for vazio in (None, ""):
        assert enderecos.desenho("P/Planta.excalidraw", vazio) == (
            "/desenho?caminho=P/Planta.excalidraw")


def test_a_tag_nao_fecha_a_nota_aberta():
    assert enderecos.tag("casa/obra") == "/notas?tag=casa/obra"
    assert enderecos.tag("casa", "Inbox/Ideia.md") == "/notas?tag=casa&arquivo=Inbox/Ideia.md"


def test_ninguem_mais_monta_esses_enderecos_a_mao():
    """Eram dez lugares em seis módulos, cada um com o seu quote(): um
    esquecido quebra caminho com espaço, e calado.

    Procura nas strings do código, e não no texto do arquivo: docstring e
    comentário podem citar o endereço à vontade."""
    pasta = pathlib.Path(enderecos.__file__).parent
    padrao = re.compile(r"^/(notas\?(arquivo|tag)=|desenho\?caminho=)")
    culpados = {}
    for arquivo in sorted(pasta.glob("*.py")):
        if arquivo.name == "enderecos.py":
            continue
        arvore = ast.parse(arquivo.read_text())
        docs = {id(no.body[0].value) for no in ast.walk(arvore)
                if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                   ast.ClassDef))
                and no.body and isinstance(no.body[0], ast.Expr)
                and isinstance(no.body[0].value, ast.Constant)
                and isinstance(no.body[0].value.value, str)}
        for no in ast.walk(arvore):
            if (isinstance(no, ast.Constant) and isinstance(no.value, str)
                    and padrao.match(no.value) and id(no) not in docs):
                culpados[f"{arquivo.name}:{no.lineno}"] = no.value
    assert not culpados, culpados
