"""O desenho do grafo de notas."""

import re

from aide.web import grafo_svg


def test_desenho_com_nos_links_e_ligacoes():
    svg = grafo_svg.desenhar(["A.md", "B.md", "C.md"], {("A.md", "B.md")})
    assert svg.count("<line ") == 1
    assert svg.count('<a href="/notas?arquivo=') == 3
    assert 'aria-label="grafo de 3 notas e 1 ligações"' in svg


def test_orfa_em_cinza_e_ligada_no_acento():
    from aide.web.graficos import ACENTO, FRACO

    svg = grafo_svg.desenhar(["A.md", "B.md", "Sozinha.md"], {("A.md", "B.md")})
    sozinha = svg[svg.index('href="/notas?arquivo=Sozinha.md"'):]
    assert f'fill="{FRACO}"' in sozinha.split("</a>")[0]
    assert f'fill="{ACENTO}"' in svg


def test_vizinhas_marcadas_para_o_destaque():
    svg = grafo_svg.desenhar(["A.md", "B.md", "C.md"], {("A.md", "B.md"), ("A.md", "C.md")})
    assert re.search(r'data-id="n0" data-vizinhos="n1 n2"', svg)


def test_nome_que_nao_cabe_so_aparece_no_destaque():
    nos = [f"Nota com nome bem comprido {i}.md" for i in range(60)]
    svg = grafo_svg.desenhar(nos, set())
    assert 'class="so-perto"' in svg
    assert svg.count("<text ") == 60


def test_nota_aberta_destacada():
    assert 'class="no atual"' in grafo_svg.desenhar(["A.md", "B.md"], set(), aberto="B.md")


def test_nomes_sao_escapados():
    svg = grafo_svg.desenhar(["<script>x.md"], set())
    assert "<script>" not in svg


def test_vazio():
    assert "Nenhuma nota" in grafo_svg.desenhar([], set())


def test_ligacoes_do_mapa_sem_direcao_nem_repeticao(tmp_path):
    from aide.web import grafo

    for nome, texto in {"A.md": "[[B]] [[B]] [[A]]", "B.md": "[[A]] [[Nada]]"}.items():
        (tmp_path / nome).write_text(texto)
    mapa = grafo.mapa(tmp_path)
    assert grafo_svg.do_mapa(mapa, ["A.md", "B.md"]) == {("A.md", "B.md")}


def test_classe_do_desenho_nao_e_trocada_pela_de_cada_no():
    svg = grafo_svg.desenhar(["A.md", "B.md"], {("A.md", "B.md")}, classe="grafo local")
    assert svg.startswith('<svg class="grafo local"')


def test_vizinhanca_traz_os_links_entre_as_vizinhas():
    arestas = {("A", "B"), ("A", "C"), ("B", "C"), ("C", "D"), ("E", "F")}
    nos, lig = grafo_svg.vizinhanca(arestas, "A")
    assert nos == ["A", "B", "C"]
    assert lig == {("A", "B"), ("A", "C"), ("B", "C")}
    assert grafo_svg.vizinhanca(arestas, "A", saltos=2)[0] == ["A", "B", "C", "D"]


# ---------- desenhos ----------

def test_desenho_e_quadrado_e_abre_na_tela_dele():
    svg = grafo_svg.desenhar(["Inbox/Ideia.md", "Projetos/Casa.excalidraw"],
                             {("Inbox/Ideia.md", "Projetos/Casa.excalidraw")},
                             aberto="Inbox/Ideia.md")
    desenho = svg[svg.index('href="/desenho'):]
    desenho = desenho[:desenho.index("</a>")]
    assert desenho.startswith('href="/desenho?caminho=Projetos/Casa.excalidraw'
                              '&amp;de=Inbox/Ideia.md" class="no desenho"')
    assert "<rect " in desenho and "<circle" not in desenho
    assert "Casa · Projetos/Casa.excalidraw · desenho" in desenho
    assert ">Casa</text>" in desenho
    assert 'aria-label="grafo de 1 notas e 1 desenhos e 1 ligações"' in svg


def test_nome_de_desenho_sai_escapado():
    svg = grafo_svg.desenhar(["<b>x.excalidraw"], set())
    assert "<b>" not in svg


def test_ligacoes_de_nota_para_desenho_so_com_o_desenho_nos_nos(tmp_path):
    from aide.storage import desenhos
    from aide.web import grafo

    (tmp_path / "A.md").write_text("[[B]] [[Casa.excalidraw]] [[Sumido.excalidraw]]")
    (tmp_path / "B.md").write_text("x")
    (tmp_path / "Casa.excalidraw").write_text(desenhos.vazio())
    mapa = grafo.mapa(tmp_path)
    assert grafo_svg.do_mapa(mapa, ["A.md", "B.md"]) == {("A.md", "B.md")}
    assert grafo_svg.do_mapa(mapa, ["A.md", "B.md", "Casa.excalidraw"]) == {
        ("A.md", "B.md"), ("A.md", "Casa.excalidraw")}
