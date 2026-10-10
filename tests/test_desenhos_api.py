"""As rotas dos desenhos .excalidraw pela página."""

import json
import os

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import connect, desenhos, migrate
from aide.web import criar_app

LOCAL = "http://127.0.0.1:8787"
DA_PAGINA = {"origin": LOCAL, "x-aide": "1", "sec-fetch-site": "same-origin"}
URL = "/api/desenhos/arquivo"


@pytest.fixture
def app(config, tmp_path):
    object.__setattr__(config, "vault_dir", tmp_path / "vault")
    (tmp_path / "vault" / "Projetos").mkdir(parents=True)
    (tmp_path / "vault" / "Projetos" / "Casa.excalidraw").write_text(desenhos.vazio())

    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app, base_url=LOCAL, headers=DA_PAGINA)


@pytest.fixture
def vault_dir(app):
    from pathlib import Path

    return Path(app.state.config.vault_dir)


def _cena(texto="planta baixa") -> str:
    """O que o editor manda: sem a chave "aide", que o Excalidraw descarta."""
    return json.dumps({"type": "excalidraw", "version": 2, "source": "x", "appState": {},
                       "elements": [{"id": "a", "type": "text", "text": texto}], "files": {}})


def _abrir(cliente, caminho="Projetos/Casa.excalidraw"):
    resposta = cliente.get(URL, params={"caminho": caminho})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _salvar(cliente, texto, versao, caminho="Projetos/Casa.excalidraw", **extra):
    # json.dumps com ensure_ascii: um surrogate solto vai como o escape
    # "\ud800", que é como ele chega de um navegador
    corpo = json.dumps({"caminho": caminho, "texto": texto, "versao": versao, **extra})
    return cliente.put(URL, content=corpo, headers={"content-type": "application/json"})


def _trilha(app):
    return [(r["actor"], r["tool"], json.loads(r["args_json"])) for r in
            app.state.conn_factory().execute(
                "SELECT actor, tool, args_json FROM audit ORDER BY id").fetchall()]


# ---------- abrir e salvar ----------

def test_abrir_devolve_texto_versao_e_privado(cliente):
    aberto = _abrir(cliente)
    assert json.loads(aberto["texto"])["type"] == "excalidraw"
    assert aberto["versao"] and aberto["privada"] is False


def test_salvar_grava_e_audita_so_o_caminho(cliente, vault_dir, app):
    resposta = _salvar(cliente, _cena("senha do banco"), _abrir(cliente)["versao"])
    assert resposta.status_code == 200, resposta.text
    assert (vault_dir / "Projetos" / "Casa.excalidraw").read_text() == _cena("senha do banco")
    assert resposta.json()["versao"] == _abrir(cliente)["versao"]
    trilha = _trilha(app)
    assert trilha == [("web", "desenhos.salvar", {"caminho": "Projetos/Casa.excalidraw"})]
    # a trilha não guarda uma segunda cópia do desenho
    assert "senha" not in json.dumps(trilha)


def test_salvar_do_editor_nao_desfaz_o_privado(cliente, vault_dir):
    arquivo = vault_dir / "Projetos" / "Casa.excalidraw"
    arquivo.write_text(json.dumps({**json.loads(_cena()), "aide": {"privada": True}}))
    resposta = _salvar(cliente, _cena("outra coisa"), _abrir(cliente)["versao"])
    assert resposta.json()["privada"] is True
    assert _abrir(cliente)["privada"] is True


def test_caixa_de_privado_muda_e_audita_a_mudanca(cliente, app):
    versao = _abrir(cliente)["versao"]
    resposta = _salvar(cliente, _cena(), versao, privada=True)
    assert resposta.json()["privada"] is True
    assert _abrir(cliente)["privada"] is True
    resposta = _salvar(cliente, _cena(), resposta.json()["versao"], privada=False)
    assert _abrir(cliente)["privada"] is False
    assert [args.get("privada") for _, _, args in _trilha(app)] == [True, False]


