"""O /app.js no que dá para conferir sem navegador: as regras de texto.

Roda o trecho do próprio script no Node; sem Node, pula.
"""

import json
import re
import shutil
import subprocess

import pytest

from aide.storage import vault
from aide.web import estaticos

JS = estaticos.ler("js/app.js")

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


def test_o_script_e_um_modulo_valido(tmp_path):
    """Erro de sintaxe derruba as notas inteiras sem nenhum teste Python notar.
    A página carrega com type="module": conferido como módulo, e não como
    script, que aceita coisas que o módulo recusa (o return no topo, por exemplo)."""
    arquivo = tmp_path / "app.mjs"
    arquivo.write_text(estaticos.ler("js/app.js"))
    subprocess.run([node, "--check", str(arquivo)], check=True, capture_output=True)


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


# ---------- desfazer no ao vivo ----------

def _historico(roteiro: str) -> dict:
    """Roda o histórico do ao vivo no Node, com o resto da página de mentira."""
    inicio = JS.index("  var desfazer = [];")
    fim = JS.index("  function mostrarLinha()")
    codigo = (
        "var editor = {value: 'a'}; var conflito = {hidden: true}; var salvo = 'a';"
        "var avisos = []; var salvos = 0; var privada = {};"
        "function mostrar(t) { avisos.push(t); } function marcadaNoTexto() { return false; }"
        "function corretor() {} function agendarRealce() {} function salvar() { salvos++; }"
        + JS[inicio:fim] + roteiro
        + "\nconsole.log(JSON.stringify({texto: editor.value, avisos: avisos, salvos: salvos,"
          " desfazer: desfazer.length, refazer: refazer.length}));")
    saida = subprocess.run([node, "-e", codigo], capture_output=True, text=True, check=True)
    return json.loads(saida.stdout)


def test_desfazer_e_refazer_passo_a_passo():
    r = _historico("""
        editor.value = 'ab'; registrar('a', 'ab', 0);
        editor.value = 'abc'; registrar('ab', 'abc', 0);
        andarNoHistorico('desfazer'); var um = editor.value;
        andarNoHistorico('desfazer'); var dois = editor.value;
        andarNoHistorico('refazer');
        avisos.push(um, dois);""")
    assert r["texto"] == "ab"
    assert r["avisos"][-2:] == ["ab", "a"]
    assert r["salvos"] == 3 and r["desfazer"] == 1 and r["refazer"] == 1


def test_o_bloco_do_shift_enter_entra_no_mesmo_passo():
    r = _historico("""
        editor.value = 'b'; registrar('a', 'b', 0);
        editor.value = 'c'; registrar('b', 'c', 1, true);
        andarNoHistorico('desfazer');""")
    assert r["texto"] == "a" and r["desfazer"] == 0


def test_escrever_depois_de_desfazer_esquece_o_refazer():
    r = _historico("""
        editor.value = 'b'; registrar('a', 'b', 0);
        andarNoHistorico('desfazer');
        editor.value = 'z'; registrar('a', 'z', 0);""")
    assert r["refazer"] == 0 and r["desfazer"] == 1


def test_texto_mudado_por_outro_caminho_nao_e_desfeito():
    """O modo editar ou o conflito mexeram: voltar apagaria o que mudou."""
    r = _historico("""
        editor.value = 'b'; registrar('a', 'b', 0);
        editor.value = 'b e mais o que foi escrito no modo editar';
        andarNoHistorico('desfazer');""")
    assert r["texto"] == "b e mais o que foi escrito no modo editar"
    assert r["desfazer"] == 0 and r["salvos"] == 0
    assert "mudou por outro caminho" in r["avisos"][-1]


def test_sem_nada_para_desfazer_so_avisa():
    r = _historico("andarNoHistorico('desfazer'); andarNoHistorico('refazer');")
    assert r["texto"] == "a" and r["avisos"] == ["nada para desfazer", "nada para refazer"]


@pytest.mark.parametrize("tecla, esperado", [
    ({"key": "z", "ctrlKey": True}, "desfazer"),
    ({"key": "Z", "ctrlKey": True, "shiftKey": True}, "refazer"),
    ({"key": "y", "metaKey": True}, "refazer"),
    ({"key": "z", "ctrlKey": True, "altKey": True}, None),
    ({"key": "z"}, None),
])
def test_atalhos_de_desfazer(tecla, esperado):
    r = _historico(f"avisos.push(passoPedido({json.dumps(tecla)}));")
    assert r["avisos"] == [esperado]


def test_desfazer_no_bloco_so_quando_ele_esta_como_abriu():
    """Com o bloco já mexido, o Ctrl+Z é o do navegador, dentro dele."""
    teclado = JS[JS.index('      var passo = passoPedido(ev);'):]
    teclado = teclado[:teclado.index("      }\n") + 8]
    assert "campo.value === b.fonte" in teclado
    assert teclado.index("fecharBloco();") < teclado.index("andarNoHistorico(passo);")
    pagina = JS[JS.index('  document.addEventListener("keydown", function (e) {\n'
                         '    if (area.dataset.modo !== "vivo" || bloco)'):]
    assert 'closest("input, textarea, select, [contenteditable]")' in pagina[:400]


# ---------- lado a lado ----------

def _interpolar(pares, x):
    inicio = JS.index("  function interpolar(")
    fim = JS.index("  // o topo de cada linha do campo")
    codigo = JS[inicio:fim] + f"\nconsole.log(JSON.stringify(interpolar({json.dumps(pares)}, {x})));"
    saida = subprocess.run([node, "-e", codigo], capture_output=True, text=True, check=True)
    return json.loads(saida.stdout)


@pytest.mark.parametrize("x, y", [
    (-5, 0), (0, 0), (50, 100), (100, 200), (150, 250), (300, 400), (999, 400),
])
def test_rolagem_anda_em_reta_entre_os_blocos(x, y):
    """Campo e prévia têm alturas diferentes por bloco: cada trecho tem a sua escala."""
    assert _interpolar([[0, 0], [100, 200], [300, 400]], x) == y


def test_rolagem_sem_pares_fica_no_topo():
    assert _interpolar([], 50) == 0
