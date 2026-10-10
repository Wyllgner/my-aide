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
    html = cliente.get("/notas").text
    nav = html[html.index("<nav>"):html.index("</nav>")]
    assert "/desenho" not in nav


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


def test_todo_elemento_que_o_script_procura_existe_na_tela(cliente):
    """Um id trocado de um lado só deixa a página quebrada sem erro no Python."""
    from aide.web.desenho_script import JS

    html = _tela(cliente).text
    ids = set(re.findall(r'getElementById\("([^"]+)"\)', JS))
    assert {"desenho", "desenho-estado", "conflito", "usar-meu", "usar-disco"} <= ids
    for id_ in ids:
        assert f'id="{id_}"' in html, id_


def test_conflito_comeca_escondido(cliente):
    assert re.search(r'<div id="conflito"[^>]*\bhidden\b', _tela(cliente).text)


def test_script_salva_com_a_marca_da_pagina_e_so_a_caixa_mexe_no_privado():
    """Sem X-Aide a fronteira recusa. E `privada` só vai no pedido quando a
    caixa mudou: no salvamento comum o servidor mantém o que está no disco."""
    from aide.web.desenho_script import JS

    assert '"X-Aide": "1"' in JS
    assert re.findall(r"corpo\.privada\s*=\s*\w+", JS) == ["corpo.privada = pedida"]
    assert "if (pedida !== null) corpo.privada = pedida;" in JS
    assert "privada:" not in JS


def test_caixa_de_privado_comeca_desabilitada(cliente):
    """Só depois de o desenho abrir dá para saber se ele é privado."""
    assert re.search(r'<input type="checkbox" id="privada" disabled>', _tela(cliente).text)


def test_desenho_privado_desliga_o_corretor_quando_o_campo_nasce():
    """O corretor avançado do Chrome manda o texto para o Google. O campo de
    texto do Excalidraw nasce na hora de editar, e evento de foco nem sempre
    dispara: vale o MutationObserver, e a troca da caixa reaplica."""
    from aide.web.desenho_script import JS

    assert "campo.spellcheck = !caixaPrivada.checked" in JS
    assert ".observe(raiz, { childList: true, subtree: true })" in JS
    troca = JS[JS.index('caixaPrivada.addEventListener("change"'):]
    assert "corretor(raiz);" in troca[:troca.index("});")]


def test_desenho_grande_demais_avisa_o_limite():
    """O 413 vem da fronteira, antes da rota, e não é JSON."""
    from aide.web.desenho_script import JS

    assert "resposta.status === 413" in JS and "20 MB" in JS


def test_procurar_bibliotecas_escondido():
    from aide.web.estilo import CSS

    assert ".library-menu-browse-button {\n  display: none; }" in CSS


def test_apagar_pede_dois_cliques_e_para_de_salvar():
    """Um salvamento depois de apagar recriaria o desenho."""
    from aide.web.desenho_script import JS

    clique = JS[JS.index('botaoApagar.addEventListener("click"'):]
    assert clique.index("if (!armado)") < clique.index('method: "DELETE"')
    assert clique.index("apagado = true;") < clique.index('method: "DELETE"')
    assert 'headers: { "X-Aide": "1" }' in clique
    assert "api !== null && !apagado" in JS


def test_botao_apagar_na_barra(cliente):
    html = _tela(cliente).text
    barra = html[html.index('<header class="desenho-barra">'):html.index("</header>")]
    assert 'id="apagar" class="botao botao-perigo"' in barra
