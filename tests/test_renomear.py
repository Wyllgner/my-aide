"""Renomear e mover notas consertando os links que apontavam para elas."""

import pytest

from aide.web import renomear


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    arquivos = {
        "Inbox/Reunião.md": "---\ntitle: R\n---\n\nver [[Telhado]] e [[Telhado#Orçamento|o orçamento]]",
        "Projetos/Casa/Telhado.md": "# Telhado\n\n## Orçamento\n\n[volta](../../Inbox/Reuni%C3%A3o.md)",
        "Projetos/Casa/Obra.md": "[o telhado](Telhado.md#Orçamento) e `[[Telhado]]` e ![[Telhado]]",
        "Solta.md": "[[telhado]] minúsculo e [[Projetos/Casa/Telhado]] com pasta",
    }
    for caminho, texto in arquivos.items():
        (pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
        (pasta / caminho).write_text(texto)
    return pasta


def _ler(raiz, caminho):
    return (raiz / caminho).read_text()


def test_renomear_atualiza_wikilinks_com_secao_e_apelido(raiz):
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    assert _ler(raiz, "Inbox/Reunião.md").endswith(
        "ver [[Cobertura]] e [[Cobertura#Orçamento|o orçamento]]")


def test_renomear_atualiza_link_markdown_e_mantem_a_secao(raiz):
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    assert _ler(raiz, "Projetos/Casa/Obra.md").startswith("[o telhado](Cobertura.md#Orçamento)")


def test_codigo_nao_e_mexido(raiz):
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    texto = _ler(raiz, "Projetos/Casa/Obra.md")
    assert "`[[Telhado]]`" in texto
    assert "![[Cobertura]]" in texto


def test_maiuscula_e_caminho_escritos_tambem_sao_trocados(raiz):
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    assert _ler(raiz, "Solta.md") == "[[Cobertura]] minúsculo e [[Cobertura]] com pasta"


def test_mover_de_pasta_refaz_os_links_relativos_da_propria_nota(raiz):
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Arquivo/Telhado.md")
    assert "[volta](../Inbox/Reuni%C3%A3o.md)" in _ler(raiz, "Arquivo/Telhado.md")
    # e quem apontava por relativo também
    assert _ler(raiz, "Projetos/Casa/Obra.md").startswith(
        "[o telhado](../../Arquivo/Telhado.md#Orçamento)")


def test_nome_repetido_em_outra_pasta_leva_a_pasta_no_link(raiz):
    (raiz / "Outro").mkdir()
    (raiz / "Outro" / "Cobertura.md").write_text("homônima")
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    assert "[[Projetos/Casa/Cobertura]]" in _ler(raiz, "Inbox/Reunião.md")


def test_link_markdown_escrito_sem_codificar(raiz):
    (raiz / "Inbox" / "Reunião.md").write_text("[t](<../Projetos/Casa/Telhado.md>)")
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    assert _ler(raiz, "Inbox/Reunião.md") == "[t](../Projetos/Casa/Cobertura.md)"


def test_devolve_so_as_notas_que_mudaram(raiz):
    mudadas = renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    assert sorted(mudadas) == ["Inbox/Reunião.md", "Projetos/Casa/Obra.md", "Solta.md"]


def test_nota_sem_ninguem_apontando_so_muda_de_nome(raiz):
    assert renomear.mover(raiz, "Solta.md", "Arquivo/Solta.md") == []
    assert (raiz / "Arquivo" / "Solta.md").exists()


def test_texto_em_volta_fica_como_estava(raiz):
    (raiz / "Inbox" / "Reunião.md").write_text("  linha com [[Telhado]]   e espaços  \n\nfim\n")
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    assert _ler(raiz, "Inbox/Reunião.md") == "  linha com [[Cobertura]]   e espaços  \n\nfim\n"


# ---------- pastas ----------

def test_mover_pasta_leva_as_notas_e_conserta_link_com_caminho(raiz):
    movidas, mudadas = renomear.mover_pasta(raiz, "Projetos/Casa", "Obras/Casa nova")
    assert movidas == {"Projetos/Casa/Obra.md": "Obras/Casa nova/Obra.md",
                       "Projetos/Casa/Telhado.md": "Obras/Casa nova/Telhado.md"}
    assert (raiz / "Obras" / "Casa nova" / "Telhado.md").exists()
    assert not (raiz / "Projetos" / "Casa").exists()
    # [[Telhado]] por nome continua valendo; [[Projetos/Casa/Telhado]] muda
    assert "[[Telhado]]" in _ler(raiz, "Inbox/Reunião.md")
    assert "[[Telhado]] com pasta" in _ler(raiz, "Solta.md")
    assert "Solta.md" in mudadas


def test_link_relativo_que_sai_da_pasta_e_refeito(raiz):
    renomear.mover_pasta(raiz, "Projetos/Casa", "Casa")
    assert "[volta](../Inbox/Reuni%C3%A3o.md)" in _ler(raiz, "Casa/Telhado.md")


def test_link_relativo_dentro_da_pasta_fica_igual(raiz):
    antes = _ler(raiz, "Projetos/Casa/Obra.md")
    renomear.mover_pasta(raiz, "Projetos/Casa", "Outra/Casa")
    assert _ler(raiz, "Outra/Casa/Obra.md") == antes


def test_pasta_nao_vai_para_dentro_dela_mesma(raiz):
    with pytest.raises(ValueError):
        renomear.mover_pasta(raiz, "Projetos", "Projetos/Casa/Dentro")
    assert (raiz / "Projetos" / "Casa" / "Telhado.md").exists()


def test_pasta_nunca_passa_por_cima_de_outra(raiz):
    (raiz / "Destino").mkdir()
    with pytest.raises(FileExistsError):
        renomear.mover_pasta(raiz, "Projetos/Casa", "Destino")
    assert (raiz / "Projetos" / "Casa" / "Telhado.md").exists()


# ---------- o destino dos outros links não muda ----------

@pytest.fixture
def homonimas(tmp_path):
    pasta = tmp_path / "v2"
    for caminho, texto in {"Arquivo/Ideias.md": "a de verdade", "Projetos/Lista.md": "ver [[Ideias]]",
                           "Inbox/Ideias.md": "outra"}.items():
        (pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
        (pasta / caminho).write_text(texto)
    return pasta


def test_nota_que_chega_nao_rouba_o_link_de_outra(homonimas):
    """Mover a Inbox/Ideias para Projetos faria o [[Ideias]] da Lista mudar
    de destino sozinho, pela preferência da mesma pasta."""
    from aide.storage import links

    renomear.mover(homonimas, "Inbox/Ideias.md", "Projetos/Ideias.md")
    assert _ler(homonimas, "Projetos/Lista.md") == "ver [[Arquivo/Ideias]]"
    assert links.indice(homonimas).resolver("Arquivo/Ideias", "Projetos/Lista.md") \
        == "Arquivo/Ideias.md"


def test_nota_movida_nao_muda_o_destino_dos_proprios_links(homonimas):
    """A Lista indo para Arquivo: o [[Ideias]] dela já ia para Arquivo/Ideias."""
    renomear.mover(homonimas, "Projetos/Lista.md", "Inbox/Lista.md")
    assert _ler(homonimas, "Inbox/Lista.md") == "ver [[Arquivo/Ideias]]"


def test_link_sem_ambiguidade_nao_e_tocado(raiz):
    antes = _ler(raiz, "Inbox/Reunião.md")
    renomear.mover(raiz, "Solta.md", "Arquivo/Solta.md")
    assert _ler(raiz, "Inbox/Reunião.md") == antes


def test_nota_que_nao_da_para_ler_fica_de_fora_sem_parar_o_resto(raiz):
    (raiz / "Velha.md").write_bytes("[[Telhado]] cita\xe7\xe3o".encode("latin-1"))
    puladas = []
    mudadas = renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md",
                             puladas)
    assert puladas == ["Velha.md"]
    assert "Inbox/Reunião.md" in mudadas
    assert (raiz / "Velha.md").read_bytes().endswith(b"cita\xe7\xe3o")


def test_link_com_caminho_numa_linha_e_curto_na_seguinte(raiz):
    """O mesmo parágrafo: o nome "Telhado" também está dentro do link com
    pasta da linha de cima, e o curto era atribuído àquela linha — que o
    renomear não conseguia trocar, deixando o link quebrado."""
    (raiz / "Mista.md").write_text("a [[Projetos/Casa/Telhado]]\nb [[Telhado|o telhado]]\n")
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md")
    # nome único: o renomear encurta o de cima também, como sempre fez
    assert _ler(raiz, "Mista.md") == "a [[Cobertura]]\nb [[Cobertura|o telhado]]\n"


# ---------- o link dos elementos dos desenhos ----------

def _desenho(raiz, caminho, *links_, privada=False):
    import json

    from aide.storage import desenhos

    dados = json.loads(desenhos.vazio())
    dados["elements"] = [{"type": "rectangle", "id": f"e{i}", "version": 3, "link": link}
                         for i, link in enumerate(links_)]
    if privada:
        dados["aide"] = {"privada": True}
    (raiz / caminho).write_text(json.dumps(dados))


def _links(raiz, caminho):
    import json

    return [e["link"] for e in json.loads((raiz / caminho).read_text())["elements"]]


def test_renomear_nota_conserta_o_link_do_desenho_no_mesmo_formato(raiz):
    _desenho(raiz, "Projetos/Corte.excalidraw", "[[Telhado#Orçamento|o orçamento]]",
             "Telhado", " [[telhado]] ", "Casa/Telhado.md#Orçamento", "[[Reunião]]",
             "https://x.org")
    mudados = []
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md",
                   desenhos_mudados=mudados)
    assert mudados == ["Projetos/Corte.excalidraw"]
    assert _links(raiz, "Projetos/Corte.excalidraw") == [
        "[[Cobertura#Orçamento|o orçamento]]", "Cobertura", "[[Cobertura]]",
        "Casa/Cobertura.md#Orçamento", "[[Reunião]]", "https://x.org"]


