"""A rota de escrita da tela de gastos: mudar o teto de um mês.

Passa pela mesma tool da conversa (`expenses.set_budget`), e não por um
INSERT próprio: a regra de "vale deste mês em diante" e a recusa do teto zero
moram lá, e duas portas para o mesmo dado acabariam dizendo coisas
diferentes. A fronteira de escrita (Host, Origin, `X-Aide`) é a de
`seguranca.py`, como em toda rota que não é GET.

Entra na auditoria com `actor="web"`, pela própria tool.
"""

from __future__ import annotations

ROTA_DO_TETO = "/api/gastos/teto"


def instalar(app) -> None:
    from fastapi import Body, HTTPException

    from aide.tools import registry
    from aide.tools.registry import ToolContext

    config = app.state.config

    @app.put(ROTA_DO_TETO)
    def mudar_teto(categoria: str = Body(...), mes: str = Body(...),
                   valor: str | None = Body(None), remover: bool = Body(False)) -> dict:
        # o teto nao revela gasto nenhum: ver_privado fica no padrao, falso
        ctx = ToolContext(config=config, conn=app.state.conn_factory(), actor="web")
        argumentos = {"category": categoria, "month": mes, "remove": remover}
        if valor is not None:
            argumentos["amount"] = valor
        resultado = registry.call("expenses.set_budget", argumentos, ctx)
        if not resultado.ok:
            raise HTTPException(400, resultado.error)
        return resultado.data
