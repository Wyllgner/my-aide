"""Os números do painel do vault."""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from aide.web import visao
from aide.web.markdown import etiquetas

FUSO = ZoneInfo("America/Porto_Velho")
AGORA = datetime(2026, 10, 8, 12, 0, tzinfo=FUSO)


@pytest.fixture
def raiz(tmp_path):
    pasta = tmp_path / "vault"
    arquivos = {
        "Inbox/Reunião.md": "---\ntags: [trabalho]\n---\n\nver [[Telhado]] e [[Telhado]] #urgente",
        "Projetos/Telhado.md": "volta para [[Reunião]] e [[Telhado]] #Trabalho #casa",
        "Projetos/Obra.md": "[[Telhado]] e [[Nada]]",
        "Solta.md": "uma nota sozinha com cinco palavras",
        "Só para si.md": "[[Só para si]]",
    }
    for caminho, texto in arquivos.items():
        (pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
        (pasta / caminho).write_text(texto)
        momento = (AGORA - timedelta(days=2)).timestamp()
        os.utime(pasta / caminho, (momento, momento))
    return pasta


@pytest.fixture
def v(raiz):
    return visao.montar(raiz, AGORA, dias=7)


def test_contagens(v):
    assert v.notas == 5
    assert v.quebrados == 1
    # Reunião->Telhado, Telhado->Reunião, Obra->Telhado: links repetidos e para si não somam
    assert v.ligacoes == 3


def test_orfas_sao_as_sem_link_para_nem_de_ninguem(v):
    """Link para si mesma não tira a nota da solidão."""
    assert v.orfas == ["Solta.md", "Só para si.md"]


def test_mais_citadas_contam_notas_e_nao_links(v):
    assert v.mais_citadas[0] == ("Projetos/Telhado.md", 2)


def test_tags_juntam_frontmatter_e_texto_sem_caixa(v):
    assert v.tags == [("trabalho", 2), ("casa", 1), ("urgente", 1)]


def test_atividade_dos_ultimos_dias(v):
    assert len(v.atividade) == 7
    assert v.atividade[-1] == ("2026-10-08", 0)
    assert v.atividade[-3] == ("2026-10-06", 5)


def test_palavras_nao_contam_o_frontmatter(raiz):
    (raiz / "Solta.md").write_text("---\ntitle: muitas palavras aqui no topo\n---\n\num dois")
    assert visao.montar(raiz, AGORA).palavras < 30


def test_vault_vazio(tmp_path):
    v = visao.montar(tmp_path / "nada", AGORA, dias=3)
    assert (v.notas, v.orfas, v.tags) == (0, [], [])
    assert [n for _, n in v.atividade] == [0, 0, 0]


# ---------- tags ----------

@pytest.mark.parametrize("texto, tags", [
    ("#casa e #projeto/telhado", ["casa", "projeto/telhado"]),
    ("#2024 não é tag, #2024a é", ["2024a"]),
    ("e-mail a@b.com#x e url http://x.org/#ancora", []),
    ("`#codigo` e\n\n```\n#bloco\n```", []),
    ("# Título não é tag", []),
    ("#ação e #Ação", ["ação"]),
    ("---\ntags: [a, #b,  c ]\n---\n", ["a", "b", "c"]),
    ("---\ntags: x, y\n---\n#x", ["x", "y"]),
])
def test_etiquetas(texto, tags):
    assert etiquetas(texto) == tags


@pytest.mark.parametrize("texto, tags", [
    ("---\ntags:\n  - casa\n  - projeto/telhado\n---\n", ["casa", "projeto/telhado"]),
    ("---\ntag: solta\n---\n", ["solta"]),
    ('---\ntags: "[a, b]"\n---\n', ["a", "b"]),
])
def test_etiquetas_no_formato_do_obsidian(texto, tags):
    assert etiquetas(texto) == tags
