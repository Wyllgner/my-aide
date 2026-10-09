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


# ---------- receber pela página ----------

@pytest.fixture
def pagina(config, tmp_path, raiz):
    from aide.storage import connect, migrate
    from aide.web import criar_app

    object.__setattr__(config, "vault_dir", raiz)

    def conn_factory():
        conn = connect(tmp_path / "a.db")
        migrate(conn)
        return conn

    local = "http://127.0.0.1:8787"
    return TestClient(criar_app(config, conn_factory), base_url=local,
                      headers={"origin": local, "x-aide": "1", "sec-fetch-site": "same-origin"})


def _anexar(pagina, dados=PNG, nota="Casa/Nota.md", nome="", tipo="image/png"):
    return pagina.post("/api/notas/anexo", params={"nota": nota, "nome": nome},
                       content=dados, headers={"content-type": tipo})


def test_captura_colada_vai_para_anexos_ao_lado_da_nota(pagina, raiz):
    resposta = _anexar(pagina)
    assert resposta.status_code == 201, resposta.text
    caminho = resposta.json()["caminho"]
    assert caminho.startswith("Casa/anexos/Captura ") and caminho.endswith(".png")
    assert (raiz / caminho).read_bytes() == PNG
    assert oct((raiz / caminho).stat().st_mode & 0o777) == "0o600"
    assert resposta.json()["link"] == f"![[{caminho.rpartition('/')[2]}]]"


def test_arquivo_com_nome_mantem_o_nome_e_nao_sobrescreve(pagina, raiz):
    primeiro = _anexar(pagina, b"%PDF-1", nome="Orçamento: telhado.pdf", tipo="application/pdf")
    segundo = _anexar(pagina, b"%PDF-2", nome="Orçamento: telhado.pdf", tipo="application/pdf")
    assert primeiro.json()["caminho"] == "Casa/anexos/Orçamento telhado.pdf"
    assert segundo.json()["caminho"] == "Casa/anexos/Orçamento telhado 2.pdf"
    assert (raiz / "Casa/anexos/Orçamento telhado.pdf").read_bytes() == b"%PDF-1"


def test_nome_que_ja_existe_ganha_numero_e_o_link_acompanha(pagina):
    # já existe Casa/anexos/planta.png: a nova é "planta 2.png"
    assert _anexar(pagina, nome="planta.png").json()["link"] == "![[planta 2.png]]"


def test_nome_repetido_em_outra_pasta_vira_caminho_no_link(pagina, raiz):
    """Na raiz, "planta.png" acharia antes a de Outra/ (caminho mais curto)."""
    (raiz / ".obsidian").mkdir()
    (raiz / ".obsidian" / "app.json").write_text('{"attachmentFolderPath": "Fotos/2026"}')
    (raiz / "Raiz.md").write_text("x")
    resposta = _anexar(pagina, nome="planta.png", nota="Raiz.md")
    assert resposta.json()["link"] == "![[Fotos/2026/planta.png]]"


@pytest.mark.parametrize("nome, tipo", [("evil.svg", "image/svg+xml"), ("p.html", "text/html"),
                                        ("", "text/html"), ("x.exe", "application/octet-stream")])
def test_svg_html_e_desconhecido_sao_recusados(pagina, raiz, nome, tipo):
    assert _anexar(pagina, b"<script>", nome=nome, tipo=tipo).status_code == 415
    assert [p.name for p in (raiz / "Casa" / "anexos").iterdir()] == ["planta.png"]


def test_respeita_a_pasta_de_anexos_do_obsidian(pagina, raiz):
    (raiz / ".obsidian").mkdir()
    (raiz / ".obsidian" / "app.json").write_text('{"attachmentFolderPath": "Arquivos"}')
    assert _anexar(pagina, nome="a.png").json()["caminho"] == "Arquivos/a.png"


@pytest.mark.parametrize("configurado, esperado", [
    ("/", ""), ("./", "Casa"), ("./img", "Casa/img"), ("Fixa/Sub", "Fixa/Sub"), ("", "")])
def test_pasta_para(raiz, configurado, esperado):
    (raiz / ".obsidian").mkdir()
    (raiz / ".obsidian" / "app.json").write_text(f'{{"attachmentFolderPath": "{configurado}"}}')
    assert anexos.pasta_para(raiz, "Casa/Nota.md") == esperado


def test_pasta_de_anexos_que_sai_do_vault_e_recusada(pagina, raiz):
    (raiz / ".obsidian").mkdir()
    (raiz / ".obsidian" / "app.json").write_text('{"attachmentFolderPath": "../fora"}')
    assert _anexar(pagina, nome="a.png").status_code == 400
    assert not (raiz.parent / "fora").exists()


def test_nota_que_nao_existe_ou_fora_do_vault(pagina):
    assert _anexar(pagina, nota="Casa/Nada.md").status_code == 404
    assert _anexar(pagina, nota="../x.md").status_code == 400


def test_arquivo_vazio_nao_fica(pagina, raiz):
    assert _anexar(pagina, b"", nome="a.png").status_code == 400
    assert not (raiz / "Casa/anexos/a.png").exists()


def test_maior_que_o_limite_e_recusado_e_apagado(pagina, raiz, monkeypatch):
    monkeypatch.setattr(anexos, "TAMANHO_MAXIMO", 10)
    assert _anexar(pagina, b"0" * 11, nome="a.png").status_code == 413
    assert not (raiz / "Casa/anexos/a.png").exists()


def test_anexar_de_outra_origem_e_recusado(pagina, raiz):
    resposta = pagina.post("/api/notas/anexo", params={"nota": "Casa/Nota.md"}, content=PNG,
                           headers={"origin": "http://evil.example", "content-type": "image/png"})
    assert resposta.status_code == 403
    assert not (raiz / "Casa/anexos").exists() or not any(
        p.name.startswith("Captura") for p in (raiz / "Casa/anexos").iterdir())


def test_anexo_grande_passa_da_porta_das_notas(pagina):
    """3 MB é o limite de uma nota, não de uma foto: a rota de anexo tem o seu."""
    from aide.web import seguranca

    assert seguranca.limite_do_corpo("POST", "/api/notas/anexo") == anexos.TAMANHO_MAXIMO
    assert seguranca.limite_do_corpo("PUT", "/api/notas/arquivo") == seguranca.CORPO_MAXIMO


def test_anexar_fica_na_trilha(pagina):
    import json

    from aide.storage import connect

    _anexar(pagina, nome="a.png")
    conn = connect(pagina.app.state.config.vault_dir.parent / "a.db")
    row = conn.execute("SELECT tool, args_json FROM audit ORDER BY id DESC").fetchone()
    assert row["tool"] == "notas.anexar"
    assert json.loads(row["args_json"])["caminho"] == "Casa/anexos/a.png"
