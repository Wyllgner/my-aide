"""O grafo das notas desenhado em SVG, no servidor.

Cada nota é um círculo clicável, maior quanto mais ligada; cada link é uma
linha fina. Nome escrito só nas mais ligadas — escrever todos vira mancha —,
e todas têm o nome ao passar o mouse. Órfã em cinza: o que importa nela é
justamente não ter ligação.

Desenhado aqui e não por uma biblioteca no navegador: a página só roda o
próprio script, e a posição já vem pronta de `layout.py`. O `/app.js` só
cuida de arrastar, dar zoom e destacar as vizinhas de quem está sob o mouse.
"""

from __future__ import annotations

import math
from html import escape

from aide.web import layout
from aide.web.graficos import ACENTO, FRACO
from aide.web.markdown import href_da_nota

LARGURA, ALTURA, MARGEM = 1000, 640, 40
ROTULOS = 24  # quantas das mais ligadas ganham o nome escrito


def _nome(caminho: str) -> str:
    return caminho.rpartition("/")[2].removesuffix(".md")


def desenhar(nos: list[str], arestas: set[tuple[str, str]], aberto: str | None = None) -> str:
    if not nos:
        return '<p class="vazio">Nenhuma nota para desenhar ainda.</p>'
    posicoes = layout.posicionar(nos, arestas)
    grau = {no: 0 for no in nos}
    vizinhos: dict[str, set[str]] = {no: set() for no in nos}
    for a, b in arestas:
        grau[a] += 1
        grau[b] += 1
        vizinhos[a].add(b)
        vizinhos[b].add(a)
    ids = {no: f"n{i}" for i, no in enumerate(sorted(nos))}

    def xy(no: str) -> tuple[float, float]:
        x, y = posicoes[no]
        return (MARGEM + x * (LARGURA - 2 * MARGEM), MARGEM + y * (ALTURA - 2 * MARGEM))

    def raio(no: str) -> float:
        return 4 + 2.2 * math.sqrt(grau[no])

    # nome escrito por ordem de importância, pulando o que cairia em cima de
    # um já escrito: dois nomes encavalados não se leem nenhum dos dois
    com_nome: set[str] = set()
    caixas: list[tuple[float, float, float, float]] = []
    prioridade = sorted(nos, key=lambda n: (n != aberto, -grau[n], n.casefold()))
    for no in prioridade[:ROTULOS * 2]:
        if len(com_nome) >= ROTULOS and no != aberto:
            break
        x, y = xy(no)
        meia = len(_nome(no)) * 3.2 + 3
        caixa = (x - meia, y + raio(no) + 1, x + meia, y + raio(no) + 15)
        if any(caixa[0] < c[2] and c[0] < caixa[2] and caixa[1] < c[3] and c[1] < caixa[3]
               for c in caixas):
            continue
        caixas.append(caixa)
        com_nome.add(no)

    linhas = "".join(
        f'<line x1="{xy(a)[0]:.1f}" y1="{xy(a)[1]:.1f}" x2="{xy(b)[0]:.1f}" y2="{xy(b)[1]:.1f}"'
        f' data-a="{ids[a]}" data-b="{ids[b]}"/>'
        for a, b in sorted(arestas))
    circulos = ""
    for no in sorted(nos, key=lambda n: grau[n]):  # as mais ligadas por cima
        x, y = xy(no)
        r = raio(no)
        cor = ACENTO if grau[no] else FRACO
        classe = "no atual" if no == aberto else "no"
        # todas têm o nome; as que não couberam só o mostram quando são
        # vizinhas da nota sob o mouse
        extra = "" if no in com_nome else ' class="so-perto"'
        rotulo = f'<text x="{x:.1f}" y="{y + r + 12:.1f}"{extra}>{escape(_nome(no))}</text>'
        circulos += (
            f'<a href="{escape(href_da_nota(no))}" class="{classe}" data-id="{ids[no]}"'
            f' data-vizinhos="{" ".join(ids[v] for v in sorted(vizinhos[no]))}">'
            f'<title>{escape(_nome(no))} · {escape(no)}'
            f'{f" · {grau[no]} ligações" if grau[no] != 1 else " · 1 ligação"}</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{cor}"/>{rotulo}</a>')
    return (f'<svg class="grafo" viewBox="0 0 {LARGURA} {ALTURA}" role="img"'
            f' aria-label="grafo de {len(nos)} notas e {len(arestas)} ligações">'
            f'<g class="arestas">{linhas}</g><g class="nos">{circulos}</g></svg>')


def do_mapa(mapa, nos: list[str]) -> set[tuple[str, str]]:
    """As ligações entre notas diferentes, sem direção e sem repetição."""
    validos = set(nos)
    return {tuple(sorted((lig.origem, lig.destino))) for lig in mapa.ligacoes
            if lig.destino is not None and lig.destino != lig.origem
            and lig.origem in validos and lig.destino in validos}
