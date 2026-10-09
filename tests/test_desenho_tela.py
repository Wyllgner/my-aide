"""A tela de um desenho (/desenho) e o seu script (/desenho.js)."""

import re
import shutil
import subprocess

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import connect, desenhos, migrate
from aide.web import criar_app

LOCAL = "http://127.0.0.1:8787"


@pytest.fixture
def app(config, tmp_path):
    object.__setattr__(config, "vault_dir", tmp_path / "vault")
    (tmp_path / "vault" / "Projetos").mkdir(parents=True)
    (tmp_path / "vault" / "Projetos" / "Casa.excalidraw").write_text(desenhos.vazio())
    (tmp_path / "vault" / "Inbox").mkdir()
    (tmp_path / "vault" / "Inbox" / "Obra.md").write_text("# Obra\n")

    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app, base_url=LOCAL)


def _tela(cliente, **params):
    return cliente.get("/desenho", params={"caminho": "Projetos/Casa.excalidraw", **params})


def test_tela_monta_a_casca_com_o_caminho_e_o_editor(cliente):
    resposta = _tela(cliente)
    assert resposta.status_code == 200
    html = resposta.text
    assert 'data-caminho="Projetos/Casa.excalidraw"' in html
    assert '<script type="module" src="/desenho.js"></script>' in html
    assert 'href="/vendor/excalidraw/excalidraw.css"' in html
    assert "<title>Casa · my-aide</title>" in html
    # nenhum script embutido: a CSP não deixaria rodar
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)


def test_tela_tem_a_csp_do_site(cliente):
    csp = _tela(cliente).headers["content-security-policy"]
    assert "script-src 'self'" in csp and "unsafe-eval" not in csp


def test_nome_sai_escapado(cliente, app):
    """< e > o vault já recusa no nome; & e aspa simples ele aceita."""
    from pathlib import Path

    raiz = Path(app.state.config.vault_dir)
    nome = "Plano & 'x'.excalidraw"
    (raiz / nome).write_text(desenhos.vazio())
    html = cliente.get("/desenho", params={"caminho": nome}).text
    assert 'data-caminho="Plano &amp; &#x27;x&#x27;.excalidraw"' in html
    assert "<strong>Plano &amp; &#x27;x&#x27;</strong>" in html
    assert cliente.get("/desenho", params={"caminho": "<b>.excalidraw"}).status_code == 400


def test_volta_para_a_nota_de_onde_veio(cliente):
    assert 'href="/notas?arquivo=Inbox/Obra.md"' in _tela(cliente, de="Inbox/Obra.md").text


@pytest.mark.parametrize("de", [
    "https://evil.com", "//evil.com", "javascript:alert(1)", "../fora.md", "Inbox/Nada.md",
    "Projetos/Casa.excalidraw", "/notas", "",
])
def test_volta_so_para_nota_que_existe_no_vault(cliente, de):
    """`de` vem da URL: link de volta não pode levar para fora do site."""
    html = _tela(cliente, de=de).text
    assert re.search(r'<a class="botao" href="/notas">', html), de


@pytest.mark.parametrize("caminho,status", [
    ("../fora.excalidraw", 400), ("Inbox/Obra.md", 400), (".trash/x.excalidraw", 400),
    ("Projetos/Nada.excalidraw", 404),
])
def test_caminho_invalido_ou_ausente_e_pagina_de_erro(cliente, caminho, status):
    resposta = cliente.get("/desenho", params={"caminho": caminho})
    assert resposta.status_code == status
    assert 'href="/notas"' in resposta.text
    assert "desenho.js" not in resposta.text


def test_tela_fora_da_navegacao_lateral(cliente):
    """É uma tela de um arquivo, não uma seção: não entra no menu."""
    assert 'href="/desenho' not in cliente.get("/notas").text


# ---------- o script ----------

def test_script_e_servido_como_modulo(cliente):
    resposta = cliente.get("/desenho.js")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/javascript")
    assert 'from "/vendor/excalidraw/excalidraw.js"' in resposta.text


def test_script_importa_so_o_que_o_bundle_exporta(cliente):
    from aide.web.desenho_script import JS

    importado = re.search(r"import \{([^}]*)\} from", JS).group(1)
    nomes = {n.strip() for n in importado.split(",")} - {""}
    entrada = cliente.get("/vendor/excalidraw/excalidraw.js").text
    exportado = re.search(r"export\{([^}]*)\}", entrada).group(1)
    publicos = {parte.split(" as ")[-1].strip() for parte in exportado.split(",")}
    assert nomes <= publicos, nomes - publicos


@pytest.mark.skipif(shutil.which("node") is None, reason="sem node")
def test_script_e_javascript_valido(tmp_path):
    from aide.web.desenho_script import JS

    arquivo = tmp_path / "desenho.mjs"
    arquivo.write_text(JS)
    subprocess.run([shutil.which("node"), "--check", str(arquivo)], check=True,
                   capture_output=True)
