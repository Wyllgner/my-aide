"""A prévia das notas: markdown, links do Obsidian e o que nunca pode virar código."""

import pytest

from aide.storage import links
from aide.web import markdown


@pytest.fixture
def indice(tmp_path):
    for caminho in ("Inbox/Reunião de orçamento.md", "Projetos/Casa/Telhado.md",
                    "Projetos/Casa/Ideias.md"):
        (tmp_path / caminho).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / caminho).write_text("x")
    return links.indice(tmp_path)


def _html(texto, indice, origem="Projetos/Casa/Telhado.md"):
    return markdown.renderizar(texto, origem, indice)


# ---------- markdown comum ----------

def test_markdown_basico(indice):
    html = _html("# Título\n\n**negrito** e *itálico* e ~~riscado~~\n\n- um\n- dois", indice)
    assert "<strong>negrito</strong>" in html
    assert "<em>itálico</em>" in html
    assert "<s>riscado</s>" in html
    assert '<li data-fonte="4">um</li>' in html


def test_tabela(indice):
    assert '<table data-fonte="0">' in _html("| a | b |\n|---|---|\n| 1 | 2 |", indice)


def test_frontmatter_vira_propriedades_e_nao_texto(indice):
    html = _html("---\ntitle: Telhado\ntags: [casa]\n---\n\ncorpo", indice)
    assert '<dl class="propriedades">' in html
    assert "<dt>tags</dt><dd>[casa]</dd>" in html
    assert "<hr" not in html


# ---------- [[links]] ----------

def test_wikilink_resolvido(indice):
    html = _html("ver [[Reunião de orçamento]]", indice)
    assert ('href="/notas?arquivo=Inbox/Reuni%C3%A3o%20de%20or%C3%A7amento.md"' in html)
    assert ">Reunião de orçamento</a>" in html


def test_wikilink_com_apelido_e_secao(indice):
    html = _html("[[Reunião de orçamento#Próximos passos|o plano]]", indice)
    assert "#s-pr%C3%B3ximos-passos" in html
    assert ">o plano</a>" in html


def test_wikilink_so_com_secao_aponta_para_a_propria_nota(indice):
    html = _html("[[#Fim]]\n\n# Fim", indice)
    assert 'href="/notas?arquivo=Projetos/Casa/Telhado.md#s-fim"' in html
    assert '<h1 id="s-fim" data-fonte="2">' in html


def test_wikilink_quebrado_nao_leva_a_lugar_nenhum(indice):
    html = _html("[[Não existe]]", indice)
    assert 'class="wikilink quebrado"' in html
    assert 'data-alvo="Não existe"' in html
    assert "href" not in html
    # ainda alcançável pelo teclado
    assert 'role="link" tabindex="0"' in html


def test_wikilink_prefere_a_mesma_pasta(indice):
    assert "Projetos/Casa/Ideias.md" in _html("[[Ideias]]", indice)


def test_wikilink_dentro_de_codigo_fica_texto(indice):
    html = _html("`[[Reunião de orçamento]]`\n\n```\n[[Telhado]]\n```", indice)
    assert "wikilink" not in html
    assert "[[Reunião de orçamento]]" in html


def test_link_markdown_para_outra_nota(indice):
    html = _html("[a reunião](../../Inbox/Reuni%C3%A3o%20de%20or%C3%A7amento.md) e "
                 "[ideias](Ideias.md)", indice)
    assert "/notas?arquivo=Inbox/Reuni" in html
    assert "/notas?arquivo=Projetos/Casa/Ideias.md" in html


# ---------- tarefas e âncoras ----------

def test_lista_de_tarefas(indice):
    html = _html("- [ ] comprar telha\n- [x] medir o telhado\n- item comum", indice)
    assert '<input type="checkbox" data-linha="0"> comprar telha' in html
    assert '<input type="checkbox" data-linha="1" checked> medir o telhado' in html
    assert '<li data-fonte="2">item comum</li>' in html


def test_a_linha_da_tarefa_e_a_do_arquivo(indice):
    """Com frontmatter e linhas vazias antes: a caixa marca a linha certa."""
    texto = "---\ntitle: x\n---\n\n\n# Lista\n\n- [ ] a\n  - [x] dentro\n\n```\n- [ ] código\n```\n- [ ] b"
    html = _html(texto, indice)
    linhas = texto.split("\n")
    import re

    for numero in re.findall(r'data-linha="(\d+)"', html):
        assert re.match(r"\s*- \[[ x]\] ", linhas[int(numero)])
    assert re.findall(r'data-linha="(\d+)"', html) == ["7", "8", "13"]


def test_titulos_repetidos_ganham_numero(indice):
    html = _html("# A\n\n# A", indice)
    assert 'id="s-a"' in html and 'id="s-a-2"' in html


def test_titulo_nao_pode_roubar_o_id_de_um_elemento_da_pagina(indice):
    """Um "# editor" na nota não pode virar id="editor" — o do campo de texto."""
    html = _html("# editor\n\n# privada", indice)
    assert 'id="editor"' not in html and 'id="privada"' not in html


# ---------- nada vira código ----------

def _tags(html):
    """As tags e os atributos como o navegador vai ler."""
    from html.parser import HTMLParser

    achadas = []

    class Leitor(HTMLParser):
        def handle_starttag(self, tag, attrs):
            achadas.append((tag, attrs))

    Leitor().feed(html)
    return achadas


