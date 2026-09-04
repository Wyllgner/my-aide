import json

from aide.config import load_config
from aide.core.orchestrator import Orchestrator
from aide.llm.base import LLMProvider, LLMResponse
from aide.storage import connect, migrate
from aide.tools import registry as tool_registry


def _call(name, args, call_id="c1"):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class ScriptedLLM(LLMProvider):
    """Devolve respostas pré-programadas, uma por iteração do loop."""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def complete(self, messages, *, fast=False, tools=None, purpose="chat"):
        self.seen.append(messages[:])
        step = self.script.pop(0)
        if isinstance(step, str):
            return LLMResponse(text=step, model="fake")
        return LLMResponse(text="", model="fake", tool_calls=step)


def _agent(tmp_path, script, confirm=None):
    config = load_config()
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    llm = ScriptedLLM(script)
    agent = Orchestrator(config, conn, llm, registry=tool_registry, confirm=confirm)
    return agent, conn, llm


def test_executa_tool_e_responde(tmp_path):
    agent, conn, llm = _agent(tmp_path, [
        [_call("tasks_create", {"title": "Pagar IPVA"})],
        "Criei a tarefa.",
    ])
    assert agent.ask("me lembra do IPVA") == "Criei a tarefa."
    assert conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 1
    # o resultado da tool voltou para o modelo na segunda rodada
    assert any(m.role == "tool" for m in llm.seen[-1])


def test_erro_de_tool_volta_para_o_modelo(tmp_path):
    agent, _, llm = _agent(tmp_path, [
        [_call("tasks_complete", {"id": 999})],
        "Essa tarefa não existe.",
    ])
    agent.ask("conclui a 999")
    tool_msg = [m for m in llm.seen[-1] if m.role == "tool"][-1]
    payload = json.loads(tool_msg.content)
    assert payload["ok"] is False
    assert "não existe" in payload["error"]


def test_confirmacao_bloqueia_tool_perigosa(tmp_path):
    agent, conn, llm = _agent(tmp_path, [
        [_call("tasks_create", {"title": "X"})], [_call("tasks_drop", {"id": 1})], "Ok.",
    ], confirm=lambda name, args: False)
    agent.ask("descarta a X")
    tool_msg = [m for m in llm.seen[-1] if m.role == "tool"][-1]
    assert "não autorizou" in json.loads(tool_msg.content)["error"]
    assert conn.execute("SELECT status FROM tasks WHERE id = 1").fetchone()["status"] == "open"


def test_loop_tem_teto(tmp_path):
    script = [[_call("time_now", {})] for _ in range(30)]
    agent, _, llm = _agent(tmp_path, script)
    resposta = agent.ask("gira pra sempre")
    assert "voltas demais" in resposta
    assert len(llm.seen) == 8


def test_historico_nao_remonta_par_de_tool(tmp_path):
    agent, _, _ = _agent(tmp_path, [
        [_call("tasks_create", {"title": "A"})], "Criei.", "Oi.",
    ])
    agent.ask("cria A")
    agent.ask("e aí")
    roles = [m.role for m in agent.history()]
    assert "tool" not in roles
    assert roles == ["user", "assistant", "user", "assistant"]
