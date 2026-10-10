"""A tela de notas: árvore do vault e editor."""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import connect, migrate
from aide.web import criar_app


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    (pasta / "Inbox").mkdir(parents=True)
    (pasta / "Projetos" / "Casa").mkdir(parents=True)
    (pasta / "Inbox" / "Ideia.md").write_text("uma ideia")
    (pasta / "Projetos" / "Casa" / "Telhado.md").write_text(
        "---\ntitle: Telhado\nprivate: true\n---\n\ntrocar as telhas\n")
    return pasta


@pytest.fixture
def cliente(config, tmp_path, raiz):
    object.__setattr__(config, "vault_dir", raiz)

    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return TestClient(criar_app(config, conn_factory), base_url="http://127.0.0.1:8787")


def _tela(cliente, arquivo=None):
    url = "/notas" + (f"?arquivo={arquivo}" if arquivo else "")
    resposta = cliente.get(url)
    assert resposta.status_code == 200
    return resposta.text


def test_a_arvore_mostra_pastas_e_notas(cliente):
    html = _tela(cliente)
    for nome in ("Inbox", "Projetos", "Casa", "Ideia", "Telhado"):
        assert f">{nome}<" in html
    assert "2 notas · 3 pastas" in html


def test_so_a_pasta_da_nota_aberta_vem_aberta(cliente):
    html = _tela(cliente, "Projetos/Casa/Telhado.md")
    assert '<details open data-pasta="Projetos">' in html
    assert '<details open data-pasta="Projetos/Casa">' in html
    assert '<details data-pasta="Inbox">' in html


def test_o_editor_traz_o_arquivo_inteiro_e_a_versao(cliente, raiz):
    html = _tela(cliente, "Projetos/Casa/Telhado.md")
    assert 'data-caminho="Projetos/Casa/Telhado.md"' in html
    versao = str((raiz / "Projetos" / "Casa" / "Telhado.md").stat().st_mtime_ns)
    assert f'data-versao="{versao}"' in html
    assert "title: Telhado\nprivate: true" in html


def test_a_caixa_privada_segue_o_frontmatter(cliente):
    assert 'id="privada" checked' in _tela(cliente, "Projetos/Casa/Telhado.md")
    assert 'id="privada" checked' not in _tela(cliente, "Inbox/Ideia.md")


def test_privada_so_no_banco_abre_com_a_caixa_marcada(cliente, raiz):
    cliente.app.state.conn_factory().execute("INSERT INTO notes (title, path, private) VALUES ('Ideia', ?, 1)",
                 (str(raiz / "Inbox" / "Ideia.md"),))
    html = _tela(cliente, "Inbox/Ideia.md")
    assert 'id="privada" checked' in html
    assert "private: true" in (raiz / "Inbox" / "Ideia.md").read_text()


def test_sem_arquivo_abre_a_ultima_mexida(cliente, raiz):
    import os

    ideia = raiz / "Inbox" / "Ideia.md"
    os.utime(ideia, (ideia.stat().st_mtime + 100,) * 2)
    assert 'data-caminho="Inbox/Ideia.md"' in _tela(cliente)


@pytest.mark.parametrize("arquivo", ["../fora.md", "Nada.md", "%2Fetc%2Fpasswd", ".trash/x.md"])
def test_arquivo_ruim_na_url_cai_numa_nota_valida(cliente, arquivo):
    assert 'data-caminho="' in _tela(cliente, arquivo)


def test_texto_da_nota_nao_fecha_o_editor(cliente, raiz):
    """O texto vai dentro de <textarea>; um </textarea> nele sairia do campo."""
    (raiz / "Inbox" / "Ideia.md").write_text("</textarea><img src=x onerror=alert(1)>")
    html = _tela(cliente, "Inbox/Ideia.md")
    assert "<img src=x" not in html
    assert "&lt;/textarea&gt;" in html


