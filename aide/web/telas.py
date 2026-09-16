"""O conteúdo de cada tela. A moldura vem de `paginas.py`."""

from __future__ import annotations

from datetime import datetime
from html import escape

from aide.channels.formato import por_extenso, quando
from aide.web import consultas, graficos
from aide.web.icones import icone
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


# ---------- conversas ----------

def _hora_curta(iso: str, agora: datetime) -> str:
    try:
        momento = datetime.fromisoformat(iso.replace(" ", "T"))
    except ValueError:
        return iso[:16]
    if momento.tzinfo is None:
        from datetime import UTC
        momento = momento.replace(tzinfo=UTC)
    momento = momento.astimezone(agora.tzinfo)
    if momento.date() == agora.date():
        return momento.strftime("%H:%M")
    return momento.strftime("%d/%m")


def _bolha_tool(chamada: dict) -> str:
    """A chamada de ferramenta aparece no meio da conversa, que é onde ela acontece."""
    fn = chamada.get("function") or {}
    nome = fn.get("name", "?")
    args = (fn.get("arguments") or "").strip()
    if len(args) > 120:
        args = args[:117] + "…"
    return (f'<div class="card" style="padding:7px 14px;border-radius:16px 16px 16px 4px;'
            f'align-self:flex-start;max-width:74%;display:flex;align-items:center;gap:9px">'
            f'{icone("ferramentas", 14)}'
            f'<span class="mono" style="font-size:11.5px;color:var(--muted)">{escape(nome)}</span>'
            f'<span style="font-size:11.5px;color:var(--faint);overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap">{escape(args)}</span></div>')


def conversas(ctx, registry, agora: datetime, sessao: str | None = None) -> str:
    sessoes = consultas.conversas(ctx.conn)
    if not sessoes:
        return (cabecalho("Conversas")
                + '<p class="vazio">Nenhuma conversa ainda. Fale com ele por '
                  '<span class="mono">myaide chat</span> ou pelo Telegram.</p>')

    escolhida = sessao if any(s["sessao"] == sessao for s in sessoes) else sessoes[0]["sessao"]

    itens = ""
    for s in sessoes:
        ativa = s["sessao"] == escolhida
        fundo = "background:var(--soft);" if ativa else ""
        cor = "var(--accent)" if ativa else "var(--ink)"
        fraco = "#A8674F" if ativa else "var(--faint)"
        abertura = s["abertura"] or "(sem texto)"
        itens += (
            f'<a href="/conversas?sessao={escape(s["sessao"])}" style="display:block;'
            f'padding:11px 12px;border-radius:var(--r-inner);{fundo}color:{cor}">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px">'
            f'<span style="font-size:13.5px;font-weight:{"600" if ativa else "450"};'
            f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{escape(abertura)}</span>'
            f'<span class="mono" style="font-size:11px;color:{fraco};flex-shrink:0">'
            f'{escape(_hora_curta(s["fim"], agora))}</span></div>'
            f'<p style="margin:3px 0 0;font-size:12.5px;color:{fraco}">'
            f'{escape(s["canal"])} · {s["mensagens"]} mensagem(ns)</p></a>')

    baloes = ""
    for m in consultas.mensagens(ctx.conn, escolhida):
        if m["role"] == "user":
            baloes += (f'<div style="align-self:flex-end;max-width:62%;background:var(--ink);'
                       f'color:#FFF;padding:12px 16px;border-radius:16px 16px 4px 16px;'
                       f'font-size:14.5px;line-height:1.5;white-space:pre-wrap">'
                       f'{escape(m["content"] or "")}</div>')
        elif m["role"] == "assistant":
            if m["tool_calls"]:
                import json
                try:
                    for chamada in json.loads(m["tool_calls"]):
                        baloes += _bolha_tool(chamada)
                except (ValueError, TypeError):
                    pass
            if (m["content"] or "").strip():
                baloes += (f'<div class="card" style="align-self:flex-start;max-width:74%;'
                           f'padding:14px 18px;border-radius:16px 16px 16px 4px;'
                           f'font-size:14.5px;line-height:1.55;white-space:pre-wrap">'
                           f'{escape(m["content"])}</div>')

    return f"""
{cabecalho("Conversas", f"{len(sessoes)} sessão(ões)")}
<div style="display:grid;grid-template-columns:300px minmax(0,1fr);gap:20px;align-items:start">
  <div class="card" style="padding:10px;display:flex;flex-direction:column;gap:2px;
                           max-height:74vh;overflow:auto">{itens}</div>
  <div class="card" style="padding:24px;display:flex;flex-direction:column;gap:14px;
                           max-height:74vh;overflow:auto">
    <p class="mono" style="margin:0;font-size:11.5px;color:var(--faint)">
      sessão {escape(escolhida)}</p>
    {baloes or '<p class="vazio">Sessão sem mensagens legíveis.</p>'}
    <p style="margin:auto 0 0;padding-top:14px;border-top:1px solid var(--line);
              font-size:12.5px;color:var(--faint)">
      Só leitura. Para conversar, use <span class="mono">myaide chat</span> ou o Telegram.</p>
  </div>
</div>
"""


