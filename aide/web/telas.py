"""O conteúdo de cada tela. A moldura vem de `paginas.py`."""

from __future__ import annotations

from datetime import datetime
from html import escape

from aide.channels.formato import por_extenso, quando
from aide.web import consultas, graficos
from aide.web.paginas import cabecalho


def _cartao(titulo: str, corpo: str, extra: str = "") -> str:
    return (f'<div class="card" style="padding:18px 20px;{extra}">'
            f'<p class="eyebrow" style="margin-bottom:12px">{escape(titulo)}</p>{corpo}</div>')


def _indicador(rotulo: str, valor: str, nota: str = "", alerta: bool = False) -> str:
    cor = "var(--accent)" if alerta else "var(--ink)"
    return (f'<div class="card" style="padding:15px 18px">'
            f'<p class="eyebrow" style="margin-bottom:7px">{escape(rotulo)}</p>'
            f'<p class="mono" style="margin:0;font-size:24px;letter-spacing:-.01em;color:{cor}">'
            f'{escape(valor)}</p>'
            f'<p style="margin:5px 0 0;font-size:11.5px;color:var(--faint)">{escape(nota)}</p></div>')


def _lista(itens: list[str], vazio: str) -> str:
    if not itens:
        return f'<p class="vazio">{escape(vazio)}</p>'
    return "".join(itens)


def _linha_tarefa(t: dict, agora: datetime, atrasada: bool = False) -> str:
    marca = quando(t.get("due_at"), agora)
    classe = "quando mono late" if atrasada else "quando mono"
    return (f'<div class="linha"><span class="ref mono">#{t["id"]}</span>'
            f'<span style="font-size:14.5px">{escape(t["title"])}</span>'
            f'<span class="{classe}">{escape(marca)}</span></div>')


# ---------- painel ----------

def painel(ctx, registry, agora: datetime) -> str:
    conn = ctx.conn
    n = consultas.contagens(conn, agora)
    canais = consultas.mensagens_por_canal(conn)
    total_msg = canais["aqui"] + canais["telegram"] or 1

    resumo = registry.call("expenses.summary", {"periodo": "mes"}, ctx)
    gasto = resumo.data if resumo.ok else {"total": "R$ 0,00", "quantos": 0}

    from aide.scheduler import rules
    achados = rules.evaluate(conn, agora)
    por_regra: dict[str, int] = {}
    for f in achados:
        por_regra[f.rule] = por_regra.get(f.rule, 0) + 1

    indicadores = "".join([
        _indicador("Tarefas abertas", str(n["abertas"]), f'{n["lembretes"]} lembrete(s)'),
        _indicador("Atrasadas", str(n["atrasadas"]), "pedindo decisão",
                   alerta=bool(n["atrasadas"])),
        _indicador("Gasto do mês", gasto["total"], f'{gasto["quantos"]} lançamento(s)'),
        _indicador("Chamadas de LLM", str(n["chamadas"]), "desde o começo"),
        _indicador("Notas", str(n["notas"]), f'{n["perfil"]} fato(s) no perfil'),
    ])

    regras_html = "".join(
        f'<div style="display:flex;align-items:center;gap:10px;font-size:13px;'
        f'color:{"var(--ink)" if por_regra.get(r) else "var(--faint)"}">'
        f'<span class="mono" style="width:18px;'
        f'color:{"var(--accent)" if por_regra.get(r) else "var(--faint)"}">'
        f'{por_regra.get(r, 0)}</span>{escape(rotulo)}</div>'
        for r, rotulo in (("atrasadas", "atrasadas"), ("adiada_demais", "adiada demais"),
                          ("projeto_parado", "projeto parado"),
                          ("contato_atrasado", "contato atrasado"), ("zumbi", "zumbi")))

    return f"""
{cabecalho("Painel", por_extenso(agora))}
<div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px">{indicadores}</div>

<div style="display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:16px;margin-top:16px">
  {_cartao("Chamadas de LLM por dia",
           graficos.area(consultas.chamadas_por_dia(conn, agora), 620, 96,
                         vazio="nenhuma chamada nos últimos 14 dias"))}
  {_cartao("Uso das ferramentas",
           graficos.barras(consultas.uso_das_ferramentas(conn), rotulo_px=104,
                           vazio="nenhuma ferramenta usada ainda"))}
</div>

<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:16px">
  {_cartao("Tarefas criadas por dia",
           graficos.colunas(consultas.tarefas_por_dia(conn, agora), 330, 96,
                            vazio="nenhuma tarefa criada nos últimos 14 dias"))}
  <div class="card" style="padding:18px 20px;display:flex;gap:18px;align-items:center">
    <div style="flex:1">
      <p class="eyebrow" style="margin-bottom:12px">Por onde você fala</p>
      <div style="display:flex;flex-direction:column;gap:9px">
        <div style="display:flex;align-items:center;gap:9px">
          <span style="width:9px;height:9px;border-radius:3px;background:var(--accent)"></span>
          <span style="font-size:13px">aqui</span>
          <span class="mono" style="margin-left:auto;font-size:13px">{canais["aqui"]}</span></div>
        <div style="display:flex;align-items:center;gap:9px">
          <span style="width:9px;height:9px;border-radius:3px;background:#E9B3A6"></span>
          <span style="font-size:13px">telegram</span>
          <span class="mono" style="margin-left:auto;font-size:13px">{canais["telegram"]}</span></div>
      </div>
    </div>
    {graficos.anel(canais["aqui"] / total_msg, f'{canais["aqui"] / total_msg * 100:.0f}%')}
  </div>
  {_cartao("Regras disparando",
           f'<div style="display:flex;flex-direction:column;gap:9px">{regras_html}</div>')}
</div>
"""


