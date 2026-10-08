from pathlib import Path

from aide.storage import vault
from aide.storage.search import buscar_texto, preparar_consulta


def _config_vault(ctx, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "vault")
    return ctx


def test_cria_nota_e_grava_o_arquivo(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    resultado = registry.call(
        "notes.create", {"title": "Arquitetura do my-aide", "body": "Vault é a fonte."}, ctx
    )
    assert resultado.ok
    caminho = Path(resultado.data["path"])
    assert caminho.exists()
    texto = caminho.read_text()
    assert "title: Arquitetura do my-aide" in texto
    assert "Vault é a fonte." in texto


def test_arquivo_vai_para_pasta_do_mes(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    caminho = Path(registry.call("notes.create", {"title": "X", "body": "y"}, ctx).data["path"])
    assert caminho.parent.name.count("-") == 1  # 2026-09


def test_titulos_iguais_nao_se_sobrescrevem(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    a = registry.call("notes.create", {"title": "Igual", "body": "um"}, ctx).data["path"]
    b = registry.call("notes.create", {"title": "Igual", "body": "dois"}, ctx).data["path"]
    assert a != b
    assert Path(a).read_text() != Path(b).read_text()


def test_nota_vazia_e_recusada(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    assert not registry.call("notes.create", {"title": "X", "body": "   "}, ctx).ok


def test_append_data_o_trecho(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "Diário", "body": "primeiro"}, ctx).data
    assert registry.call("notes.append", {"id": nota["id"], "body": "segundo"}, ctx).ok
    corpo = Path(nota["path"]).read_text()
    assert "primeiro" in corpo and "segundo" in corpo


def test_append_por_titulo(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    registry.call("notes.create", {"title": "Diário", "body": "um"}, ctx)
    assert registry.call("notes.append", {"title": "Diário", "body": "dois"}, ctx).ok


def test_ler_nota(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "X", "body": "conteúdo real"}, ctx).data
    assert registry.call("notes.read", {"id": nota["id"]}, ctx).data["body"] == "conteúdo real"


def test_nota_inexistente_falha(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    assert not registry.call("notes.read", {"id": 999}, ctx).ok


def test_busca_por_palavra_chave(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    registry.call("notes.create", {"title": "Reunião", "body": "falamos de orçamento"}, ctx)
    registry.call("notes.create", {"title": "Receita", "body": "bolo de cenoura"}, ctx)
    achados = buscar_texto(ctx.conn, "orçamento")
    assert [a["title"] for a in achados] == ["Reunião"]


def test_busca_ignora_pontuacao_da_pergunta(ctx, registry, tmp_path):
    """Sem sanitizar, aspas e parênteses viram erro de sintaxe do FTS5."""
    _config_vault(ctx, tmp_path)
    registry.call("notes.create", {"title": "Deploy", "body": "usamos docker"}, ctx)
    assert buscar_texto(ctx.conn, 'o que eu disse sobre "docker" (mesmo)?')


def test_busca_com_consulta_vazia_nao_quebra(ctx):
    assert buscar_texto(ctx.conn, "  ") == []
    assert preparar_consulta("!!!") == ""


def test_busca_pode_esconder_privadas(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    registry.call("notes.create", {"title": "Segredo", "body": "senha do cofre",
                                   "private": True}, ctx)
    assert buscar_texto(ctx.conn, "cofre", incluir_privadas=False) == []
    assert buscar_texto(ctx.conn, "cofre", incluir_privadas=True)


def test_append_reindexa(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "X", "body": "inicial"}, ctx).data
    assert buscar_texto(ctx.conn, "posterior") == []
    registry.call("notes.append", {"id": nota["id"], "body": "texto posterior"}, ctx)
    assert buscar_texto(ctx.conn, "posterior")


def test_apagar_leva_o_arquivo_para_a_lixeira(ctx, registry, tmp_path):
    """Apagar é um ato completo. Enquanto o arquivo ficava no vault, existia a
    nota que está no disco e não está em lugar nenhum mais: invisível na busca,
    na listagem e para a reindexação, que varria as linhas."""
    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "X", "body": "conteudo unico"}, ctx).data
    resultado = registry.call("notes.delete", {"id": nota["id"]}, ctx).data

    assert buscar_texto(ctx.conn, "unico") == []
    assert not Path(nota["path"]).exists()
    # não é destruição: o texto continua legível, e voltar é um mv
    na_lixeira = Path(resultado["arquivo"])
    assert na_lixeira.parent.name == ".trash"
    assert "conteudo unico" in na_lixeira.read_text()


def test_lixeira_nao_sobrescreve_homonimo(ctx, registry, tmp_path):
    """Duas notas de mesmo título apagadas não podem virar uma."""
    _config_vault(ctx, tmp_path)
    primeira = registry.call("notes.create", {"title": "X", "body": "a primeira"}, ctx).data
    segunda = registry.call("notes.create", {"title": "X", "body": "a segunda"}, ctx).data

    um = registry.call("notes.delete", {"id": primeira["id"]}, ctx).data["arquivo"]
    dois = registry.call("notes.delete", {"id": segunda["id"]}, ctx).data["arquivo"]

    assert um != dois
    assert "a primeira" in Path(um).read_text()
    assert "a segunda" in Path(dois).read_text()


def test_a_lixeira_fica_fora_da_varredura(ctx, registry, tmp_path):
    """Senão a reindexação adotaria de volta o que acabou de ser apagado."""
    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "X", "body": "conteudo"}, ctx).data
    registry.call("notes.delete", {"id": nota["id"]}, ctx)

    assert vault.arquivos(Path(ctx.config.vault_dir)) == []


def test_frontmatter_e_lido_de_volta(tmp_path):
    from datetime import datetime

    caminho = tmp_path / "n.md"
    vault.escrever(caminho, "Título", "corpo aqui", "a,b", datetime(2026, 9, 3, 10, 0))
    meta, corpo = vault.ler(caminho)
    assert meta["title"] == "Título"
    assert corpo == "corpo aqui"


def test_arquivo_sem_frontmatter_tambem_serve(tmp_path):
    caminho = tmp_path / "solto.md"
    caminho.write_text("só texto")
    assert vault.ler(caminho) == ({}, "só texto")


def test_slug_lida_com_acento_e_simbolo():
    assert vault.slugify("Reunião: orçamento & prazos!") == "reuniao-orcamento-prazos"


def test_reindexar_reconstroi_do_arquivo(ctx, registry, tmp_path):
    """O markdown é a fonte da verdade: perder o índice não pode perder a nota."""
    from aide.storage.search import indexar

    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "X", "body": "conteudo original"}, ctx).data

    ctx.conn.execute("DELETE FROM notes_fts")
    assert buscar_texto(ctx.conn, "original") == []

    corpo = vault.corpo_de(Path(nota["path"]))
    indexar(ctx.conn, nota["id"], "X", corpo)
    assert buscar_texto(ctx.conn, "original")