# ---------- ferramentas ----------

# A família é o nome técnico da tool; o ícone tem nome de tela. Sem este mapa
# o `icone()` cai no traço genérico, e metade dos cartões fica sem símbolo.
ICONE_DA_FAMILIA = {
    "tasks": "hoje", "notes": "notas", "expenses": "gastos", "memory": "memoria",
    "people": "pessoas", "events": "calendario", "reminders": "hoje",
    "work_orders": "fila", "usage": "custo", "time": "calendario",
}


def ferramentas(ctx, registry, agora: datetime) -> str:
    import collections

    uso = dict(consultas.uso_das_ferramentas(ctx.conn, limite=50))

    familias: dict[str, list] = collections.OrderedDict()
    for nome in registry.names():
        familias.setdefault(nome.split(".")[0], []).append(registry.get(nome))

    cartoes = ""
    for familia, tools in sorted(familias.items(), key=lambda kv: -uso.get(kv[0], 0)):
        linhas = ""
        for tool in sorted(tools, key=lambda t: t.name):
            confirma = ('<span class="pill" style="font-size:10px">confirma</span>'
                        if tool.safety == "confirm" else "")
            descricao = tool.description.split(".")[0][:110]
            linhas += (
                f'<div style="display:flex;align-items:baseline;gap:10px;padding:7px 0;'
                f'border-top:1px solid var(--line-soft)">'
                f'<span class="mono" style="font-size:12.5px;flex-shrink:0">'
                f'{escape(tool.name.split(".", 1)[1])}</span>{confirma}'
                f'<span style="font-size:12px;color:var(--faint);margin-left:auto;'
                f'text-align:right;line-height:1.35">{escape(descricao)}</span></div>')
        cartoes += (
            f'<div class="card" style="padding:16px 18px">'
            f'<div style="display:flex;align-items:center;gap:9px;margin-bottom:10px;'
            f'color:var(--accent)">{icone(ICONE_DA_FAMILIA.get(familia, "ferramentas"), 17)}'
            f'<span class="mono" style="font-size:13.5px;font-weight:500;color:var(--ink)">'
            f'{escape(familia)}</span>'
            f'<span style="margin-left:auto;font-size:11.5px;color:var(--faint)">'
            f'{uso.get(familia, 0)} uso(s)</span></div>{linhas}</div>')

    confirmam = sum(1 for n in registry.names() if registry.get(n).safety == "confirm")
    return f"""
{cabecalho("Ferramentas", f"{len(registry.names())} registradas · {len(familias)} famílias",
           f'<p style="margin:0;font-size:13px;color:var(--muted);max-width:52ch;'
           f'text-align:right;line-height:1.5">Tudo que ele sabe fazer. As '
           f'{confirmam} marcadas <span style="color:var(--accent);font-weight:600">confirma</span> '
           f'pedem autorização e não são expostas por MCP.</p>')}
<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;
            align-items:start">{cartoes}</div>
"""


# ---------- auditoria ----------

