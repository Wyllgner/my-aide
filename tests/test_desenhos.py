"""Os desenhos .excalidraw do vault: a porta (resolver) e o que se aceita gravar."""

import json

import pytest

from aide.storage import desenhos
from aide.storage.desenhos import DesenhoInvalido
from aide.storage.vault import ForaDoVault


@pytest.fixture
def raiz(tmp_path):
    raiz = tmp_path / "vault"
    raiz.mkdir()
    return raiz


def _desenho(**extra) -> str:
    dados = json.loads(desenhos.vazio())
    dados.update(extra)
    return json.dumps(dados)


def _imagem(tipo="image/png", url=None) -> dict:
    return {"x1": {"id": "x1", "mimeType": tipo, "created": 1,
                   "dataURL": url if url is not None else f"data:{tipo};base64,AAAA"}}


# ---------- a porta ----------

def test_resolver_aceita_desenho_em_pasta(raiz):
    assert desenhos.resolver(raiz, "Projetos/Casa.excalidraw") == (
        raiz.resolve() / "Projetos" / "Casa.excalidraw")


@pytest.mark.parametrize("caminho", [
    "../fora.excalidraw", "/etc/x.excalidraw", ".trash/x.excalidraw", "a\\b.excalidraw",
    "Nota.md", "foto.png", "x.excalidraw.md", "x.excalidrawlib", ".excalidraw", "",
])
def test_resolver_recusa(raiz, caminho):
    with pytest.raises(ForaDoVault):
        desenhos.resolver(raiz, caminho)


def test_link_simbolico_nao_entra(raiz, tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    (raiz / "atalho").symlink_to(fora)
    with pytest.raises(ForaDoVault):
        desenhos.resolver(raiz, "atalho/x.excalidraw")


# ---------- o que se aceita ----------

def test_vazio_e_valido_e_nao_e_privado():
    dados = desenhos.validar(desenhos.vazio())
    assert dados["elements"] == []
    assert not desenhos.privado(dados)


def test_aceita_o_que_o_excalidraw_com_grava():
    texto = json.dumps({
        "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
        "elements": [{"id": "a", "type": "rectangle", "x": 0, "y": 0}],
        "appState": {"viewBackgroundColor": "#ffffff"}, "files": _imagem("image/jpeg"),
    })
    assert desenhos.validar(texto)["elements"][0]["type"] == "rectangle"


def test_sem_files_nem_appstate_tambem_serve():
    assert desenhos.validar('{"type": "excalidraw", "elements": []}')


@pytest.mark.parametrize("texto", [
    "", "não é json", "[]", '"excalidraw"', '{"type": "excalidrawlib", "elements": []}',
    '{"elements": []}', '{"type": "excalidraw", "elements": {}}',
    '{"type": "excalidraw", "elements": [1]}', '{"type": "excalidraw", "elements": [{}]}',
    '{"type": "excalidraw", "appState": []}', '{"type": "excalidraw", "files": []}',
    '{"type": "excalidraw", "files": {"a": "data:image/png;base64,AA"}}',
])
def test_recusa_o_que_nao_e_desenho(texto):
    with pytest.raises(DesenhoInvalido):
        desenhos.validar(texto)


@pytest.mark.parametrize("constante", ["NaN", "Infinity", "-Infinity"])
def test_recusa_numero_que_o_navegador_nao_le(constante):
    """O JSON.parse do navegador não aceita: gravado, o desenho não abriria."""
    with pytest.raises(DesenhoInvalido):
        desenhos.validar('{"type": "excalidraw", "elements": [], "version": ' + constante + "}")


def test_json_fundo_demais_e_recusado_e_nao_estoura():
    with pytest.raises(DesenhoInvalido):
        desenhos.validar('{"type": "excalidraw", "x": ' + "[" * 100_000 + "]" * 100_000 + "}")


@pytest.mark.parametrize("tipo,url", [
    ("text/html", "data:text/html;base64,AAAA"),
    ("image/png", "https://exemplo.com/a.png"),
    ("image/png", "javascript:alert(1)"),
    ("image/png", "data:text/html;base64,AAAA"),
    ("image/png", "data:image/svg+xml;base64,AAAA"),
    ("image/png", 7),
    ("application/octet-stream", "data:application/octet-stream;base64,AAAA"),
])
def test_imagem_embutida_so_de_tipo_aceito_e_so_data(tipo, url):
    with pytest.raises(DesenhoInvalido):
        desenhos.validar(_desenho(files=_imagem(tipo, url)))


@pytest.mark.parametrize("tipo", sorted(desenhos.TIPOS_DE_IMAGEM))
def test_imagem_embutida_dos_tipos_do_excalidraw(tipo):
    assert desenhos.validar(_desenho(files=_imagem(tipo)))


def test_grande_demais(monkeypatch):
    monkeypatch.setattr(desenhos, "TAMANHO_MAXIMO", 100)
    with pytest.raises(DesenhoInvalido, match="grande"):
        desenhos.validar(_desenho(source="x" * 200))


# ---------- privado ----------

def test_privado_pela_chave_nossa():
    assert desenhos.privado(desenhos.validar(_desenho(aide={"privada": True})))
    assert not desenhos.privado(desenhos.validar(_desenho(aide={"privada": False})))
    assert not desenhos.privado(desenhos.validar(_desenho(aide={})))


@pytest.mark.parametrize("aide", [[], "sim", {"privada": "true"}, {"privada": 1}])
def test_marcacao_de_privado_torta_e_recusada(aide):
    """Melhor recusar do que adivinhar: "true" como texto não pode virar
    público calado nem privado por acaso."""
    with pytest.raises(DesenhoInvalido):
        desenhos.validar(_desenho(aide=aide))


# ---------- disco ----------

def test_criar_grava_vazio_so_para_o_dono_e_nao_sobrescreve(raiz):
    caminho = desenhos.resolver(raiz, "Projetos/Casa.excalidraw")
    desenhos.criar(caminho)
    assert caminho.read_text() == desenhos.vazio()
    assert caminho.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        desenhos.criar(caminho)


def test_gravar_guarda_o_texto_como_veio(raiz):
    """Sem reformatar: um desenho do Obsidian não vira outro arquivo no git."""
    caminho = desenhos.resolver(raiz, "Casa.excalidraw")
    texto = '{"type":"excalidraw",  "elements":[]}'
    desenhos.gravar(caminho, texto)
    assert caminho.read_text() == texto
    assert desenhos.ler(caminho) == (texto, json.loads(texto))


def test_gravar_invalido_nao_toca_no_arquivo(raiz):
    caminho = desenhos.resolver(raiz, "Casa.excalidraw")
    desenhos.criar(caminho)
    with pytest.raises(DesenhoInvalido):
        desenhos.gravar(caminho, "{}")
    assert caminho.read_text() == desenhos.vazio()
    assert [p.name for p in raiz.iterdir()] == ["Casa.excalidraw"]


def test_ler_recusa_arquivo_torto_posto_por_fora(raiz, monkeypatch):
    binario = raiz / "a.excalidraw"
    binario.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(DesenhoInvalido, match="UTF-8"):
        desenhos.ler(binario)
    monkeypatch.setattr(desenhos, "TAMANHO_MAXIMO", 10)
    grande = raiz / "b.excalidraw"
    grande.write_text(desenhos.vazio())
    with pytest.raises(DesenhoInvalido, match="grande"):
        desenhos.ler(grande)


def test_surrogate_solto_e_desenho_invalido_e_nao_erro_500():
    with pytest.raises(DesenhoInvalido):
        desenhos.validar('{"type": "excalidraw", "elements": [], "x": "\ud800"}')

