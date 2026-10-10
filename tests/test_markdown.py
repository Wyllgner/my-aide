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
    assert '<table data-fonte="0" data-bloco="0-3">' in _html("| a | b |\n|---|---|\n| 1 | 2 |", indice)


def test_frontmatter_vira_propriedades_e_nao_texto(indice):
    html = _html("---\ntitle: Telhado\ntags: [casa]\n---\n\ncorpo", indice)
    assert '<dl class="propriedades" data-bloco="0-4">' in html
    assert "<dt>title</dt><dd>Telhado</dd>" in html
    assert "<dt>tags</dt><dd><a class=\"tag\"" in html
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
    assert '<h1 id="s-fim" data-fonte="2" data-bloco="2-3">' in html


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
    assert '<input type="checkbox" data-linha="0"> <span class="tarefa-texto">comprar telha' in html
    assert '<input type="checkbox" data-linha="1" checked> <span class="tarefa-texto">medir' in html
    assert '<li data-fonte="2">item comum</li>' in html
    # a feita é marcada no item, para sair riscada; a de baixo dela não
    assert '<li class="tarefa feita" data-fonte="1">' in html
    assert '<li class="tarefa" data-fonte="0">' in html


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
    assert '<h1 id="s-um" data-fonte="4" data-bloco="4-5">' in html
    assert '<p data-fonte="6" data-bloco="6-7">texto</p>' in html
    assert '<blockquote data-fonte="8" data-bloco="8-9">' in html


def test_cada_bloco_de_fora_diz_onde_comeca_e_termina(indice):
    """O modo ao vivo abre só as linhas do bloco clicado: a lista vai inteira,
    o código conta as cercas, e a linha vazia depois do bloco fica de fora."""
    html = markdown.renderizar(
        "---\ntitle: x\n---\n\ntexto\nmais\n\n- a\n  - b\n- c\n\n```py\nx\n```\n",
        "a.md", indice)
    assert '<dl class="propriedades" data-bloco="0-3">' in html
    assert '<p data-fonte="4" data-bloco="4-6">' in html
    assert '<ul data-bloco="7-10">' in html
    assert html.count("data-bloco") == 4  # o item de dentro da lista não
    assert 'data-bloco="11-14"' in html


# ---------- callouts ----------

def test_callout_vira_caixa_com_titulo_e_corpo(indice):
    html = _html("> [!warning] Cuidado **aqui**\n> o corpo", indice)
    assert '<blockquote class="callout" data-callout="warning"' in html
    assert '<div class="callout-titulo"><svg' in html
    assert "<span>Cuidado <strong>aqui</strong></span></div>" in html
    assert "<p data-fonte=\"0\">o corpo</p>" in html
    assert "[!warning]" not in html


def test_callout_sem_titulo_usa_o_nome_do_tipo_e_apelido_vira_o_tipo(indice):
    html = _html("> [!tldr]\n> resumo", indice)
    assert 'data-callout="abstract"' in html
    assert "<span>Resumo</span>" in html


def test_callout_so_com_titulo_nao_deixa_paragrafo_vazio(indice):
    html = _html("> [!tip] Só isto", indice)
    assert "<p>" not in html and "<p " not in html
    assert "<span>Só isto</span>" in html


def test_callout_que_dobra_vira_details(indice):
    fechado = _html("> [!faq]- Pergunta?\n> resposta", indice)
    assert '<details class="callout" data-callout="question"' in fechado
    assert ' open=""' not in fechado
    assert '<summary class="callout-titulo">' in fechado and "</details>" in fechado
    assert ' open=""' in _html("> [!faq]+ Pergunta?\n> resposta", indice)


def test_callout_de_tipo_desconhecido_e_citacao_comum(indice):
    html = _html("> [!inventado] x\n\n> só uma citação", indice)
    assert 'data-callout="inventado"' in html
    assert "<blockquote data-fonte" in html  # a citação comum segue como era


def test_callout_nao_injeta_html(indice):
    html = _html('> [!info] <img src=x onerror=alert(1)>\n> <script>x</script>', indice)
    assert "<img" not in html and "<script" not in html


def test_link_no_titulo_do_callout_conta_como_ligacao():
    achadas = markdown.citacoes("> [!info] veja [[Telhado]]\n> e [[Ideias]]")
    assert [c.alvo for c in achadas] == ["Telhado", "Ideias"]


# ---------- tags ----------

def test_tag_no_texto_vira_etiqueta_que_leva_a_lista(indice):
    html = _html("comprar telhas #compras e #casa/obra", indice)
    assert ('<a class="tag" href="/notas?tag=compras&amp;arquivo=Projetos/Casa/Telhado.md">'
            "#compras</a>") in html
    assert '#casa/obra</a>' in html


def test_tag_em_codigo_link_ou_numero_nao_vira_etiqueta(indice):
    html = _html("`#nao` [veja #isto](https://a.org) #2024 email@x#y", indice)
    assert 'class="tag"' not in html


def test_tags_do_frontmatter_viram_etiquetas(indice):
    html = _html("---\ntags: [casa, #obra]\n---\n\ntexto", indice)
    assert "<dt>tags</dt><dd><a class=\"tag\"" in html
    assert ">#casa</a> <a class=\"tag\"" in html and ">#obra</a></dd>" in html


def test_etiquetas_continua_achando_as_tags():
    assert markdown.etiquetas("---\ntags: [a]\n---\n\n#b e `#c` #b") == ["a", "b"]


# ---------- [[desenho.excalidraw]] ----------

