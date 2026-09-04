"""O servidor MCP é adaptador: não decide nada, só traduz o registry."""

import asyncio

import pytest

from aide.mcp.server import build_server, tools_expostas
from aide.tools import registry as tool_registry


def _chamar(servidor, metodo, params):
    from mcp.server import ServerRequestContext

    handler = getattr(servidor, metodo)
    return asyncio.run(handler(ServerRequestContext, params))


@pytest.fixture
def servidor(ctx):
    return build_server(config=ctx.config, conn=ctx.conn, registry=tool_registry)


def test_expoe_apenas_tools_seguras():
    """Uma tool 'confirm' precisa de um humano confirmando; por MCP não há um."""
    nomes = {t.name for t in tools_expostas()}
    assert "tasks.create" in nomes
    assert "tasks.drop" not in nomes
    assert "notes.delete" not in nomes
    assert "memory.forget" not in nomes


def test_nomes_expostos_sao_validos_no_protocolo():
    import re

    for tool in tools_expostas():
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", tool.api_name)


def test_toda_tool_exposta_tem_descricao_e_schema():
    for tool in tools_expostas():
        assert tool.description.strip()
        assert tool.parameters.get("type") == "object"


def test_registry_novo_aparece_sem_codigo_novo():
    """O adaptador lê o registry: tool nova entra sozinha."""
    from aide.tools.registry import Registry

    outro = Registry()

    @outro.register(name="x.ping", description="ping", parameters={
        "type": "object", "properties": {}, "required": []})
    def _ping(ctx):
        return "pong"

    assert [t.api_name for t in tools_expostas(outro)] == ["x_ping"]


def test_servidor_declara_identidade(servidor):
    assert servidor.server_info.name == "my-aide"


def test_tool_confirm_e_recusada_pelo_mesmo_caminho():
    """Mesmo que o cliente adivinhe o nome, a tool não é exposta."""
    assert "tasks_drop" not in {t.api_name for t in tools_expostas()}


@pytest.mark.slow
def test_protocolo_de_ponta_a_ponta(tmp_path):
    """Sobe o servidor de verdade e conversa JSON-RPC por stdio.

    Vale o custo: é o único teste que prova que um cliente MCC externo
    consegue mesmo falar com o assessor.
    """
    import json
    import os
    import subprocess
    import sys

    # AIDE_ROOT isola o teste: banco e config próprios, longe dos dados reais
    (tmp_path / "config.yaml").write_text("timezone: America/Sao_Paulo\n")
    (tmp_path / ".env").write_text("")
    ambiente = {**os.environ, "AIDE_ROOT": str(tmp_path), "OPENAI_API_KEY": "",
                "PYTHONPATH": os.getcwd()}
    proc = subprocess.Popen(
        [sys.executable, "-m", "aide.mcp.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, env=ambiente,
    )

    def rpc(msg, espera=True):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline()) if espera else None

    try:
        inicio = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"}}})
        assert inicio["result"]["serverInfo"]["name"] == "my-aide"

        rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, espera=False)

        listagem = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        nomes = [t["name"] for t in listagem["result"]["tools"]]
        assert "work_orders_list" in nomes
        assert "tasks_drop" not in nomes

        chamada = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "tasks_list", "arguments": {"filter": "all"}}})
        assert json.loads(chamada["result"]["content"][0]["text"])["ok"] is True

        negada = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                      "params": {"name": "tasks_drop", "arguments": {"id": 1}}})
        assert "indisponível" in negada["result"]["content"][0]["text"]
    finally:
        proc.terminate()
        proc.wait(timeout=10)
