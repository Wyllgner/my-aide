"""A tela Arquivos: a moldura que o servidor monta."""

import pytest
from fastapi.testclient import TestClient

from aide.storage import connect, migrate
from aide.web.app import criar_app


@pytest.fixture
def cliente(config, tmp_path):
    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return TestClient(criar_app(config, conn_factory), base_url="http://127.0.0.1:8787")


def test_a_tela_entra_no_menu_logo_depois_das_notas(cliente):
    html = cliente.get("/arquivos").text
    assert '<a href="/arquivos" aria-current="page">' in html
    assert html.index('href="/notas"') < html.index('href="/arquivos"') < html.index('href="/gastos"')


def test_tem_onde_soltar_e_escolher_varios(cliente):
    html = cliente.get("/arquivos").text
    assert 'id="arq-soltar"' in html
    assert '<input type="file" id="arq-escolher" multiple hidden>' in html
    assert "nada fica guardado" in html


def test_as_acoes_nascem_desligadas(cliente):
    """Sem arquivo marcado, nenhuma ação tem sobre o que agir: quem liga é o
    script, conforme o tipo do que você marcou."""
    from aide.web.arquivos_tela import ACOES

    html = cliente.get("/arquivos").text
    for chave, rotulo, *_ in ACOES:
        assert f'data-acao="{chave}" disabled' in html
        assert rotulo in html
    assert len(ACOES) == 6



def test_o_script_e_arquivo_da_casa(cliente):
    """A CSP só deixa rodar script daqui; embutido na página não rodaria."""
    html = cliente.get("/arquivos").text
    assert '<script type="module" src="/arquivos.js"></script>' in html
    resposta = cliente.get("/arquivos.js")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/javascript")
    assert "dataTransfer" in resposta.text


def test_soltar_nao_manda_nada_ao_servidor(cliente):
    """Até você escolher a ação, os arquivos ficam na página."""
    js = cliente.get("/arquivos.js").text
    assert "fetch(" not in js
    assert "innerHTML" not in js  # nome de arquivo é texto, nunca marcação


def test_o_pdf_e_lido_no_navegador_pelo_pdfjs_da_casa(cliente):
    js = cliente.get("/arquivos.js").text
    assert 'from "/vendor/pdfjs/pdf.js"' in js
    assert 'workerSrc = "/vendor/pdfjs/pdf.worker.js"' in js
    # WebAssembly precisaria de 'wasm-unsafe-eval' na CSP
    assert "useWasm: false" in js


def test_a_grade_de_paginas_nasce_escondida(cliente):
    html = cliente.get("/arquivos").text
    assert '<section class="card editor-pdf" id="arq-editor" hidden>' in html


def test_nenhum_id_da_tela_e_procurado_pelo_app_js(cliente):
    """O /app.js roda em toda página e liga o editor de notas se achar
    #editor: um id repetido aqui dispara código das notas nesta tela."""
    import re

    html = cliente.get("/arquivos").text
    ids = set(re.findall(r'id="([^"]+)"', html))
    procurados = set(re.findall(r'getElementById\("([^"]+)"\)', cliente.get("/app.js").text))
    assert ids and procurados
    assert not ids & procurados
