"""Onde cada nota fica no desenho do grafo.

Força dirigida (Fruchterman–Reingold): toda nota empurra as outras, todo link
puxa as duas pontas, e uma gravidade fraca segura as órfãs perto do centro em
vez de deixá-las fugir para a borda. Três escolhas:

- **Sempre o mesmo desenho.** A posição inicial sai de um hash do caminho, não
  de um sorteio: o mesmo vault desenha igual em toda abertura, e a nota que
  você achou "lá em cima à direita" continua lá.
- **Repulsão só entre vizinhas.** Comparar cada nota com todas é n²; numa
  grade de células, cada uma só empurra quem está nas células em volta. Nota
  longe já não empurra quase nada mesmo.
- **Desenho guardado.** Enquanto as notas e os links forem os mesmos, o
  resultado volta do cache; só uma mudança de estrutura recalcula.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

Posicoes = dict[str, tuple[float, float]]


def _semente(caminho: str) -> tuple[float, float]:
    digest = hashlib.sha256(caminho.encode()).digest()
    return (int.from_bytes(digest[:4], "big") / 2**32,
            int.from_bytes(digest[4:8], "big") / 2**32)


def posicionar(nos: list[str], arestas: set[tuple[str, str]],
               iteracoes: int | None = None) -> Posicoes:
    """Posição de cada nota em [0, 1] x [0, 1]."""
    chave = (tuple(sorted(nos)), tuple(sorted(tuple(sorted(a)) for a in arestas)))
    return dict(_calcular(chave, iteracoes))


@lru_cache(maxsize=8)
def _calcular(chave, iteracoes: int | None) -> tuple[tuple[str, tuple[float, float]], ...]:
    nos, arestas = chave
    n = len(nos)
    if n == 0:
        return ()
    if n == 1:
        return ((nos[0], (0.5, 0.5)),)

    lado = math.sqrt(n)
    k = 1.0  # distância ideal entre duas notas ligadas
    pos = {no: [x * lado * 2, y * lado * 2] for no in nos for x, y in [_semente(no)]}
    iteracoes = iteracoes or max(40, min(200, 12000 // n))
    temperatura = lado
    celula = 3 * k

    for passo in range(iteracoes):
        desloc = {no: [0.0, 0.0] for no in nos}

        grade: dict[tuple[int, int], list[str]] = {}
        for no, (x, y) in pos.items():
            grade.setdefault((int(x // celula), int(y // celula)), []).append(no)
        for (cx, cy), presentes in grade.items():
            vizinhos = [o for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                        for o in grade.get((cx + dx, cy + dy), ())]
            for a in presentes:
                ax, ay = pos[a]
                for b in vizinhos:
                    if a == b:
                        continue
                    dx, dy = ax - pos[b][0], ay - pos[b][1]
                    dist = math.hypot(dx, dy) or 0.01
                    forca = k * k / dist
                    desloc[a][0] += dx / dist * forca
                    desloc[a][1] += dy / dist * forca

        for a, b in arestas:
            dx, dy = pos[a][0] - pos[b][0], pos[a][1] - pos[b][1]
            dist = math.hypot(dx, dy) or 0.01
            forca = dist * dist / k
            desloc[a][0] -= dx / dist * forca
            desloc[a][1] -= dy / dist * forca
            desloc[b][0] += dx / dist * forca
            desloc[b][1] += dy / dist * forca

        cx = sum(p[0] for p in pos.values()) / n
        cy = sum(p[1] for p in pos.values()) / n
        for no, (x, y) in pos.items():
            # gravidade: as órfãs ficam por perto em vez de irem para a borda
            dx_, dy_ = desloc[no][0] - (x - cx) * 0.05, desloc[no][1] - (y - cy) * 0.05
            mod = math.hypot(dx_, dy_) or 0.01
            passo_max = min(mod, temperatura)
            pos[no][0] += dx_ / mod * passo_max
            pos[no][1] += dy_ / mod * passo_max
        temperatura = lado * (1 - (passo + 1) / iteracoes) + 0.01

    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    largura = (max(xs) - min(xs)) or 1
    altura = (max(ys) - min(ys)) or 1
    escala = max(largura, altura)  # mesma escala nos dois eixos: o desenho não estica
    return tuple((no, ((x - min(xs)) / escala + (1 - largura / escala) / 2,
                       (y - min(ys)) / escala + (1 - altura / escala) / 2))
                 for no, (x, y) in pos.items())
