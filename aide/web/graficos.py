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

# Séries com identidade (débito e crédito, as tags). Ordem fixa, validada para
# daltonismo contra a superfície clara; a cor segue a entidade, nunca a posição.
# Três delas têm contraste baixo com o fundo, por isso todo gráfico que as usa
# leva legenda com o valor escrito: a cor nunca carrega o número sozinha.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7")
DEBITO, CREDITO = SERIES[0], SERIES[1]
RESTO = "#C9CDD4"   # "sem tag" e "outras": o que não tem identidade própria

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


def _eixo(rotulos: list[str], passo: int = 1) -> str:
    """Rótulos sob o gráfico, distribuídos como as colunas ficam.

    Com muitos pontos eles se encavalam, então só um a cada `passo` aparece —
    melhor um eixo esparso e legível que um borrão de números.
    """
    celulas = "".join(
        f'<span class="mono" style="flex:1;text-align:center;font-size:9px;'
        f'color:{FRACO}">{escape(r) if i % passo == 0 else ""}</span>'
        for i, r in enumerate(rotulos))
    return f'<div style="display:flex;margin-top:2px">{celulas}</div>'


def area(pares: list[tuple[str, float]], largura: int = 600, altura: int = 96,
         vazio: str = "sem uso registrado ainda") -> str:
    """Área com linha e eixo de rótulos. Uma série, um tom.

    A altura é modesta de propósito: uma série quase toda em zero com muito
    espaço em cima vira um cartão vazio com um risco no pé.
    """
    rotulos = [r for r, _ in pares]
    serie = [v for _, v in pares]
    if not serie or max(serie) <= 0:
        return _sem_dado(largura, altura, vazio) + (_eixo(rotulos, 2) if rotulos else "")

    pad = 6
    n = len(serie)
    maximo = max(serie)
    px = (lambda i: pad + i * (largura - 2 * pad) / (n - 1)) if n > 1 else (lambda i: largura / 2)
    def py(v): return altura - pad - (v / maximo) * (altura - 2 * pad)

    pontos = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(serie))
    grad = _id("g")
    marcas = "".join(
        f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="2.5" fill="{ACENTO}" '
        f'opacity=".55"><title>{escape(r)}: {v:g}</title></circle>'
        for i, (r, v) in enumerate(pares) if v)
    ultimo = f'<circle cx="{px(n - 1):.1f}" cy="{py(serie[-1]):.1f}" r="3.5" ' \
             f'fill="{ACENTO}" stroke="#FFF" stroke-width="2"/>'
    svg = (
        f'<svg width="100%" height="{altura}" viewBox="0 0 {largura} {altura}" role="img" '
        f'preserveAspectRatio="none">'
        f'<defs><linearGradient id="{grad}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACENTO}" stop-opacity=".16"/>'
        f'<stop offset="1" stop-color="{ACENTO}" stop-opacity="0"/></linearGradient></defs>'
        f'<polygon points="{pad},{altura - pad} {pontos} {largura - pad},{altura - pad}" '
        f'fill="url(#{grad})"/>'
        f'<polyline points="{pontos}" fill="none" stroke="{ACENTO}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>{marcas}{ultimo}</svg>')
    return svg + _eixo(rotulos, 2 if n > 10 else 1)


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
           vazio: str = "nada registrado ainda", formatar=None) -> str:
    """Barras horizontais. Rótulo ao lado, valor no fim — nunca cor sozinha.

    `formatar` existe porque o padrão escreve 0.0406 com ponto, e a página
    inteira escreve vírgula: o número destoar do resto é o mesmo defeito que
    escrever a data em inglês.
    """
    escrever = formatar or (lambda v: f"{v:g}")
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
            f'<span class="mono" style="white-space:nowrap;text-align:right;'
            f'font-size:12.5px">{escape(escrever(valor))}</span></div>')
    return f'<div style="display:flex;flex-direction:column;gap:7px">{linhas}</div>'


# cores de estado do medidor: o número sempre acompanha, a cor só reforça
ALERTA = "#C4432B"
ATENCAO = "#B8860B"
CALMA = "#3F7A54"


def medidores(linhas: list[dict], rotulo_px: int = 104,
              vazio: str = "nenhum teto declarado", ritmo: float | None = None) -> str:
    """Barras contra uma **meta**, não contra o maior valor da série.

    `barras()` normaliza pelo maior item, o que responde "qual é o maior". Teto é
    outra pergunta: quanto falta para passar. Aqui cada linha tem escala própria,
    o traço marca 100% e o que passa do teto aparece em cor distinta — com o
    número ao lado, porque cor sozinha não carrega dado.

    Cada linha: {rotulo, valor, meta, texto}.
    """
    if not linhas:
        return f'<p style="margin:0;font-size:12.5px;color:{FRACO}">{escape(vazio)}</p>'

    html = ""
    for linha in linhas:
        meta = linha["meta"] or 1
        fracao = linha["valor"] / meta
        cor = ALERTA if fracao > 1 else ATENCAO if fracao >= 0.8 else CALMA
        # a barra para em 100%: o excesso vira cor e número, não uma barra que
        # estoura a coluna e desalinha as outras
        largura = min(fracao, 1.0) * 100
        # onde o gasto estaria hoje se o teto fosse gasto por igual no mês:
        # passar do traço antes do fim do mês é o aviso que chega cedo
        marca_ritmo = "" if ritmo is None else (
            f'<span title="ritmo do mês: {ritmo * 100:.0f}%" style="position:absolute;'
            f'left:calc({ritmo * 100:.1f}% - 1px);top:-2px;bottom:-2px;width:2px;'
            f'background:{TINTA};opacity:.55"></span>')
        html += (
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<span style="width:{rotulo_px}px;flex-shrink:0;font-size:12.5px;'
            f'color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap"'
            f' title="{escape(linha["rotulo"])}">{escape(linha["rotulo"])}</span>'
            f'<div style="flex:1;height:16px;background:{TRILHO};border-radius:5px;'
            f'position:relative;overflow:hidden">'
            f'<div style="width:{largura:.1f}%;height:100%;background:{cor};'
            f'border-radius:5px"></div>'
            f'<span style="position:absolute;right:0;top:0;bottom:0;width:2px;'
            f'background:{TINTA};opacity:.16"></span>{marca_ritmo}</div>'
            f'<span class="mono" style="white-space:nowrap;text-align:right;font-size:12.5px;'
            f'color:{cor if fracao >= 0.8 else "var(--ink)"}">'
            f'{escape(linha["texto"])}</span></div>')
    return f'<div style="display:flex;flex-direction:column;gap:7px">{html}</div>'


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