# ---------- hoje ----------

def hoje(ctx, registry, agora: datetime) -> str:
    atrasadas = registry.call("tasks.list", {"filter": "overdue", "limit": 20}, ctx)
    do_dia = registry.call("tasks.list", {"filter": "today", "limit": 20}, ctx)
    ids_atrasadas = {t["id"] for t in (atrasadas.data or [])}
    hoje_sem_atraso = [t for t in (do_dia.data or []) if t["id"] not in ids_atrasadas]

    from aide.scheduler import rules
    decidir = [f for f in rules.evaluate(ctx.conn, agora)
               if f.rule in {"adiada_demais", "zumbi", "projeto_parado"}]

    lembretes = ctx.conn.execute(
        "SELECT text, fire_at FROM reminders WHERE status='pending' ORDER BY fire_at LIMIT 8"
    ).fetchall()

    contagem = []
    if atrasadas.data:
        contagem.append(f"{len(atrasadas.data)} atrasada(s)")
    if hoje_sem_atraso:
        contagem.append(f"{len(hoje_sem_atraso)} para hoje")

    return f"""
{cabecalho("Hoje", por_extenso(agora),
           f'<p style="margin:0;font-size:13px;color:var(--muted)">{" · ".join(contagem)}</p>'
           if contagem else "")}
<div class="card" style="margin-bottom:16px">
  <div style="display:flex;align-items:center;gap:10px;padding:16px 20px 13px">
    <span class="eyebrow" style="color:var(--accent)">Atrasadas</span>
    {f'<span class="pill">{len(atrasadas.data)}</span>' if atrasadas.data else ''}
  </div>
  <div style="border-top:1px solid var(--line-soft)">
    {_lista([_linha_tarefa(t, agora, atrasada=True) for t in (atrasadas.data or [])],
            "Nada atrasado.")}
  </div>
</div>

<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start">
  <div class="card">
    <div style="padding:16px 20px 13px"><span class="eyebrow">Hoje</span></div>
    <div style="border-top:1px solid var(--line-soft)">
      {_lista([_linha_tarefa(t, agora) for t in hoje_sem_atraso]
              + [f'<div class="linha"><span class="ref"></span>'
                 f'<span style="font-size:14.5px">{escape(r["text"])}</span>'
                 f'<span class="quando mono">{escape(quando(r["fire_at"], agora))}</span></div>'
                 for r in lembretes],
              "Nada marcado para hoje.")}
    </div>
  </div>
  <div class="card">
    <div style="padding:16px 20px 13px"><span class="eyebrow">Precisa decidir</span></div>
    <div style="border-top:1px solid var(--line-soft);padding:4px 20px 18px">
      {"".join(f'<p style="margin:14px 0 0;font-size:14px;line-height:1.5;text-wrap:pretty">'
               f'{escape(f.summary)}</p>' for f in decidir[:5])
       or '<p class="vazio" style="padding:20px 0">Nada pedindo decisão.</p>'}
    </div>
  </div>
</div>
"""


# ---------- calendário ----------

DIAS_CURTOS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")
ITENS_POR_DIA = 3


