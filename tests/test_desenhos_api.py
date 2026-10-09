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
