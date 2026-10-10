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
from urllib.parse import quote

from aide.web import layout
from aide.web.graficos import ACENTO, FRACO
from aide.web.markdown import href_da_nota

LARGURA, ALTURA, MARGEM = 1000, 640, 40
ROTULOS = 24  # quantas das mais ligadas ganham o nome escrito


def _nome(caminho: str) -> str:
    return caminho.rpartition("/")[2].removesuffix(".md").removesuffix(".excalidraw")


def _desenho(caminho: str) -> bool:
    return caminho.endswith(".excalidraw")


def _contagem(nos: list[str]) -> str:
    desenhos = sum(1 for no in nos if _desenho(no))
    texto = f"{len(nos) - desenhos} notas"
    return texto + (f" e {desenhos} desenhos" if desenhos else "")


def _href(no: str, aberto: str | None) -> str:
    """Nota abre nas notas; desenho na tela dele, voltando para a nota aberta."""
    if not _desenho(no):
        return href_da_nota(no)
    href = "/desenho?caminho=" + quote(no, safe="/")
    if aberto and aberto.endswith(".md"):
        href += "&de=" + quote(aberto, safe="/")
    return href


def desenhar(nos: list[str], arestas: set[tuple[str, str]], aberto: str | None = None,
             classe: str = "grafo", largura: int = LARGURA, altura: int = ALTURA) -> str:
    """`largura` e `altura` são as do desenho, não as da tela: o grafo local,
    que ocupa um terço da largura, desenha num espaço menor para que o texto
    e os círculos não encolham até sumir."""
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
        return (MARGEM + x * (largura - 2 * MARGEM), MARGEM + y * (altura - 2 * MARGEM))

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
        classe_no = "no atual" if no == aberto else "no"
        # todas têm o nome; as que não couberam só o mostram quando são
        # vizinhas da nota sob o mouse
        extra = "" if no in com_nome else ' class="so-perto"'
        rotulo = f'<text x="{x:.1f}" y="{y + r + 12:.1f}"{extra}>{escape(_nome(no))}</text>'
        if _desenho(no):
            # desenho é um quadrado: no meio das notas, a forma diz o que é
            classe_no += " desenho"
            forma = (f'<rect x="{x - r:.1f}" y="{y - r:.1f}" width="{2 * r:.1f}"'
                     f' height="{2 * r:.1f}" rx="2" fill="{cor}"/>')
        else:
            forma = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{cor}"/>'
        circulos += (
            f'<a href="{escape(_href(no, aberto))}" class="{classe_no}" data-id="{ids[no]}"'
            f' data-vizinhos="{" ".join(ids[v] for v in sorted(vizinhos[no]))}">'
            f'<title>{escape(_nome(no))} · {escape(no)}'
            f'{" · desenho" if _desenho(no) else ""}'
            f'{f" · {grau[no]} ligações" if grau[no] != 1 else " · 1 ligação"}</title>'
            f'{forma}{rotulo}</a>')
    return (f'<svg class="{escape(classe)}" viewBox="0 0 {largura} {altura}" role="img"'
            f' aria-label="grafo de {_contagem(nos)} e {len(arestas)} ligações">'
            f'<g class="arestas">{linhas}</g><g class="nos">{circulos}</g></svg>')


def do_mapa(mapa, nos: list[str]) -> set[tuple[str, str]]:
    """As ligações entre notas diferentes, sem direção e sem repetição; com
    os desenhos em `nos`, também as de nota para desenho."""
    validos = set(nos)
    return {tuple(sorted((lig.origem, lig.destino)))
            for lig in [*mapa.ligacoes, *mapa.desenhos]
            if lig.destino is not None and lig.destino != lig.origem
            and lig.origem in validos and lig.destino in validos}


def vizinhanca(arestas: set[tuple[str, str]], centro: str,
               saltos: int = 1) -> tuple[list[str], set[tuple[str, str]]]:
    """A nota e as que estão a até `saltos` ligações dela, com os links entre
    elas — inclusive entre duas vizinhas, que é o que mostra o assunto."""
    perto = {centro}
    for _ in range(saltos):
        perto |= {b for a, b in arestas if a in perto} | {a for a, b in arestas if b in perto}
    return sorted(perto), {(a, b) for a, b in arestas if a in perto and b in perto}