def test_nome_de_arquivo_estranho_e_escapado(cliente, raiz):
    """O Obsidian aceita nomes que a página não criaria; a árvore mostra mesmo assim."""
    (raiz / "Inbox" / "<b>negrito.md").write_text("x")
    html = _tela(cliente)
    assert "<b>negrito" not in html
    assert "&lt;b&gt;negrito" in html


def test_vault_vazio_convida_a_criar(cliente, raiz):
    import shutil

    shutil.rmtree(raiz)
    html = _tela(cliente)
    assert "Nenhuma nota ainda" in html


def test_a_pagina_so_carrega_script_de_arquivo(cliente):
    import re

    html = _tela(cliente)
    assert re.findall(r"<script[^>]*>", html) == ['<script src="/app.js" defer>']


def test_o_script_e_servido_como_javascript(cliente):
    resposta = cliente.get("/app.js")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/javascript")
    assert '"X-Aide": "1"' in resposta.text


def test_busca_lista_o_caminho_de_cada_achado(cliente, registry, config):
    from aide.storage.reconciliacao import reconciliar

    conn = cliente.app.state.conn_factory()
    reconciliar(conn, config.vault_dir)
    html = cliente.get("/notas?busca=ideia").text
    assert "Inbox/Ideia.md" in html
    assert "voltar às pastas" in html


def test_hidden_vence_o_display_das_classes():
    """O campo de criar aparecia vazio, aberto, porque .criar tem display:flex."""
    from aide.web.estilo import CSS

    assert "[hidden] { display: none !important; }" in CSS


def test_nota_privada_abre_sem_corretor(cliente):
    """O corretor avançado do Chrome manda o texto para o Google."""
    assert 'spellcheck="false"' in _tela(cliente, "Projetos/Casa/Telhado.md")
    assert 'spellcheck="true"' in _tela(cliente, "Inbox/Ideia.md")


def test_linha_vazia_no_comeco_sobrevive_ao_textarea(cliente, raiz):
    """O HTML descarta a primeira quebra depois de <textarea>."""
    import html as h
    import re

    (raiz / "Inbox" / "Ideia.md").write_text("\nlinha depois do vazio")
    pagina = _tela(cliente, "Inbox/Ideia.md")
    bruto = re.search(r'<textarea id="editor"[^>]*>(.*?)</textarea>', pagina, re.DOTALL).group(1)
    # o que o navegador vai pôr no campo: o conteúdo menos a primeira quebra
    assert h.unescape(bruto)[1:] == "\nlinha depois do vazio"


def test_a_busca_da_pagina_acha_a_privada(cliente, config):
    """Quem procura aqui é o dono; a tool do modelo esconde de propósito."""
    from aide.storage.reconciliacao import reconciliar

    reconciliar(cliente.app.state.conn_factory(), config.vault_dir)
    html = cliente.get("/notas?busca=telhas").text
    assert "Projetos/Casa/Telhado.md" in html


def test_script_e_estilo_nao_ficam_velhos_no_cache(cliente):
    """Com max-age, depois de atualizar o navegador rodava o script antigo
    contra rotas novas por até cinco minutos."""
    for caminho in ("/app.js", "/app.css"):
        assert cliente.get(caminho).headers["cache-control"] == "no-cache"


# ---------- prévia ----------

