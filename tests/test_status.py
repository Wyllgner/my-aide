"""Custo estimado a partir dos preços do config."""


def test_precos_do_config_viram_custo(ctx):
    """Preço fica em config: muda de tempos em tempos e não deve virar código."""
    object.__setattr__(ctx.config.llm, "precos", {"m": (2.0, 8.0)})
    ctx.conn.execute(
        "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
        " VALUES ('m', 'chat', 1000000, 1000000)")

    linha = ctx.conn.execute(
        "SELECT SUM(input_tokens) i, SUM(output_tokens) o FROM llm_usage").fetchone()
    entrada, saida = ctx.config.llm.precos["m"]
    assert linha["i"] / 1e6 * entrada + linha["o"] / 1e6 * saida == 10.0


def test_modelo_sem_preco_nao_quebra_a_conta(ctx):
    """Trocar de modelo sem atualizar o config não pode derrubar o comando."""
    object.__setattr__(ctx.config.llm, "precos", {})
    assert ctx.config.llm.precos.get("desconhecido") is None
