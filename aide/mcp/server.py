"""Servidor MCP: expõe o toolbelt para executores externos.

Adaptador fino, de propósito. Ele não decide nada — lê o mesmo `registry.py`
que o loop interno usa, então uma tool nova aparece aqui sem escrever código.

Roda por stdio, iniciado pelo cliente (Claude Desktop, Cowork e afins).
Só a sessão local alcança este banco; ver ARQUITETURA.md seção 2.
"""

from __future__ import annotations

import logging
import sys

from aide.config import load_config
from aide.storage import connect, migrate
from aide.tools import registry as tool_registry
from aide.tools.registry import ToolContext

log = logging.getLogger(__name__)

# Tools marcadas 'confirm' exigem um "tem certeza?" que não existe por MCP:
# o cliente do outro lado não é a pessoa. Ficam de fora.
EXPOR_CONFIRM = False


def _descricao(tool) -> str:
    return tool.description


def tools_expostas(registry=tool_registry) -> list:
    return [
        registry.get(nome)
        for nome in registry.names()
        if EXPOR_CONFIRM or registry.get(nome).safety == "safe"
    ]


def build_server(config=None, conn=None, registry=tool_registry, embedder=None):
    """Monta o servidor. Recebe as dependências para poder ser testado.

    A API do SDK 2.x recebe os handlers no construtor; nada de decorador.
    """
    from mcp import types
    from mcp.server import Server

    config = config or load_config()
    if conn is None:
        conn = connect(config.db_path)
        migrate(conn)

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[
            types.Tool(
                name=tool.api_name,
                description=_descricao(tool),
                input_schema=tool.parameters,
            )
            for tool in tools_expostas(registry)
        ])

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        tool = registry.get(params.name)
        if tool is None or (not EXPOR_CONFIRM and tool.safety != "safe"):
            # não existe, ou existe mas não é exposta — a resposta é a mesma
            return types.CallToolResult(
                content=[types.TextContent(
                    type="text",
                    text=f'{{"ok": false, "error": "tool indisponível: {params.name}"}}',
                )],
                is_error=True,
            )

        tool_ctx = ToolContext(config=config, conn=conn, actor="mcp", embedder=embedder)
        resultado = registry.call(tool.name, params.arguments or {}, tool_ctx)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=resultado.to_json())],
            is_error=not resultado.ok,
        )

    return Server(
        "my-aide",
        version="0.1.0",
        instructions=(
            "Assessor pessoal local. Tem as tarefas, notas, memória e a fila de "
            "trabalho do usuário. Comece por work_orders_list para ver o que "
            "ficou pendente esperando por você."
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _rodar() -> None:
    from mcp.server.stdio import stdio_server

    config = load_config()
    conn = connect(config.db_path)
    migrate(conn)

    embedder = None
    if config.llm.api_key:
        try:
            from aide.core.orchestrator import record_usage
            from aide.llm.embeddings import Embedder

            embedder = Embedder(config, usage_sink=record_usage(conn))
        except Exception:  # noqa: BLE001 - sem embedder a busca ainda funciona
            log.warning("sem embedder; busca só por palavra-chave")

    servidor = build_server(config, conn, embedder=embedder)
    async with stdio_server() as (leitura, escrita):
        await servidor.run(leitura, escrita, servidor.create_initialization_options())


def main() -> None:
    import asyncio

    # stdout é o canal do protocolo: qualquer print quebra a conversa
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_rodar())


if __name__ == "__main__":
    main()
