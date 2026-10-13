"""A rota que monta PDF: recebe, devolve e não guarda nada."""

import io
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from aide.storage import connect, migrate
from aide.web.app import criar_app

ROTA = "/api/arquivos/montar"
ESCRITA = {"X-Aide": "1", "Origin": "http://127.0.0.1:8787",
           "Content-Type": "application/octet-stream"}


def pdf_com(larguras) -> bytes:
    escritor = PdfWriter()
    for largura in larguras:
        escritor.add_blank_page(width=largura, height=200)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def corpo(arquivos: list[bytes], paginas) -> bytes:
    plano = {"arquivos": [len(a) for a in arquivos], "paginas": paginas}
    return json.dumps(plano).encode() + b"\n" + b"".join(arquivos)


def larguras(resposta) -> list[int]:
    return [int(p.mediabox.width) for p in PdfReader(io.BytesIO(resposta.content)).pages]


@pytest.fixture
def app(config, tmp_path):
    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app, base_url="http://127.0.0.1:8787")


@pytest.fixture
def temporarios(monkeypatch, tmp_path):
    """As pastas que a rota cria, num lugar onde o teste consegue olhar."""
    base = tmp_path / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    return base


def test_monta_na_ordem_pedida_com_dois_arquivos(cliente, temporarios):
    a, b = pdf_com([101, 102, 103]), pdf_com([201, 202])
    resposta = cliente.post(ROTA, content=corpo([a, b], [[0, 2], [1, 0], [0, 0]]), headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["cache-control"] == "no-store"
    assert larguras(resposta) == [103, 201, 101]


def test_nao_sobra_nada_depois_da_resposta(cliente, temporarios):
    a = pdf_com([101])
    assert cliente.post(ROTA, content=corpo([a], [[0, 0]]), headers=ESCRITA).status_code == 200
    assert list(temporarios.iterdir()) == []


def test_nem_quando_o_pedido_falha(cliente, temporarios):
    resposta = cliente.post(ROTA, content=corpo([b"nao sou pdf"], [[0, 0]]), headers=ESCRITA)
    assert resposta.status_code == 422
    assert "não é um PDF" in resposta.json()["detail"]
    assert list(temporarios.iterdir()) == []


def test_nao_toca_no_vault_nem_na_auditoria(cliente, app, config):
    antes = sorted(Path(config.vault_dir).rglob("*")) if Path(config.vault_dir).exists() else []
    conn = app.state.conn_factory()
    trilha = conn.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"]
    cliente.post(ROTA, content=corpo([pdf_com([101])], [[0, 0]]), headers=ESCRITA)
    depois = sorted(Path(config.vault_dir).rglob("*")) if Path(config.vault_dir).exists() else []
    assert depois == antes
    assert conn.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"] == trilha


@pytest.mark.parametrize("bruto, motivo", [
    (b"sem plano nenhum", "não começa com o plano"),
    (b"{nao e json}\n", "plano ilegível"),
    (b'{"arquivos": [], "paginas": []}\n', "de 1 a"),
    (b'{"arquivos": [0], "paginas": [[0, 0]]}\n', "nenhum vazio"),
    (b'{"arquivos": [5], "paginas": "tudo"}\nabcde', "páginas ilegível"),
    (b'{"arquivos": [5], "paginas": [[0, 0]]}\nabc', "menos bytes"),
    (b'{"arquivos": [2], "paginas": [[0, 0]]}\nabcdef', "mais bytes"),
])
def test_pedido_que_nao_fecha(cliente, temporarios, bruto, motivo):
    resposta = cliente.post(ROTA, content=bruto, headers=ESCRITA)
    assert resposta.status_code == 400
    assert motivo in resposta.json()["detail"]
    assert list(temporarios.iterdir()) == []


def test_pagina_que_nao_existe_e_422(cliente):
    resposta = cliente.post(ROTA, content=corpo([pdf_com([101])], [[0, 3]]), headers=ESCRITA)
    assert resposta.status_code == 422
    assert "não tem a página 4" in resposta.json()["detail"]


def test_plano_que_promete_demais_e_recusado_antes_de_ler(cliente, monkeypatch):
    from aide import arquivos

    monkeypatch.setattr(arquivos, "TAMANHO_MAXIMO", 10)
    monkeypatch.setattr("aide.web.arquivos_api.TAMANHO_MAXIMO", 10)
    resposta = cliente.post(ROTA, content=b'{"arquivos": [11], "paginas": [[0, 0]]}\n',
                            headers=ESCRITA)
    assert resposta.status_code == 413


def test_corpo_acima_do_limite_nem_entra(cliente):
    from aide import arquivos

    tamanho = str(arquivos.TAMANHO_MAXIMO + arquivos.PLANO_MAXIMO + 1)
    resposta = cliente.post(ROTA, content=b"x", headers={**ESCRITA, "Content-Length": tamanho})
    assert resposta.status_code == 413


def test_o_limite_desta_tela_e_maior_que_o_das_notas():
    """PDF escaneado passa fácil dos 3 MB do corpo comum."""
    from aide import arquivos
    from aide.web import seguranca

    assert seguranca.limite_do_corpo("POST", ROTA) == arquivos.TAMANHO_MAXIMO + arquivos.PLANO_MAXIMO
    assert seguranca.limite_do_corpo("POST", "/api/notas/arquivo") == seguranca.CORPO_MAXIMO


@pytest.mark.parametrize("cabecalhos", [
    {"Origin": "http://127.0.0.1:8787"},                     # sem X-Aide
    {"X-Aide": "1", "Origin": "http://evil.example"},        # de outro site
])
def test_vale_a_fronteira_de_escrita(cliente, cabecalhos):
    resposta = cliente.post(ROTA, content=corpo([pdf_com([101])], [[0, 0]]), headers=cabecalhos)
    assert resposta.status_code == 403
