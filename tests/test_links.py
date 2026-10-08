"""Resolução de [[links]] entre notas, na regra do Obsidian."""

import unicodedata

import pytest

from aide.storage import links


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    for caminho in ("Inbox/Reunião de orçamento.md", "Inbox/Ideias.md",
                    "Projetos/Casa/Telhado.md", "Projetos/Casa/Ideias.md",
                    "Arquivo/Velho/Telhado.md", "Telhado.md", "Leia-me.md"):
        (pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
        (pasta / caminho).write_text("x")
    return pasta


@pytest.fixture
def indice(raiz):
    return links.indice(raiz)


def test_acha_pelo_nome_sem_extensao(indice):
    assert indice.resolver("Reunião de orçamento") == "Inbox/Reunião de orçamento.md"


def test_maiuscula_e_extensao_nao_importam(indice):
    assert indice.resolver("reunião DE orçamento.md") == "Inbox/Reunião de orçamento.md"


def test_acento_decomposto_acha_o_composto(indice):
    """O mesmo "ã" pode chegar como um caractere só ou como "a" + til."""
    assert indice.resolver(unicodedata.normalize("NFD", "Reunião de orçamento"))


def test_mesmo_nome_prefere_a_pasta_de_quem_linka(indice):
    assert indice.resolver("Ideias", origem="Projetos/Casa/Lista.md") == "Projetos/Casa/Ideias.md"
    assert indice.resolver("Ideias", origem="Inbox/Outra.md") == "Inbox/Ideias.md"


def test_mesmo_nome_sem_pasta_em_comum_vai_para_o_mais_curto(indice):
    assert indice.resolver("Telhado", origem="Inbox/x.md") == "Telhado.md"


def test_empate_e_sempre_o_mesmo(indice):
    """Sem isto o link mudaria de destino conforme a ordem do disco."""
    assert indice.resolver("Ideias", origem="Leia-me.md") == "Inbox/Ideias.md"


def test_caminho_completo(indice):
    assert indice.resolver("Arquivo/Velho/Telhado") == "Arquivo/Velho/Telhado.md"


def test_final_do_caminho(indice):
    assert indice.resolver("Velho/Telhado") == "Arquivo/Velho/Telhado.md"
    assert indice.resolver("Casa/Telhado") == "Projetos/Casa/Telhado.md"


@pytest.mark.parametrize("alvo", ["Não existe", "", "   ", "/", "Casa/Nada"])
def test_link_quebrado_e_none(indice, alvo):
    assert indice.resolver(alvo) is None


def test_lixeira_e_oculto_nao_sao_destino(raiz):
    (raiz / ".trash").mkdir()
    (raiz / ".trash" / "Apagada.md").write_text("x")
    assert links.indice(raiz).resolver("Apagada") is None


def test_caminhos_para_o_autocompletar(indice):
    assert indice.caminhos[0] == "Arquivo/Velho/Telhado.md"
    assert len(indice.caminhos) == 7