def test_elemento_mudado_sobe_de_versao_e_o_privado_fica(raiz):
    import json

    from aide.storage import desenhos

    _desenho(raiz, "Corte.excalidraw", "[[Telhado]]", "[[Reunião]]", privada=True)
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md",
                   desenhos_mudados=[])
    dados = json.loads((raiz / "Corte.excalidraw").read_text())
    assert [e["version"] for e in dados["elements"]] == [4, 3]
    assert desenhos.privado(dados)


def test_mover_pasta_leva_o_desenho_e_refaz_o_link_relativo_dele(raiz):
    _desenho(raiz, "Projetos/Casa/Corte.excalidraw", "../../Inbox/Reuni%C3%A3o.md",
             "[[Projetos/Casa/Telhado]]")
    mudados = []
    renomear.mover_pasta(raiz, "Projetos", "Arquivo", desenhos_mudados=mudados)
    assert mudados == ["Arquivo/Casa/Corte.excalidraw"]
    assert _links(raiz, "Arquivo/Casa/Corte.excalidraw") == [
        "../../Inbox/Reuni%C3%A3o.md", "[[Telhado]]"]


def test_desenho_que_nao_abre_vai_para_as_puladas(raiz, monkeypatch):
    from aide.storage import desenhos

    _desenho(raiz, "Corte.excalidraw", "[[Telhado]]")

    def falha(*_a, **_k):
        raise OSError("sem permissão")

    monkeypatch.setattr(desenhos, "gravar", falha)
    puladas, mudados = [], []
    renomear.mover(raiz, "Projetos/Casa/Telhado.md", "Projetos/Casa/Cobertura.md",
                   puladas, mudados)
    assert puladas == ["Corte.excalidraw"] and mudados == []


