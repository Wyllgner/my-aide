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
    assert "<li>um</li>" in html


def test_tabela(indice):
    assert "<table>" in _html("| a | b |\n|---|---|\n| 1 | 2 |", indice)


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
    assert '<h1 id="s-fim">' in html


def test_wikilink_quebrado_nao_leva_a_lugar_nenhum(indice):
    html = _html("[[Não existe]]", indice)
    assert 'class="wikilink quebrado"' in html
    assert 'data-alvo="Não existe"' in html
    assert "href" not in html


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
    assert '<input type="checkbox" disabled> comprar telha' in html
    assert '<input type="checkbox" disabled checked> medir o telhado' in html
    assert "<li>item comum</li>" in html


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