def legenda(itens: list[tuple[str, str, str]]) -> str:
    """[(nome, cor, valor)]. Nome e valor em tinta; a cor só no quadradinho."""
    if not itens:
        return ""
    partes = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;white-space:nowrap">'
        f'<span style="width:9px;height:9px;border-radius:2px;background:{cor};'
        f'flex-shrink:0"></span>'
        f'<span style="color:var(--muted)">{escape(nome)}</span>'
        f'<span class="mono" style="color:var(--ink)">{escape(valor)}</span></span>'
        for nome, cor, valor in itens)
    return (f'<div style="display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:10px;'
            f'font-size:12px">{partes}</div>')


def colunas_empilhadas(rotulos: list[str], series: list[tuple[str, str, list[float]]],
                       largura: int = 600, altura: int = 110, vazio: str = "nada neste período",
                       formatar=None) -> str:
    """Colunas com partes empilhadas: [(nome, cor, valores)], a primeira embaixo.

    Uma folga de 2px separa as partes, para a divisa não depender da cor. Passar
    o mouse mostra o dia com cada parte e o total.
    """
    escrever = formatar or (lambda v: f"{v:g}")
    totais = [sum(serie[2][i] for serie in series) for i in range(len(rotulos))]
    if not rotulos or max(totais, default=0) <= 0:
        return _sem_dado(largura, altura, vazio) + (_eixo(rotulos, 2) if rotulos else "")

    maximo = max(totais)
    n = len(rotulos)
    vago = 3 if n > 20 else 5
    bw = (largura - vago * (n - 1)) / n
    util = altura - 4
    corpo = ""
    for i, rotulo in enumerate(rotulos):
        x = i * (bw + vago)
        if not totais[i]:
            corpo += (f'<rect x="{x:.1f}" y="{altura - 2}" width="{bw:.1f}" height="2" '
                      f'rx="1" fill="{TRILHO}"/>')
            continue
        base = altura
        dica = f"{rotulo}: " + " · ".join(
            f"{nome} {escrever(valores[i])}" for nome, _, valores in series if valores[i])
        dica += f" · total {escrever(totais[i])}" if len([s for s in series if s[2][i]]) > 1 else ""
        for nome, cor, valores in series:
            v = valores[i]
            if not v:
                continue
            h = max(v / maximo * util, 2)
            y = base - h
            corpo += (f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                      f'rx="2" fill="{cor}"/>')
            base = y - 2
        # alvo do mouse do tamanho da coluna inteira, não da parte
        corpo += (f'<rect x="{x:.1f}" y="0" width="{bw:.1f}" height="{altura}" '
                  f'fill="transparent"><title>{escape(dica)}</title></rect>')
    return (f'<svg width="100%" height="{altura}" viewBox="0 0 {largura} {altura}" '
            f'preserveAspectRatio="none" role="img">{corpo}</svg>'
            + _eixo(rotulos, 2 if n > 14 else 1))


def barras_empilhadas(linhas: list[tuple[str, list[tuple[str, str, float]]]],
                      rotulo_px: int = 104, vazio: str = "nada registrado ainda",
                      formatar=None) -> str:
    """Uma barra por linha, dividida em partes: [(rótulo, [(parte, cor, valor)])].

    A escala é a da maior linha, como `barras()`: responde qual é a maior e, de
    dentro dela, de onde veio. O total vai escrito no fim.
    """
    escrever = formatar or (lambda v: f"{v:g}")
    if not linhas:
        return f'<p style="margin:0;font-size:12.5px;color:{FRACO}">{escape(vazio)}</p>'

    maximo = max(sum(v for _, _, v in partes) for _, partes in linhas) or 1
    html = ""
    for rotulo, partes in linhas:
        total = sum(v for _, _, v in partes)
        segmentos = "".join(
            f'<div title="{escape(nome)}: {escape(escrever(v))}" '
            f'style="width:{v / maximo * 100:.2f}%;height:100%;background:{cor};'
            f'border-radius:3px;flex-shrink:0"></div>'
            for nome, cor, v in partes if v)
        html += (
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'<span style="width:{rotulo_px}px;flex-shrink:0;font-size:12.5px;'
            f'color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap"'
            f' title="{escape(rotulo)}">{escape(rotulo)}</span>'
            f'<div style="flex:1;height:16px;display:flex;gap:2px;background:{TRILHO};'
            f'border-radius:5px;overflow:hidden">{segmentos}</div>'
            f'<span class="mono" style="white-space:nowrap;text-align:right;'
            f'font-size:12.5px">{escape(escrever(total))}</span></div>')
    return f'<div style="display:flex;flex-direction:column;gap:7px">{html}</div>'
