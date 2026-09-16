"""Gráficos em SVG, escritos à mão.

Sem biblioteca: são quatro formas, e uma dependência de front para desenhar
quatro formas custaria mais em peso e atualização do que o desenho inteiro.

**Todos aparecem mesmo sem dado.** Decisão do dono: um gráfico vazio hoje é o
mesmo gráfico que se preenche com o uso, e isso vale mais do que esconder a
moldura. Vazio não pode parecer quebrado, então cada forma tem um estado
próprio de "ainda não há o que mostrar" — eixo, moldura e legenda continuam
lá, com uma linha dizendo por quê.
"""

from __future__ import annotations

from html import escape

ACENTO = "#C4432B"
TINTA = "#15171C"
FRACO = "#9CA2AD"
TRILHO = "#F0F1F4"

_seq = [0]


def _id(prefixo: str) -> str:
    """Gradiente precisa de id único: dois com o mesmo id na página colidem."""
    _seq[0] += 1
    return f"{prefixo}{_seq[0]}"


def _sem_dado(largura: int, altura: int, texto: str) -> str:
    """A moldura fica; some só o traço. Assim a tela não muda de forma depois."""
    y = altura / 2
    return (f'<svg width="100%" height="{altura}" viewBox="0 0 {largura} {altura}" '
            f'preserveAspectRatio="none" role="img" aria-label="{escape(texto)}">'
            f'<line x1="0" y1="{y}" x2="{largura}" y2="{y}" stroke="{TRILHO}" '
            f'stroke-width="2" stroke-dasharray="4 5"/></svg>'
            f'<p style="margin:6px 0 0;font-size:11.5px;color:{FRACO}">{escape(texto)}</p>')


def area(serie: list[float], largura: int = 600, altura: int = 120,
         vazio: str = "sem uso registrado ainda") -> str:
    """Área com linha. Uma série, um tom — identidade vem do título."""
    if not serie or max(serie) <= 0:
        return _sem_dado(largura, altura, vazio)

    pad = 6
    n = len(serie)
    maximo = max(serie)
    px = (lambda i: pad + i * (largura - 2 * pad) / (n - 1)) if n > 1 else (lambda i: largura / 2)
    def py(v): return altura - pad - (v / maximo) * (altura - 2 * pad)

    pontos = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(serie))
    grad = _id("g")
    ultimo = f'<circle cx="{px(n - 1):.1f}" cy="{py(serie[-1]):.1f}" r="3.5" ' \
             f'fill="{ACENTO}" stroke="#FFF" stroke-width="2"/>'
    return (
        f'<svg width="100%" height="{altura}" viewBox="0 0 {largura} {altura}" role="img">'
        f'<defs><linearGradient id="{grad}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACENTO}" stop-opacity=".16"/>'
        f'<stop offset="1" stop-color="{ACENTO}" stop-opacity="0"/></linearGradient></defs>'
        f'<polygon points="{pad},{altura - pad} {pontos} {largura - pad},{altura - pad}" '
        f'fill="url(#{grad})"/>'
        f'<polyline points="{pontos}" fill="none" stroke="{ACENTO}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>{ultimo}</svg>')


def colunas(pares: list[tuple[str, float]], largura: int = 600, altura: int = 96,
            vazio: str = "nada neste período") -> str:
    """Barras verticais com rótulo embaixo. Coluna zerada fica como traço."""
    if not pares:
        return _sem_dado(largura, altura, vazio)

    maximo = max(v for _, v in pares) or 1
    vago = 4
    n = len(pares)
    bw = (largura - vago * (n - 1)) / n
    corpo = ""
    for i, (rotulo, valor) in enumerate(pares):
        h = (valor / maximo) * (altura - 18) if valor else 2
        x = i * (bw + vago)
        cor = ACENTO if valor else TRILHO
        opac = f"{0.45 + 0.55 * valor / maximo:.2f}" if valor else "1"
        corpo += (
            f'<rect x="{x:.1f}" y="{altura - 15 - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
            f'rx="3" fill="{cor}" opacity="{opac}"><title>{escape(rotulo)}: {valor:g}</title></rect>'
            f'<text x="{x + bw / 2:.1f}" y="{altura - 3}" text-anchor="middle" font-size="9" '
            f'fill="{FRACO}" font-family="IBM Plex Mono, monospace">{escape(rotulo)}</text>')
    return (f'<svg width="100%" height="{altura}" viewBox="0 0 {largura} {altura}" '
            f'role="img">{corpo}</svg>')


def barras(pares: list[tuple[str, float]], rotulo_px: int = 96,
           vazio: str = "nada registrado ainda") -> str:
    """Barras horizontais. Rótulo ao lado, valor no fim — nunca cor sozinha."""
    if not pares:
        return f'<p style="margin:0;font-size:12.5px;color:{FRACO}">{escape(vazio)}</p>'

    maximo = max(v for _, v in pares) or 1
    linhas = ""
    for nome, valor in pares:
        pc = valor / maximo * 100
        opac = 0.35 + 0.65 * valor / maximo
        linhas += (
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<span style="width:{rotulo_px}px;flex-shrink:0;font-size:12.5px;'
            f'color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap"'
            f' title="{escape(nome)}">{escape(nome)}</span>'
            f'<div style="flex:1;height:16px;background:{TRILHO};border-radius:5px;overflow:hidden">'
            f'<div style="width:{pc:.1f}%;height:100%;background:{ACENTO};'
            f'opacity:{opac:.2f};border-radius:5px"></div></div>'
            f'<span class="mono" style="width:38px;text-align:right;font-size:12.5px">'
            f'{valor:g}</span></div>')
    return f'<div style="display:flex;flex-direction:column;gap:7px">{linhas}</div>'


def anel(fracao: float, rotulo: str, tamanho: int = 92) -> str:
    """Proporção de duas partes. O número vai no meio — a cor não carrega o dado."""
    import math

    r = tamanho / 2 - 7
    volta = 2 * math.pi * r
    fracao = max(0.0, min(fracao, 1.0))
    return (
        f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 {tamanho} {tamanho}" role="img">'
        f'<circle cx="{tamanho/2}" cy="{tamanho/2}" r="{r}" fill="none" stroke="{TRILHO}" stroke-width="8"/>'
        f'<circle cx="{tamanho/2}" cy="{tamanho/2}" r="{r}" fill="none" stroke="{ACENTO}" '
        f'stroke-width="8" stroke-linecap="round" '
        f'stroke-dasharray="{volta * fracao:.1f} {volta:.1f}" '
        f'transform="rotate(-90 {tamanho/2} {tamanho/2})"/>'
        f'<text x="{tamanho/2}" y="{tamanho/2 + 5}" text-anchor="middle" font-size="15" '
        f'fill="{TINTA}" font-family="IBM Plex Mono, monospace">{escape(rotulo)}</text></svg>')
