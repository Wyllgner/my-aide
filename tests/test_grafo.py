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
    original = grafo.citacoes_separadas
    monkeypatch.setattr(grafo, "citacoes_separadas", lambda t: lidos.append(t) or original(t))
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


def test_cada_citacao_traz_a_linha_em_volta():
    achadas = citacoes("# T\n\n  ver o [[Telhado]] amanhã  \n")
    assert achadas[0].trecho == "ver o [[Telhado]] amanhã"


# ---------- revisão ----------

def test_contexto_e_a_linha_do_link_no_paragrafo():
    achadas = citacoes("Primeira linha do parágrafo\ne o [[Telhado]] na segunda\ne [x](B.md) na terceira")
    assert [(c.linha, c.trecho) for c in achadas] == [
        (1, "e o [[Telhado]] na segunda"), (2, "e [x](B.md) na terceira")]


@pytest.mark.parametrize("texto", ["[foto](foto.png)", "[pasta](Projetos/)", "[api](/api/x)",
                                   "[x](mailto:a@b.c)", "[x](https://a.b/c.md)"])
def test_link_que_nao_e_para_nota_nao_entra_no_mapa(texto):
    """Como link quebrado, o "criar" faria foto.png.md."""
    assert citacoes(texto) == []


def test_link_markdown_para_secao_da_propria_nota_entra():
    assert [c.alvo for c in citacoes("[topo](#Fim)")] == ["#Fim"]


@pytest.mark.parametrize("texto, origem, pedido", [
    ("[[Fornecedores]]", "Inbox/A.md", "Inbox/Fornecedores.md"),
    ("[[Base/Nova]]", "Inbox/A.md", "Base/Nova.md"),
    ("[[Nova.md]]", "A.md", "Nova.md"),
    ("[n](Nova%20nota.md)", "Inbox/A.md", "Inbox/Nova nota.md"),
    ("[n](../Raiz.md)", "Inbox/A.md", "Raiz.md"),
    ("[n](../../fora.md)", "Inbox/A.md", "../fora.md"),
])
def test_caminho_que_o_link_pede(texto, origem, pedido):
    assert citacoes(texto)[0].caminho_pedido(origem) == pedido


# ---------- desenhos ----------

@pytest.fixture
def com_desenhos(raiz):
    from aide.storage import desenhos

    (raiz / "Projetos/Casa/Planta.excalidraw").write_text(desenhos.vazio())
    (raiz / "Inbox/Ideias.md").write_text(
        "a [[Planta.excalidraw]] e [[Telhado]]\n\n![[Projetos/Casa/Planta.excalidraw|400]]"
        "\n\n[[Sumido.excalidraw]]")
    return raiz


def test_link_de_desenho_fica_fora_das_ligacoes_entre_notas(com_desenhos):
    mapa = grafo.mapa(com_desenhos)
    assert all(not lig.citacao.alvo.endswith(".excalidraw") for lig in mapa.ligacoes)
    assert [lig.citacao.alvo for lig in mapa.entradas("Projetos/Casa/Telhado.md")
            if lig.origem == "Inbox/Ideias.md"] == ["Telhado"]


def test_quem_cita_o_desenho_com_a_linha(com_desenhos):
    citam = grafo.mapa(com_desenhos).citam_desenho("Projetos/Casa/Planta.excalidraw")
    assert [(lig.origem, lig.citacao.linha) for lig in citam] == [
        ("Inbox/Ideias.md", 0), ("Inbox/Ideias.md", 2)]


def test_desenho_que_nao_existe_e_quebrado_a_parte(com_desenhos):
    mapa = grafo.mapa(com_desenhos)
    assert [lig.citacao.alvo for lig in mapa.desenhos_quebrados()] == ["Sumido.excalidraw"]
    # a lista de quebrados das notas não muda
    assert [lig.citacao.alvo for lig in mapa.quebrados()] == ["Fornecedores"]


def test_caminho_pedido_do_desenho_nao_ganha_md():
    from aide.web.markdown import Citacao

    assert Citacao("wiki", "Sumido.excalidraw", "", 0).caminho_pedido(
        "Inbox/Ideias.md") == "Inbox/Sumido.excalidraw"
    assert Citacao("wiki", "Outra/Sumido.excalidraw", "", 0).caminho_pedido(
        "Inbox/Ideias.md") == "Outra/Sumido.excalidraw"


def test_citacoes_separadas_numa_passada_so():
    from aide.web.markdown import citacoes_separadas

    notas, de_desenhos = citacoes_separadas("[[A]] [[B.excalidraw]]\n[[C]] ![[foto.png]]")
    assert [c.alvo for c in notas] == ["A", "C"]
    assert [(c.alvo, c.linha) for c in de_desenhos] == [("B.excalidraw", 0)]


def _desenho_com_links(arquivo, *links_, apagado=None):
    import json

    from aide.storage import desenhos

    dados = json.loads(desenhos.vazio())
    dados["elements"] = [{"type": "rectangle", "id": f"e{i}", "link": link}
                         for i, link in enumerate(links_)]
    if apagado:
        dados["elements"].append({"type": "rectangle", "id": "x", "link": apagado,
                                  "isDeleted": True})
    arquivo.write_text(json.dumps(dados))


def test_desenho_que_cita_nota_pelo_link_do_elemento(raiz):
    _desenho_com_links(raiz / "Projetos/Casa/Corte.excalidraw", "[[Telhado#Calhas]]",
                       "../../Inbox/Reuni%C3%A3o.md", "[[Sumida]]", "https://x.org",
                       "[[Outro.excalidraw]]", apagado="[[Solta]]")
    mapa = grafo.mapa(raiz)
    assert [(lig.origem, lig.citacao.trecho) for lig in
            mapa.desenhos_que_citam("Projetos/Casa/Telhado.md")] == [
        ("Projetos/Casa/Corte.excalidraw", "[[Telhado#Calhas]]")]
    assert [lig.origem for lig in mapa.desenhos_que_citam("Inbox/Reunião.md")] == [
        "Projetos/Casa/Corte.excalidraw"]
    assert mapa.desenhos_que_citam("Solta.md") == []
    # o mapa entre notas (visão geral, assessor, renomear) não muda
    assert all(not lig.origem.endswith(".excalidraw") for lig in mapa.ligacoes)


def test_desenho_que_leva_a_outro_desenho_fica_a_parte(raiz):
    from aide.storage import desenhos

    (raiz / "Projetos/Casa/Planta.excalidraw").write_text(desenhos.vazio())
    _desenho_com_links(raiz / "Projetos/Casa/Corte.excalidraw", "[[Planta.excalidraw]]",
                       "Planta.excalidraw", "[[Sumido.excalidraw]]", "[[Telhado]]")
    mapa = grafo.mapa(raiz)
    assert [(lig.origem, lig.destino, lig.citacao.trecho) for lig in mapa.entre_desenhos] == [
        ("Projetos/Casa/Corte.excalidraw", "Projetos/Casa/Planta.excalidraw",
         "[[Planta.excalidraw]]"),
        ("Projetos/Casa/Corte.excalidraw", "Projetos/Casa/Planta.excalidraw",
         "Planta.excalidraw")]
    assert [lig.destino for lig in mapa.de_desenhos] == ["Projetos/Casa/Telhado.md"]