@pytest.mark.parametrize("texto", [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '<a href="javascript:alert(1)">x</a>',
    "[x](javascript:alert(1))",
    "[x](JaVaScRiPt:alert(1))",
    "[x](vbscript:msgbox)",
    "[x](data:text/html;base64,PHNjcmlwdD4=)",
    "![x](javascript:alert(1))",
    '[[x" onmouseover="alert(1)]]',
    '[[Telhado|"><script>alert(1)</script>]]',
    "# <script>alert(1)</script>",
    "---\n<script>: <img src=x onerror=alert(1)>\n---\n",
    "| <script>alert(1)</script> |\n|---|",
])
def test_nada_da_nota_vira_codigo(indice, texto):
    tags = _tags(_html(texto, indice))
    # o texto pode aparecer escapado; o que não pode é virar tag ou atributo
    assert {t for t, _ in tags} <= {"p", "a", "h1", "dl", "dt", "dd", "table", "thead",
                                    "tbody", "tr", "th", "td", "span", "code", "pre"}
    for _, atributos in tags:
        for nome, valor in atributos:
            assert not nome.startswith("on")
            if nome in ("href", "src"):
                assert valor.startswith(("/notas?", "https:", "http:", "mailto:"))


def test_link_de_fora_abre_em_outra_aba_sem_contar_de_onde_veio(indice):
    html = _html("[site](https://exemplo.org)", indice)
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


def test_imagem_nunca_carrega(indice):
    """Imagem de fora avisa o dono dela de que você abriu a nota."""
    html = _html("![foto](https://rastreio.exemplo/pixel.png) ![local](foto.png)", indice)
    assert "<img" not in html
    assert 'class="imagem-externa" href="https://rastreio.exemplo/pixel.png"' in html
    assert '<span class="imagem-externa">local</span>' in html


def test_link_relativo_que_nao_e_nota_fica_sem_destino(indice):
    html = _html("[x](/api/notas/arquivo?caminho=a.md)", indice)
    assert "href" not in html


def test_link_markdown_leva_a_secao(indice):
    html = _html("[ir](../../Inbox/Reuni%C3%A3o%20de%20or%C3%A7amento.md#Pr%C3%B3ximos%20passos)",
                 indice)
    assert "Inbox/Reuni%C3%A3o%20de%20or%C3%A7amento.md#s-pr%C3%B3ximos-passos" in html


def test_link_markdown_para_titulo_da_propria_nota(indice):
    html = _html("[topo](#Fim)\n\n# Fim", indice)
    assert 'href="/notas?arquivo=Projetos/Casa/Telhado.md#s-fim"' in html


@pytest.mark.parametrize("texto", ["![[foto.png]]", "[[relatório.pdf]]", "![[Plano.PDF|o plano]]"])
def test_anexo_nao_vira_nota_para_criar(indice, texto):
    """Como link quebrado, um clique criaria "foto.png.md"."""
    html = _html(texto, indice)
    assert 'class="anexo"' in html
    assert "quebrado" not in html
    assert not html.startswith("<p>!")


def test_embutir_nota_vira_link(indice):
    html = _html("![[Reunião de orçamento]]", indice)
    assert 'class="wikilink" href="/notas?arquivo=Inbox/' in html
    assert "<p>!" not in html


def test_nome_com_ponto_continua_nota(indice):
    """"v1.2" não é extensão de anexo que importe: "Plano v1.2" é nota."""
    assert "quebrado" in _html("[[Plano v1.2]]", indice)


# ---------- URL solta ----------

@pytest.mark.parametrize("texto, url", [
    ("veja https://exemplo.org/a?b=1 depois", "https://exemplo.org/a?b=1"),
    ("fim de frase https://exemplo.org.", "https://exemplo.org"),
    ("(entre parênteses https://exemplo.org)", "https://exemplo.org"),
    ("wiki https://pt.wikipedia.org/wiki/Teste_(desambiguação) ok",
     "https://pt.wikipedia.org/wiki/Teste_(desambigua%C3%A7%C3%A3o)"),
    ("HTTP://EXEMPLO.ORG", "HTTP://EXEMPLO.ORG"),
])
def test_url_solta_vira_link(indice, texto, url):
    html = _html(texto, indice)
    assert f'href="{url}"' in html
    assert 'target="_blank"' in html and 'rel="noopener noreferrer"' in html


@pytest.mark.parametrize("texto", [
    "`https://exemplo.org` em código",
    "```\nhttps://exemplo.org\n```",
    "[já é link](https://exemplo.org)",
    "javascript://alert(1)",
    "só https:// sem nada",
])
def test_url_que_nao_deve_virar_link_novo(indice, texto):
    assert _html(texto, indice).count("<a ") <= 1


def test_url_solta_nao_vira_atributo(indice):
    html = _html('https://x.org/"><script>alert(1)</script>', indice)
    assert "<script>" not in html
    for _, atributos in _tags(html):
        assert not any(nome.startswith("on") for nome, _ in atributos)


def test_url_solta_nao_conta_como_ligacao_entre_notas():
    from aide.web.markdown import citacoes

    assert citacoes("veja https://exemplo.org/nota.md") == []


def test_cada_bloco_diz_a_linha_do_arquivo_onde_comeca(indice):
    """A lista de links quebrados leva até o link: a prévia precisa saber onde
    cada bloco está no arquivo, contando o frontmatter."""
    from aide.web import markdown

    html = markdown.renderizar("---\ntitle: x\n---\n\n# Um\n\ntexto\n\n> citação", "a.md", indice)
    assert '<h1 id="s-um" data-fonte="4">' in html
    assert '<p data-fonte="6">texto</p>' in html
    assert '<blockquote data-fonte="8">' in html
