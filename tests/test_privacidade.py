"""O que é `private` não sai da máquina.

Esta é a promessa mais forte do projeto: marcar algo como privado significa que
nem a OpenAI nem um cliente MCP de terceiro veem aquilo. A promessa estava no
`ARQUITETURA.md` e era cumprida só em parte — `tasks.list`, `notes.list`,
`notes.read` e `memory.list` devolviam conteúdo privado inteiro.

O teste que importa aqui é o último: ele varre **todas** as tools registradas,
para a próxima a ser escrita não repetir o esquecimento.
"""

import pytest

from aide.tools.registry import ToolContext

SEGREDO = "TERAPIA-QUINTA-FEIRA"


@pytest.fixture
def dono(ctx, tmp_path):
    """O terminal do dono: vê tudo."""
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    return ToolContext(config=ctx.config, conn=ctx.conn, actor="cli", ver_privado=True)


@pytest.fixture
def modelo(ctx):
    """Tudo o mais — modelo, MCP, Telegram, GUI — no padrão, que é negar."""
    return ToolContext(config=ctx.config, conn=ctx.conn, actor="mcp")


@pytest.fixture
def com_segredos(dono, registry):
    registry.call("tasks.create", {"title": f"Tarefa {SEGREDO}", "private": True}, dono)
    registry.call("tasks.create", {"title": "Comprar pão"}, dono)
    registry.call("notes.create", {"title": f"Nota {SEGREDO}", "body": f"corpo {SEGREDO}",
                                   "private": True}, dono)
    registry.call("notes.create", {"title": "Pública", "body": "qualquer coisa"}, dono)
    registry.call("memory.save", {"kind": "profile", "key": "k",
                                  "value": f"perfil {SEGREDO}", "private": True}, dono)
    registry.call("memory.save", {"kind": "episodic", "key": "e",
                                  "value": f"episódio {SEGREDO}", "private": True}, dono)
    return dono


def test_padrao_do_contexto_e_negar(ctx):
    """Esquecer de passar o parâmetro tem de falhar fechado, não aberto."""
    assert ToolContext(config=ctx.config, conn=ctx.conn).ver_privado is False


def test_ver_privado_nao_e_argumento_de_tool(registry):
    """Se estivesse no schema, o próprio modelo poderia ligar."""
    for nome in registry.names():
        propriedades = registry.get(nome).parameters.get("properties", {})
        assert "ver_privado" not in propriedades, nome


def test_tarefa_privada_fica_fora_da_listagem(com_segredos, modelo, registry):
    titulos = [t["title"] for t in registry.call("tasks.list", {"filter": "all"}, modelo).data]
    assert titulos == ["Comprar pão"]


def test_nota_privada_fica_fora_da_listagem(com_segredos, modelo, registry):
    titulos = [n["title"] for n in registry.call("notes.list", {}, modelo).data]
    assert titulos == ["Pública"]


def test_nota_privada_nao_pode_ser_lida(com_segredos, modelo, registry):
    resultado = registry.call("notes.read", {"id": 1}, modelo)
    assert not resultado.ok
    assert "privada" in resultado.error
    assert SEGREDO not in resultado.error


def test_nota_privada_nao_pode_ser_escrita(com_segredos, modelo, registry):
    """Escrever também revelaria que ela existe."""
    assert not registry.call("notes.append", {"id": 1, "body": "x"}, modelo).ok


def test_memoria_privada_fica_fora(com_segredos, modelo, registry):
    for kind in ("profile", "episodic"):
        assert registry.call("memory.list", {"kind": kind}, modelo).data == []


def test_o_dono_continua_vendo_tudo(com_segredos, registry):
    """A privacidade é contra o que sai da máquina, não contra você."""
    titulos = [t["title"] for t in registry.call("tasks.list", {"filter": "all"},
                                                 com_segredos).data]
    assert f"Tarefa {SEGREDO}" in titulos
    assert registry.call("notes.read", {"id": 1}, com_segredos).ok
    assert registry.call("memory.list", {"kind": "profile"}, com_segredos).data


def test_o_snapshot_do_prompt_nao_leva_privado(com_segredos, ctx):
    from aide.core.context import build, state_snapshot

    snapshot = state_snapshot(ctx.conn, ctx.config)
    assert SEGREDO not in (snapshot.content if snapshot else "")

    prompt = "\n".join(m.content for m in build(ctx.config, [], conn=ctx.conn))
    assert SEGREDO not in prompt


def test_nenhuma_tool_devolve_conteudo_privado(com_segredos, modelo, registry):
    """A varredura: toda tool registrada, com os argumentos que ela aceita.

    É o que protege a tool que ainda não foi escrita — quem esquecer o filtro
    quebra aqui, não em produção.
    """
    argumentos = {
        "id": 1, "task_id": 1, "query": SEGREDO.lower(), "filter": "all",
        "kind": "profile", "name": "k", "key": "k", "status": "all",
        "limit": 50, "dias": 365, "text": "x", "goal": "x", "body": "x",
        "when": "2030-01-01T09:00", "value": "x",
    }

    vistos = []
    for nome in registry.names():
        tool = registry.get(nome)
        if tool.safety == "confirm":
            continue  # apagar não devolve conteúdo, e o teste não deve apagar
        aceitos = tool.parameters.get("properties", {})
        args = {k: v for k, v in argumentos.items() if k in aceitos}
        if set(tool.parameters.get("required", [])) - set(args):
            continue
        resultado = registry.call(nome, args, modelo)
        vistos.append(nome)
        assert SEGREDO not in resultado.to_json(), f"{nome} vazou conteúdo privado"

    # buscar pelo segredo e recebê-lo de volta seria o pior vazamento: é por
    # isso que `query` leva o próprio segredo em vez de um termo inócuo.
    for busca in ("notes.search", "memory.search"):
        assert busca in vistos

    # se a varredura parar de exercitar as tools, ela deixa de valer
    assert len(vistos) >= 10


# ---------- o que vai parar no journal ----------

def test_conversa_nao_vaza_para_o_log_em_info(ctx, registry, caplog):
    """O daemon roda sob systemd: o que sai em INFO vira cópia no journal.

    Fora do banco 0600, sem passar pela marca de `private` e com outra política
    de retenção. Em INFO fica o suficiente para acompanhar o serviço.
    """
    import logging

    from aide.core.orchestrator import Orchestrator
    from aide.llm.base import LLMProvider, LLMResponse

    class LLMMudo(LLMProvider):
        def complete(self, messages, *, fast=False, tools=None, purpose="chat"):
            return LLMResponse(text=f"anotei: {SEGREDO}", model="fake")

    agente = Orchestrator(ctx.config, ctx.conn, LLMMudo(), actor="test")

    with caplog.at_level(logging.INFO, logger="aide.core.orchestrator"):
        agente.ask(f"me lembra de {SEGREDO}")
    assert SEGREDO not in caplog.text
    assert "mensagem recebida" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="aide.core.orchestrator"):
        agente.ask(f"me lembra de {SEGREDO}")
    assert SEGREDO in caplog.text, "em DEBUG o conteúdo precisa continuar disponível"


def test_trilha_de_auditoria_continua_completa(com_segredos, registry):
    """A trilha detalhada não some — ela vai para dentro do banco fechado."""
    linhas = com_segredos.conn.execute(
        "SELECT tool, args_json FROM audit ORDER BY id").fetchall()
    assert any(SEGREDO in (r["args_json"] or "") for r in linhas)
