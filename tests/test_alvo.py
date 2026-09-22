"""O que vai ser apagado, em palavras.

Uma confirmação que diz `notes.delete {'id': 7}` não é confirmação: para
responder "sim" com consciência é preciso saber o que é o 7.
"""

from aide.tools import alvo


def test_tarefa_e_descrita_pelo_titulo(ctx, registry):
    tarefa = registry.call("tasks.create", {"title": "Pagar o IPVA"}, ctx).data
    frase = alvo.descrever(ctx.conn, "tasks.drop", {"id": tarefa["id"]}, ver_privado=True)
    assert "Pagar o IPVA" in frase
    assert f"#{tarefa['id']}" in frase


def test_gasto_traz_o_valor_junto(ctx, registry):
    gasto = registry.call("expenses.add", {"amount": "10,50", "description": "almoço"}, ctx).data
    frase = alvo.descrever(ctx.conn, "expenses.delete", {"id": gasto["id"]}, ver_privado=True)
    assert "almoço" in frase
    assert "R$ 10,50" in frase


def test_nota_privada_nao_tem_o_titulo_revelado(ctx, registry, tmp_path):
    """A pergunta vai para onde o pedido veio, e no Telegram isso é rede de
    terceiro: o título de uma nota privada não pode sair por ali."""
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    nota = registry.call("notes.create", {"title": "Senha do cofre", "body": "x",
                                          "private": True}, ctx).data

    escondido = alvo.descrever(ctx.conn, "notes.delete", {"id": nota["id"]}, ver_privado=False)
    assert "Senha" not in escondido
    assert "privada" in escondido
    assert f"#{nota['id']}" in escondido

    # no terminal do dono, o título aparece
    aberto = alvo.descrever(ctx.conn, "notes.delete", {"id": nota["id"]}, ver_privado=True)
    assert "Senha do cofre" in aberto


def test_memoria_diz_o_que_estava_guardado(ctx, registry):
    registry.call("memory.save", {"kind": "profile", "key": "cidade",
                                  "value": "Porto Velho"}, ctx)
    frase = alvo.descrever(ctx.conn, "memory.forget", {"key": "cidade"}, ver_privado=True)
    assert "cidade" in frase and "Porto Velho" in frase


def test_pessoa_e_descrita_pelo_nome(ctx, registry):
    registry.call("people.add", {"name": "Pedro"}, ctx)
    assert "Pedro" in alvo.descrever(ctx.conn, "people.remove", {"name": "Pedro"})


def test_alvo_que_nao_existe_mais_e_dito_assim(ctx):
    frase = alvo.descrever(ctx.conn, "tasks.drop", {"id": 999}, ver_privado=True)
    assert "não existe mais" in frase


def test_tool_sem_descricao_mostra_o_que_da(ctx):
    """Tool nova marcada `confirm` sem entrada no mapa: cru é melhor que
    silenciosamente errado."""
    assert "xpto.delete" in alvo.descrever(ctx.conn, "xpto.delete", {"id": 3})


def test_o_verbo_acompanha_a_acao(ctx):
    assert alvo.verbo("memory.forget") == "esquecer"
    assert alvo.verbo("people.remove") == "parar de acompanhar"
    assert alvo.verbo("notes.delete") == "apagar"


# ---------- o nome chega com sublinhado ----------

def test_aceita_o_nome_que_o_modelo_devolve(ctx, registry):
    """A OpenAI não aceita ponto em nome de tool, então o que chega pela
    confirmação é `notes_delete`. Com o mapa só em ponto, toda pergunta caía no
    formato cru: "Quer mesmo apagar notes_delete {'id': 7}?"."""
    tarefa = registry.call("tasks.create", {"title": "Pagar o IPVA"}, ctx).data

    com_sublinhado = alvo.descrever(ctx.conn, "tasks_drop", {"id": tarefa["id"]},
                                    ver_privado=True)
    com_ponto = alvo.descrever(ctx.conn, "tasks.drop", {"id": tarefa["id"]}, ver_privado=True)
    assert com_sublinhado == com_ponto
    assert "Pagar o IPVA" in com_sublinhado


def test_o_verbo_tambem_aceita_sublinhado(ctx):
    assert alvo.verbo("memory_forget") == "esquecer"
    assert alvo.verbo("people_remove") == "parar de acompanhar"


def test_memoria_e_gasto_tambem(ctx, registry, tmp_path):
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("memory.save", {"kind": "profile", "key": "cidade",
                                  "value": "Porto Velho"}, ctx)
    gasto = registry.call("expenses.add", {"amount": "10,50", "description": "almoço"}, ctx).data

    assert "Porto Velho" in alvo.descrever(ctx.conn, "memory_forget", {"key": "cidade"},
                                           ver_privado=True)
    assert "almoço" in alvo.descrever(ctx.conn, "expenses_delete", {"id": gasto["id"]},
                                      ver_privado=True)


def test_tool_desconhecida_com_sublinhado_nao_e_traduzida_errado(ctx):
    """`xpto_delete` não existe no registro: melhor mostrar cru do que inventar."""
    frase = alvo.descrever(ctx.conn, "xpto_delete", {"id": 3})
    assert "xpto_delete" in frase
