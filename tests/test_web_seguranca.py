"""A fronteira da página contra o próprio navegador do dono.

Escutar em 127.0.0.1 só barra outras máquinas. Estes testes cobrem o que um
site aberto noutra aba consegue fazer com a página: lê-la por DNS rebinding,
escrever nela por um formulário, ou injetar script pelo que você mesmo
escreveu numa tarefa ou nota.
"""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import connect, migrate
from aide.web import criar_app, seguranca
from aide.web.paginas import TELAS

LOCAL = "http://127.0.0.1:8787"


@pytest.fixture
def app(config, tmp_path):
    object.__setattr__(config, "vault_dir", tmp_path / "vault")

    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app, base_url=LOCAL)


# ---------- Host ----------

@pytest.mark.parametrize("host", ["evil.example", "evil.example:8787", "127.0.0.1.evil.example",
                                  "192.168.0.10:8787", ""])
def test_host_de_fora_e_recusado_em_toda_tela(app, host):
    """DNS rebinding: o domínio do atacante passa a apontar para cá, e o
    navegador entrega a página a ele. O nome no Host é o que o denuncia."""
    cliente = TestClient(app, base_url=LOCAL)
    for tela in TELAS:
        resposta = cliente.get(tela.caminho, headers={"host": host})
        assert resposta.status_code == 421, tela.caminho


@pytest.mark.parametrize("host", ["127.0.0.1:8787", "localhost:8787", "LOCALHOST:9999",
                                  "127.0.0.1"])
def test_host_local_passa(app, host):
    assert TestClient(app, base_url=LOCAL).get("/", headers={"host": host}).status_code == 200


def test_saude_tambem_confere_o_host(app):
    assert TestClient(app, base_url="http://evil.example").get("/saude").status_code == 421


# ---------- escrita ----------

def test_escrita_sem_o_cabecalho_da_pagina_e_recusada(cliente):
    """O formulário de outro site não consegue pôr X-Aide."""
    resposta = cliente.post("/", headers={"origin": LOCAL})
    assert resposta.status_code == 403


def test_escrita_de_outra_origem_e_recusada(cliente):
    resposta = cliente.post("/", headers={"origin": "http://evil.example", "x-aide": "1"})
    assert resposta.status_code == 403


def test_escrita_sem_origin_e_recusada(cliente):
    assert cliente.post("/", headers={"x-aide": "1"}).status_code == 403


def test_escrita_de_outro_site_pelo_sec_fetch_e_recusada(cliente):
    resposta = cliente.post("/", headers={"origin": LOCAL, "x-aide": "1",
                                          "sec-fetch-site": "cross-site"})
    assert resposta.status_code == 403


@pytest.mark.parametrize("metodo", ["put", "delete", "patch"])
def test_todo_metodo_de_escrita_passa_pela_mesma_porta(cliente, metodo):
    assert getattr(cliente, metodo)("/").status_code == 403


def test_origin_com_porta_trocada_e_outra_origem():
    assert seguranca.escrita_permitida("POST", "127.0.0.1:8787", "http://127.0.0.1:8788",
                                       "1", "same-origin")
    assert seguranca.escrita_permitida("POST", "127.0.0.1:8787", "https://127.0.0.1:8787",
                                       "1", "same-origin")
    assert seguranca.escrita_permitida("POST", "127.0.0.1:8787", "http://127.0.0.1:8787",
                                       "1", "same-origin") is None