@pytest.fixture
def com_desenhos(tmp_path, indice):
    from aide.storage import desenhos

    for caminho in ("Projetos/Casa/Planta.excalidraw", "Outros/Planta.excalidraw",
                    "Inbox/Fluxo & 'x'.excalidraw"):
        (tmp_path / caminho).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / caminho).write_text(desenhos.vazio())
    return desenhos.indice(tmp_path)


def _com(texto, indice, desenhos, origem="Projetos/Casa/Telhado.md"):
    return markdown.renderizar(texto, origem, indice, None, desenhos)


def test_link_de_desenho_abre_a_tela_e_volta_para_a_nota(indice, com_desenhos):
    html = _com("ver [[Planta.excalidraw]]", indice, com_desenhos)
    assert ('<a class="wikilink desenho" href="/desenho?caminho=Projetos/Casa/Planta.excalidraw'
            '&amp;de=Projetos/Casa/Telhado.md" title="Projetos/Casa/Planta.excalidraw">'
            'Planta</a>') in html


def test_link_de_desenho_acha_na_pasta_da_nota_primeiro_e_pelo_caminho(indice, com_desenhos):
    longe = _com("[[Planta.excalidraw]]", indice, com_desenhos, origem="Outros/Nota.md")
    assert "caminho=Outros/Planta.excalidraw" in longe
    caminho = _com("[[Outros/Planta.excalidraw|a outra]]", indice, com_desenhos)
    assert "caminho=Outros/Planta.excalidraw" in caminho and ">a outra</a>" in caminho


def test_link_de_desenho_que_nao_existe_fica_quebrado_para_criar(indice, com_desenhos):
    html = _com("[[Fachada.excalidraw]]", indice, com_desenhos)
    assert ('<a class="wikilink desenho quebrado" role="link" tabindex="0"'
            ' data-alvo="Fachada.excalidraw"') in html
    assert "href=" not in html.split("Fachada")[0].rsplit("<a", 1)[1]


def test_sem_indice_de_desenhos_o_link_nao_leva_a_lugar_nenhum(indice):
    html = _html("[[Planta.excalidraw]]", indice)
    assert "wikilink desenho quebrado" in html


def test_nome_de_desenho_escapado(indice, com_desenhos):
    html = _com("[[Fluxo & 'x'.excalidraw]]", indice, com_desenhos)
    assert ">Fluxo &amp; &#x27;x&#x27;</a>" in html
    assert "Fluxo%20%26%20%27x%27.excalidraw" in html


def test_link_de_desenho_nao_entra_no_mapa_como_nota():
    """Viraria "nota que não existe" nos quebrados, e o criar faria .excalidraw.md."""
    achadas = markdown.citacoes("[[Planta.excalidraw]] e [[Telhado]]")
    assert [c.alvo for c in achadas] == ["Telhado"]


def test_indice_de_desenhos_so_tem_desenho(tmp_path, com_desenhos):
    assert com_desenhos.resolver("Telhado.md") is None
    assert com_desenhos.resolver("Planta.excalidraw", "Projetos/Casa/X.md") == (
        "Projetos/Casa/Planta.excalidraw")


# ---------- ![[desenho.excalidraw]] ----------

def _embutido(texto, indice, desenhos, previa_de, origem="Projetos/Casa/Telhado.md"):
    return markdown.renderizar(texto, origem, indice, None, desenhos, previa_de)


def test_desenho_embutido_mostra_a_previa_e_leva_ao_desenho(indice, com_desenhos):
    html = _embutido("![[Planta.excalidraw]]", indice, com_desenhos, lambda c: "f" * 32)
    assert ('<a class="desenho-embutido" href="/desenho?caminho=Projetos/Casa/Planta.excalidraw'
            '&amp;de=Projetos/Casa/Telhado.md" title="Projetos/Casa/Planta.excalidraw">'
            '<img src="/api/desenhos/previa?caminho=Projetos/Casa/Planta.excalidraw&amp;v='
            + "f" * 32 + '" alt="Planta" loading="lazy"></a>') in html


def test_desenho_embutido_com_largura_e_apelido(indice, com_desenhos):
    largo = _embutido("![[Planta.excalidraw|400]]", indice, com_desenhos, lambda c: "f" * 32)
    assert 'width="400"' in largo
    absurdo = _embutido("![[Planta.excalidraw|99999]]", indice, com_desenhos, lambda c: "f" * 32)
    assert "width=" not in absurdo
    nomeado = _embutido("![[Planta.excalidraw|a planta]]", indice, com_desenhos, lambda c: "f" * 32)
    assert 'alt="a planta"' in nomeado


def test_desenho_embutido_sem_previa_convida_a_abrir(indice, com_desenhos):
    html = _embutido("![[Planta.excalidraw]]", indice, com_desenhos, lambda c: None)
    assert 'class="desenho-embutido sem-previa"' in html
    assert "abrir para gerar a prévia" in html and "<img" not in html


def test_desenho_embutido_que_nao_existe_fica_quebrado(indice, com_desenhos):
    html = _embutido("![[Fachada.excalidraw|300]]", indice, com_desenhos, lambda c: "f" * 32)
    assert 'class="wikilink desenho quebrado"' in html and "<img" not in html
    assert ">Fachada</a>" in html


def test_link_sem_exclamacao_continua_link(indice, com_desenhos):
    html = _embutido("[[Planta.excalidraw]]", indice, com_desenhos, lambda c: "f" * 32)
    assert "<img" not in html and 'class="wikilink desenho"' in html