def test_a_previa_sai_pronta_com_os_links(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("# Ideia\n\nver [[Telhado]] e [[Nada]]")
    html = _tela(cliente, "Inbox/Ideia.md")
    previa = html[html.index('<article id="previa"'):]
    assert '<h1 id="s-ideia" data-fonte="0" data-bloco="0-1">Ideia</h1>' in previa
    assert 'href="/notas?arquivo=Projetos/Casa/Telhado.md"' in previa
    assert 'class="wikilink quebrado"' in previa


def test_o_editor_leva_a_lista_de_notas_para_o_autocompletar(cliente):
    import html as h
    import json
    import re

    pagina = _tela(cliente, "Inbox/Ideia.md")
    bruto = re.search(r'data-notas="([^"]*)"', pagina).group(1)
    assert json.loads(h.unescape(bruto)) == ["Inbox/Ideia.md", "Projetos/Casa/Telhado.md"]


def test_os_quatro_modos(cliente):
    html = _tela(cliente, "Inbox/Ideia.md")
    for modo in ("editar", "dividido", "vivo", "ler"):
        assert f'data-modo="{modo}"' in html


def test_o_modo_lembrado_vem_do_cookie(cliente):
    """Lido no servidor, a página já nasce no modo; sem piscar."""
    cliente.cookies.set("notas_modo", "ler")
    html = _tela(cliente, "Inbox/Ideia.md")
    assert '<div class="area" data-modo="ler">' in html
    assert 'data-modo="ler" aria-pressed="true"' in html


def test_o_modo_ao_vivo_tambem_fica_lembrado(cliente):
    cliente.cookies.set("notas_modo", "vivo")
    html = _tela(cliente, "Inbox/Ideia.md")
    assert '<div class="area" data-modo="vivo">' in html
    assert "data-bloco=" in html  # é por onde o script sabe que linhas abrir


def test_cookie_de_modo_estranho_cai_no_padrao(cliente):
    cliente.cookies.set("notas_modo", '"><script>')
    html = _tela(cliente, "Inbox/Ideia.md")
    assert '<div class="area" data-modo="dividido">' in html
    assert "<script>" not in html.split("</head>")[1]


# ---------- backlinks ----------

def test_backlinks_mostram_quem_aponta_e_o_contexto(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("pensar no [[Telhado]] antes da chuva")
    html = _tela(cliente, "Projetos/Casa/Telhado.md")
    painel = html[html.index('<section class="backlinks">'):]
    assert "Links para esta nota · 1 nota" in painel
    assert 'href="/notas?arquivo=Inbox/Ideia.md">Ideia</a>' in painel
    assert "pensar no [[Telhado]] antes da chuva" in painel


def test_sem_backlinks_diz_que_nao_ha(cliente):
    assert "Nenhuma nota aponta para esta ainda." in _tela(cliente, "Inbox/Ideia.md")


def test_contexto_do_backlink_e_escapado(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("<img src=x onerror=alert(1)> [[Telhado]]")
    html = _tela(cliente, "Projetos/Casa/Telhado.md")
    assert "<img src=x" not in html


# ---------- links quebrados ----------

def test_aviso_de_links_quebrados_na_lateral(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("[[Fornecedores]] e [[fornecedores]] e [[Orçamento]]")
    html = _tela(cliente, "Inbox/Ideia.md")
    assert "2 links quebrados</span></a>" in html
    assert 'href="/notas?quebrados=1&amp;arquivo=Inbox/Ideia.md"' in html


def test_sem_links_quebrados_sem_aviso(cliente):
    assert "aviso-quebrados" not in _tela(cliente)


def test_lista_de_quebrados_com_quem_cita_e_onde_criar(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("[[Fornecedores]]")
    (raiz / "Projetos" / "Casa" / "Telhado.md").write_text("[[Fornecedores]] [[Base/Nova]]")
    html = cliente.get("/notas?quebrados=1").text
    assert "<strong>Fornecedores</strong>" in html
    assert 'data-caminho="Inbox/Fornecedores.md"' in html
    assert 'data-caminho="Base/Nova.md"' in html
    assert "voltar às pastas" in html


def test_nome_que_nao_vira_arquivo_nao_ganha_botao(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("[[O que é?]] e [[../../fora]]")
    html = cliente.get("/notas?quebrados=1").text
    assert "criar-quebrado" not in html
    assert html.count("nome que não pode virar arquivo") == 2


def test_alvo_quebrado_e_escapado(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text('[[<img src=x onerror=alert(1)>]]')
    assert "<img src=x" not in cliente.get("/notas?quebrados=1").text


def test_quebrado_por_link_markdown_mostra_o_nome_de_verdade(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("[n](Nova%20nota.md) e [r](../Raiz.md) e [f](foto.png)")
    html = cliente.get("/notas?quebrados=1").text
    assert "<strong>Nova nota</strong>" in html
    assert 'data-caminho="Inbox/Nova nota.md"' in html
    assert 'data-caminho="Raiz.md"' in html
    lista = html[html.index('<div class="arvore"'):html.index("voltar às pastas")]
    # foto.png não vira item próprio (a linha citada pode mencioná-la)
    assert "<strong>foto" not in lista and 'data-caminho="Inbox/foto' not in lista


def test_nota_enorme_nao_abre_no_editor(cliente, raiz):
    """Um export de 3 MB jogado no vault não pode travar a página."""
    (raiz / "Inbox" / "Export.md").write_text("[[Telhado]] " + "x" * (3 * 1024 * 1024))
    html = _tela(cliente, "Inbox/Export.md")
    assert "grande demais para abrir" in html
    assert 'id="editor"' not in html
    # e o link dela não entra no mapa
    assert "Nenhuma nota aponta" in _tela(cliente, "Projetos/Casa/Telhado.md")


# ---------- renomear ----------

def test_titulo_abre_o_renomear_com_o_caminho(cliente):
    html = _tela(cliente, "Projetos/Casa/Telhado.md")
    assert '<h2 id="titulo" class="titulo-nota"' in html
    assert 'id="renomear-caminho" autocomplete="off" spellcheck="false"\n        value="Projetos/Casa/Telhado"' in html
    assert 'id="botao-renomear"' in html


def test_cada_pasta_tem_o_botao_de_renomear(cliente):
    html = _tela(cliente)
    for pasta in ("Inbox", "Projetos", "Projetos/Casa"):
        assert f'class="renomear-pasta" data-pasta="{pasta}"' in html


# ---------- visão geral ----------

def test_visao_geral_mostra_os_numeros_e_as_orfas(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("ver [[Telhado]] #casa")
    (raiz / "Solta.md").write_text("sozinha")
    html = cliente.get("/notas?geral=1").text
    painel = html[html.index('<div class="visao">'):]
    assert "Notas mexidas por dia" in painel
    assert "Mais citadas" in painel and ">Telhado</span>" in painel
    assert 'href="/notas?arquivo=Solta.md">Solta</a>' in painel
    assert 'id="editor"' not in html


def test_atalho_para_a_visao_geral_na_lateral(cliente):
    html = _tela(cliente, "Inbox/Ideia.md")
    assert 'href="/notas?geral=1&amp;arquivo=Inbox/Ideia.md"><svg' in html
    assert "<span>visão geral do vault</span>" in html


def test_visao_geral_escapa_nome_e_tag(cliente, raiz):
    (raiz / "Inbox" / "<b>x.md").write_text("#<i>tag")
    assert "<b>x" not in cliente.get("/notas?geral=1").text


def test_na_visao_geral_nenhuma_nota_fica_marcada_como_aberta(cliente):
    html = cliente.get("/notas?geral=1&arquivo=Inbox/Ideia.md").text
    assert 'aria-current="page" title' not in html.split('<div class="arvore"')[1].split("</div>")[0]


def test_tela_do_grafo(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("[[Telhado]]")
    html = cliente.get("/notas?grafo=1").text
    assert '<svg class="grafo"' in html
    assert "2 notas · 1 ligação" in html
    assert 'id="editor"' not in html


def test_grafo_local_ao_lado_dos_backlinks(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("[[Telhado]]")
    html = _tela(cliente, "Projetos/Casa/Telhado.md")
    assert "Grafo local · 1 vizinha" in html
    assert '<svg class="grafo local"' in html


def test_nota_sem_ligacao_nao_tem_grafo_local(cliente):
    assert "Grafo local" not in _tela(cliente, "Inbox/Ideia.md")


def test_cada_pasta_tem_o_botao_de_apagar(cliente):
    assert 'class="apagar-pasta" data-pasta="Projetos/Casa"' in _tela(cliente)


def test_a_lixeira_conta_as_notas_de_pasta_apagada(cliente, raiz):
    (raiz / ".trash" / "Velha" / "Sub").mkdir(parents=True)
    (raiz / ".trash" / "Velha" / "Sub" / "a.md").write_text("x")
    (raiz / ".trash" / "Velha" / "b.md").write_text("x")
    assert "2 arquivos na lixeira" in _tela(cliente)


def test_nota_fora_de_utf8_nao_derruba_a_tela(cliente, raiz):
    """Um .md antigo do Windows: a tela abre com um aviso, em vez de 500."""
    (raiz / "Inbox" / "Velha.md").write_bytes("acentua\xe7\xe3o".encode("latin-1"))
    html = _tela(cliente, "Inbox/Velha.md")
    assert "não está em UTF-8" in html
    assert 'id="editor"' not in html


def test_os_botoes_da_nota_tem_icone_e_dica(cliente):
    html = _tela(cliente, "Inbox/Ideia.md")
    assert 'role="toolbar" aria-label="ações da nota"' in html
    assert 'title="renomear ou mover · F2"' in html
    assert 'class="botao botao-perigo"' in html
    assert '<span class="rotulo">apagar</span>' in html
    assert "Ctrl+E alterna com ler" in html


def test_a_lateral_diz_onde_a_nota_nova_vai(cliente):
    html = _tela(cliente, "Projetos/Casa/Telhado.md")
    assert 'id="nova-nota" class="botao botao-principal"' in html
    assert 'title="nova nota em Projetos/Casa"' in html
    assert "Enter cria · Esc cancela" in html


def test_apagar_pasta_tem_lugar_para_o_aviso(cliente):
    assert '<span class="rotulo"></span></button>' in _tela(cliente)


@pytest.mark.parametrize("param, rotulo", [("geral", "visão geral do vault"), ("grafo", "grafo")])
def test_atalho_aberto_fica_no_lugar_e_marcado(cliente, param, rotulo):
    """Clicar não some com o atalho: ele fica marcado, e clicar de novo volta à nota."""
    html = cliente.get(f"/notas?{param}=1&arquivo=Inbox/Ideia.md").text
    import re

    assert re.search(r'<a class="atalho-visao" href="/notas\?arquivo=Inbox/Ideia.md"'
                     r' aria-current="page"><svg[^<]*<path[^>]*/></svg><span>'
                     + re.escape(rotulo) + "</span>", html)
    outro = "grafo" if param == "geral" else "geral"
    assert f'href="/notas?{outro}=1&amp;arquivo=Inbox/Ideia.md"' in html


def test_links_quebrados_aberto_fica_marcado(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("[[Fornecedores]]")
    html = cliente.get("/notas?quebrados=1&arquivo=Inbox/Ideia.md").text
    assert 'class="aviso-quebrados" href="/notas?arquivo=Inbox/Ideia.md" aria-current="page"' in html
    assert "1 link quebrado</span>" in html


def test_quem_cita_o_quebrado_leva_a_linha_do_link(cliente, raiz):
    (raiz / "Inbox" / "Ideia.md").write_text("primeira\n\nfalar com [[Fornecedores]] amanhã\n\n[[Fornecedores]]")
    html = cliente.get("/notas?quebrados=1").text
    assert 'href="/notas?arquivo=Inbox/Ideia.md&amp;linha=2&amp;alvo=Fornecedores"' in html
    assert "<span>Ideia</span>" in html
    assert '<span class="vezes">2×</span>' in html
    # o trecho sem [[ ]], com o link quebrado marcado
    assert '<span class="trecho">falar com <mark>Fornecedores</mark> amanhã</span>' in html
    assert "1 nota faltando · 2 citações" in html
    assert "nasce em Inbox/" in html


def test_trecho_do_quebrado_fica_em_volta_do_link_e_nao_vira_html():
    from aide.web.notas_tela import _trecho_do_link

    longo = "a" * 80 + " [[Outra|outra]] e [[Falta]] <b>" + "z" * 80
    html = _trecho_do_link(longo, "Falta")
    assert html.startswith("…") and html.endswith("…")
    assert "<mark>Falta</mark>" in html and "outra e" in html
    assert "<b>" not in html and "&lt;b&gt;" in html


def test_botao_de_anexar_aceita_so_os_tipos_da_lista(cliente):
    html = _tela(cliente, "Inbox/Ideia.md")
    assert 'id="botao-anexar" class="botao"' in html
    escolher = html.split('id="escolher-anexo"')[1].split(">")[0]
    assert ".png" in escolher and ".pdf" in escolher
    assert ".svg" not in escolher and ".html" not in escolher


def test_a_lista_da_tag_traz_as_notas_com_ela_e_as_aninhadas(cliente, raiz):
    (raiz / "Inbox" / "Obra.md").write_text("# Obra\n\nver #casa/telhado\n")
    (raiz / "Inbox" / "Sem.md").write_text("# Sem\n\nnada aqui\n")
    (raiz / "Inbox" / "Casa.md").write_text("---\ntags: [Casa]\n---\n\nx\n")
    html = cliente.get("/notas?tag=casa").text
    assert "#casa · 2 notas" in html
    assert "Inbox/Obra.md" in html and "Inbox/Casa.md" in html
    assert "Inbox/Sem.md</span>" not in html


def test_buscar_por_hashtag_abre_a_lista_da_tag(cliente, raiz):
    (raiz / "Inbox" / "Obra.md").write_text("# Obra\n\n#reforma\n")
    html = cliente.get("/notas?busca=%23reforma").text
    assert "#reforma · 1 nota" in html


def test_a_busca_poe_o_titulo_primeiro_e_marca_o_trecho_limpo(cliente, config, raiz):
    from aide.storage.reconciliacao import reconciliar

    (raiz / "Inbox" / "Muro.md").write_text(
        "# Muro\n\nsobre o muro, o muro e mais o muro do [[Vizinho|vizinho]]\n")
    (raiz / "Inbox" / "Outra.md").write_text("# Outra\n\nfala do muro uma vez\n")
    reconciliar(cliente.app.state.conn_factory(), config.vault_dir)
    html = cliente.get("/notas?busca=muro").text
    assert "2 resultados" in html
    assert html.index("Inbox/Muro.md</span>") < html.index("Inbox/Outra.md</span>")
    assert "<mark>muro</mark>" in html
    assert "[[" not in html.split('class="arvore')[1].split("voltar às pastas")[0]


def test_trecho_da_busca_nao_vira_html():
    from aide.web.notas_tela import _trecho

    assert _trecho("<img src=x> lt", ["img"]) == "&lt;<mark>img</mark> src=x&gt; lt"


def test_a_lista_de_notas_vem_mesmo_sem_nota_aberta(cliente):
    """O abrir rápido (Ctrl+O) precisa dela na página das pastas também."""
    html = cliente.get("/notas?geral=1").text
    assert '<div class="notas" data-notas="[' in html
    assert 'id="abrir-rapido"' in html and "Ctrl+O" in html


def test_quebrado_com_nome_parecido_sugere_ligar(cliente, raiz):
    (raiz / "Inbox" / "Fornecedores.md").write_text("# Fornecedores\n")
    (raiz / "Inbox" / "Ideia.md").write_text("falar com [[Fornecedor]]\n")
    html = cliente.get("/notas?quebrados=1").text
    assert 'class="ligar-quebrado" data-alvo="Fornecedor" data-para="Inbox/Fornecedores.md"' in html


# ---------- desenhos na árvore ----------

def _com_desenho(raiz, nome="Projetos/Casa/Planta.excalidraw"):
    from aide.storage import desenhos

    (raiz / nome).write_text(desenhos.vazio())


def test_desenho_aparece_na_arvore_e_abre_a_tela_dele(cliente, raiz):
    _com_desenho(raiz)
    html = cliente.get("/notas", params={"arquivo": "Inbox/Ideia.md"}).text
    assert ('<a class="arquivo desenho" '
            'href="/desenho?caminho=Projetos/Casa/Planta.excalidraw&amp;de=Inbox/Ideia.md"'
            ' title="Projetos/Casa/Planta.excalidraw">') in html
    assert "<span>Planta</span>" in html


def test_desenho_sem_nota_aberta_nao_leva_de(cliente, raiz):
    _com_desenho(raiz, "Solto.excalidraw")
    html = cliente.get("/notas", params={"geral": "true"}).text
    assert 'href="/desenho?caminho=Solto.excalidraw"' in html


def test_resumo_conta_desenhos_a_parte_e_a_pasta_conta_os_dois(cliente, raiz):
    _com_desenho(raiz)
    html = cliente.get("/notas", params={"arquivo": "Inbox/Ideia.md"}).text
    assert "2 notas" in html and "1 desenho" in html
    pasta = html[html.index('data-pasta="Projetos/Casa"'):]
    assert '<span class="conta">2</span>' in pasta[:pasta.index("</summary>")]


def test_desenho_nao_vira_destino_de_link_de_nota(cliente, raiz):
    """[[Planta]] é uma nota que não existe, não o desenho Planta.excalidraw."""
    from aide.storage import links

    _com_desenho(raiz)
    (raiz / "Inbox" / "Ideia.md").write_text("ver [[Planta]]")
    indice = links.indice(raiz)
    assert indice.resolver("Planta") is None
    assert "Projetos/Casa/Planta.excalidraw" not in indice.caminhos


def test_nome_de_desenho_sai_escapado_na_arvore(cliente, raiz):
    _com_desenho(raiz, "Plano & 'x'.excalidraw")
    html = cliente.get("/notas", params={"geral": "true"}).text
    assert "<span>Plano &amp; &#x27;x&#x27;</span>" in html
    assert 'title="Plano &amp; &#x27;x&#x27;.excalidraw"' in html


def test_arrastar_desenho_usa_a_rota_de_desenho():
    """A de nota recusaria o .excalidraw (e reescreve links de nota)."""
    from aide.web.script import JS

    assert ('var rota = /\\.excalidraw$/i.test(de) ? "/api/desenhos/mover" : "/api/notas/mover";'
            in JS)
    assert 'return pedir("POST", rota, { de: de, para: para });' in JS


def test_botao_de_novo_desenho_no_topo_e_em_cada_pasta(cliente, raiz):
    html = cliente.get("/notas", params={"arquivo": "Inbox/Ideia.md"}).text
    assert 'id="novo-desenho"' in html
    assert ('<button type="button" class="novo-desenho-na-pasta" data-pasta="Projetos/Casa"'
            in html)


def test_script_cria_desenho_pela_rota_dele_e_abre_a_tela():
    from aide.web.script import JS

    assert 'desenho: "/api/desenhos/arquivo"' in JS
    assert 'criando === "desenho" && !/\\.excalidraw$/i.test(caminho)' in JS
    assert 'location.href = "/desenho?caminho=" + encodeURIComponent(caminho)' in JS
    # cada id que o script procura existe na tela
    assert 'getElementById("novo-desenho")' in JS


def test_previa_da_nota_mostra_link_para_o_desenho(cliente, raiz):
    _com_desenho(raiz)
    (raiz / "Inbox" / "Ideia.md").write_text("ver [[Planta.excalidraw]]")
    html = cliente.get("/notas", params={"arquivo": "Inbox/Ideia.md"}).text
    assert 'class="wikilink desenho" href="/desenho?caminho=Projetos/Casa/Planta.excalidraw' in html