def _etiqueta(item: dict, atrasado: bool) -> str:
    """Uma marca dentro do quadrado do dia. Curta: o dia tem 3 linhas úteis."""
    if item["feito"]:
        fundo, cor, risco = "#F3F4F6", "var(--faint)", "text-decoration:line-through;"
    elif atrasado:
        fundo, cor, risco = "var(--soft)", "var(--accent)", ""
    else:
        fundo, cor, risco = "#F5F6F8", "#4A505C", ""

    hora = ""
    if item["tipo"] != "tarefa" or not item.get("dia_inteiro"):
        parte = item["quando"].partition("T")[2][:5]
        if parte and parte != "00:00":
            hora = f"{parte} "
    return (f'<div style="background:{fundo};color:{cor};font-size:11px;font-weight:500;'
            f'padding:3px 7px;border-radius:6px;white-space:nowrap;overflow:hidden;'
            f'text-overflow:ellipsis;{risco}" title="{escape(item["texto"])}">'
            f'{escape(hora)}{escape(item["texto"])}</div>')


def calendario(ctx, registry, agora: datetime, ano: int | None = None,
               mes: int | None = None) -> str:
    from calendar import Calendar

    ano = ano or agora.year
    mes = mes or agora.month
    por_dia = consultas.planejado_no_mes(ctx.conn, ano, mes, agora.tzinfo)
    hoje = agora.day if (ano, mes) == (agora.year, agora.month) else None

    semanas = Calendar(firstweekday=0).monthdayscalendar(ano, mes)
    celulas = []
    for semana in semanas:
        for dia in semana:
            if dia == 0:
                celulas.append('<div style="background:var(--paper);border-radius:12px"></div>')
                continue

            itens = por_dia.get(dia, [])
            eh_hoje = dia == hoje
            no_passado = hoje is not None and dia < hoje
            marcas = "".join(_etiqueta(i, atrasado=no_passado and not i["feito"])
                             for i in itens[:ITENS_POR_DIA])
            if len(itens) > ITENS_POR_DIA:
                marcas += (f'<div style="font-size:10.5px;color:var(--faint);padding:1px 7px">'
                           f'+{len(itens) - ITENS_POR_DIA}</div>')

            borda = "var(--accent)" if eh_hoje else "var(--line)"
            cor_num = "var(--accent)" if eh_hoje else "var(--ink)"
            peso = "600" if eh_hoje else "450"
            celulas.append(
                # min-width:0 é o que deixa o quadrado encolher: item de grid
                # nasce com min-width:auto, que é a largura do texto sem quebra,
                # e aí a grade transborda e o domingo sai da tela.
                f'<div style="background:var(--surface);border:1px solid {borda};'
                f'border-radius:12px;padding:9px 10px;display:flex;flex-direction:column;'
                f'gap:4px;min-width:0;min-height:0;overflow:hidden">'
                f'<span class="mono" style="font-size:12px;color:{cor_num};font-weight:{peso}">'
                f'{dia}</span>{marcas}</div>')

    legenda = "".join(
        f'<span style="display:flex;align-items:center;gap:7px">'
        f'<span style="width:9px;height:9px;border-radius:3px;background:{fundo};'
        f'{borda}"></span>{rotulo}</span>'
        for rotulo, fundo, borda in (
            ("atrasado", "var(--soft)", "border:1px solid var(--accent)"),
            ("planejado", "#F5F6F8", ""), ("feito", "#F3F4F6", "")))

    total = sum(len(v) for v in por_dia.values())
    cabeca = "".join(
        f'<div style="text-align:center;font-size:11px;letter-spacing:.07em;'
        f'text-transform:uppercase;color:var(--faint);font-weight:600">{d}</div>'
        for d in DIAS_CURTOS)

    return f"""
{cabecalho(MESES[mes - 1].capitalize(), str(ano),
           f'<div style="display:flex;align-items:center;gap:18px;font-size:13px;'
           f'color:var(--muted)">{legenda}</div>')}
<p style="margin:-14px 0 16px;font-size:13px;color:var(--muted)">
  {total} compromisso(s) no mês</p>
<div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px;margin-bottom:6px">
  {cabeca}
</div>
<div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));
            grid-auto-rows:minmax(104px,1fr);gap:8px">{"".join(celulas)}</div>
"""


# ---------- gastos ----------

PERIODOS_ROTULO = (("hoje", "hoje"), ("semana", "semana"), ("mes", "mês"),
                   ("ano", "ano"), ("sempre", "tudo"))


def _seletor(caminho: str, atual: str) -> str:
    """Links, não botões: a página é de leitura e o histórico do navegador funciona."""
    itens = ""
    for chave, rotulo in PERIODOS_ROTULO:
        ativo = chave == atual
        estilo = ("background:var(--surface);font-weight:600;"
                  "box-shadow:0 1px 2px rgba(21,23,28,.06)" if ativo else "color:var(--muted)")
        itens += (f'<a href="{caminho}?periodo={chave}" style="font-size:12.5px;'
                  f'padding:6px 14px;border-radius:var(--r-pill);{estilo}">{rotulo}</a>')
    return (f'<div style="display:flex;gap:6px;background:#F5F6F8;padding:3px;'
            f'border-radius:var(--r-pill)">{itens}</div>')


