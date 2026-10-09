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
                                  "192.168.0.10:8787", "", "127.0.0.1:8787@evil.example",
                                  "localhost:evil", "127.0.0.1:", "[::1]:8787"])
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


# ---------- cabeçalhos ----------

def test_toda_tela_sai_com_os_cabecalhos(cliente):
    for tela in TELAS:
        cab = cliente.get(tela.caminho).headers
        assert cab["x-frame-options"] == "DENY", tela.caminho
        assert cab["x-content-type-options"] == "nosniff"
        assert cab["referrer-policy"] == "no-referrer"
        assert cab["cache-control"] == "no-store", "privado não pode ir para cache em disco"
        assert "frame-ancestors 'none'" in cab["content-security-policy"]


def test_script_so_da_propria_pagina():
    """Sem 'unsafe-inline' em script: um <script> que escape do escape não roda."""
    diretivas = dict(d.split(" ", 1) for d in seguranca.CSP.split("; "))
    assert diretivas["script-src"] == "'self'"
    assert diretivas["default-src"] == "'none'"


def test_recusa_tambem_sai_com_os_cabecalhos(app):
    resposta = TestClient(app, base_url="http://evil.example").get("/")
    assert resposta.headers["x-frame-options"] == "DENY"


# ---------- injeção pelo que você escreveu ----------

ISCA = '"><img src=x onerror=alert(1)>'


@pytest.fixture
def com_iscas(app, registry):
    """A isca em todo campo que alguma tela mostra."""
    ctx = app.state.contexto()
    registry.call("tasks.create", {"title": ISCA, "project": ISCA, "tags": ISCA,
                                   "notes": ISCA, "due": "2020-01-01T09:00"}, ctx)
    registry.call("tasks.create", {"title": ISCA, "project": ISCA}, ctx)
    registry.call("notes.create", {"title": ISCA, "body": ISCA, "tags": ISCA}, ctx)
    registry.call("expenses.add", {"amount": "10", "description": ISCA,
                                   "category": ISCA, "tag": ISCA}, ctx)
    registry.call("people.add", {"name": ISCA, "relation": ISCA, "cadence_days": 1,
                                 "last_contact": "2020-01-01"}, ctx)
    registry.call("memory.save", {"kind": "profile", "key": ISCA, "value": ISCA}, ctx)
    registry.call("work_orders.create", {"goal": ISCA, "context": ISCA}, ctx)
    ctx.conn.execute("INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                     (ISCA, ISCA))
    ctx.conn.execute("INSERT INTO audit (actor, tool, args_json, result_summary)"
                     " VALUES (?, ?, ?, ?)", (ISCA, ISCA, ISCA, ISCA))
    ctx.conn.commit()
    return app


def test_nenhuma_tela_devolve_a_isca_crua(cliente, com_iscas):
    for tela in TELAS:
        html = cliente.get(tela.caminho).text
        assert "<img src=x" not in html, tela.caminho


@pytest.mark.parametrize("consulta", [
    "/gastos?q={i}&categoria={i}&tag={i}&forma={i}&tipo={i}&de={i}&ate={i}&min={i}&max={i}&ordem={i}&periodo={i}",
    "/notas?busca={i}",
    "/conversas?sessao={i}",
    "/auditoria?ator={i}",
])
def test_parametro_da_url_nao_volta_cru(cliente, com_iscas, consulta):
    from urllib.parse import quote

    html = cliente.get(consulta.format(i=quote(ISCA))).text
    assert "<img src=x" not in html


def test_a_isca_chegou_mesmo_as_telas(cliente, com_iscas):
    """Sem isto o teste acima passaria com o banco vazio."""
    for caminho in ("/hoje", "/notas", "/gastos", "/pessoas", "/memoria", "/fila",
                    "/conversas", "/auditoria", "/calendario?ano=2020&mes=1"):
        assert "&lt;img src=x" in cliente.get(caminho).text, caminho


def test_corpo_enorme_e_recusado_antes_de_ser_lido(cliente):
    cabecalhos = {"origin": LOCAL, "x-aide": "1", "content-length": str(50 * 1024 * 1024)}
    assert cliente.put("/api/notas/arquivo", headers=cabecalhos).status_code == 413


def test_tamanho_que_nao_e_numero_e_recusado():
    assert seguranca.corpo_grande_demais("abc")
    assert not seguranca.corpo_grande_demais(None)


# ---------- fontes ----------

def test_a_pagina_nao_chama_nada_de_fora(cliente):
    """As fontes vinham do Google: cada página aberta avisava a ele."""
    html = cliente.get("/").text
    assert "googleapis" not in html and "gstatic" not in html
    assert "http" not in seguranca.CSP


def test_fontes_servidas_pelo_proprio_site(cliente):
    from aide.web.estilo import CSS

    nomes = __import__("re").findall(r"url\(/fontes/([^)]+)\)", CSS)
    assert len(nomes) == 8
    for nome in nomes:
        resposta = cliente.get(f"/fontes/{nome}")
        assert resposta.status_code == 200, nome
        assert resposta.headers["content-type"] == "font/woff2"
        assert resposta.content[:4] == b"wOF2"


@pytest.mark.parametrize("nome", ["../app.py", "..%2Fapp.py", "OFL-publicsans.txt", "x.woff2"])
def test_rota_de_fontes_so_entrega_as_fontes(cliente, nome):
    assert cliente.get(f"/fontes/{nome}").status_code == 404
