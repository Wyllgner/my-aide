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