def test_mudou_por_fora_devolve_409_com_o_que_esta_no_disco(cliente, vault_dir):
    versao = _abrir(cliente)["versao"]
    arquivo = vault_dir / "Projetos" / "Casa.excalidraw"
    arquivo.write_text(_cena("do Obsidian"))
    os.utime(arquivo, ns=(1, 1))
    resposta = _salvar(cliente, _cena("da página"), versao)
    assert resposta.status_code == 409
    assert json.loads(resposta.json()["texto"])["elements"][0]["text"] == "do Obsidian"
    assert arquivo.read_text() == _cena("do Obsidian")


@pytest.mark.parametrize("texto", ["{}", "não é json", '{"type": "excalidraw", "x": NaN}',
                                   '{"type": "excalidraw", "x": "\ud800"}'])
def test_salvar_invalido_e_400_e_nao_toca_no_arquivo(cliente, vault_dir, texto, app):
    versao = _abrir(cliente)["versao"]
    resposta = _salvar(cliente, texto, versao)
    assert resposta.status_code == 400
    assert (vault_dir / "Projetos" / "Casa.excalidraw").read_text() == desenhos.vazio()
    assert _trilha(app) == []


def test_salvar_o_que_nao_existe_e_404_e_nao_cria(cliente, vault_dir):
    resposta = _salvar(cliente, _cena(), "1", caminho="Projetos/Novo.excalidraw")
    assert resposta.status_code == 404
    assert not (vault_dir / "Projetos" / "Novo.excalidraw").exists()


def test_arquivo_torto_posto_por_fora_e_422_ao_abrir(cliente, vault_dir):
    (vault_dir / "Torto.excalidraw").write_bytes(b"\xff\xfe")
    (vault_dir / "Lista.excalidraw").write_text("[]")
    for caminho in ("Torto.excalidraw", "Lista.excalidraw"):
        resposta = cliente.get(URL, params={"caminho": caminho})
        assert resposta.status_code == 422, caminho
        assert "não abre como desenho" in resposta.json()["detail"]


def test_desenho_grande_passa_pela_fronteira(cliente, vault_dir, monkeypatch):
    """O limite geral de corpo é o da nota (3 MB); o do desenho é maior."""
    imagem = "data:image/png;base64," + "A" * (5 * 1024 * 1024)
    cena = json.loads(_cena())
    cena["files"] = {"x": {"id": "x", "mimeType": "image/png", "dataURL": imagem}}
    resposta = _salvar(cliente, json.dumps(cena), _abrir(cliente)["versao"])
    assert resposta.status_code == 200, resposta.text[:200]


def test_corpo_acima_do_limite_do_desenho_e_413(cliente):
    from aide.web import seguranca

    tamanho = str(2 * desenhos.TAMANHO_MAXIMO + 1)
    assert seguranca.corpo_grande_demais(tamanho, seguranca.limite_do_corpo("PUT", URL))
    # o limite maior vale só para salvar desenho
    assert seguranca.limite_do_corpo("POST", URL) == seguranca.CORPO_MAXIMO
    assert seguranca.limite_do_corpo("PUT", "/api/notas/arquivo") == seguranca.CORPO_MAXIMO


# ---------- criar e apagar ----------

def test_criar_desenho_vazio_numa_pasta_nova(cliente, vault_dir, app):
    resposta = cliente.post(URL, json={"caminho": "Ideias/Fluxo.excalidraw"})
    assert resposta.status_code == 201
    assert (vault_dir / "Ideias" / "Fluxo.excalidraw").read_text() == desenhos.vazio()
    assert _abrir(cliente, "Ideias/Fluxo.excalidraw")["privada"] is False
    assert _trilha(app)[-1][:2] == ("web", "desenhos.criar")


def test_criar_por_cima_e_409(cliente, vault_dir):
    (vault_dir / "Projetos" / "Casa.excalidraw").write_text(_cena("meu"))
    resposta = cliente.post(URL, json={"caminho": "Projetos/Casa.excalidraw"})
    assert resposta.status_code == 409
    assert (vault_dir / "Projetos" / "Casa.excalidraw").read_text() == _cena("meu")


