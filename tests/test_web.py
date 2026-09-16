"""A interface web: esqueleto e, sobretudo, a fronteira.

A página mostra tudo — inclusive o que está marcado como `private` — e não pede
senha. O que a torna segura é escutar só em 127.0.0.1. Esse é o teste que não
pode falhar em silêncio, porque a falha dele vaza dado pessoal na rede.
"""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import connect, migrate
from aide.web import ENDERECO, criar_app


@pytest.fixture
def app(config, tmp_path):
    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app)


# ---------- a fronteira ----------

def test_o_endereco_e_loopback():
    """Constante, não configuração: endereço em arquivo se troca e se esquece."""
    import ipaddress

    assert ipaddress.ip_address(ENDERECO).is_loopback


def test_o_endereco_nao_vem_de_configuracao(config):
    """Se virar opção, a única defesa da interface passa a ser um valor editável."""
    import aide.web.app as modulo

    assert not hasattr(config, "web_host")
    assert modulo.ENDERECO == "127.0.0.1"


def test_o_servidor_so_escuta_em_loopback(monkeypatch, config, tmp_path):
    """O que chega ao uvicorn, e não só o que a constante diz."""
    capturado = {}

    class FakeConfig:
        def __init__(self, app, **kw):
            capturado.update(kw)

    class FakeServer:
        def __init__(self, cfg):
            self.should_exit = False

        def run(self):
            pass

    import uvicorn
    monkeypatch.setattr(uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(uvicorn, "Server", FakeServer)

    from aide.web.servidor import ServidorWeb

    ServidorWeb(config, lambda: connect(tmp_path / "s.db"))
    assert capturado["host"] == "127.0.0.1"
    assert capturado["host"] not in ("0.0.0.0", "::", "")


def test_a_url_anunciada_e_local(config, tmp_path, monkeypatch):
    from aide.web.servidor import ServidorWeb

    monkeypatch.setattr("uvicorn.Server", lambda cfg: type(
        "S", (), {"should_exit": False, "run": lambda self: None})())
    servidor = ServidorWeb(config, lambda: connect(tmp_path / "s.db"), porta=9999)
    assert servidor.url == "http://127.0.0.1:9999"


# ---------- só leitura ----------

def test_nenhuma_rota_escreve(app):
    """Sem POST não há confirmação a pedir nem clique errado a temer."""
    metodos = set()
    for rota in app.routes:
        metodos |= getattr(rota, "methods", set())
    assert metodos <= {"GET", "HEAD"}, f"rota de escrita exposta: {metodos}"


def test_a_api_nao_publica_documentacao(cliente):
    """/docs montaria um formulário de chamada — superfície sem motivo."""
    for caminho in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(caminho).status_code == 404


# ---------- o esqueleto ----------

def test_a_raiz_responde_html(cliente):
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/html")
    assert "my-aide" in resposta.text


def test_a_pagina_declara_fuso_e_idioma(cliente):
    assert 'lang="pt-BR"' in cliente.get("/").text


def test_saude_responde(cliente):
    dados = cliente.get("/saude").json()
    assert dados["ok"] is True
    assert dados["escutando"] == "127.0.0.1"


def test_caminho_desconhecido_e_404(cliente):
    assert cliente.get("/nao-existe").status_code == 404


# ---------- o contexto que as telas vão usar ----------

def test_o_contexto_ve_o_privado(app):
    """É o dono, na máquina dele, numa porta local — como o terminal."""
    ctx = app.state.contexto()
    assert ctx.ver_privado is True
    assert ctx.actor == "web"


def test_cada_pedido_abre_sua_conexao(app):
    """O uvicorn atende em thread; sqlite recusa conexão criada noutra."""
    assert app.state.contexto().conn is not app.state.contexto().conn


# ---------- a moldura ----------

def test_toda_tela_tem_rota(cliente):
    """A navegação mostra 12 links; um deles em 404 é um beco sem saída."""
    from aide.web.paginas import TELAS

    for tela in TELAS:
        resposta = cliente.get(tela.caminho)
        assert resposta.status_code == 200, tela.caminho
        assert tela.rotulo in resposta.text


def test_a_tela_aberta_se_marca_na_navegacao(cliente):
    """aria-current diz ao leitor de tela onde ele está, não só a cor."""
    html = cliente.get("/gastos").text
    assert '<a href="/gastos" aria-current="page">' in html
    assert '<a href="/notas" aria-current="page">' not in html


def test_o_estilo_e_servido_uma_vez(cliente):
    """Inline em cada página, o navegador reprocessaria o mesmo texto a cada clique."""
    resposta = cliente.get("/app.css")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/css")
    assert "--accent:#C4432B" in resposta.text
    assert '<link rel="stylesheet" href="/app.css">' in cliente.get("/").text


def test_o_titulo_da_aba_diz_onde_voce_esta(cliente):
    assert "<title>Calendário · my-aide</title>" in cliente.get("/calendario").text


def test_sem_saldo_anotado_a_lateral_convida_a_anotar(cliente):
    """Melhor pedir o número do que inventar um."""
    html = cliente.get("/").text
    assert "nenhum anotado" in html
    assert "myaide saldo" in html


def test_com_saldo_anotado_a_lateral_mostra(cliente, app):
    from aide.llm import custo as calculo

    calculo.anotar_saldo(app.state.conn_factory(), 4.22, "2026-09-16T17:00-04:00")
    html = cliente.get("/").text
    assert "US$&nbsp;4,22" in html or "4.22" in html


def test_saldo_quebrado_nao_derruba_a_pagina(cliente, app, monkeypatch):
    """A lateral é enfeite perto do conteúdo; ela falha sozinha."""
    monkeypatch.setattr("aide.llm.custo.saldo_estimado",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "Saldo API" in resposta.text


def test_o_texto_da_tela_e_escapado():
    """Título de nota com < ou & não pode virar marcação."""
    from aide.web.paginas import cabecalho

    assert "&lt;script&gt;" in cabecalho("<script>")


def test_icone_e_desenhado_nao_emoji():
    """Emoji vira bloco em tema/fonte que não tem o glifo."""
    from aide.web.icones import icone

    marcacao = icone("gastos")
    assert marcacao.startswith("<svg")
    assert "currentColor" in marcacao  # recolore junto com o texto


def test_valor_usa_virgula_como_a_pagina_toda():
    """A interface é em português; 'US$ 4.21' destoa de 'R$ 10,50' no resto."""
    from aide.web.paginas import usd

    assert usd(4.21) == "US$ 4,21"
    assert usd(0) == "US$ 0,00"
