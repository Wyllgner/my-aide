"""As rotas de escrita da tela de gastos: o teto de um mês e os gastos fixos.

Passam pelas mesmas tools da conversa (`expenses.set_budget`,
`expenses.*_recurring`), e não por um INSERT próprio: a regra de "vale deste
mês em diante" e a recusa do teto zero moram lá, e duas portas para o mesmo dado acabariam dizendo coisas
diferentes. A fronteira de escrita (Host, Origin, `X-Aide`) é a de
`seguranca.py`, como em toda rota que não é GET.

Entram na auditoria com `actor="web"`, pela própria tool.
"""

from __future__ import annotations

ROTA_DO_TETO = "/api/gastos/teto"
ROTA_DOS_FIXOS = "/api/gastos/recorrentes"


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

    def chamar(tool: str, argumentos: dict) -> dict:
        # a mesma decisao da pagina (ver `contexto` em app.py): e o dono, e a tela
        # mostra o fixo privado, entao precisa poder muda-lo. Diferente da
        # pagina, aqui a auditoria fica ligada: isto e escrita
        ctx = ToolContext(config=config, conn=app.state.conn_factory(), actor="web",
                          ver_privado=True)
        resultado = registry.call(tool, argumentos, ctx)
        if not resultado.ok:
            raise HTTPException(400, resultado.error)
        return resultado.data

    @app.post(ROTA_DOS_FIXOS)
    def criar_fixo(descricao: str = Body(...), valor: str = Body(...), dia: str = Body(...),
                   categoria: str | None = Body(None), forma: str | None = Body(None)) -> dict:
        # o dia vem como texto do formulario, e quem recusa o que nao e dia e a tool
        argumentos = {"description": descricao, "amount": valor, "day": dia}
        if categoria:
            argumentos["category"] = categoria
        if forma:
            argumentos["method"] = forma
        return chamar("expenses.add_recurring", argumentos)

    @app.put(ROTA_DOS_FIXOS + "/{id}")
    def mudar_fixo(id: int, valor: str | None = Body(None), dia: str | None = Body(None)) -> dict:
        argumentos: dict = {"id": id}
        if valor:
            argumentos["amount"] = valor
        if dia:
            argumentos["day"] = dia
        return chamar("expenses.update_recurring", argumentos)

    @app.delete(ROTA_DOS_FIXOS + "/{id}")
    def encerrar_fixo(id: int) -> dict:
        return chamar("expenses.cancel_recurring", {"id": id})
