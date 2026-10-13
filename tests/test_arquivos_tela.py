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
    assert 'id="soltar"' in html
    assert '<input type="file" id="escolher" multiple hidden>' in html
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