def test_apagar_manda_para_a_lixeira(cliente, vault_dir, app):
    resposta = cliente.delete(URL, params={"caminho": "Projetos/Casa.excalidraw"})
    assert resposta.status_code == 200
    assert not (vault_dir / "Projetos" / "Casa.excalidraw").exists()
    assert (vault_dir / ".trash" / "Casa.excalidraw").read_text() == desenhos.vazio()
    assert _trilha(app)[-1][:2] == ("web", "desenhos.apagar")
    assert cliente.delete(URL, params={"caminho": "Projetos/Casa.excalidraw"}).status_code == 404


# ---------- a fronteira ----------

@pytest.mark.parametrize("caminho", [
    "../fora.excalidraw", ".trash/Casa.excalidraw", "Projetos/Casa.md", "Nota.md",
    "/etc/passwd", "Projetos\\Casa.excalidraw",
])
def test_caminho_fora_do_vault_ou_de_outro_tipo_e_400(cliente, caminho):
    assert cliente.get(URL, params={"caminho": caminho}).status_code == 400
    assert cliente.post(URL, json={"caminho": caminho}).status_code == 400
    assert cliente.delete(URL, params={"caminho": caminho}).status_code == 400
    assert _salvar(cliente, _cena(), "1", caminho=caminho).status_code == 400