def _periodo_por_extenso(de: str, ate: str, periodo: str) -> str:
    """'1 a 16 de setembro'. '2026/09/01 a 2026/09/16' é formato de máquina."""
    if periodo == "sempre":
        return "desde o começo"
    inicio = datetime.fromisoformat(de)
    fim = datetime.fromisoformat(ate)
    if periodo in ("hoje", "ontem"):
        return por_extenso(inicio)
    if inicio.month == fim.month:
        return f"{inicio.day} a {fim.day} de {MESES[fim.month - 1]}"
    return (f"{inicio.day} de {MESES[inicio.month - 1]} "
            f"a {fim.day} de {MESES[fim.month - 1]}")


def gastos(ctx, registry, agora: datetime, periodo: str = "mes") -> str:
    from aide.tools.expenses import PERIODOS, formatar, intervalo

    if periodo not in PERIODOS:
        periodo = "mes"

    resumo = registry.call("expenses.summary", {"periodo": periodo}, ctx)
    lista = registry.call("expenses.list", {"periodo": periodo, "limit": 40}, ctx)
    if not resumo.ok:
        return cabecalho("Gastos") + f'<p class="vazio">{escape(resumo.error)}</p>'

    dados = resumo.data
    lancamentos = lista.data or []
    de, ate = intervalo(periodo, agora)

    por_dia = consultas.gastos_por_dia(ctx.conn, de, ate, agora.tzinfo)
    # séries longas em barra diária viram cerca; acima de 40 dias só o acumulado
    diario = graficos.colunas([(r, v / 100) for r, v in por_dia], 1260, 76,
                              vazio="nenhum gasto neste período") if len(por_dia) <= 40 else ""
    acum = graficos.area([(r, v / 100) for r, v in consultas.acumulado(por_dia)], 300, 62,
                         vazio="nada lançado ainda")

    maior = max(lancamentos, key=lambda g: g["cents"], default=None)
    categorias = [(c["category"], c["cents"] / 100) for c in dados["por_categoria"]]

    def _linha_gasto(g: dict) -> str:
        dia = f'{g["spent_at"][8:10]}/{g["spent_at"][5:7]}'
        etiqueta = ""
        if g["category"]:
            etiqueta = (f'<span style="font-size:11px;color:var(--muted);background:#F5F6F8;'
                        f'padding:2px 8px;border-radius:var(--r-pill)">'
                        f'{escape(g["category"])}</span>')
        return (f'<div class="linha" style="padding:10px 18px">'
                f'<span class="mono" style="font-size:12px;color:var(--faint);width:46px;'
                f'flex-shrink:0">{escape(dia)}</span>'
                f'<span style="font-size:13.5px">{escape(g["description"])}</span>'
                f'{etiqueta}'
                f'<span class="quando mono" style="color:var(--ink);font-size:13.5px">'
                f'{escape(g["valor"])}</span></div>')

    linhas = "".join(_linha_gasto(g) for g in lancamentos)

    return f"""
{cabecalho("Gastos", _periodo_por_extenso(de, ate, periodo), _seletor("/gastos", periodo))}
<div style="display:grid;grid-template-columns:minmax(0,1.6fr) repeat(3,minmax(0,1fr));gap:14px">
  <div class="card" style="padding:16px 20px">
    <p class="eyebrow" style="margin-bottom:6px">Acumulado</p>
    <p class="mono" style="margin:0 0 6px;font-size:26px;letter-spacing:-.01em">
      {escape(dados["total"])}</p>
    {acum}
  </div>
  {_indicador("Lançamentos", str(dados["quantos"]), "no período")}
  {_indicador("Média", dados["media"], "por lançamento")}
  {_indicador("Maior", formatar(maior["cents"]) if maior else "—",
              maior["description"][:28] if maior else "nada lançado")}
</div>

{f'<div class="card" style="padding:16px 20px;margin-top:16px">'
 f'<p class="eyebrow" style="margin-bottom:8px">Por dia</p>{diario}</div>' if diario else ''}

<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.1fr);
            gap:16px;margin-top:16px;align-items:start">
  {_cartao("Por categoria",
           graficos.barras(categorias, rotulo_px=104, vazio="nenhuma categoria ainda",
                           formatar=lambda v: f"R$ {v:,.2f}".replace(",", "@")
                                               .replace(".", ",").replace("@", ".")))}
  <div class="card">
    <div style="padding:15px 18px 11px"><span class="eyebrow">Lançamentos</span></div>
    <div style="border-top:1px solid var(--line-soft)">
      {linhas or '<p class="vazio">Nenhum gasto neste período.</p>'}
    </div>
  </div>
</div>
"""