def auditoria(ctx, registry, agora: datetime, ator: str | None = None) -> str:
    atores = consultas.atores_da_auditoria(ctx.conn)
    if not atores:
        return cabecalho("Auditoria") + '<p class="vazio">Nada registrado ainda.</p>'

    if ator and ator not in {a for a, _ in atores}:
        ator = None
    linhas_db = consultas.auditoria(ctx.conn, limite=150, ator=ator)

    filtros = (f'<a href="/auditoria" style="font-size:12.5px;padding:5px 12px;'
               f'border-radius:var(--r-pill);'
               f'{"background:var(--soft);font-weight:600" if not ator else "color:var(--muted)"}">'
               f'todos</a>')
    for nome, total in atores:
        marcado = nome == ator
        estilo = ("background:var(--soft);font-weight:600" if marcado else "color:var(--muted)")
        filtros += (f'<a href="/auditoria?ator={escape(nome)}" style="font-size:12.5px;'
                    f'padding:5px 12px;border-radius:var(--r-pill);{estilo}">'
                    f'{escape(nome)} <span class="mono">{total}</span></a>')

    linhas = ""
    for r in linhas_db:
        falhou = not r["ok"]
        resumo = (r["result_summary"] or "")[:150]
        linhas += (
            f'<div class="linha" style="padding:9px 18px;align-items:baseline">'
            f'<span class="mono" style="font-size:11.5px;color:var(--faint);width:80px;'
            f'flex-shrink:0">{escape(_hora_curta(r["ts"], agora))}</span>'
            f'<span style="font-size:11px;color:var(--muted);background:#F5F6F8;'
            f'padding:2px 8px;border-radius:var(--r-pill);flex-shrink:0">'
            f'{escape(r["actor"])}</span>'
            f'<span class="mono" style="font-size:12.5px;width:170px;flex-shrink:0;'
            f'color:{"var(--accent)" if falhou else "var(--ink)"}">{escape(r["tool"])}</span>'
            f'<span style="font-size:12px;color:var(--faint);overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap">{escape(resumo)}</span></div>')

    total_geral = sum(n for _, n in atores)
    return f"""
{cabecalho("Auditoria", f"{total_geral} chamadas registradas · mostrando as 150 últimas")}
<div style="display:flex;gap:6px;flex-wrap:wrap;margin:-14px 0 16px">{filtros}</div>
<div class="card"><div>{linhas or '<p class="vazio">Nada deste ator.</p>'}</div></div>
"""


# ---------- notas ----------

def notas(ctx, registry, agora: datetime, nota: int | None = None,
          busca: str | None = None) -> str:
    if busca:
        achados = registry.call("notes.search", {"query": busca, "limit": 20}, ctx)
        lista = [{"id": a.get("id"), "title": a.get("title", ""), "tags": a.get("tags"),
                  "trecho": a.get("trecho", ""), "tipo": a.get("tipo", "nota")}
                 for a in (achados.data or []) if a.get("id")]
    else:
        lista = [dict(n, trecho="", tipo="nota")
                 for n in (registry.call("notes.list", {"limit": 60}, ctx).data or [])]

    escolhida = nota if any(n["id"] == nota for n in lista) else (lista[0]["id"] if lista else None)

    itens = ""
    for n in lista:
        ativa = n["id"] == escolhida
        fundo = "background:var(--soft);" if ativa else ""
        cor = "var(--accent)" if ativa else "var(--ink)"
        alvo = f"/notas?nota={n['id']}" + (f"&busca={escape(busca)}" if busca else "")
        etiquetas = ""
        if n.get("tags"):
            # bloco, não inline: coladas ao título elas viram parte dele
            etiquetas = (f'<p style="margin:4px 0 0;font-size:11px;color:var(--faint)">'
                         f'{escape(str(n["tags"]))}</p>')
        trecho = ""
        if n.get("trecho"):
            trecho = (f'<p style="margin:4px 0 0;font-size:12px;color:var(--faint);'
                      f'line-height:1.4">{escape(n["trecho"][:110])}</p>')
        itens += (f'<a href="{alvo}" style="display:block;padding:11px 12px;'
                  f'border-radius:var(--r-inner);{fundo}color:{cor}">'
                  f'<span style="font-size:13.5px;font-weight:{"600" if ativa else "450"};'
                  f'display:block">{escape(n["title"])}</span>{etiquetas}{trecho}</a>')

    if escolhida is None:
        corpo = ('<p class="vazio">Nenhuma nota. Escreva com '
                 '<span class="mono">myaide nota "Título" "corpo"</span>.</p>')
    else:
        lida = registry.call("notes.read", {"id": escolhida}, ctx)
        if lida.ok:
            corpo = (f'<h2 style="margin:0 0 4px;font-size:20px;font-weight:600">'
                     f'{escape(lida.data["title"])}</h2>'
                     f'<p class="mono" style="margin:0 0 18px;font-size:11.5px;'
                     f'color:var(--faint)">#{lida.data["id"]}'
                     f'{" · " + escape(str(lida.data["tags"])) if lida.data["tags"] else ""}</p>'
                     f'<div style="font-size:14.5px;line-height:1.7;white-space:pre-wrap">'
                     f'{escape(lida.data["body"])}</div>')
        else:
            corpo = f'<p class="vazio">{escape(lida.error)}</p>'

    return f"""
{cabecalho("Notas", f"{len(lista)} nota(s)" + (f' para "{escape(busca)}"' if busca else ""),
           f'<form method="get" action="/notas" style="display:flex;gap:6px">'
           f'<input name="busca" value="{escape(busca or "")}" placeholder="buscar por significado"'
           f' style="font:inherit;font-size:13px;padding:7px 13px;border:1px solid var(--line);'
           f'border-radius:var(--r-pill);background:var(--surface);width:230px">'
           f'</form>')}
<div style="display:grid;grid-template-columns:300px minmax(0,1fr);gap:20px;align-items:start">
  <div class="card" style="padding:10px;display:flex;flex-direction:column;gap:2px;
                           max-height:74vh;overflow:auto">
    {itens or '<p class="vazio">Nada encontrado.</p>'}</div>
  <div class="card" style="padding:26px 28px;max-height:74vh;overflow:auto">{corpo}</div>
</div>
"""


