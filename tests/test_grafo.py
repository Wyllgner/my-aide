"""O mapa de links do vault."""

import os

import pytest

from aide.web import grafo
from aide.web.markdown import citacoes


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    arquivos = {
        "Inbox/Reunião.md": "---\ntitle: R\n---\n\nver [[Telhado]] e [[Fornecedores]]",
        "Projetos/Casa/Telhado.md": "# Telhado\n\nvolta para [[Reunião#Pauta]]\n\n[[Telhado]]",
        "Projetos/Casa/Obra.md": "[a reunião](../../Inbox/Reuni%C3%A3o.md) e [[Telhado]]",
        "Solta.md": "sem link nenhum",
    }
    for caminho, texto in arquivos.items():
        (pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
        (pasta / caminho).write_text(texto)
    return pasta


# ---------- citações ----------

def test_citacoes_com_a_linha_do_arquivo():
    texto = "---\ntitle: x\n---\n\nver [[A]] e [[B#s|b]]\n\n```\n[[C]]\n```\n- [ir](D.md)"
    achadas = [(c.tipo, c.alvo, c.secao, c.linha) for c in citacoes(texto)]
    assert achadas == [("wiki", "A", "", 4), ("wiki", "B", "s", 4), ("md", "D.md", "", 9)]


def test_citacoes_ignoram_site_anexo_e_codigo():
    texto = "[site](https://x.org) ![[foto.png]] `[[código]]` <https://y.org>"
    assert citacoes(texto) == []


# ---------- mapa ----------

def test_entradas_de_uma_nota(raiz):
    entradas = grafo.mapa(raiz).entradas("Projetos/Casa/Telhado.md")
    assert sorted(lig.origem for lig in entradas) == ["Inbox/Reunião.md", "Projetos/Casa/Obra.md"]


def test_link_para_si_mesma_nao_e_entrada(raiz):
    assert all(lig.origem != "Projetos/Casa/Telhado.md"
               for lig in grafo.mapa(raiz).entradas("Projetos/Casa/Telhado.md"))


def test_link_markdown_relativo_tambem_conta(raiz):
    entradas = grafo.mapa(raiz).entradas("Inbox/Reunião.md")
    assert sorted(lig.origem for lig in entradas) == ["Projetos/Casa/Obra.md",
                                                     "Projetos/Casa/Telhado.md"]


def test_quebrados(raiz):
    quebrados = grafo.mapa(raiz).quebrados()
    assert [(lig.origem, lig.citacao.alvo) for lig in quebrados] == [
        ("Inbox/Reunião.md", "Fornecedores")]


def test_criar_a_nota_conserta_o_link_sem_mexer_em_quem_aponta(raiz):
    """O destino é resolvido na hora; o arquivo de origem nem mudou."""
    grafo.mapa(raiz)
    (raiz / "Inbox" / "Fornecedores.md").write_text("x")
    assert grafo.mapa(raiz).quebrados() == []


def test_arquivo_mudado_e_lido_de_novo(raiz):
    grafo.mapa(raiz)
    solta = raiz / "Solta.md"
    solta.write_text("agora aponta para [[Telhado]]")
    os.utime(solta, ns=(solta.stat().st_mtime_ns + 10**9,) * 2)
    origens = [lig.origem for lig in grafo.mapa(raiz).entradas("Projetos/Casa/Telhado.md")]
    assert "Solta.md" in origens


def test_arquivo_sem_mudanca_nao_e_relido(raiz, monkeypatch):
    grafo.mapa(raiz)
    lidos = []
    original = grafo.citacoes
    monkeypatch.setattr(grafo, "citacoes", lambda t: lidos.append(t) or original(t))
    grafo.mapa(raiz)
    assert lidos == []


def test_arquivo_apagado_sai_do_cache(raiz):
    grafo.mapa(raiz)
    (raiz / "Solta.md").unlink()
    grafo.mapa(raiz)
    assert (raiz / "Solta.md").resolve() not in grafo._CACHE


def test_a_lixeira_nao_aponta_para_ninguem(raiz):
    (raiz / ".trash").mkdir()
    (raiz / ".trash" / "Velha.md").write_text("[[Telhado]]")
    origens = [lig.origem for lig in grafo.mapa(raiz).entradas("Projetos/Casa/Telhado.md")]
    assert not any(".trash" in o for o in origens)
