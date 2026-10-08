"""O vault visto pela página: caminhos vindos de fora, árvore e gravação."""

import pytest

from aide.storage import vault
from aide.storage.vault import ForaDoVault


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    (pasta / "Inbox").mkdir(parents=True)
    (pasta / "Inbox" / "Nota.md").write_text("x")
    return pasta


# ---------- resolver ----------

@pytest.mark.parametrize("caminho", [
    "Inbox/Nota.md", "Nota nova.md", "Projetos/Casa/Reunião de orçamento.md",
])
def test_caminho_comum_resolve_dentro_do_vault(raiz, caminho):
    assert vault.resolver(raiz, caminho).is_relative_to(raiz.resolve())


@pytest.mark.parametrize("caminho", [
    "", "   ", "../fora.md", "Inbox/../../fora.md", "/etc/passwd.md",
    "Inbox\\..\\fora.md", ".trash/Nota.md", ".obsidian/app.md", "Inbox/.oculta.md",
    "Inbox//Nota.md", "./Nota.md", "Inbox/Nota.txt", "Inbox/Nota", "nul\x00.md",
    "Inbox/a:b.md", "Inbox/[[x]].md", " Inbox/Nota.md ", "Inbox /Nota.md",
    "a" * 300 + ".md",
])
def test_caminho_suspeito_e_recusado(raiz, caminho):
    with pytest.raises(ForaDoVault):
        vault.resolver(raiz, caminho)


def test_pasta_nao_precisa_de_extensao(raiz):
    assert vault.resolver(raiz, "Projetos/Casa", pasta=True).name == "Casa"


def test_link_simbolico_para_fora_e_recusado(raiz, tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    (raiz / "atalho").symlink_to(fora)
    with pytest.raises(ForaDoVault):
        vault.resolver(raiz, "atalho/x.md")


def test_link_simbolico_mesmo_dentro_e_recusado(raiz):
    """Um link interno vira externo com um `ln -sf`; nem vale a conferência."""
    (raiz / "Inbox" / "atalho.md").symlink_to(raiz / "Inbox" / "Nota.md")
    with pytest.raises(ForaDoVault):
        vault.resolver(raiz, "Inbox/atalho.md")


def test_vault_atras_de_link_simbolico_continua_valendo(tmp_path, raiz):
    """O próprio vault pode ser um link (Dropbox, outro disco); o que não pode
    é link dentro dele."""
    link = tmp_path / "link-do-vault"
    link.symlink_to(raiz)
    assert vault.resolver(link, "Inbox/Nota.md").exists()


def test_relativo_e_o_inverso(raiz):
    caminho = vault.resolver(raiz, "Inbox/Nota.md")
    assert vault.relativo_de(raiz, caminho) == "Inbox/Nota.md"


# ---------- árvore ----------

def test_arvore_pastas_primeiro_e_sem_caixa(raiz):
    (raiz / "zebra.md").write_text("")
    (raiz / "Abacate.md").write_text("")
    (raiz / "Projetos" / "Casa").mkdir(parents=True)
    (raiz / "Projetos" / "Casa" / "Telhado.md").write_text("")
    nomes = [i["nome"] for i in vault.arvore(raiz)]
    assert nomes == ["Inbox", "Projetos", "Abacate", "zebra"]
    casa = vault.arvore(raiz)[1]["filhos"][0]
    assert casa["filhos"][0] == {"nome": "Telhado", "caminho": "Projetos/Casa/Telhado.md",
                                 "tipo": "nota", "filhos": []}


def test_arvore_esconde_o_que_a_pagina_nao_abriria(raiz, tmp_path):
    (raiz / ".trash").mkdir()
    (raiz / ".trash" / "Velha.md").write_text("")
    (raiz / ".obsidian").mkdir()
    (raiz / "foto.png").write_bytes(b"")
    (raiz / "atalho.md").symlink_to(raiz / "Inbox" / "Nota.md")
    assert [i["nome"] for i in vault.arvore(raiz)] == ["Inbox"]


def test_arvore_de_vault_que_nao_existe(tmp_path):
    assert vault.arvore(tmp_path / "nada") == []


def test_todo_caminho_da_arvore_passa_no_resolver(raiz):
    (raiz / "Projetos" / "Casa").mkdir(parents=True)
    (raiz / "Projetos" / "Casa" / "Reunião de orçamento.md").write_text("")

    def todos(itens):
        for i in itens:
            yield i
            yield from todos(i["filhos"])

    for item in todos(vault.arvore(raiz)):
        vault.resolver(raiz, item["caminho"], pasta=item["tipo"] == "pasta")