# ---------- memória ----------

def memoria(ctx, registry, agora: datetime) -> str:
    def bloco(kind: str, titulo: str, vazio: str) -> str:
        fatos = registry.call("memory.list", {"kind": kind}, ctx).data or []
        linhas = ""
        for f in fatos:
            incerto = ""
            if f.get("confidence", 1) < 1:
                incerto = (f'<span class="quando mono" style="font-size:11.5px">'
                           f'incerto {f["confidence"]:.1f}</span>')
            linhas += (
                f'<div class="linha" style="padding:11px 18px;align-items:baseline">'
                f'<span class="mono" style="font-size:12.5px;color:var(--muted);width:150px;'
                f'flex-shrink:0">{escape(f["key"])}</span>'
                f'<span style="font-size:14px;line-height:1.5">{escape(f["value"])}</span>'
                f'{incerto}</div>')
        vazio_html = f'<p class="vazio">{escape(vazio)}</p>'
        return (f'<div class="card"><div style="padding:16px 20px 12px;display:flex;'
                f'justify-content:space-between;align-items:baseline">'
                f'<span class="eyebrow">{escape(titulo)}</span>'
                f'<span class="mono" style="font-size:12px;color:var(--faint)">'
                f'{len(fatos)}</span></div>'
                f'<div style="border-top:1px solid var(--line-soft)">'
                f'{linhas or vazio_html}</div></div>')

    return f"""
{cabecalho("Memória", "o que ele sabe sobre você",
           '<p style="margin:0;font-size:12.5px;color:var(--faint);max-width:40ch;'
           'text-align:right;line-height:1.5">O perfil vai inteiro em toda conversa. '
           'O que está marcado como privado não sai desta máquina.</p>')}
<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;
            align-items:start">
  {bloco("profile", "Perfil", "Nada guardado ainda.")}
  {bloco("episodic", "Episódico", "Nenhum episódio registrado.")}
</div>
"""


# ---------- pessoas ----------

def pessoas(ctx, registry, agora: datetime) -> str:
    gente = registry.call("people.list", {}, ctx).data or []
    if not gente:
        return (cabecalho("Pessoas")
                + '<p class="vazio">Ninguém registrado. Peça a ele: '
                  '"passa a acompanhar o Pedro, falo a cada 14 dias".</p>')

    linhas = ""
    for p in gente:
        dias = p.get("dias_sem_falar")
        atraso = p.get("atrasado")
        texto = "—" if dias is None else f"{dias}d"
        cor = "var(--accent)" if atraso else "var(--ink)"
        combinado = (f'a cada {p["cadence_days"]}d' if p.get("cadence_days")
                     else "sem cobrança")
        linhas += (
            f'<div class="linha">'
            f'<span style="font-size:14.5px;width:160px;flex-shrink:0">{escape(p["name"])}</span>'
            f'<span style="font-size:12.5px;color:var(--faint);width:120px;flex-shrink:0">'
            f'{escape(p.get("relation") or "")}</span>'
            f'<span class="mono" style="font-size:13px;color:{cor};width:70px">{texto}</span>'
            f'<span class="quando">{escape(combinado)}</span></div>')

    atrasados = sum(1 for p in gente if p.get("atrasado"))
    return f"""
{cabecalho("Pessoas", f"{len(gente)} acompanhada(s)",
           f'<p style="margin:0;font-size:13px;color:'
           f'{"var(--accent)" if atrasados else "var(--muted)"}">'
           f'{atrasados} em atraso</p>')}
<div class="card">{linhas}</div>
"""


