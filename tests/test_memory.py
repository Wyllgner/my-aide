from aide.core.context import build, profile_prompt
from aide.tools.memory import LIMITE_PERFIL, perfil_para_prompt


def test_salva_e_lista_perfil(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "academia",
                                  "value": "treina 6h da manhã"}, ctx)
    perfil = registry.call("memory.list", {}, ctx).data
    assert perfil[0]["key"] == "academia"


def test_chave_e_normalizada(ctx, registry):
    resultado = registry.call("memory.save", {"kind": "profile", "key": "Horário Academia",
                                              "value": "6h"}, ctx)
    assert resultado.data["key"] == "horário_academia"


def test_fato_novo_substitui_o_antigo(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "cidade",
                                  "value": "São Paulo"}, ctx)
    novo = registry.call("memory.save", {"kind": "profile", "key": "cidade",
                                         "value": "Belo Horizonte"}, ctx)
    assert novo.data["substituiu"] == 1
    vigentes = registry.call("memory.list", {}, ctx).data
    assert [m["value"] for m in vigentes] == ["Belo Horizonte"]


def test_antigo_vira_historico_e_nao_some(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "cidade", "value": "SP"}, ctx)
    registry.call("memory.save", {"kind": "profile", "key": "cidade", "value": "BH"}, ctx)
    total = ctx.conn.execute("SELECT COUNT(*) c FROM memory").fetchone()["c"]
    assert total == 2  # o antigo continua lá, apontando para o novo


def test_confidence_invalida_e_recusada(ctx, registry):
    assert not registry.call("memory.save", {"kind": "profile", "key": "x",
                                             "value": "y", "confidence": 2}, ctx).ok


def test_perfil_tem_teto(ctx, registry):
    """O perfil vai inteiro em todo prompt; sem teto ele vira uma conta crescente."""
    for i in range(LIMITE_PERFIL):
        registry.call("memory.save", {"kind": "profile", "key": f"k{i}", "value": "v"}, ctx)

    estourou = registry.call("memory.save", {"kind": "profile", "key": "nova",
                                             "value": "v"}, ctx)
    assert not estourou.ok
    assert "teto" in estourou.error
    # atualizar um fato existente continua valendo
    assert registry.call("memory.save", {"kind": "profile", "key": "k0", "value": "novo"},
                         ctx).ok


def test_episodic_nao_tem_teto(ctx, registry):
    for i in range(LIMITE_PERFIL + 5):
        assert registry.call("memory.save", {"kind": "episodic", "key": f"e{i}",
                                             "value": "v"}, ctx).ok


def test_esquecer_remove_do_vigente(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "cidade", "value": "SP"}, ctx)
    assert registry.call("memory.forget", {"key": "cidade"}, ctx).ok
    assert registry.call("memory.list", {}, ctx).data == []


def test_esquecer_o_que_nao_existe_falha(ctx, registry):
    assert not registry.call("memory.forget", {"key": "inexistente"}, ctx).ok


def test_busca_na_memoria(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "academia",
                                  "value": "treina de manhã cedo"}, ctx)
    registry.call("memory.save", {"kind": "profile", "key": "cafe",
                                  "value": "sem açúcar"}, ctx)
    achados = registry.call("memory.search", {"query": "academia treino"}, ctx).data
    assert achados[0]["key"] == "academia"


def test_memoria_privada_nao_vai_para_o_modelo(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "senha_cofre",
                                  "value": "1234", "private": True}, ctx)
    registry.call("memory.save", {"kind": "profile", "key": "cidade", "value": "SP"}, ctx)

    perfil = perfil_para_prompt(ctx.conn, ctx.config)
    assert "cidade" in perfil
    assert "1234" not in perfil and "senha_cofre" not in perfil

    achados = registry.call("memory.search", {"query": "senha cofre"}, ctx).data
    assert achados == []


def test_perfil_entra_no_prompt(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "academia",
                                  "value": "treina 6h"}, ctx)
    mensagens = build(ctx.config, [], conn=ctx.conn)
    assert any("treina 6h" in m.content for m in mensagens)


def test_sem_perfil_nao_polui_o_prompt(ctx):
    assert profile_prompt(ctx.conn, ctx.config) is None


def test_incerteza_e_marcada_no_prompt(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "aniversario",
                                  "value": "12 de maio", "confidence": 0.6}, ctx)
    assert "incerto" in perfil_para_prompt(ctx.conn, ctx.config)
