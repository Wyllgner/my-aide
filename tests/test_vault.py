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


class Espiao:
    modelo = "espiao-1"

    def __init__(self):
        self.enviado = []

    def embed_one(self, texto):
        self.enviado.append(texto)
        return [1.0, 0.0]


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


def test_o_daemon_gera_o_vetor_so_da_normal(raiz, banco):
    from aide.storage.reconciliacao import reconciliar, sincronizar

    vault.gravar(raiz / "Inbox" / "Normal.md", "pode ir")
    vault.gravar(raiz / "Inbox" / "Diário.md", "---\nprivate: true\n---\n\nSEGREDO")
    for nome in ("Normal.md", "Diário.md", "Nota.md"):
        sincronizar(banco, raiz / "Inbox" / nome)
    espiao = Espiao()
    relato = reconciliar(banco, raiz, embedder=espiao)
    assert len(relato.vetorizadas) == 2
    assert not any("SEGREDO" in t for t in espiao.enviado)
    # na volta seguinte não manda de novo
    assert reconciliar(banco, raiz, embedder=Espiao()).vetorizadas == []


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


def test_o_daemon_relê_o_privado_antes_de_mandar(raiz, banco):
    """O banco ainda diz normal, mas o arquivo já foi marcado: vale o arquivo."""
    from aide.storage.reconciliacao import reconciliar, sincronizar

    caminho = raiz / "Inbox" / "Nota.md"
    sincronizar(banco, caminho)
    caminho.write_text("---\nprivate: true\n---\n\nSEGREDO")
    espiao = Espiao()
    reconciliar(banco, raiz, embedder=espiao)
    assert espiao.enviado == []
    assert banco.execute("SELECT private FROM notes").fetchone()[0] == 1


# ---------- frontmatter ----------

def test_frontmatter_vai_ate_a_linha_que_fecha():
    meta, corpo = vault.separar("---\ntitle: a --- b\n---\n\ncorpo\n\n---\n\nresto")
    assert meta == {"title": "a --- b"}
    assert corpo == "corpo\n\n---\n\nresto"


def test_tracos_no_comeco_que_nao_sao_frontmatter():
    assert vault.separar("----\nlinha") == ({}, "----\nlinha")
    assert vault.separar("---\nnunca fecha") == ({}, "---\nnunca fecha")


def test_frontmatter_vazio():
    assert vault.separar("---\n---\ncorpo") == ({}, "corpo")


# ---------- mover ----------

def test_mover_leva_o_arquivo_e_cria_a_pasta(raiz):
    vault.mover(raiz / "Inbox" / "Nota.md", raiz / "Projetos" / "Casa" / "Nota nova.md")
    assert not (raiz / "Inbox" / "Nota.md").exists()
    assert (raiz / "Projetos" / "Casa" / "Nota nova.md").read_text() == "x"


def test_mover_nunca_passa_por_cima(raiz):
    (raiz / "Outra.md").write_text("não apague")
    with pytest.raises(FileExistsError):
        vault.mover(raiz / "Inbox" / "Nota.md", raiz / "Outra.md")
    assert (raiz / "Outra.md").read_text() == "não apague"
    assert (raiz / "Inbox" / "Nota.md").exists()


def test_mover_no_indice_mantem_a_linha_e_o_vetor(raiz, banco):
    from aide.storage.reconciliacao import mover_no_indice, sincronizar
    from aide.storage.search import buscar_texto, guardar_vetor

    de, para = raiz / "Inbox" / "Nota.md", raiz / "Inbox" / "Telhado.md"
    note_id = sincronizar(banco, de)
    guardar_vetor(banco, "note", note_id, "x", [1.0], "m")
    vault.mover(de, para)
    assert mover_no_indice(banco, de, para) == note_id
    row = banco.execute("SELECT path, title FROM notes WHERE id = ?", (note_id,)).fetchone()
    assert tuple(row) == (str(para), "Telhado")
    assert banco.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 1
    assert buscar_texto(banco, "Telhado")


def test_mover_no_indice_mantem_o_titulo_do_frontmatter(raiz, banco):
    from aide.storage.reconciliacao import mover_no_indice, sincronizar

    de, para = raiz / "Inbox" / "Nota.md", raiz / "Arquivo.md"
    de.write_text("---\ntitle: Título próprio\n---\n\nx")
    sincronizar(banco, de)
    vault.mover(de, para)
    note_id = mover_no_indice(banco, de, para)
    assert banco.execute("SELECT title FROM notes WHERE id = ?", (note_id,)).fetchone()[0] \
        == "Título próprio"


def test_mover_para_o_caminho_de_uma_nota_apagada(raiz, banco):
    """O caminho é único no banco; a linha apagada não pode travar o mover."""
    from aide.storage.reconciliacao import esquecer, mover_no_indice, reconciliar, sincronizar

    velha = raiz / "Velha.md"
    velha.write_text("antiga")
    sincronizar(banco, velha)
    esquecer(banco, velha)
    vault.para_lixeira(raiz, velha)
    de = raiz / "Inbox" / "Nota.md"
    sincronizar(banco, de)
    vault.mover(de, velha)
    mover_no_indice(banco, de, velha)
    reconciliar(banco, raiz)
    assert velha.exists(), "a reconciliação não pode mandar a nota movida para a lixeira"


def test_mover_arquivo_que_o_banco_nao_conhecia(raiz, banco):
    from aide.storage.reconciliacao import mover_no_indice

    de, para = raiz / "Inbox" / "Nota.md", raiz / "Nova.md"
    vault.mover(de, para)
    note_id = mover_no_indice(banco, de, para)
    assert banco.execute("SELECT path FROM notes WHERE id = ?", (note_id,)).fetchone()[0] \
        == str(para)


def test_mover_em_disco_sem_link_fisico(raiz, monkeypatch):
    """exFAT e algumas pastas sincronizadas não têm link físico."""
    import errno
    import os

    def sem_link(*a):
        raise OSError(errno.EPERM, "sem link")

    monkeypatch.setattr(os, "link", sem_link)
    vault.mover(raiz / "Inbox" / "Nota.md", raiz / "Nova.md")
    assert (raiz / "Nova.md").read_text() == "x"
    (raiz / "Outra.md").write_text("fica")
    with pytest.raises(FileExistsError):
        vault.mover(raiz / "Nova.md", raiz / "Outra.md")
    assert (raiz / "Outra.md").read_text() == "fica"


def test_outro_erro_de_disco_nao_e_engolido(raiz, monkeypatch):
    import errno
    import os

    def cheio(*a):
        raise OSError(errno.ENOSPC, "disco cheio")

    monkeypatch.setattr(os, "link", cheio)
    with pytest.raises(OSError):
        vault.mover(raiz / "Inbox" / "Nota.md", raiz / "Nova.md")
    assert (raiz / "Inbox" / "Nota.md").exists()