# ---------- notes.list ----------

def test_lista_notas_da_mais_recente_para_a_mais_antiga(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    for titulo in ("Primeira", "Segunda", "Terceira"):
        registry.call("notes.create", {"title": titulo, "body": "x"}, ctx)
    # updated_at tem resolução de segundos: sem separar, a ordem fica empatada
    ctx.conn.execute("UPDATE notes SET updated_at = '2026-01-0' || id || ' 00:00'")

    titulos = [n["title"] for n in registry.call("notes.list", {}, ctx).data]
    assert titulos == ["Terceira", "Segunda", "Primeira"]


def test_lista_respeita_o_limite(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    for i in range(5):
        registry.call("notes.create", {"title": f"N{i}", "body": "x"}, ctx)
    assert len(registry.call("notes.list", {"limit": 2}, ctx).data) == 2


def test_lista_filtra_por_tag(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Com", "body": "x", "tags": "carro,viagem"}, ctx)
    registry.call("notes.create", {"title": "Sem", "body": "x", "tags": "trabalho"}, ctx)

    achadas = registry.call("notes.list", {"tag": "carro"}, ctx).data
    assert [n["title"] for n in achadas] == ["Com"]


def test_lista_esconde_nota_apagada(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Alvo", "body": "x"}, ctx)
    ctx.conn.execute("UPDATE notes SET deleted_at = datetime('now')")
    assert registry.call("notes.list", {}, ctx).data == []


def test_a_listagem_traz_a_data_pronta(ctx, registry, tmp_path):
    """Sem uma data pronta a resposta saía sem data nenhuma — `updated_at` é
    carimbo de máquina, e converter é onde o modelo erra de fuso."""
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Deploy", "body": "x"}, ctx)

    nota = registry.call("notes.list", {}, ctx).data[0]
    assert nota["quando"] == "hoje"
    assert ":" not in nota["quando"]  # sem hora


# ---------- privada não vira vetor ----------

class EmbedderEspiao:
    """Guarda tudo o que teria ido para a OpenAI."""

    modelo = "espiao-1"

    def __init__(self):
        self.enviado = []

    def embed_one(self, texto):
        self.enviado.append(texto)
        return [1.0, 0.0]


def test_nota_privada_nao_vai_para_o_embedding(ctx, registry, tmp_path):
    """Gerar o vetor é mandar o texto para fora; privado não sai desta máquina."""
    _config_vault(ctx, tmp_path)
    ctx.embedder = EmbedderEspiao()
    registry.call("notes.create", {"title": "Laudo", "body": "SEGREDO", "private": True}, ctx)
    assert ctx.embedder.enviado == []
    # a busca local continua achando
    assert buscar_texto(ctx.conn, "SEGREDO")


def test_acrescentar_em_privada_nao_vai_para_o_embedding(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    ctx.ver_privado = True
    nota = registry.call("notes.create", {"title": "Laudo", "body": "a",
                                          "private": True}, ctx).data
    ctx.embedder = EmbedderEspiao()
    registry.call("notes.append", {"id": nota["id"], "body": "SEGREDO"}, ctx)
    assert ctx.embedder.enviado == []


def test_reindexar_privada_nao_vai_para_o_embedding(ctx, registry, tmp_path):
    from aide.storage.reconciliacao import reconciliar

    _config_vault(ctx, tmp_path)
    registry.call("notes.create", {"title": "Laudo", "body": "SEGREDO", "private": True}, ctx)
    espiao = EmbedderEspiao()
    reconciliar(ctx.conn, Path(ctx.config.vault_dir), embedder=espiao, forcar=True)
    assert espiao.enviado == []


def test_nota_normal_continua_virando_vetor(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    ctx.embedder = EmbedderEspiao()
    registry.call("notes.create", {"title": "Mercado", "body": "comprar pão"}, ctx)
    assert len(ctx.embedder.enviado) == 1


# ---------- privado no frontmatter ----------

def test_privada_fica_marcada_no_arquivo(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "Laudo", "body": "x", "private": True}, ctx).data
    meta, _ = vault.ler(Path(nota["path"]))
    assert vault.privada(meta)


def test_normal_nao_ganha_a_linha(ctx, registry, tmp_path):
    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "Mercado", "body": "x"}, ctx).data
    assert "private" not in vault.ler(Path(nota["path"]))[0]


def test_arquivo_privado_adotado_nasce_privado(ctx, tmp_path):
    from aide.storage.reconciliacao import reconciliar

    _config_vault(ctx, tmp_path)
    pasta = Path(ctx.config.vault_dir)
    pasta.mkdir()
    (pasta / "Diário.md").write_text("---\nprivate: true\n---\n\nSEGREDO\n")
    espiao = EmbedderEspiao()
    reconciliar(ctx.conn, pasta, embedder=espiao)
    assert ctx.conn.execute("SELECT private FROM notes").fetchone()[0] == 1
    assert espiao.enviado == []


def test_marcar_privada_por_fora_sobe_e_apaga_o_vetor(ctx, registry, tmp_path):
    import os

    from aide.storage.reconciliacao import reconciliar

    _config_vault(ctx, tmp_path)
    ctx.embedder = EmbedderEspiao()
    nota = registry.call("notes.create", {"title": "Diário", "body": "x"}, ctx).data
    caminho = Path(nota["path"])
    caminho.write_text(caminho.read_text().replace("---\n\n", "private: true\n---\n\n", 1))
    os.utime(caminho, (caminho.stat().st_mtime + 60,) * 2)

    reconciliar(ctx.conn, Path(ctx.config.vault_dir), embedder=EmbedderEspiao())
    assert ctx.conn.execute("SELECT private FROM notes").fetchone()[0] == 1
    assert ctx.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0


def test_tirar_a_linha_por_fora_nao_desmarca(ctx, registry, tmp_path):
    """Desmarcar o privado é decisão explícita, não efeito colateral."""
    import os

    from aide.storage.reconciliacao import reconciliar

    _config_vault(ctx, tmp_path)
    nota = registry.call("notes.create", {"title": "Laudo", "body": "x", "private": True}, ctx).data
    caminho = Path(nota["path"])
    caminho.write_text(caminho.read_text().replace("private: true\n", ""))
    os.utime(caminho, (caminho.stat().st_mtime + 60,) * 2)

    espiao = EmbedderEspiao()
    reconciliar(ctx.conn, Path(ctx.config.vault_dir), embedder=espiao)
    assert ctx.conn.execute("SELECT private FROM notes").fetchone()[0] == 1
    assert espiao.enviado == []
