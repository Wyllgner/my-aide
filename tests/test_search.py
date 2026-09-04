import math

from aide.llm.embeddings import desempacotar, empacotar, similaridade
from aide.storage.search import buscar, buscar_semantico, fundir, guardar_vetor


class FakeEmbedder:
    """Vetores fabricados: cada palavra-chave vira uma dimensão."""

    EIXOS = ("dinheiro", "saude", "codigo")

    def __init__(self, mapa=None, erro=None):
        self.mapa = mapa or {}
        self.erro = erro

    def _vetor(self, texto):
        texto = texto.lower()
        for chave, eixo in self.mapa.items():
            if chave in texto:
                return [1.0 if i == eixo else 0.0 for i in range(len(self.EIXOS))]
        return [0.0, 0.0, 0.0]

    def embed_one(self, texto):
        if self.erro:
            raise self.erro
        return self._vetor(texto)


def test_empacota_e_desempacota_vetor():
    original = [0.5, -0.25, 0.125]
    voltou = desempacotar(empacotar(original))
    assert all(math.isclose(a, b, rel_tol=1e-6) for a, b in zip(original, voltou, strict=True))


def test_similaridade_reconhece_iguais_e_ortogonais():
    assert math.isclose(similaridade([1, 0], [1, 0]), 1.0)
    assert math.isclose(similaridade([1, 0], [0, 1]), 0.0)
    assert similaridade([], [1, 0]) == 0.0
    assert similaridade([1, 0], [1, 0, 0]) == 0.0  # tamanhos diferentes


def test_rrf_premia_quem_aparece_nas_duas_listas():
    texto = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
    semantico = [{"id": 2, "title": "B"}, {"id": 3, "title": "C"}]
    resultado = fundir([texto, semantico])
    assert resultado[0]["id"] == 2  # única presente nas duas


def test_rrf_mantem_quem_so_aparece_numa():
    resultado = fundir([[{"id": 1, "title": "A"}], [{"id": 2, "title": "B"}]])
    assert {r["id"] for r in resultado} == {1, 2}


def test_busca_semantica_ordena_por_proximidade(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    embedder = FakeEmbedder({"boleto": 0, "dentista": 1, "consulta médica": 1})
    ctx.embedder = embedder

    registry.call("notes.create", {"title": "Boleto", "body": "pagar boleto"}, ctx)
    registry.call("notes.create", {"title": "Dentista", "body": "marcar dentista"}, ctx)

    achados = buscar_semantico(ctx.conn, embedder.embed_one("consulta médica"))
    assert achados[0]["title"] == "Dentista"


def test_busca_hibrida_acha_por_significado_sem_a_palavra(ctx, registry, tmp_path):
    """O ponto dos embeddings: achar sem o termo exato aparecer no texto."""
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    ctx.embedder = FakeEmbedder({"dentista": 1, "consulta médica": 1})
    registry.call("notes.create", {"title": "Dentista", "body": "marcar dentista"}, ctx)

    assert buscar(ctx.conn, "consulta médica", embedder=ctx.embedder)


def test_busca_cai_para_texto_se_o_embedder_falha(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Orçamento", "body": "planilha do mês"}, ctx)

    quebrado = FakeEmbedder(erro=RuntimeError("sem rede"))
    achados = buscar(ctx.conn, "planilha", embedder=quebrado)
    assert [a["title"] for a in achados] == ["Orçamento"]


def test_nota_e_gravada_mesmo_sem_embedder(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    ctx.embedder = FakeEmbedder(erro=RuntimeError("sem rede"))
    resultado = registry.call("notes.create", {"title": "X", "body": "importante"}, ctx)
    assert resultado.ok
    assert buscar(ctx.conn, "importante", embedder=None)


def test_reindexar_substitui_o_vetor(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    ctx.embedder = FakeEmbedder({"x": 0})
    registry.call("notes.create", {"title": "X", "body": "um"}, ctx)
    guardar_vetor(ctx.conn, "note", 1, "outro", [0.0, 1.0, 0.0])
    total = ctx.conn.execute(
        "SELECT COUNT(*) c FROM embeddings WHERE ref_id = 1").fetchone()["c"]
    assert total == 1


def test_search_nao_devolve_nota_privada(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Segredo", "body": "conteudo sigiloso",
                                   "private": True}, ctx)
    achados = registry.call("notes.search", {"query": "sigiloso"}, ctx)
    assert achados.data == []


def test_palavras_funcionais_nao_entram_na_busca():
    """'no' e 'meu' casam com qualquer nota e afogam o termo que importa."""
    from aide.storage.search import preparar_consulta

    consulta = preparar_consulta("problema no meu dente")
    assert '"dente"' in consulta
    assert '"meu"' not in consulta and '"no"' not in consulta


def test_pergunta_so_de_stopwords_nao_vira_busca():
    from aide.storage.search import preparar_consulta

    assert preparar_consulta("o que é isso?") == ""


def test_ordem_correta_com_pergunta_natural(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Orçamento",
                                   "body": "cortar gastos no próximo trimestre"}, ctx)
    registry.call("notes.create", {"title": "Dentista", "body": "marcar limpeza do dente"}, ctx)
    achados = buscar(ctx.conn, "problema no meu dente")
    assert achados[0]["title"] == "Dentista"
