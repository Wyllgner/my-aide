"""O layout do grafo de notas."""

import math
import time

from aide.web import layout


def _dist(p, a, b):
    return math.hypot(p[a][0] - p[b][0], p[a][1] - p[b][1])


def test_vazio_e_uma_nota():
    assert layout.posicionar([], set()) == {}
    assert layout.posicionar(["a"], set()) == {"a": (0.5, 0.5)}


def test_tudo_fica_entre_zero_e_um():
    nos = [f"n{i}" for i in range(30)]
    arestas = {(f"n{i}", f"n{i + 1}") for i in range(29)}
    for x, y in layout.posicionar(nos, arestas).values():
        assert 0 <= x <= 1 and 0 <= y <= 1


def test_mesmo_vault_mesmo_desenho():
    """Sem sorteio: a nota não muda de lugar entre uma abertura e outra."""
    nos = ["a", "b", "c", "d"]
    arestas = {("a", "b"), ("c", "d")}
    primeiro = layout.posicionar(nos, arestas)
    layout._calcular.cache_clear()
    assert layout.posicionar(list(reversed(nos)), {("b", "a"), ("d", "c")}) == primeiro


def test_ligadas_ficam_mais_perto_que_soltas():
    nos = ["a", "b", "c", "d", "e", "f"]
    arestas = {("a", "b"), ("b", "c"), ("a", "c")}
    p = layout.posicionar(nos, arestas)
    perto = (_dist(p, "a", "b") + _dist(p, "b", "c")) / 2
    longe = (_dist(p, "a", "e") + _dist(p, "c", "f")) / 2
    assert perto < longe


def test_ninguem_fica_em_cima_de_ninguem():
    nos = [f"n{i}" for i in range(40)]
    p = layout.posicionar(nos, set())
    menor = min(_dist(p, a, b) for i, a in enumerate(nos) for b in nos[i + 1:])
    assert menor > 0.01


def test_quinhentas_notas_em_tempo_de_pagina():
    nos = [f"nota {i}" for i in range(500)]
    arestas = {(f"nota {i}", f"nota {(i * 7) % 500}") for i in range(500)} - {("nota 0", "nota 0")}
    layout._calcular.cache_clear()
    inicio = time.perf_counter()
    layout.posicionar(nos, arestas)
    assert time.perf_counter() - inicio < 4


def test_o_segundo_pedido_vem_do_cache():
    nos = [f"m{i}" for i in range(200)]
    layout.posicionar(nos, set())
    inicio = time.perf_counter()
    layout.posicionar(nos, set())
    assert time.perf_counter() - inicio < 0.05