def test_link_simbolico_nao_entra(cliente, vault_dir, tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    (fora / "x.excalidraw").write_text(desenhos.vazio())
    (vault_dir / "atalho").symlink_to(fora)
    assert cliente.get(URL, params={"caminho": "atalho/x.excalidraw"}).status_code == 400
    assert cliente.delete(URL, params={"caminho": "atalho/x.excalidraw"}).status_code == 400
    assert (fora / "x.excalidraw").exists()


@pytest.mark.parametrize("cabecalhos", [
    {},
    {"origin": "http://evil.com", "x-aide": "1"},
    {"origin": LOCAL},
    {"origin": LOCAL, "x-aide": "1", "sec-fetch-site": "cross-site"},
])
def test_escrita_de_fora_da_pagina_e_recusada(app, vault_dir, cabecalhos):
    cliente = TestClient(app, base_url=LOCAL, headers=cabecalhos)
    assert cliente.put(URL, json={"caminho": "Projetos/Casa.excalidraw", "texto": _cena(),
                                  "versao": "1"}).status_code == 403
    assert cliente.post(URL, json={"caminho": "Novo.excalidraw"}).status_code == 403
    assert cliente.delete(URL, params={"caminho": "Projetos/Casa.excalidraw"}).status_code == 403
    assert (vault_dir / "Projetos" / "Casa.excalidraw").read_text() == desenhos.vazio()
    assert not (vault_dir / "Novo.excalidraw").exists()


def test_leitura_responde_sem_cache(cliente):
    """O desenho pode ser privado: cópia em cache de disco é cópia fora do vault."""
    resposta = cliente.get(URL, params={"caminho": "Projetos/Casa.excalidraw"})
    assert resposta.headers["cache-control"] == "no-store"


# ---------- a biblioteca de formas ----------

BIB = "/api/desenhos/biblioteca"


def _bib(*ids) -> str:
    return json.dumps({"type": "excalidrawlib", "version": 2, "source": "x", "libraryItems": [
        {"id": i, "status": "unpublished", "created": 1,
         "elements": [{"id": "e", "type": "rectangle"}]} for i in ids]})


def test_biblioteca_comeca_vazia_e_a_primeira_gravacao_cria(cliente, vault_dir, app):
    lida = cliente.get(BIB).json()
    assert json.loads(lida["texto"])["libraryItems"] == [] and lida["versao"] == ""
    resposta = cliente.put(BIB, json={"texto": _bib("a"), "versao": ""})
    assert resposta.status_code == 200, resposta.text
    assert (vault_dir / "Biblioteca.excalidrawlib").read_text() == _bib("a")
    assert resposta.json()["versao"] == cliente.get(BIB).json()["versao"]
    assert _trilha(app)[-1] == ("web", "desenhos.biblioteca",
                                {"caminho": "Biblioteca.excalidrawlib"})


def test_biblioteca_mudou_em_outra_aba_e_409_com_a_de_la(cliente, vault_dir):
    cliente.put(BIB, json={"texto": _bib("a"), "versao": ""})
    resposta = cliente.put(BIB, json={"texto": _bib("b"), "versao": ""})
    assert resposta.status_code == 409
    assert json.loads(resposta.json()["texto"])["libraryItems"][0]["id"] == "a"
    assert (vault_dir / "Biblioteca.excalidrawlib").read_text() == _bib("a")


def test_biblioteca_torta_e_400_e_nao_grava(cliente, vault_dir):
    assert cliente.put(BIB, json={"texto": "{}", "versao": ""}).status_code == 400
    assert not (vault_dir / "Biblioteca.excalidrawlib").exists()


def test_biblioteca_corrompida_no_disco_e_422_ao_abrir(cliente, vault_dir):
    (vault_dir / "Biblioteca.excalidrawlib").write_text("não é json")
    resposta = cliente.get(BIB)
    assert resposta.status_code == 422
    assert "biblioteca não abre" in resposta.json()["detail"]


def test_biblioteca_link_simbolico_e_400(cliente, vault_dir, tmp_path):
    fora = tmp_path / "fora.excalidrawlib"
    fora.write_text(_bib("a"))
    (vault_dir / "Biblioteca.excalidrawlib").symlink_to(fora)
    assert cliente.get(BIB).status_code == 400
    assert cliente.put(BIB, json={"texto": _bib("b"), "versao": ""}).status_code == 400
    assert fora.read_text() == _bib("a")


def test_biblioteca_de_fora_da_pagina_e_recusada(app, vault_dir):
    de_fora = TestClient(app, base_url=LOCAL, headers={"origin": "http://evil.com"})
    assert de_fora.put(BIB, json={"texto": _bib("a"), "versao": ""}).status_code == 403
    assert not (vault_dir / "Biblioteca.excalidrawlib").exists()


# ---------- mover ----------

MOVER = "/api/desenhos/mover"


def test_mover_para_outra_pasta_e_audita(cliente, vault_dir, app):
    resposta = cliente.post(MOVER, json={"de": "Projetos/Casa.excalidraw",
                                         "para": "Arquivo/Casa.excalidraw"})
    assert resposta.status_code == 200, resposta.text
    assert not (vault_dir / "Projetos" / "Casa.excalidraw").exists()
    assert (vault_dir / "Arquivo" / "Casa.excalidraw").read_text() == desenhos.vazio()
    assert _trilha(app)[-1] == ("web", "desenhos.mover", {
        "caminho": "Projetos/Casa.excalidraw", "para": "Arquivo/Casa.excalidraw",
        "links_atualizados": [], "links_nao_atualizados": []})


def test_mover_por_cima_de_outro_e_409_e_nada_some(cliente, vault_dir):
    (vault_dir / "Outro.excalidraw").write_text(_cena("outro"))
    resposta = cliente.post(MOVER, json={"de": "Projetos/Casa.excalidraw",
                                         "para": "Outro.excalidraw"})
    assert resposta.status_code == 409
    assert (vault_dir / "Outro.excalidraw").read_text() == _cena("outro")
    assert (vault_dir / "Projetos" / "Casa.excalidraw").exists()


def test_mover_o_que_nao_existe_e_404(cliente):
    assert cliente.post(MOVER, json={"de": "Nada.excalidraw",
                                     "para": "X.excalidraw"}).status_code == 404


@pytest.mark.parametrize("de,para", [
    ("Projetos/Casa.excalidraw", "../fora.excalidraw"),
    ("Projetos/Casa.excalidraw", "Projetos/Casa.md"),
    ("Projetos/Casa.excalidraw", ".trash/Casa.excalidraw"),
    ("../x.excalidraw", "Casa.excalidraw"),
    ("Inbox/Nota.md", "Inbox/Nota.excalidraw"),
])
def test_mover_so_dentro_do_vault_e_so_desenho(cliente, vault_dir, de, para):
    assert cliente.post(MOVER, json={"de": de, "para": para}).status_code == 400
    assert (vault_dir / "Projetos" / "Casa.excalidraw").exists()


def test_mover_de_fora_da_pagina_e_recusado(app, vault_dir):
    de_fora = TestClient(app, base_url=LOCAL, headers={"origin": "http://evil.com"})
    assert de_fora.post(MOVER, json={"de": "Projetos/Casa.excalidraw",
                                     "para": "X.excalidraw"}).status_code == 403
    assert (vault_dir / "Projetos" / "Casa.excalidraw").exists()


# ---------- a prévia em PNG ----------

PREVIA = "/api/desenhos/previa"
PNG_OK = b"\x89PNG\r\n\x1a\n" + b"x" * 100


def _mandar_previa(cliente, assinatura, corpo=PNG_OK, caminho="Projetos/Casa.excalidraw"):
    return cliente.put(PREVIA, params={"caminho": caminho, "assinatura": assinatura},
                       content=corpo, headers={"content-type": "image/png"})


def test_abrir_diz_a_assinatura_e_que_ainda_nao_ha_previa(cliente):
    aberto = _abrir(cliente)
    assert len(aberto["assinatura"]) == 32 and aberto["previa"] is False


def test_previa_da_versao_atual_e_guardada_e_servida_sem_cache(cliente, app):
    assinatura = _abrir(cliente)["assinatura"]
    assert _mandar_previa(cliente, assinatura).status_code == 200
    assert _abrir(cliente)["previa"] is True
    resposta = cliente.get(PREVIA, params={"caminho": "Projetos/Casa.excalidraw"})
    assert resposta.status_code == 200
    assert resposta.content == PNG_OK
    assert resposta.headers["content-type"] == "image/png"
    assert resposta.headers["cache-control"] == "no-store"
    assert resposta.headers["content-security-policy"] == "default-src 'none'"
    # cache não é dado do vault: nada na trilha
    assert _trilha(app) == []


def test_previa_de_outra_versao_e_recusada(cliente):
    velha = _abrir(cliente)["assinatura"]
    _salvar(cliente, _cena("nova"), _abrir(cliente)["versao"])
    assert _mandar_previa(cliente, velha).status_code == 409
    assert cliente.get(PREVIA, params={"caminho": "Projetos/Casa.excalidraw"}).status_code == 404


def test_salvar_devolve_a_assinatura_do_que_ficou_no_disco(cliente, vault_dir):
    """Com o privado reposto pelo servidor, o texto gravado não é o enviado."""
    from aide.storage import previas

    arquivo = vault_dir / "Projetos" / "Casa.excalidraw"
    arquivo.write_text(json.dumps({**json.loads(_cena()), "aide": {"privada": True}}))
    salvo = _salvar(cliente, _cena("x"), _abrir(cliente)["versao"]).json()
    assert salvo["assinatura"] == previas.assinatura(arquivo.read_bytes())
    assert salvo["assinatura"] != previas.assinatura(_cena("x").encode())


@pytest.mark.parametrize("corpo,status", [(b"GIF89a....", 415), (b"<svg onload=1>", 415)])
def test_previa_so_png(cliente, corpo, status):
    assinatura = _abrir(cliente)["assinatura"]
    assert _mandar_previa(cliente, assinatura, corpo).status_code == status


def test_previa_de_desenho_que_nao_existe_ou_fora_do_vault(cliente):
    assert _mandar_previa(cliente, "a" * 32, caminho="Nada.excalidraw").status_code == 404
    assert _mandar_previa(cliente, "a" * 32, caminho="../x.excalidraw").status_code == 400
    assert _mandar_previa(cliente, "../../x", caminho="Projetos/Casa.excalidraw").status_code in (
        400, 409)


def test_previa_grande_demais_e_413(cliente, monkeypatch):
    from aide.storage import previas

    monkeypatch.setattr(previas, "TAMANHO_MAXIMO", 50)
    assinatura = _abrir(cliente)["assinatura"]
    assert _mandar_previa(cliente, assinatura).status_code == 413


def test_apagar_e_mover_tiram_a_previa(cliente, app):
    from pathlib import Path

    pasta = Path(app.state.config.data_dir) / "previas-desenho"
    _mandar_previa(cliente, _abrir(cliente)["assinatura"])
    assert list(pasta.glob("*.png"))
    cliente.post(MOVER, json={"de": "Projetos/Casa.excalidraw", "para": "Casa.excalidraw"})
    assert not list(pasta.glob("*.png"))
    _mandar_previa(cliente, _abrir(cliente, "Casa.excalidraw")["assinatura"],
                   caminho="Casa.excalidraw")
    cliente.delete(URL, params={"caminho": "Casa.excalidraw"})
    assert not list(pasta.glob("*.png"))


def test_previa_de_fora_da_pagina_e_recusada(app):
    de_fora = TestClient(app, base_url=LOCAL, headers={"origin": "http://evil.com"})
    assert _mandar_previa(de_fora, "a" * 32).status_code == 403


# ---------- renomear reescreve os links ----------

def test_renomear_reescreve_os_links_das_notas(cliente, vault_dir, app):
    (vault_dir / "Inbox").mkdir()
    (vault_dir / "Inbox" / "Obra.md").write_text(
        "planta: [[Casa.excalidraw]]\n"
        "grande: ![[Projetos/Casa.excalidraw|300]]\n"
        "com nome: [[Casa.excalidraw|a casa]]\n"
        "código: `[[Casa.excalidraw]]`\n")
    resposta = cliente.post(MOVER, json={"de": "Projetos/Casa.excalidraw",
                                         "para": "Projetos/Sobrado.excalidraw"})
    assert resposta.status_code == 200
    assert resposta.json()["links_atualizados"] == ["Inbox/Obra.md"]
    assert (vault_dir / "Inbox" / "Obra.md").read_text() == (
        "planta: [[Sobrado.excalidraw]]\n"
        "grande: ![[Sobrado.excalidraw|300]]\n"
        "com nome: [[Sobrado.excalidraw|a casa]]\n"
        "código: `[[Casa.excalidraw]]`\n")
    assert _trilha(app)[-1][2]["links_atualizados"] == ["Inbox/Obra.md"]


def test_renomear_para_nome_repetido_escreve_o_caminho(cliente, vault_dir):
    (vault_dir / "Inbox").mkdir()
    (vault_dir / "Inbox" / "Sobrado.excalidraw").write_text(desenhos.vazio())
    (vault_dir / "Inbox" / "Obra.md").write_text("ver [[Casa.excalidraw]]\n")
    cliente.post(MOVER, json={"de": "Projetos/Casa.excalidraw",
                              "para": "Projetos/Sobrado.excalidraw"})
    # na pasta da nota há outro Sobrado: o nome curto levaria a ele
    assert (vault_dir / "Inbox" / "Obra.md").read_text() == (
        "ver [[Projetos/Sobrado.excalidraw]]\n")


def test_desenho_que_chega_nao_rouba_o_link_de_outro(cliente, vault_dir):
    """[[Planta]] da nota em Inbox levava a Outros/Planta; uma Planta movida
    para Inbox ganharia o link pela regra da mesma pasta."""
    for pasta in ("Inbox", "Outros"):
        (vault_dir / pasta).mkdir(exist_ok=True)
    (vault_dir / "Outros" / "Planta.excalidraw").write_text(desenhos.vazio())
    (vault_dir / "Projetos" / "Planta.excalidraw").write_text(desenhos.vazio())
    (vault_dir / "Inbox" / "Obra.md").write_text("ver [[Outros/Planta.excalidraw]]\n")
    (vault_dir / "Inbox" / "Ref.md").write_text("e [[Planta.excalidraw]]\n")
    antes = desenhos.indice(vault_dir).resolver("Planta.excalidraw", "Inbox/Ref.md")
    cliente.post(MOVER, json={"de": "Projetos/Planta.excalidraw",
                              "para": "Inbox/Planta.excalidraw"})
    texto = (vault_dir / "Inbox" / "Ref.md").read_text()
    depois = desenhos.indice(vault_dir).resolver(texto.split("[[")[1].split("]]")[0],
                                                "Inbox/Ref.md")
    assert depois == antes


def test_mover_sem_ninguem_citando_nao_mexe_em_nota(cliente, vault_dir):
    (vault_dir / "Nota.md").write_text("nada de desenho aqui\n")
    resposta = cliente.post(MOVER, json={"de": "Projetos/Casa.excalidraw",
                                         "para": "Casa2.excalidraw"})
    assert resposta.json()["links_atualizados"] == []
    assert (vault_dir / "Nota.md").read_text() == "nada de desenho aqui\n"



# ---------- o privado que não se perde (desenhos.marcados) ----------

def _sem_marca_no_arquivo(vault_dir, caminho="Projetos/Casa.excalidraw"):
    """O que o Obsidian ou o excalidraw.com fazem ao salvar: a chave "aide" some."""
    arquivo = vault_dir / caminho
    arquivo.write_text(_cena("editado no Obsidian"))
    import os

    os.utime(arquivo, ns=(arquivo.stat().st_mtime_ns + 10**9,) * 2)


def test_privado_continua_depois_de_editado_por_fora(cliente, vault_dir, app):
    _salvar(cliente, _cena(), _abrir(cliente)["versao"], privada=True)
    _sem_marca_no_arquivo(vault_dir)
    assert _abrir(cliente)["privada"] is True
    # e o próximo salvamento daqui devolve a marcação ao arquivo
    _salvar(cliente, _cena("de novo"), _abrir(cliente)["versao"])
    assert json.loads((vault_dir / "Projetos" / "Casa.excalidraw").read_text())["aide"] == {
        "privada": True}


def test_registro_fica_em_data_so_com_o_dono(cliente, app):
    from pathlib import Path

    _salvar(cliente, _cena(), _abrir(cliente)["versao"], privada=True)
    registro = Path(app.state.config.data_dir) / desenhos.MARCAS
    assert json.loads(registro.read_text()) == ["Projetos/Casa.excalidraw"]
    assert registro.stat().st_mode & 0o777 == 0o600


def test_so_a_caixa_tira_o_privado(cliente, vault_dir):
    _salvar(cliente, _cena(), _abrir(cliente)["versao"], privada=True)
    _sem_marca_no_arquivo(vault_dir)
    _salvar(cliente, _cena(), _abrir(cliente)["versao"], privada=False)
    assert _abrir(cliente)["privada"] is False


def test_marcado_no_arquivo_entra_no_registro_ao_abrir(cliente, vault_dir, app):
    """Desenho marcado antes do registro existir."""
    arquivo = vault_dir / "Projetos" / "Casa.excalidraw"
    arquivo.write_text(json.dumps({**json.loads(_cena()), "aide": {"privada": True}}))
    _abrir(cliente)
    assert "Projetos/Casa.excalidraw" in desenhos.marcados(app.state.config.data_dir)


def test_renomear_leva_o_privado_junto(cliente, vault_dir):
    _salvar(cliente, _cena(), _abrir(cliente)["versao"], privada=True)
    resposta = cliente.post("/api/desenhos/mover", json={
        "de": "Projetos/Casa.excalidraw", "para": "Projetos/Sobrado.excalidraw"})
    assert resposta.status_code == 200, resposta.text
    _sem_marca_no_arquivo(vault_dir, "Projetos/Sobrado.excalidraw")
    assert _abrir(cliente, "Projetos/Sobrado.excalidraw")["privada"] is True


def test_mover_a_pasta_leva_o_privado_junto(cliente, vault_dir):
    _salvar(cliente, _cena(), _abrir(cliente)["versao"], privada=True)
    resposta = cliente.post("/api/notas/mover-pasta", json={"de": "Projetos", "para": "Arquivo"})
    assert resposta.status_code == 200, resposta.text
    _sem_marca_no_arquivo(vault_dir, "Arquivo/Casa.excalidraw")
    assert _abrir(cliente, "Arquivo/Casa.excalidraw")["privada"] is True


def test_desenho_novo_com_nome_de_um_privado_apagado_nasce_privado(cliente):
    """Na dúvida, privado: é só desmarcar a caixa."""
    _salvar(cliente, _cena(), _abrir(cliente)["versao"], privada=True)
    assert cliente.delete(URL, params={"caminho": "Projetos/Casa.excalidraw"}).status_code == 200
    resposta = cliente.post(URL, json={"caminho": "Projetos/Casa.excalidraw"})
    assert resposta.json()["privada"] is True


def test_registro_ilegivel_conta_tudo_como_privado(cliente, app):
    from pathlib import Path

    registro = Path(app.state.config.data_dir) / desenhos.MARCAS
    registro.parent.mkdir(parents=True, exist_ok=True)
    registro.write_text("{ torto")
    assert _abrir(cliente)["privada"] is True


# ---------- o link de um elemento do desenho ----------

def _link(cliente, alvo, caminho="Projetos/Casa.excalidraw"):
    return cliente.get("/api/desenhos/link", params={"caminho": caminho, "alvo": alvo})


@pytest.fixture
def com_notas(vault_dir):
    (vault_dir / "Projetos" / "Telhado.md").write_text("# Calhas\n")
    (vault_dir / "Inbox").mkdir()
    (vault_dir / "Inbox" / "Telhado.md").write_text("outro")
    (vault_dir / "Inbox" / "Reunião.md").write_text("x")
    return vault_dir


def test_link_leva_a_nota_da_pasta_do_desenho_primeiro(cliente, com_notas):
    dados = _link(cliente, "[[Telhado#Calhas|calhas]]").json()
    assert dados == {"tipo": "nota", "existe": True, "caminho": "Projetos/Telhado.md",
                     "href": "/notas?arquivo=Projetos/Telhado.md#s-calhas"}


def test_link_markdown_relativo_ao_desenho(cliente, com_notas):
    dados = _link(cliente, "../Inbox/Reuni%C3%A3o.md").json()
    assert dados["caminho"] == "Inbox/Reunião.md"


def test_link_para_outro_desenho(cliente, vault_dir):
    (vault_dir / "Planta.excalidraw").write_text(desenhos.vazio())
    dados = _link(cliente, "[[Planta.excalidraw]]").json()
    assert dados == {"tipo": "desenho", "existe": True, "caminho": "Planta.excalidraw",
                     "href": "/desenho?caminho=Planta.excalidraw"}


@pytest.mark.parametrize("alvo, tipo, pedido", [
    ("[[Nova ideia]]", "nota", "Projetos/Nova ideia.md"),
    ("Base/Nova", "nota", "Base/Nova.md"),
    ("[[Corte.excalidraw]]", "desenho", "Projetos/Corte.excalidraw"),
])
def test_link_para_o_que_nao_existe_diz_o_caminho_que_pede(cliente, alvo, tipo, pedido):
    assert _link(cliente, alvo).json() == {"tipo": tipo, "existe": False, "caminho": pedido}


@pytest.mark.parametrize("alvo", ["https://x.org", "javascript:alert(1)", "[[foto.png]]",
                                  "../../fora.md", "[[.obsidian/app]]", "[[../../fora]]"])
def test_link_que_nao_e_do_vault_e_recusado(cliente, alvo):
    assert _link(cliente, alvo).status_code == 422


def test_link_de_desenho_fora_do_vault_e_recusado(cliente):
    assert _link(cliente, "[[Telhado]]", caminho="../fora.excalidraw").status_code == 400


def test_renomear_nota_conserta_o_link_do_desenho_e_audita(cliente, com_notas, app):
    import json as json_

    arquivo = com_notas / "Projetos" / "Casa.excalidraw"
    dados = json_.loads(arquivo.read_text())
    dados["elements"] = [{"type": "rectangle", "id": "a", "link": "[[Telhado]]"}]
    arquivo.write_text(json_.dumps(dados))
    resposta = cliente.post("/api/notas/mover", json={"de": "Projetos/Telhado.md",
                                                      "para": "Projetos/Cobertura.md"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["desenhos_atualizados"] == ["Projetos/Casa.excalidraw"]
    assert json_.loads(arquivo.read_text())["elements"][0]["link"] == "[[Cobertura]]"
    trilha = app.state.conn_factory().execute(
        "SELECT args_json FROM audit WHERE tool = 'notas.mover'").fetchone()[0]
    assert json_.loads(trilha)["desenhos_atualizados"] == ["Projetos/Casa.excalidraw"]