# ---------- renomear desenho: o link de outros desenhos ----------

def test_renomear_desenho_conserta_o_link_de_outro_desenho(raiz):
    from aide.storage import desenhos

    (raiz / "Projetos/Casa/Planta.excalidraw").write_text(desenhos.vazio())
    _desenho(raiz, "Inbox/Ideias.excalidraw", "[[Planta.excalidraw|a planta]]",
             "Projetos/Casa/Planta.excalidraw", "[[Reunião]]")
    mudados = []
    renomear.mover_desenho(raiz, "Projetos/Casa/Planta.excalidraw",
                           "Projetos/Casa/Corte.excalidraw", desenhos_mudados=mudados)
    assert mudados == ["Inbox/Ideias.excalidraw"]
    assert _links(raiz, "Inbox/Ideias.excalidraw") == [
        "[[Corte.excalidraw|a planta]]", "Corte.excalidraw", "[[Reunião]]"]


def test_desenho_movido_refaz_os_proprios_links(raiz):
    from aide.storage import desenhos

    (raiz / "Projetos/Casa/Planta.excalidraw").write_text(desenhos.vazio())
    _desenho(raiz, "Projetos/Casa/Corte.excalidraw", "Telhado.md", "[[Corte.excalidraw]]",
             "[[Planta.excalidraw]]")
    (raiz / "Inbox" / "Planta.excalidraw").write_text(desenhos.vazio())
    mudados = []
    renomear.mover_desenho(raiz, "Projetos/Casa/Corte.excalidraw", "Inbox/Corte.excalidraw",
                           desenhos_mudados=mudados)
    assert mudados == ["Inbox/Corte.excalidraw"]
    # o .md relativo muda de pasta; o link para si mesmo segue o nome; e a
    # Planta da pasta nova não rouba o link que levava à de Projetos/Casa
    assert _links(raiz, "Inbox/Corte.excalidraw") == [
        "../Projetos/Casa/Telhado.md", "[[Corte.excalidraw]]",
        "[[Projetos/Casa/Planta.excalidraw]]"]


def test_mover_pasta_conserta_link_de_desenho_com_caminho(raiz):
    from aide.storage import desenhos

    (raiz / "Projetos/Casa/Planta.excalidraw").write_text(desenhos.vazio())
    _desenho(raiz, "Inbox/Ideias.excalidraw", "[[Projetos/Casa/Planta.excalidraw]]")
    mudados = []
    renomear.mover_pasta(raiz, "Projetos", "Arquivo", desenhos_mudados=mudados)
    assert mudados == ["Inbox/Ideias.excalidraw"]
    assert _links(raiz, "Inbox/Ideias.excalidraw") == ["[[Planta.excalidraw]]"]


def test_sem_desenhos_mudados_nao_le_o_mapa(raiz, monkeypatch):
    """Quem não pede (o mover antigo) não paga a leitura dos desenhos."""
    from aide.storage import desenhos

    (raiz / "Planta.excalidraw").write_text(desenhos.vazio())

    def proibido(*_a, **_k):
        raise AssertionError("leu o mapa")

    monkeypatch.setattr(renomear.grafo, "mapa", proibido)
    renomear.mover_desenho(raiz, "Planta.excalidraw", "Corte.excalidraw")
