"""Busca por palavra no texto dos desenhos."""

import json
import os

import pytest

from aide.storage import busca_desenhos, desenhos


def _cena(*elementos, privada=False):
    dados = json.loads(desenhos.vazio())
    dados["elements"] = list(elementos)
    if privada:
        dados["aide"] = {"privada": True}
    return json.dumps(dados)


def _texto(escrito, **extra):
    return {"type": "text", "id": escrito[:8], "text": escrito, "originalText": escrito, **extra}


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    (pasta / "Projetos").mkdir(parents=True)
    (pasta / "Projetos" / "Casa.excalidraw").write_text(_cena(
        _texto("Orçamento do telhado"), _texto("cozinha nova"),
        {"type": "frame", "id": "f", "name": "Térreo"},
        {"type": "rectangle", "id": "r"}))
    (pasta / "Diário.excalidraw").write_text(_cena(_texto("consulta no dentista"), privada=True))
    return pasta


# ---------- o texto ----------

def test_texto_de_pega_textos_e_frames_e_pula_apagado():
    dados = json.loads(_cena(
        _texto("um"), _texto("apagado", isDeleted=True),
        {"type": "text", "id": "q", "text": "quebrado\nna caixa", "originalText": "quebrado na caixa"},
        {"type": "frame", "id": "f", "name": "Planta"}, {"type": "frame", "id": "g", "name": None},
        {"type": "ellipse", "id": "e"}))
    assert desenhos.texto_de(dados) == "um\nquebrado na caixa\nPlanta"


# ---------- a busca ----------

def test_acha_pelo_texto_sem_acento_e_sem_caixa(raiz):
    achados = busca_desenhos.buscar(raiz, "orcamento", incluir_privados=False)
    assert [a["caminho"] for a in achados] == ["Projetos/Casa.excalidraw"]
    assert achados[0]["titulo"] == "Casa"
    assert "Orçamento do telhado" in achados[0]["trecho"]
    assert achados[0]["privado"] is False


def test_acha_pelo_nome_do_frame_e_do_arquivo(raiz):
    assert busca_desenhos.buscar(raiz, "terreo", False)[0]["titulo"] == "Casa"
    assert busca_desenhos.buscar(raiz, "casa", False)[0]["titulo"] == "Casa"


def test_palavra_inteira_como_no_fts(raiz):
    assert busca_desenhos.buscar(raiz, "cozinhas", False) == []
    assert busca_desenhos.buscar(raiz, "telha", False) == []


def test_privado_so_para_quem_pode_ver(raiz):
    assert busca_desenhos.buscar(raiz, "dentista", incluir_privados=False) == []
    achados = busca_desenhos.buscar(raiz, "dentista", incluir_privados=True)
    assert [a["caminho"] for a in achados] == ["Diário.excalidraw"]
    assert achados[0]["privado"] is True


def test_ilegivel_conta_como_privado(raiz):
    (raiz / "Quebrado.excalidraw").write_text("{ não é json")
    assert busca_desenhos.buscar(raiz, "quebrado", incluir_privados=False) == []
    achado = busca_desenhos.buscar(raiz, "quebrado", incluir_privados=True)[0]
    assert achado["privado"] is True and achado["trecho"] == ""


def test_biblioteca_lixeira_e_oculto_ficam_de_fora(raiz):
    (raiz / desenhos.BIBLIOTECA).write_text(json.dumps({
        "type": "excalidrawlib", "version": 2,
        "libraryItems": [{"elements": [_texto("dentista segredo")]}]}))
    (raiz / ".trash").mkdir()
    (raiz / ".trash" / "Velho.excalidraw").write_text(_cena(_texto("segredo")))
    (raiz / ".oculto.excalidraw").write_text(_cena(_texto("segredo")))
    assert busca_desenhos.buscar(raiz, "segredo", incluir_privados=True) == []


def test_link_simbolico_fica_de_fora(raiz, tmp_path):
    fora = tmp_path / "fora.excalidraw"
    fora.write_text(_cena(_texto("segredo")))
    (raiz / "Atalho.excalidraw").symlink_to(fora)
    assert busca_desenhos.buscar(raiz, "segredo", incluir_privados=True) == []


def test_mais_palavras_achadas_vem_antes(raiz):
    (raiz / "Outro.excalidraw").write_text(_cena(_texto("cozinha")))
    achados = busca_desenhos.buscar(raiz, "cozinha telhado", False)
    assert [a["titulo"] for a in achados] == ["Casa", "Outro"]


def test_consulta_so_de_palavras_vazias_nao_acha_nada(raiz):
    assert busca_desenhos.buscar(raiz, "de um o", True) == []


def test_mudou_o_arquivo_le_de_novo_e_sem_mudar_nao_rele(raiz, monkeypatch):
    busca_desenhos.buscar(raiz, "x", False)
    lidos = []
    original = desenhos.ler
    monkeypatch.setattr(desenhos, "ler", lambda c: lidos.append(c) or original(c))
    busca_desenhos.buscar(raiz, "x", False)
    assert lidos == []
    casa = raiz / "Projetos" / "Casa.excalidraw"
    casa.write_text(_cena(_texto("piscina")))
    os.utime(casa, ns=(casa.stat().st_mtime_ns + 10**9,) * 2)
    assert busca_desenhos.buscar(raiz, "piscina", False)[0]["titulo"] == "Casa"


def test_desenho_que_virou_privado_some(raiz):
    casa = raiz / "Projetos" / "Casa.excalidraw"
    casa.write_text(_cena(_texto("telhado"), privada=True))
    os.utime(casa, ns=(casa.stat().st_mtime_ns + 10**9,) * 2)
    assert busca_desenhos.buscar(raiz, "telhado", False) == []


def test_trecho_longo_tem_reticencias(raiz):
    longo = "palavra " * 30 + "alvo " + "outra " * 30
    (raiz / "Longo.excalidraw").write_text(_cena(_texto(longo)))
    trecho = busca_desenhos.buscar(raiz, "alvo", False)[0]["trecho"]
    assert trecho.startswith("…") and trecho.endswith("…") and "alvo" in trecho
