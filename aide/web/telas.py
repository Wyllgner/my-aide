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
           graficos.area([v for _, v in consultas.chamadas_por_dia(conn, agora)], 620, 122,
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
