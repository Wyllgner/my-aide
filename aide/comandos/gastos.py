"""Controle de gastos."""

from __future__ import annotations

import typer
from rich.table import Table

from aide.channels import formato
from aide.comandos.base import _ctx, app, console
from aide.tools import registry
from aide.tools.expenses import PERIODOS, parse_lancamento, por_extenso


@app.command(rich_help_panel="Dinheiro")
def gasto(texto: str,
          categoria: str = typer.Option(None, "--categoria", "-c"),
          quando: str = typer.Option(None, "--quando", "-q", help="ISO 8601"),
          credito: bool = typer.Option(False, "--credito", help="Padrão: débito."),
          privado: bool = typer.Option(False, "--privado", "-p")) -> None:
    """Registra um gasto: myaide gasto "10,50 almoço com a KA"."""
    try:
        cents, descricao = parse_lancamento(texto)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    _, _, ctx = _ctx()
    args = {"amount": str(cents / 100), "description": descricao, "private": privado,
            "method": "credito" if credito else "debito"}
    if categoria:
        args["category"] = categoria
    if quando:
        args["when"] = quando

    resultado = registry.call("expenses.add", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)

    _ecoar(resultado.data)


def _ecoar(linha: dict) -> None:
    marca = f" [dim]{linha['category']}[/]" if linha["category"] else ""
    console.print(f"[green]#{linha['id']}[/] {linha['valor']} · {linha['description']}"
                  f"{marca} [dim]{por_extenso(linha['method'])}[/]")


@app.command(name="corrige-gasto", rich_help_panel="Dinheiro")
def corrige_gasto(gasto_id: int,
                  credito: bool = typer.Option(None, "--credito/--debito"),
                  valor: str = typer.Option(None, "--valor", "-v"),
                  descricao: str = typer.Option(None, "--descricao", "-d"),
                  categoria: str = typer.Option(None, "--categoria", "-c"),
                  quando: str = typer.Option(None, "--quando", "-q", help="ISO 8601")) -> None:
    """Corrige um gasto lançado: myaide corrige-gasto 12 --credito."""
    _, _, ctx = _ctx()
    args: dict = {"id": gasto_id}
    if credito is not None:
        args["method"] = "credito" if credito else "debito"
    for chave, valor_dado in (("amount", valor), ("description", descricao),
                              ("category", categoria), ("when", quando)):
        if valor_dado is not None:
            args[chave] = valor_dado

    resultado = registry.call("expenses.update", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)
    _ecoar(resultado.data)


@app.command(rich_help_panel="Dinheiro")
def gastos(periodo: str = typer.Argument("mes", help=" | ".join(PERIODOS)),
           categoria: str = typer.Option(None, "--categoria", "-c")) -> None:
    """Lista os gastos do período."""
    _, _, ctx = _ctx()
    args = {"periodo": periodo}
    if categoria:
        args["category"] = categoria

    resultado = registry.call("expenses.list", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)
    if not resultado.data:
        console.print("[dim]Nenhum gasto nesse período.[/]")
        return

    table = Table(box=None, padding=(0, 2, 0, 0))
    table.add_column("id", style="dim", justify="right")
    table.add_column("quando", style="dim")
    table.add_column("valor", justify="right")
    table.add_column("o quê")
    table.add_column("categoria", style="dim")
    table.add_column("forma", style="dim")

    for g in resultado.data:
        dia, _, hora = g["spent_at"].partition("T")
        table.add_row(str(g["id"]), f"{dia[8:10]}/{dia[5:7]} {hora[:5]}",
                      g["valor"], g["description"], g["category"] or "",
                      por_extenso(g["method"]))
    console.print(table)

    total = registry.call("expenses.summary", {k: v for k, v in args.items()}, ctx).data
    console.print(f"\n[bold]{total['total']}[/] em "
                  f"{formato.plural(total['quantos'], 'lançamento')}")


@app.command(rich_help_panel="Dinheiro")
def quanto(periodo: str = typer.Argument("mes", help=" | ".join(PERIODOS)),
           categoria: str = typer.Option(None, "--categoria", "-c")) -> None:
    """Quanto você gastou: myaide quanto mes."""
    _, _, ctx = _ctx()
    args = {"periodo": periodo}
    if categoria:
        args["category"] = categoria

    resultado = registry.call("expenses.summary", args, ctx)
    if not resultado.ok:
        console.print(f"[red]{resultado.error}[/]")
        raise typer.Exit(1)

    dados = resultado.data
    if not dados["quantos"]:
        console.print("[dim]Nenhum gasto nesse período.[/]")
        return

    console.print(f"[bold]{dados['total']}[/] · "
                  f"{formato.plural(dados['quantos'], 'lançamento')} "
                  f"· média {dados['media']}")
    console.print("[dim]" + " · ".join(f"{por_extenso(f['method'])} {f['valor']}"
                                       for f in dados["por_forma"]) + "[/]")

    if len(dados["por_categoria"]) > 1:
        maior = dados["por_categoria"][0]["cents"] or 1
        table = Table(box=None, padding=(0, 2, 0, 0), show_header=False)
        for c in dados["por_categoria"]:
            barra = "█" * max(1, round(12 * c["cents"] / maior))
            table.add_row(c["category"], c["valor"], f"[dim]{barra}[/]")
        console.print(table)
