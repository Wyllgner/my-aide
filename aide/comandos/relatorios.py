"""O que o assessor está vendo: regras, estado, histórico e custo."""

from __future__ import annotations

from datetime import timedelta

import typer
from rich.table import Table

from aide import __version__
from aide.channels import formato
from aide.comandos.base import _open_db, app, console, now_in
from aide.scheduler import rules


@app.command(rich_help_panel="Diagnóstico")
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


@app.command(rich_help_panel="Diagnóstico")
def status() -> None:
    """Um retrato do assessor: o que ele guarda, o que cobra, quanto custa."""
    config, conn = _open_db()

    def um(sql, p=()):
        linha = conn.execute(sql, p).fetchone()
        return linha[0] if linha else 0

    momento = now_in(config.timezone)
    agora = momento.isoformat(timespec="minutes")
    # Só o que vence de hoje para a frente: com `due_at <= fim_do_dia` toda
    # tarefa atrasada entrava aqui também, e o retrato dizia "2 atrasadas, 2
    # vencem hoje" sobre as mesmas duas tarefas.
    inicio_do_dia = momento.replace(hour=0, minute=0).isoformat(timespec="minutes")
    fim_do_dia = momento.replace(hour=23, minute=59).isoformat(timespec="minutes")

    estado = Table(title="Estado", box=None, title_justify="left", show_header=False)
    estado.add_column(justify="right", style="dim")
    estado.add_column()
    estado.add_row(str(um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL"
                          " AND status='open'")), "tarefas abertas")
    atrasadas = um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL AND status='open'"
                   " AND due_at IS NOT NULL AND due_at < ?", (agora,))
    estado.add_row(f"[red]{atrasadas}[/]" if atrasadas else "0", "atrasadas")
    estado.add_row(str(um("SELECT COUNT(*) FROM tasks WHERE deleted_at IS NULL"
                          " AND status='open' AND due_at BETWEEN ? AND ?",
                          (inicio_do_dia, fim_do_dia))), "vencem hoje")
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
            texto = formato.decimal(valor)
        else:
            sem_preco.append(r["model"])
            texto = "[dim]?[/]"
        custo.add_row(r["model"], formato.numero(r["n"]), formato.numero(r["i"]),
                      formato.numero(r["o"]), texto)

    if linhas:
        custo.add_row("", "", "", "[bold]total[/]", f"[bold]{formato.decimal(total)}[/]")
        console.print(custo)
        if sem_preco:
            console.print(f"[dim]sem preço em config.yaml: {', '.join(sem_preco)}[/]")
    else:
        console.print("[dim]Nenhuma chamada de LLM em 30 dias.[/]")

    ultimo = conn.execute(
        "SELECT ts FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    if ultimo:
        # o carimbo do audit é UTC; sem converter, a atividade das 20:29 de
        # hoje aparecia como 00:29 de amanhã
        quando = formato.de_utc(ultimo["ts"], momento) or momento
        console.print(f"\n[dim]última atividade: {quando.strftime('%d/%m %H:%M')} · "
                      f"banco {config.db_path.stat().st_size // 1024} KB[/]")


@app.command(rich_help_panel="Diagnóstico")
def historico(limite: int = typer.Option(15, "--limite", "-n"),
              canal: str = typer.Option(None, "--canal", "-c",
                                        help="cli | telegram")) -> None:
    """Mostra as últimas conversas e as tools que foram chamadas."""
    config, conn = _open_db()
    agora = now_in(config.timezone)

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

    # A data inteira em cada linha é ruído: numa conversa ela se repete dezenas
    # de vezes e a hora, que é o que muda, fica no meio do carimbo. O dia vira
    # cabeçalho e a linha mostra só a hora — daqui, não de Londres.
    dia_impresso = None
    for m in linhas:
        cor = "cyan" if m["role"] == "user" else "green"
        seta = "›" if m["role"] == "user" else "‹"
        origem = "tg" if m["session_id"].startswith("tg") else "cli"
        texto = (m["content"] or "").strip() or "[dim](chamou tools)[/]"
        quando = formato.de_utc(m["created_at"], agora)
        dia = quando.date() if quando else None
        if dia != dia_impresso:
            cabecalho = formato.por_extenso(quando) if quando else "sem data"
            relativo = formato.data_curta(quando.isoformat(), agora) if quando else ""
            console.print(f"\n[bold]{cabecalho}[/]"
                          + (f" [dim]({relativo})[/]" if relativo else ""))
            dia_impresso = dia
        hora = quando.strftime("%H:%M") if quando else "--:--"
        console.print(f"[dim]{hora} {origem:>3}[/] [{cor}]{seta}[/] {texto}")

    console.print("\n[dim]tools chamadas recentemente:[/]")
    for a in conn.execute(
        "SELECT ts, actor, tool, args_json, ok FROM audit ORDER BY id DESC LIMIT ?",
        (limite,),
    ).fetchall():
        marca = "[green]ok[/]" if a["ok"] else "[red]erro[/]"
        quando = formato.de_utc(a["ts"], agora)
        console.print(f"[dim]{quando.strftime('%d/%m %H:%M') if quando else a['ts']} "
                      f"{a['actor']}[/] {marca} "
                      f"[cyan]{a['tool']}[/] [dim]{a['args_json']}[/]")


@app.command(rich_help_panel="Custo da LLM")
def usage(days: int = 7) -> None:
    """Quanto o assessor consumiu de LLM nos últimos dias."""
    config, conn = _open_db()
    rows = conn.execute(
        "SELECT model, purpose, COUNT(*) n,"
        "       SUM(input_tokens) inp, SUM(output_tokens) outp"
        "  FROM llm_usage WHERE ts >= datetime('now', ?)"
        " GROUP BY model, purpose ORDER BY inp + outp DESC",
        (f"-{days} days",),
    ).fetchall()

    if not rows:
        console.print(f"[dim]Nenhuma chamada de LLM em {formato.plural(days, 'dia')}.[/]")
        return

    table = Table(title=f"Uso de LLM — {formato.plural(days, 'dia')}", box=None,
                  title_justify="left")
    # número à direita: coluna de dígito só fica comparável alinhada pela
    # unidade, e sem isso "1" e "595117" começavam no mesmo ponto
    table.add_column("modelo")
    table.add_column("para quê")
    for col in ("chamadas", "entrada", "saída", "US$"):
        table.add_column(col, justify="right")

    total = 0.0
    for r in rows:
        preco = config.llm.precos.get(r["model"])
        if preco:
            valor = r["inp"] / 1e6 * preco[0] + r["outp"] / 1e6 * preco[1]
            total += valor
            usd = formato.decimal(valor)
        else:
            usd = "[dim]sem preço[/]"
        table.add_row(r["model"], r["purpose"] or "—", formato.numero(r["n"]),
                      formato.numero(r["inp"]), formato.numero(r["outp"]), usd)
    # a pergunta que se faz olhando uso é quanto ele custou; sem esta coluna
    # a resposta exigia abrir outro comando e cruzar à mão
    table.add_row("", "", "", "", "[bold]total[/]", f"[bold]{formato.decimal(total)}[/]")
    console.print(table)


@app.command(rich_help_panel="Instalação")
def version() -> None:
    """Mostra a versão."""
    console.print(__version__)


if __name__ == "__main__":
    app()


@app.command(rich_help_panel="Custo da LLM")
def custo(dias: int = typer.Option(0, "--dias", "-d",
                                   help="Janela em dias. Padrão: mês corrente.")) -> None:
    """Quanto o assessor está custando, e quanto ainda cabe no mês.

    Saldo da conta não aparece aqui porque a OpenAI não expõe por API: os
    endpoints de billing exigem a sessão do navegador. O que dá para saber é
    quanto foi gasto — e, contra o orçamento do config.yaml, quanto sobra.
    """
    from aide.llm import custo as calculo

    config, conn = _open_db()
    agora = now_in(config.timezone)

    if dias:
        gasto = calculo.estimar(conn, config, dias=dias)
        desde = agora - timedelta(days=dias)
        titulo = f"Custo — {dias} dias"
    else:
        gasto = calculo.mes_corrente(conn, config, agora)
        desde = agora.replace(day=1, hour=0, minute=0)
        titulo = f"Custo — desde {gasto.desde}"

    gasto = calculo.com_custo_real(gasto, config, desde)

    if not gasto.chamadas:
        console.print("[dim]Nenhuma chamada registrada nesse período.[/]")
        return

    tabela = Table(title=titulo, box=None, title_justify="left")
    for coluna in ("modelo", "chamadas", "entrada", "saída", "US$"):
        tabela.add_column(coluna, justify="left" if coluna == "modelo" else "right")
    for m in gasto.por_modelo:
        tabela.add_row(m["model"], formato.numero(m["chamadas"]),
                       formato.numero(m["entrada"]), formato.numero(m["saida"]),
                       formato.decimal(m["usd"]) if m["usd"] is not None
                       else "[yellow]sem preço[/]")
    tabela.add_row("", "", "", "[dim]estimado[/]",
                   f"[bold]{formato.decimal(gasto.estimado_usd)}[/]")
    console.print(tabela)

    if gasto.sem_preco:
        console.print(f"[yellow]sem preço em config.yaml:[/] {', '.join(gasto.sem_preco)}")

    if gasto.real_usd is not None:
        console.print(f"\n[bold]{formato.dolar(gasto.real_usd)}[/] cobrados pela OpenAI "
                      f"[dim](real, não estimativa)[/]")
    elif gasto.erro_real:
        console.print(f"\n[yellow]custo real indisponível:[/] {gasto.erro_real}")

    # o saldo ancorado responde melhor "quanto ainda tenho" do que um teto
    # inventado, então ele vem primeiro quando existe
    estimado = calculo.saldo_estimado(conn, config)
    if estimado is not None:
        console.print()
        _mostrar_saldo(estimado)
        return

    sobra = calculo.restante(gasto, config.llm.orcamento_mensal_usd)
    if sobra is None:
        console.print("\n[dim]Anote o saldo do painel com [/][bold]myaide saldo 4.22[/]"
                      "[dim] para acompanhar quanto ainda resta.[/]")
        return

    console.print()
    console.print(_barra(sobra["fracao"], "do orçamento do mês"))
    fonte = "estimado" if sobra["estimado"] else "real"
    console.print(f"[bold]{formato.dolar(sobra['sobra'], casas=2)}[/] ainda cabem "
                  f"nos {formato.dolar(sobra['orcamento'], casas=2)} do mês "
                  f"[dim]({fonte})[/]")


@app.command(rich_help_panel="Custo da LLM")
def saldo(valor: str = typer.Argument(None, help='O que o painel da OpenAI mostra, ex. "4.22"')) -> None:
    """Anota o saldo da API, ou mostra o estimado.

    A OpenAI não expõe saldo por API — os endpoints de billing exigem a sessão
    do navegador. Então você lê no painel, anota aqui, e o assessor desconta o
    gasto a partir daí.
    """
    from aide.llm import custo as calculo

    config, conn = _open_db()
    agora = now_in(config.timezone)

    if valor:
        from aide.tools.expenses import parse_valor

        try:
            usd = parse_valor(valor) / 100
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc
        calculo.anotar_saldo(conn, usd, agora.isoformat(timespec="minutes"))
        console.print(f"[green]anotado[/] {formato.dolar(usd, casas=2)} em "
                      f"{agora.strftime('%d/%m %H:%M')}")
        return

    estimado = calculo.saldo_estimado(conn, config)
    if estimado is None:
        console.print("[dim]Nenhum saldo anotado ainda.[/]\n"
                      "Veja em platform.openai.com > Settings > Billing e rode:\n"
                      "  [bold]myaide saldo 4.22[/]")
        return

    _mostrar_saldo(estimado)


def _barra(fracao: float, do_que: str, largura: int = 24) -> str:
    """Barra com legenda. Sem dizer o que ela mede, a barra é enfeite: quem lê
    não sabe se o cheio é o que sobrou ou o que já foi."""
    fracao = max(0.0, min(1.0, fracao))
    cheio = round(largura * fracao)
    cor = "red" if fracao >= 0.9 else "yellow" if fracao >= 0.7 else "green"
    return (f"[{cor}]{'█' * cheio}[/][dim]{'░' * (largura - cheio)}[/] "
            f"{fracao * 100:.0f}% {do_que} já foi")


def _mostrar_saldo(e: dict) -> None:
    dias = e["dias_desde"]
    quando = "hoje" if dias == 0 else "ontem" if dias == 1 else f"há {dias} dias"

    console.print(_barra(e["fracao_usada"], "do saldo anotado"))
    console.print(f"[bold]{formato.dolar(e['saldo_usd'], casas=2)}[/] ainda no saldo "
                  f"[dim](estimado)[/]")
    console.print(f"[dim]{formato.dolar(e['ancora_usd'], casas=2)} anotados {quando} "
                  f"− {formato.dolar(e['gasto_desde'])} gastos desde então[/]")

    if dias >= 30:
        console.print("\n[yellow]a âncora tem mais de um mês.[/] Confira no painel e "
                      "rode [bold]myaide saldo <valor>[/] de novo.")
