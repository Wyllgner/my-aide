"""Anexos do vault: achar, servir e mostrar — sem abrir porta para script."""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import anexos, links
from aide.storage.vault import ForaDoVault
from aide.web import markdown

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    for caminho, conteudo in {
        "Casa/anexos/planta.png": PNG, "Outra/planta.png": PNG, "Casa/orcamento.pdf": b"%PDF-1.4",
        "Casa/audio.mp3": b"ID3", "Casa/evil.svg": b"<svg><script>alert(1)</script></svg>",
        "Casa/pagina.html": b"<script>alert(1)</script>", "Casa/Nota.md": b"x",
        ".trash/apagada.png": PNG,
    }.items():
        (pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
        (pasta / caminho).write_bytes(conteudo)
    return pasta


# ---------- índice e caminho ----------

def test_acha_pelo_nome_na_mesma_pasta_primeiro(raiz):
    indice = anexos.indice(raiz)
    assert indice.resolver("planta.png", "Casa/Nota.md") == "Casa/anexos/planta.png"
    assert indice.resolver("planta.png", "Outra/x.md") == "Outra/planta.png"
    assert indice.resolver("PLANTA.PNG") is not None
    assert indice.resolver("anexos/planta.png") == "Casa/anexos/planta.png"


@pytest.mark.parametrize("nome", ["evil.svg", "pagina.html", "Nota.md", "apagada.png", "nada.png"])
def test_fora_da_lista_ou_oculto_nao_e_anexo(raiz, nome):
    assert anexos.indice(raiz).resolver(nome) is None


@pytest.mark.parametrize("caminho", ["Casa/evil.svg", "Casa/pagina.html", "../fora.png",
                                     ".trash/apagada.png", "/etc/x.png"])
def test_resolver_recusa(raiz, caminho):
    with pytest.raises(ForaDoVault):
        anexos.resolver(raiz, caminho)


def test_link_simbolico_nao_entra(raiz, tmp_path):
    fora = tmp_path / "fora.png"
    fora.write_bytes(PNG)
    (raiz / "Casa" / "atalho.png").symlink_to(fora)
    assert anexos.indice(raiz).resolver("atalho.png") is None
    with pytest.raises(ForaDoVault):
        anexos.resolver(raiz, "Casa/atalho.png")


# ---------- prévia ----------

def _html(raiz, texto):
    return markdown.renderizar(texto, "Casa/Nota.md", links.indice(raiz), anexos.indice(raiz))


def test_imagem_do_vault_aparece_com_largura(raiz):
    html = _html(raiz, "![[planta.png|300]]")
    assert '<img class="anexo-imagem" src="/api/notas/anexo?caminho=Casa/anexos/planta.png"' in html
    assert 'width="300"' in html


def test_imagem_markdown_relativa_a_nota(raiz):
    assert 'caminho=Casa/anexos/planta.png"' in _html(raiz, "![planta](anexos/planta.png)")


def test_pdf_vira_link_e_audio_vira_player(raiz):
    html = _html(raiz, "[[orcamento.pdf]] ![[audio.mp3]]")
    assert '<a class="anexo" href="/api/notas/anexo?caminho=Casa/orcamento.pdf"' in html
    assert '<audio class="anexo-midia" controls' in html


def test_svg_nunca_vira_imagem(raiz):
    html = _html(raiz, "![[evil.svg]] ![x](evil.svg)")
    assert "<img" not in html and "evil.svg</span>" in html


def test_imagem_de_fora_continua_bloqueada(raiz):
    assert "<img" not in _html(raiz, "![x](https://rastreio.exemplo/p.png)")


def test_largura_absurda_e_ignorada(raiz):
    assert "width=" not in _html(raiz, "![[planta.png|999999]]")


# ---------- rota ----------

@pytest.fixture
def cliente(config, tmp_path, raiz):
    from aide.storage import connect, migrate
    from aide.web import criar_app

    object.__setattr__(config, "vault_dir", raiz)

    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return TestClient(criar_app(config, conn_factory), base_url="http://127.0.0.1:8787")


def test_rota_entrega_com_o_tipo_certo_e_csp_propria(cliente):
    resposta = cliente.get("/api/notas/anexo", params={"caminho": "Casa/orcamento.pdf"})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert "sandbox" in resposta.headers["content-security-policy"]
    assert "orcamento.pdf" in resposta.headers["content-disposition"]
    assert resposta.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("caminho, codigo", [
    ("Casa/evil.svg", 400), ("Casa/pagina.html", 400), ("Casa/Nota.md", 400),
    ("../fora.png", 400), (".trash/apagada.png", 400), ("Casa/nada.png", 404),
])
def test_rota_recusa(cliente, caminho, codigo):
    assert cliente.get("/api/notas/anexo", params={"caminho": caminho}).status_code == codigo


def test_rota_de_outro_host_e_recusada(cliente):
    resposta = cliente.get("/api/notas/anexo", params={"caminho": "Casa/orcamento.pdf"},
                           headers={"host": "evil.example"})
    assert resposta.status_code == 421


def test_anexo_grande_demais(cliente, raiz, monkeypatch):
    monkeypatch.setattr(anexos, "TAMANHO_MAXIMO", 1)
    assert cliente.get("/api/notas/anexo",
                       params={"caminho": "Casa/orcamento.pdf"}).status_code == 413
