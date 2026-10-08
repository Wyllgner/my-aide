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
from aide.web import criar_app
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
