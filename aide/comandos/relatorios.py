"""O que o assessor está vendo: regras, estado, histórico e custo."""

from __future__ import annotations

import typer
from rich.table import Table

from aide import __version__
from aide.comandos.base import _open_db, app, console, now_in
from aide.scheduler import rules


@app.command()
def checar() -> None:
    """Mostra o que as regras de condição estão vendo agora."""
    config, conn = _open_db()
    achados = rules.evaluate(conn, now_in(config.timezone))
    if not achados:
        console.print("[green]Nada pedindo atenção.[/]")
        return

    cores = {1: "red", 2: "yellow", 3: "dim"}
    table = Table(box=None, show_header=False)
    for f in achados:
        table.add_row(f"[{cores[f.severity]}]{f.rule}[/]", f.summary)
    console.print(table)


@app.command()
def status() -> None:
    """Um retrato do assessor: o que ele guarda, o que cobra, quanto custa."""
    from datetime import datetime

    config, conn = _open_db()

    def um(sql, p=()):
        linha = conn.execute(sql, p).fetchone()
        return linha[0] if linha else 0

    momento = now_in(config.timezone)
    agora = momento.isoformat(timespec="minutes")
    hoje = momento.replace(hour=23, minute=59).isoformat(timespec="minutes")

    estado = Table(title="Estado", box=None, title_justify="left", show_header=False)
    estado.add_column(justify="right", style="dim")
    estado.add_column()
    estado.add_row(str(um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL"
                          " AND status='open'")), "tarefas abertas")
    atrasadas = um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL AND status='open'"
                   " AND due_at IS NOT NULL AND due_at < ?", (agora,))
    estado.add_row(f"[red]{atrasadas}[/]" if atrasadas else "0", "atrasadas")
    estado.add_row(str(um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL"
                          " AND status='open' AND due_at <= ?", (hoje,))), "vencem hoje")
    estado.add_row(str(um("SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL")), "notas")
    estado.add_row(str(um("SELECT COUNT(*) FROM memory WHERE kind='profile'"
                          " AND superseded_by IS NULL")), "fatos no perfil")
    estado.add_row(str(um("SELECT COUNT(*) FROM people")), "pessoas acompanhadas")
    estado.add_row(str(um("SELECT COUNT(*) FROM work_orders WHERE status='open'")),
                   "na fila de trabalho")
    estado.add_row(str(um("SELECT COUNT(*) FROM reminders WHERE status='pending'")),
                   "lembretes pendentes")
    console.print(estado)

    achados = rules.evaluate(conn, momento)
    if achados:
        console.print()
        pedindo = Table(title="Pedindo atenção", box=None, title_justify="left",
                        show_header=False)
        cores = {1: "red", 2: "yellow", 3: "dim"}
        for f in achados[:8]:
            pedindo.add_row(f"[{cores[f.severity]}]•[/]", f.summary)
        console.print(pedindo)

    console.print()
    custo = Table(title="Custo — 30 dias", box=None, title_justify="left")
    for coluna in ("modelo", "chamadas", "entrada", "saída", "US$"):
        custo.add_column(coluna, justify="right" if coluna != "modelo" else "left")

    linhas = conn.execute(
        "SELECT model, COUNT(*) n, SUM(input_tokens) i, SUM(output_tokens) o"
        "  FROM llm_usage WHERE ts >= datetime('now','-30 days')"
        " GROUP BY model ORDER BY i + o DESC"
    ).fetchall()

    total = 0.0
    sem_preco = []
    for r in linhas:
        preco = config.llm.precos.get(r["model"])
        if preco:
            valor = r["i"] / 1e6 * preco[0] + r["o"] / 1e6 * preco[1]
            total += valor
            texto = f"{valor:.4f}"
        else:
            sem_preco.append(r["model"])
            texto = "[dim]?[/]"
        custo.add_row(r["model"], str(r["n"]), f"{r['i']:,}", f"{r['o']:,}", texto)

    if linhas:
        custo.add_row("", "", "", "[bold]total[/]", f"[bold]{total:.4f}[/]")
        console.print(custo)
        if sem_preco:
            console.print(f"[dim]sem preço em config.yaml: {', '.join(sem_preco)}[/]")
    else:
        console.print("[dim]Nenhuma chamada de LLM em 30 dias.[/]")

    ultimo = conn.execute(
        "SELECT ts FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    if ultimo:
        quando = datetime.fromisoformat(ultimo["ts"]).replace(tzinfo=momento.tzinfo)
        console.print(f"\n[dim]última atividade: {quando.strftime('%d/%m %H:%M')} · "
                      f"banco {config.db_path.stat().st_size // 1024} KB[/]")


@app.command()
def historico(limite: int = typer.Option(15, "--limite", "-n"),
              canal: str = typer.Option(None, "--canal", "-c",
                                        help="cli | telegram")) -> None:
    """Mostra as últimas conversas e as tools que foram chamadas."""
    _, conn = _open_db()

    sql = ("SELECT id, session_id, role, content, tool_calls, created_at"
           "  FROM messages WHERE role IN ('user', 'assistant')")
    params: list = []
    if canal == "telegram":
        sql += " AND session_id LIKE 'tg%'"
    elif canal == "cli":
        sql += " AND session_id NOT LIKE 'tg%'"
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)

    linhas = list(reversed(conn.execute(sql, params).fetchall()))
    if not linhas:
        console.print("[dim]Nada no histórico.[/]")
        return

    for m in linhas:
        cor = "cyan" if m["role"] == "user" else "green"
        seta = "›" if m["role"] == "user" else "‹"
        origem = "tg" if m["session_id"].startswith("tg") else "cli"
        texto = (m["content"] or "").strip() or "[dim](chamou tools)[/]"
        console.print(f"[dim]{m['created_at']} {origem}[/] [{cor}]{seta}[/] {texto}")

    console.print("\n[dim]tools chamadas recentemente:[/]")
    for a in conn.execute(
        "SELECT ts, actor, tool, args_json, ok FROM audit ORDER BY id DESC LIMIT ?",
        (limite,),
    ).fetchall():
        marca = "[green]ok[/]" if a["ok"] else "[red]erro[/]"
        console.print(f"[dim]{a['ts']} {a['actor']}[/] {marca} "
                      f"[cyan]{a['tool']}[/] [dim]{a['args_json']}[/]")


@app.command()
def usage(days: int = 7) -> None:
    """Quanto o assessor consumiu de LLM nos últimos dias."""
    _, conn = _open_db()
    rows = conn.execute(
        "SELECT model, purpose, COUNT(*) n,"
        "       SUM(input_tokens) inp, SUM(output_tokens) outp"
        "  FROM llm_usage WHERE ts >= datetime('now', ?)"
        " GROUP BY model, purpose ORDER BY inp + outp DESC",
        (f"-{days} days",),
    ).fetchall()

    if not rows:
        console.print("[dim]Nenhuma chamada registrada.[/]")
        return

    table = Table(title=f"Uso de LLM — {days} dias", box=None)
    for col in ("modelo", "uso", "chamadas", "entrada", "saída"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["model"], r["purpose"] or "-", str(r["n"]), str(r["inp"]), str(r["outp"]))
    console.print(table)


@app.command()
def version() -> None:
    """Mostra a versão."""
    console.print(__version__)


if __name__ == "__main__":
    app()
