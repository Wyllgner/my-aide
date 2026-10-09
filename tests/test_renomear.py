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
