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


# ---------- gravação ----------

def test_gravar_troca_o_conteudo_e_fecha_a_permissao(raiz):
    caminho = raiz / "Inbox" / "Nota.md"
    vault.gravar(caminho, "novo")
    assert caminho.read_text() == "novo"
    assert caminho.stat().st_mode & 0o777 == 0o600


def test_gravar_nao_deixa_temporario_para_tras(raiz):
    vault.gravar(raiz / "Inbox" / "Nota.md", "novo")
    assert sorted(p.name for p in (raiz / "Inbox").iterdir()) == ["Nota.md"]


def test_falha_no_meio_deixa_a_versao_antiga(raiz, monkeypatch):
    import os

    def quebra(*a):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", quebra)
    with pytest.raises(OSError):
        vault.gravar(raiz / "Inbox" / "Nota.md", "novo")
    assert (raiz / "Inbox" / "Nota.md").read_text() == "x"
    assert sorted(p.name for p in (raiz / "Inbox").iterdir()) == ["Nota.md"]


def test_criar_nota_nao_sobrescreve(raiz):
    with pytest.raises(FileExistsError):
        vault.criar_nota(raiz / "Inbox" / "Nota.md", "outra")
    assert (raiz / "Inbox" / "Nota.md").read_text() == "x"


def test_criar_nota_em_pasta_nova(raiz):
    vault.criar_nota(raiz / "Projetos" / "Casa.md")
    assert (raiz / "Projetos" / "Casa.md").stat().st_mode & 0o777 == 0o600


def test_criar_pasta_que_ja_existe_falha(raiz):
    with pytest.raises(FileExistsError):
        vault.criar_pasta(raiz / "Inbox")


# ---------- índice do que a página salva ----------

@pytest.fixture
def banco(tmp_path):
    from aide.storage import connect, migrate

    conn = connect(tmp_path / "v.db")
    migrate(conn)
    return conn


def test_salvar_indexa_na_hora_pela_palavra_chave(raiz, banco):
    from aide.storage.reconciliacao import sincronizar
    from aide.storage.search import buscar_texto

    caminho = raiz / "Inbox" / "Nota.md"
    vault.gravar(caminho, "---\ntitle: Telhado\ntags: [casa]\n---\n\ntrocar as telhas\n")
    note_id = sincronizar(banco, caminho)
    row = banco.execute("SELECT title, tags, private FROM notes WHERE id = ?", (note_id,)).fetchone()
    assert tuple(row) == ("Telhado", "casa", 0)
    assert buscar_texto(banco, "telhas")


def test_sem_frontmatter_o_titulo_e_o_nome_do_arquivo(raiz, banco):
    from aide.storage.reconciliacao import sincronizar

    note_id = sincronizar(banco, raiz / "Inbox" / "Nota.md")
    assert banco.execute("SELECT title FROM notes WHERE id = ?", (note_id,)).fetchone()[0] == "Nota"


def test_salvar_de_novo_atualiza_a_mesma_linha(raiz, banco):
    from aide.storage.reconciliacao import sincronizar

    caminho = raiz / "Inbox" / "Nota.md"
    primeiro = sincronizar(banco, caminho)
    vault.gravar(caminho, "outra coisa")
    assert sincronizar(banco, caminho) == primeiro
    assert banco.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1


def test_na_pagina_o_privado_desmarca_tambem(raiz, banco):
    """Lá o frontmatter está na sua frente: tirar a linha é decisão vista."""
    from aide.storage.reconciliacao import sincronizar

    caminho = raiz / "Inbox" / "Nota.md"
    vault.gravar(caminho, "---\nprivate: true\n---\n\nx")
    note_id = sincronizar(banco, caminho)
    assert banco.execute("SELECT private FROM notes WHERE id = ?", (note_id,)).fetchone()[0] == 1
    vault.gravar(caminho, "x")
    sincronizar(banco, caminho)
    assert banco.execute("SELECT private FROM notes WHERE id = ?", (note_id,)).fetchone()[0] == 0


def test_salvar_nao_gera_vetor_e_apaga_o_velho(raiz, banco):
    from aide.storage.reconciliacao import sincronizar
    from aide.storage.search import guardar_vetor

    caminho = raiz / "Inbox" / "Nota.md"
    note_id = sincronizar(banco, caminho)
    guardar_vetor(banco, "note", note_id, "x", [1.0], "m")
    sincronizar(banco, caminho)
    assert banco.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0


def test_recriar_nota_apagada_nao_vai_para_a_lixeira(raiz, banco):
    """Sem reviver a linha, a reconciliação via "arquivo de nota apagada"."""
    from aide.storage.reconciliacao import esquecer, reconciliar, sincronizar

    caminho = raiz / "Inbox" / "Nota.md"
    sincronizar(banco, caminho)
    esquecer(banco, caminho)
    vault.para_lixeira(raiz, caminho)
    vault.criar_nota(caminho, "de novo")
    sincronizar(banco, caminho)
    reconciliar(banco, raiz)
    assert caminho.exists()


def test_esquecer_tira_da_busca(raiz, banco):
    from aide.storage.reconciliacao import esquecer, sincronizar
    from aide.storage.search import buscar_texto

    caminho = raiz / "Inbox" / "Nota.md"
    vault.gravar(caminho, "palavrarara")
    sincronizar(banco, caminho)
    assert esquecer(banco, caminho)
    assert buscar_texto(banco, "palavrarara") == []
    assert esquecer(banco, caminho) is None