# ---------- custo e saldo ----------

def custo(ctx, registry, agora: datetime) -> str:
    from aide.llm import custo as calculo
    from aide.web.paginas import usd

    gasto = calculo.mes_corrente(ctx.conn, ctx.config, agora)
    gasto = calculo.com_custo_real(gasto, ctx.config, agora.replace(day=1, hour=0, minute=0))
    saldo = calculo.saldo_estimado(ctx.conn, ctx.config)

    serie = consultas.custo_por_dia(ctx.conn, agora, 14, ctx.config.llm.precos)
    modelos = [(m["model"], round(m["usd"] or 0, 4)) for m in gasto.por_modelo]

    if saldo:
        pc = min(saldo["fracao_usada"] * 100, 100)
        dias = saldo["dias_desde"]
        idade = "hoje" if dias == 0 else "ontem" if dias == 1 else f"há {dias} dias"
        velho = ('<p style="margin:10px 0 0;font-size:12px;color:var(--accent)">'
                 'a âncora tem mais de um mês; confira no painel e rode '
                 '<span class="mono">myaide saldo</span></p>' if dias >= 30 else "")
        bloco_saldo = f"""
          <p class="eyebrow" style="margin-bottom:8px">Saldo estimado</p>
          <p class="mono" style="margin:0 0 10px;font-size:34px;letter-spacing:-.015em">
            {escape(usd(saldo["saldo_usd"]))}</p>
          <div class="barra" style="height:6px"><div style="width:{pc:.1f}%"></div></div>
          <p style="margin:10px 0 0;font-size:12.5px;color:var(--muted)">
            {escape(usd(saldo["ancora_usd"]))} anotados {idade}
            − {escape(usd(saldo["gasto_desde"]))} gastos desde então</p>{velho}"""
    else:
        bloco_saldo = """
          <p class="eyebrow" style="margin-bottom:8px">Saldo</p>
          <p style="margin:0;font-size:14px;color:var(--muted);line-height:1.6">
            A OpenAI não expõe saldo por API — os endereços de cobrança exigem a
            sessão do navegador. Veja no painel e anote com
            <span class="mono">myaide saldo 4.22</span>; daí em diante o gasto é
            descontado a partir dali.</p>"""

    real = ""
    if gasto.real_usd is not None:
        real = (f'<p style="margin:8px 0 0;font-size:12.5px;color:var(--muted)">'
                f'{escape(usd(gasto.real_usd))} cobrados pela OpenAI (real)</p>')
    elif gasto.erro_real:
        real = (f'<p style="margin:8px 0 0;font-size:12.5px;color:var(--accent)">'
                f'custo real indisponível: {escape(gasto.erro_real)}</p>')

    sem_preco = ""
    if gasto.sem_preco:
        sem_preco = (f'<p style="margin:10px 0 0;font-size:12px;color:var(--accent)">'
                     f'sem preço em config.yaml: {escape(", ".join(gasto.sem_preco))}</p>')

    return f"""
{cabecalho("Custo e saldo", f"desde {gasto.desde}",
           '<p style="margin:0;font-size:12.5px;color:var(--faint);max-width:32ch;'
           'text-align:right;line-height:1.5">O saldo é estimativa: o valor anotado '
           'do painel menos o gasto calculado desde então.</p>')}
<div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:16px">
  <div class="card" style="padding:20px 22px">{bloco_saldo}</div>
  {_cartao("Custo por dia, em dólares",
           graficos.area(serie, 620, 96, vazio="nenhuma chamada nos últimos 14 dias")
           + f'<p class="mono" style="margin:10px 0 0;font-size:20px">'
             f'{escape(usd(gasto.estimado_usd))}</p>'
             f'<p style="margin:3px 0 0;font-size:12px;color:var(--faint)">'
             f'estimado no mês · {gasto.chamadas} chamada(s)</p>{real}{sem_preco}')}
</div>

<div style="display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);
            gap:16px;margin-top:16px;align-items:start">
  {_cartao("Por modelo", graficos.barras(modelos, rotulo_px=168,
                                         vazio="nenhum modelo usado ainda",
                                         formatar=lambda v: f"{v:.4f}".replace(".", ",")))}
  {_cartao("Para quê", graficos.barras(consultas.uso_por_finalidade(ctx.conn),
                                       rotulo_px=112, vazio="nada registrado ainda"))}
</div>
"""