# ---------- fila ----------

ROTULO_STATUS = {"open": "esperando", "claimed": "em curso",
                 "done": "concluída", "dropped": "descartada"}


def fila(ctx, registry, agora: datetime) -> str:
    ordens = registry.call("work_orders.list", {"status": "all", "limit": 60}, ctx).data or []
    if not ordens:
        return (cabecalho("Fila de trabalho")
                + '<p class="vazio">Fila vazia. Enfileire com '
                  '<span class="mono">myaide enfileirar "objetivo"</span>.</p>')

    def cartao(o: dict) -> str:
        aberta = o["status"] in ("open", "claimed")
        cor = "var(--accent)" if aberta else "var(--faint)"
        resultado = ""
        if o.get("result_summary"):
            resultado = (f'<div style="margin-top:12px;padding-top:12px;'
                         f'border-top:1px solid var(--line-soft);font-size:13.5px;'
                         f'line-height:1.6;white-space:pre-wrap;color:var(--muted)">'
                         f'{escape(o["result_summary"][:900])}</div>')
        contexto_txt = ""
        if o.get("context"):
            contexto_txt = (f'<p style="margin:6px 0 0;font-size:13px;color:var(--faint);'
                            f'line-height:1.5">{escape(o["context"])}</p>')
        return (f'<div class="card" style="padding:18px 20px">'
                f'<div style="display:flex;align-items:baseline;gap:10px">'
                f'<span class="mono" style="font-size:12px;color:var(--faint)">#{o["id"]}</span>'
                f'<span style="font-size:15px;font-weight:500">{escape(o["goal"])}</span>'
                f'<span style="margin-left:auto;font-size:11px;color:{cor};background:'
                f'{"var(--soft)" if aberta else "#F5F6F8"};padding:3px 9px;'
                f'border-radius:var(--r-pill)">'
                f'{escape(ROTULO_STATUS.get(o["status"], o["status"]))}</span></div>'
                f'{contexto_txt}{resultado}</div>')

    # Separadas de propósito: uma ordem concluída é registro do que foi feito,
    # não coisa a fazer. Misturadas, o histórico empurra para baixo o que ainda
    # espera — e parece que a fila não atualizou.
    esperando = [o for o in ordens if o["status"] in ("open", "claimed")]
    passadas = [o for o in ordens if o["status"] not in ("open", "claimed")]

    blocos = ""
    if esperando:
        blocos += (f'<p class="eyebrow" style="margin-bottom:12px">Esperando um executor</p>'
                   f'<div style="display:flex;flex-direction:column;gap:14px;'
                   f'margin-bottom:28px">{"".join(cartao(o) for o in esperando)}</div>')
    else:
        blocos += ('<div class="card" style="padding:22px 24px;margin-bottom:28px">'
                   '<p style="margin:0;color:var(--muted);line-height:1.6">Nada esperando. '
                   'O daemon enfileira sozinho quando uma regra pede, ou você enfileira com '
                   '<span class="mono">myaide enfileirar "objetivo"</span>.</p></div>')

    if passadas:
        blocos += (f'<p class="eyebrow" style="margin-bottom:12px">Já feitas · {len(passadas)}</p>'
                   f'<div style="display:flex;flex-direction:column;gap:14px">'
                   f'{"".join(cartao(o) for o in passadas)}</div>')

    return f"""
{cabecalho("Fila de trabalho",
           f"{len(esperando)} esperando · {len(passadas)} no histórico",
           '<p style="margin:0;font-size:12.5px;color:var(--faint);max-width:44ch;'
           'text-align:right;line-height:1.5">O daemon enfileira; um executor externo '
           'faz por MCP e grava o resultado de volta aqui.</p>')}
{blocos}
"""
