"""A moldura das telas: cabeça do documento, barra lateral e navegação.

Sem framework de front e sem build. Cada tela entrega só o seu conteúdo; esta
camada põe o resto em volta.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from aide.web.icones import icone


@dataclass(frozen=True)
class Tela:
    slug: str
    rotulo: str
    caminho: str


TELAS = (
    Tela("painel", "Painel", "/"),
    Tela("hoje", "Hoje", "/hoje"),
    Tela("calendario", "Calendário", "/calendario"),
    Tela("conversas", "Conversas", "/conversas"),
    Tela("notas", "Notas", "/notas"),
    Tela("gastos", "Gastos", "/gastos"),
    Tela("custo", "Custo e saldo", "/custo"),
    Tela("memoria", "Memória", "/memoria"),
    Tela("pessoas", "Pessoas", "/pessoas"),
    Tela("fila", "Fila", "/fila"),
    Tela("ferramentas", "Ferramentas", "/ferramentas"),
    Tela("auditoria", "Auditoria", "/auditoria"),
)

POR_SLUG = {t.slug: t for t in TELAS}


def _nav(ativo: str) -> str:
    itens = []
    for tela in TELAS:
        atual = ' aria-current="page"' if tela.slug == ativo else ""
        itens.append(
            f'<a href="{tela.caminho}"{atual}>{icone(tela.slug)}'
            f'<span class="rotulo">{escape(tela.rotulo)}</span></a>')
    return "<nav>" + "".join(itens) + "</nav>"


def usd(valor: float) -> str:
    """4.21 -> 'US$ 4,21'. A página é em português; o separador também."""
    return f"US$ {valor:.2f}".replace(".", ",")


def _saldo(dados: dict | None) -> str:
    """Rodapé da lateral. Sem âncora anotada, convida a anotar em vez de mentir."""
    if not dados:
        return (
            '<div class="saldo">'
            '<p class="eyebrow">Saldo API</p>'
            '<p style="margin:0;font-size:12px;color:var(--faint);line-height:1.45">'
            'nenhum anotado — use <span class="mono">myaide saldo</span></p></div>')

    pc = min(dados["fracao_usada"] * 100, 100)
    dias = dados["dias_desde"]
    quando = "hoje" if dias == 0 else "ontem" if dias == 1 else f"há {dias} dias"
    velha = ' style="color:var(--accent)"' if dias >= 30 else ""
    return f"""<div class="saldo">
      <div style="display:flex;justify-content:space-between;align-items:baseline">
        <span class="eyebrow">Saldo API</span>
        <span class="mono" style="font-size:14px">{usd(dados['saldo_usd']).replace(' ', '&nbsp;')}</span>
      </div>
      <div class="barra"><div style="width:{pc:.1f}%"></div></div>
      <span style="font-size:11px;color:var(--faint)"{velha}>anotado {quando}
        · {usd(dados['gasto_desde'])} gastos</span>
    </div>"""


def pagina(corpo: str, ativo: str = "painel", titulo: str | None = None,
           saldo: dict | None = None) -> str:
    """O documento inteiro. `corpo` é o que a tela produziu."""
    tela = POR_SLUG.get(ativo)
    nome = titulo or (tela.rotulo if tela else "my-aide")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(nome)} · my-aide</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=Public+Sans:wght@400;450;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<link rel="stylesheet" href="/app.css">
</head>
<body>
<div class="app">
  <aside class="lateral">
    <a class="marca" href="/"><span class="vivo"></span><span>my-aide</span></a>
    {_nav(ativo)}
    {_saldo(saldo)}
  </aside>
  <main>{corpo}</main>
</div>
</body>
</html>
"""


def cabecalho(titulo: str, sobrancelha: str = "", direita: str = "") -> str:
    return f"""<div class="cabecalho">
      <div>{f'<p class="eyebrow" style="margin-bottom:6px">{escape(sobrancelha)}</p>' if sobrancelha else ''}
        <h1 class="h1">{escape(titulo)}</h1></div>
      {f'<div>{direita}</div>' if direita else ''}
    </div>"""


def em_breve(nome: str) -> str:
    return (f'<div class="card" style="padding:28px 24px">'
            f'<p style="margin:0;color:var(--muted);line-height:1.6">'
            f'A tela <strong>{escape(nome)}</strong> entra numa próxima etapa.</p></div>')
