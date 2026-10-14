"""O grafo das notas desenhado em SVG, no servidor.

Cada nota é um círculo clicável, maior quanto mais ligada; cada link é uma
linha fina. Desenho é um cartão com a miniatura da própria prévia — no meio
de círculos, o que é desenho se vê de longe e se reconhece de perto (o mouse
amplia) —, e a ligação com ele é tracejada. Desenho privado mostra um
cadeado em vez da imagem: o grafo é a visão de tudo de uma vez. Nome escrito só nas mais ligadas — escrever todos vira mancha —,
e todas têm o nome ao passar o mouse. Órfã em cinza: o que importa nela é
justamente não ter ligação.

Desenhado aqui e não por uma biblioteca no navegador: a página só roda o
próprio script, e a posição já vem pronta de `layout.py`. O `/app.js` só
cuida de arrastar, dar zoom e destacar as vizinhas de quem está sob o mouse.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from html import escape
from urllib.parse import quote

from aide.web import layout
from aide.web.graficos import ACENTO, FRACO
from aide.web.icones import TRACOS
from aide.web.markdown import href_da_nota

LARGURA, ALTURA, MARGEM = 1000, 640, 40
ROTULOS = 24  # quantas das mais ligadas ganham o nome escrito
COM_DESENHO = ' class="com-desenho"'
# quanto o cartão do desenho cresce sob o mouse; o CSS usa o mesmo número
AMPLIACAO = 2.6


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


def _ancora(x: float, y: float, largura: int, altura: int) -> tuple[float, float]:
    """De onde o cartão cresce, em fração dele (0 a 1): perto de uma borda do
    grafo ele cresce para dentro, senão pelo meio. Ampliado na borda, metade
    dele e o nome ficavam fora do quadro."""
    def eixo(posicao: float, total: int) -> float:
        fracao = posicao / total
        return 0.0 if fracao < 0.3 else 1.0 if fracao > 0.7 else 0.5
    return eixo(x, largura), eixo(y, altura)


def _cartao(no: str, x: float, y: float, largura: float, altura: float,
            assinatura: str | None, privado: bool,
            ancora: tuple[float, float] = (0.5, 0.5)) -> str:
    """O desenho no grafo: a miniatura da prévia num cartão; sem prévia, o
    lápis; privado, o cadeado — nunca a imagem."""
    x0, y0 = x - largura / 2, y - altura / 2
    moldura = (f'<rect class="moldura" x="{x0:.1f}" y="{y0:.1f}" width="{largura:.1f}"'
               f' height="{altura:.1f}" rx="3"/>')
    if assinatura and not privado:
        # a assinatura no endereço troca a imagem quando o desenho muda
        src = f"/api/desenhos/previa?caminho={quote(no, safe='/')}&v={quote(assinatura)}"
        miolo = (f'<image href="{escape(src)}" x="{x0 + 2:.1f}" y="{y0 + 2:.1f}"'
                 f' width="{largura - 4:.1f}" height="{altura - 4:.1f}"'
                 f' preserveAspectRatio="xMidYMid meet"/>')
    else:
        escala = altura * 0.62 / 20
        icone = TRACOS["privada" if privado else "desenho"]
        miolo = (f'<path class="icone" d="{icone}" transform="translate({x - 10 * escala:.1f}'
                 f' {y - 10 * escala:.1f}) scale({escala:.3f})"/>')
    origem = f"{ancora[0] * 100:.0f}% {ancora[1] * 100:.0f}%"
    return f'<g class="cartao" style="transform-origin:{origem}">{moldura}{miolo}</g>'


def desenhar(nos: list[str], arestas: set[tuple[str, str]], aberto: str | None = None,
             classe: str = "grafo", largura: int = LARGURA, altura: int = ALTURA,
             previa: Callable[[str], str | None] | None = None,
             privado: Callable[[str], bool] | None = None) -> str:
    """`largura` e `altura` são as do desenho, não as da tela: o grafo local,
    que ocupa um terço da largura, desenha num espaço menor para que o texto
    e os círculos não encolham até sumir.

    `previa(caminho)` dá a assinatura da prévia de um desenho (ou None), e
    `privado(caminho)` se ele é privado; sem elas, todo desenho sai com o
    lápis, que é o caso seguro."""
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

    def cartao(no: str) -> tuple[float, float]:
        """Largura e altura do cartão de um desenho: cresce com as ligações,
        como o círculo, mas parte de um tamanho em que a miniatura se lê."""
        lado = 30 + 7 * math.sqrt(grau[no])
        return lado, lado * 0.72

    def meia_altura(no: str) -> float:
        return cartao(no)[1] / 2 if _desenho(no) else raio(no)

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
        caixa = (x - meia, y + meia_altura(no) + 1, x + meia, y + meia_altura(no) + 15)
        if any(caixa[0] < c[2] and c[0] < caixa[2] and caixa[1] < c[3] and c[1] < caixa[3]
               for c in caixas):
            continue
        caixas.append(caixa)
        com_nome.add(no)

    # a ligação com desenho é tracejada: citar uma imagem não é o mesmo que
    # ligar duas ideias
    linhas = "".join(
        f'<line x1="{xy(a)[0]:.1f}" y1="{xy(a)[1]:.1f}" x2="{xy(b)[0]:.1f}" y2="{xy(b)[1]:.1f}"'
        f' data-a="{ids[a]}" data-b="{ids[b]}"'
        f'{COM_DESENHO if _desenho(a) or _desenho(b) else ""}/>'
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
        # o nome do desenho acompanha a borda de baixo do cartão ampliado, em
        # vez de ficar por cima da imagem: anda o que o centro e a base andaram
        desce = ""
        if _desenho(no):
            ancora = _ancora(x, y, largura, altura)
            lado, alto = cartao(no)
            anda_x = (0.5 - ancora[0]) * lado * (AMPLIACAO - 1)
            anda_y = (1 - ancora[1]) * alto * (AMPLIACAO - 1)
            desce = f' style="--anda:{anda_x:.1f}px;--desce:{anda_y:.1f}px"'
        rotulo = (f'<text x="{x:.1f}" y="{y + meia_altura(no) + 12:.1f}"{extra}{desce}>'
                  f'{escape(_nome(no))}</text>')
        e_privado = False
        if _desenho(no):
            classe_no += " desenho"
            e_privado = bool(privado and privado(no))
            # sem ligação o cartão fica cinza, como a nota órfã
            classe_no += "" if grau[no] else " solto"
            forma = _cartao(no, x, y, *cartao(no),
                            previa(no) if previa else None, e_privado, ancora)
        else:
            forma = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{cor}"/>'
        circulos += (
            f'<a href="{escape(_href(no, aberto))}" class="{classe_no}" data-id="{ids[no]}"'
            f' data-vizinhos="{" ".join(ids[v] for v in sorted(vizinhos[no]))}">'
            f'<title>{escape(_nome(no))} · {escape(no)}'
            f'{" · desenho" if _desenho(no) else ""}{" privado" if e_privado else ""}'
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
            for lig in [*mapa.ligacoes, *mapa.desenhos, *mapa.de_desenhos,
                        *mapa.entre_desenhos]
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
