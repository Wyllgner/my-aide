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
