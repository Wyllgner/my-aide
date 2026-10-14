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


def test_ligacao_de_desenho_para_nota_pelo_link_do_elemento(tmp_path):
    import json

    from aide.storage import desenhos
    from aide.web import grafo

    (tmp_path / "B.md").write_text("x")
    dados = json.loads(desenhos.vazio())
    dados["elements"] = [{"type": "rectangle", "id": "a", "link": "[[B]]"}]
    (tmp_path / "Casa.excalidraw").write_text(json.dumps(dados))
    mapa = grafo.mapa(tmp_path)
    assert grafo_svg.do_mapa(mapa, ["B.md"]) == set()
    assert grafo_svg.do_mapa(mapa, ["B.md", "Casa.excalidraw"]) == {("B.md", "Casa.excalidraw")}


# ---------- desenho como cartão com a miniatura ----------

NOS = ["Obra.md", "Desenhos/Planta baixa.excalidraw", "Desenhos/Rascunho.excalidraw"]
ARESTAS = {("Obra.md", "Desenhos/Planta baixa.excalidraw")}


def _no(svg: str, caminho: str) -> str:
    """O <a> inteiro de um nó do grafo."""
    inicio = svg.index(f"caminho={caminho.replace(' ', '%20')}")
    return svg[svg.rindex("<a ", 0, inicio):svg.index("</a>", inicio)]


def test_desenho_com_previa_mostra_a_miniatura():
    svg = grafo_svg.desenhar(NOS, ARESTAS, previa=lambda c: "abc123" if "Planta" in c else None)
    planta = _no(svg, "Desenhos/Planta baixa.excalidraw")
    assert '<image href="/api/desenhos/previa?caminho=Desenhos/Planta%20baixa.excalidraw&amp;v=abc123"' in planta
    assert "<circle" not in planta and 'class="moldura"' in planta


def test_sem_previa_ou_sem_saber_mostra_o_lapis():
    """Sem a função de prévia o grafo não sabe de imagem nenhuma: lápis, o caso seguro."""
    from aide.web.icones import TRACOS

    for svg in (grafo_svg.desenhar(NOS, ARESTAS, previa=lambda c: None),
                grafo_svg.desenhar(NOS, ARESTAS)):
        rascunho = _no(svg, "Desenhos/Rascunho.excalidraw")
        assert "<image" not in rascunho and TRACOS["desenho"] in rascunho


def test_desenho_privado_mostra_o_cadeado_e_nunca_a_imagem():
    """O grafo é a visão de tudo de uma vez: o conteúdo do privado não aparece
    nem quando a prévia existe."""
    from aide.web.icones import TRACOS

    svg = grafo_svg.desenhar(NOS, ARESTAS, previa=lambda c: "abc123",
                             privado=lambda c: "Planta" in c)
    planta = _no(svg, "Desenhos/Planta baixa.excalidraw")
    assert "<image" not in planta and "/api/desenhos/previa" not in planta
    assert TRACOS["privada"] in planta and "desenho privado" in planta
    assert "<image" in _no(svg, "Desenhos/Rascunho.excalidraw")


def test_ligacao_com_desenho_e_tracejada():
    svg = grafo_svg.desenhar(["A.md", "B.md", "D.excalidraw"],
                             {("A.md", "B.md"), ("A.md", "D.excalidraw")})
    linhas = re.findall(r"<line [^>]*/>", svg)
    assert sum('class="com-desenho"' in linha for linha in linhas) == 1


def test_desenho_sem_ligacao_fica_cinza_como_a_orfa():
    svg = grafo_svg.desenhar(NOS, ARESTAS)
    assert 'class="no desenho solto"' in _no(svg, "Desenhos/Rascunho.excalidraw")
    assert "solto" not in _no(svg, "Desenhos/Planta baixa.excalidraw")


def test_perto_da_borda_o_cartao_cresce_para_dentro():
    """Ampliado na borda, metade do cartão e o nome ficavam fora do quadro."""
    assert grafo_svg._ancora(50, 600, 1000, 640) == (0.0, 1.0)      # canto de baixo à esquerda
    assert grafo_svg._ancora(500, 320, 1000, 640) == (0.5, 0.5)     # meio
    assert grafo_svg._ancora(950, 30, 1000, 640) == (1.0, 0.0)      # canto de cima à direita


def test_o_nome_do_desenho_anda_com_o_cartao():
    svg = grafo_svg.desenhar(NOS, ARESTAS, previa=lambda c: "x")
    texto = re.search(r"<text [^>]*>Planta baixa</text>", svg).group(0)
    assert "--desce:" in texto and "--anda:" in texto
    assert "--desce" not in re.search(r"<text [^>]*>Obra</text>", svg).group(0)
