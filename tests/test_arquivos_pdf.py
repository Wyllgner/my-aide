"""Montar PDF: reordenar, excluir, inserir e juntar são o mesmo pedido."""

import pytest
from pypdf import PdfReader, PdfWriter

from aide.arquivos import pdf


def criar(caminho, larguras):
    """Um PDF com uma página em branco por largura: a largura é a etiqueta
    que diz, no resultado, de onde a página veio."""
    escritor = PdfWriter()
    for largura in larguras:
        escritor.add_blank_page(width=largura, height=200)
    with caminho.open("wb") as f:
        escritor.write(f)
    return caminho


def larguras(caminho):
    return [int(p.mediabox.width) for p in PdfReader(caminho).pages]


@pytest.fixture
def a(tmp_path):
    return criar(tmp_path / "a.pdf", [101, 102, 103, 104, 105])


@pytest.fixture
def b(tmp_path):
    return criar(tmp_path / "b.pdf", [201, 202, 203])


def test_reordenar_leva_a_pagina_2_para_a_5(a, tmp_path):
    saida = tmp_path / "s.pdf"
    assert pdf.montar([a], [(0, 0), (0, 2), (0, 3), (0, 4), (0, 1)], saida) == 5
    assert larguras(saida) == [101, 103, 104, 105, 102]


def test_excluir_e_nao_pedir(a, tmp_path):
    saida = tmp_path / "s.pdf"
    pdf.montar([a], [(0, 0), (0, 1), (0, 3), (0, 4)], saida)
    assert larguras(saida) == [101, 102, 104, 105]


def test_inserir_pagina_de_outro_pdf_no_meio(a, b, tmp_path):
    saida = tmp_path / "s.pdf"
    pdf.montar([a, b], [(0, 0), (0, 1), (1, 2), (0, 2), (0, 3), (0, 4)], saida)
    assert larguras(saida) == [101, 102, 203, 103, 104, 105]


def test_juntar_e_pedir_tudo_em_sequencia(a, b, tmp_path):
    saida = tmp_path / "s.pdf"
    pedido = [(1, p) for p in range(3)] + [(0, p) for p in range(5)]
    pdf.montar([a, b], pedido, saida)
    assert larguras(saida) == [201, 202, 203, 101, 102, 103, 104, 105]


def test_nao_pdf_e_recusado_pelo_conteudo_nao_pelo_nome(tmp_path):
    falso = tmp_path / "falso.pdf"
    falso.write_bytes(b"MZ\x90\x00 isto e um executavel")
    with pytest.raises(pdf.PdfInvalido, match="não é um PDF"):
        pdf.montar([falso], [(0, 0)], tmp_path / "s.pdf")


def test_pdf_quebrado_vira_erro_legivel(tmp_path):
    quebrado = tmp_path / "q.pdf"
    quebrado.write_bytes(b"%PDF-1.7\n isto nao tem nada dentro")
    with pytest.raises(pdf.PdfInvalido, match="corrompido"):
        pdf.montar([quebrado], [(0, 0)], tmp_path / "s.pdf")


def test_pdf_com_senha_e_recusado(a, tmp_path):
    escritor = PdfWriter(clone_from=a)
    escritor.encrypt("segredo")
    protegido = tmp_path / "p.pdf"
    with protegido.open("wb") as f:
        escritor.write(f)
    with pytest.raises(pdf.PdfInvalido, match="senha"):
        pdf.montar([protegido], [(0, 0)], tmp_path / "s.pdf")


@pytest.mark.parametrize("pedido, motivo", [
    ([], "nenhuma página"),
    ([(0, 5)], "não tem a página 6"),
    ([(0, -1)], "não tem a página 0"),
    ([(1, 0)], "arquivo 2 não foi enviado"),
])
def test_pedido_que_nao_fecha_com_o_arquivo(a, tmp_path, pedido, motivo):
    with pytest.raises(pdf.PdfInvalido, match=motivo):
        pdf.montar([a], pedido, tmp_path / "s.pdf")


def test_limite_de_paginas(a, tmp_path):
    with pytest.raises(pdf.PdfInvalido, match="mais de"):
        pdf.montar([a], [(0, 0)] * (pdf.MAXIMO_DE_PAGINAS + 1), tmp_path / "s.pdf")


# ---------- imagem como página ----------

def foto(caminho, tamanho=(400, 300), formato="JPEG", modo="RGB", cor=(200, 30, 30), exif=None):
    from PIL import Image

    imagem = Image.new(modo, tamanho, cor)
    extra = {"exif": exif} if exif is not None else {}
    imagem.save(caminho, formato, **extra)
    return caminho


def tamanhos(caminho):
    return [(round(float(p.mediabox.width)), round(float(p.mediabox.height)))
            for p in PdfReader(caminho).pages]


def test_imagem_no_meio_toma_o_tamanho_da_pagina_de_antes(a, tmp_path):
    imagem = foto(tmp_path / "f.jpg")
    saida = tmp_path / "s.pdf"
    pdf.montar([a, imagem], [(0, 0), (1, 0), (0, 1)], saida)
    assert tamanhos(saida) == [(101, 200), (101, 200), (102, 200)]


def test_imagem_no_comeco_toma_o_tamanho_da_primeira_de_pdf(b, tmp_path):
    imagem = foto(tmp_path / "f.png", formato="PNG")
    saida = tmp_path / "s.pdf"
    pdf.montar([imagem, b], [(0, 0), (1, 0)], saida)
    assert tamanhos(saida) == [(201, 200), (201, 200)]


def test_so_imagens_viram_a4_na_orientacao_da_foto(tmp_path):
    deitada = foto(tmp_path / "d.jpg", (800, 600))
    em_pe = foto(tmp_path / "e.jpg", (600, 800))
    saida = tmp_path / "s.pdf"
    pdf.montar([deitada, em_pe], [(0, 0), (1, 0)], saida)
    # cada imagem sozinha, sem PDF antes, decide pela própria forma;
    # a segunda já tem vizinha e herda o tamanho dela
    assert tamanhos(saida)[0] == (842, 595)


def test_a_imagem_cabe_inteira_na_pagina_com_margem(tmp_path):
    imagem = foto(tmp_path / "f.jpg", (1000, 100))
    saida = tmp_path / "s.pdf"
    pdf.montar([imagem], [(0, 0)], saida)
    pagina = PdfReader(saida).pages[0]
    assert "/XObject" in pagina["/Resources"]
    assert tamanhos(saida) == [(842, 595)]


def test_transparencia_vira_fundo_branco(tmp_path):
    imagem = foto(tmp_path / "t.png", formato="PNG", modo="RGBA", cor=(0, 0, 0, 0))
    saida = tmp_path / "s.pdf"
    pdf.montar([imagem], [(0, 0)], saida)
    convertida = pdf._abrir_imagem(imagem, "x")
    assert convertida.mode == "RGB"
    assert convertida.getpixel((0, 0)) == (255, 255, 255)


def test_foto_de_celular_deitada_pelo_exif_fica_em_pe(tmp_path):
    from PIL import Image

    exif = Image.Exif()
    exif[0x0112] = 6  # gire 90°: o sensor gravou deitado
    imagem = foto(tmp_path / "c.jpg", (800, 600), exif=exif.tobytes())
    assert pdf._abrir_imagem(imagem, "x").size == (600, 800)


def test_imagem_tem_uma_pagina_so(tmp_path):
    imagem = foto(tmp_path / "f.jpg")
    with pytest.raises(pdf.PdfInvalido, match="não tem a página 2"):
        pdf.montar([imagem], [(0, 1)], tmp_path / "s.pdf")


def test_imagem_quebrada_vira_erro_legivel(tmp_path):
    quebrada = tmp_path / "q.jpg"
    quebrada.write_bytes(b"\xff\xd8\xff\xe0 e mais nada")
    with pytest.raises(pdf.PdfInvalido, match="não é uma imagem que dê para abrir"):
        pdf.montar([quebrada], [(0, 0)], tmp_path / "s.pdf")


def test_bomba_de_descompressao_e_recusada(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "MAXIMO_DE_PIXELS", 1000)
    imagem = foto(tmp_path / "f.png", (100, 100), formato="PNG")
    with pytest.raises(pdf.PdfInvalido, match="grande demais"):
        pdf.montar([imagem], [(0, 0)], tmp_path / "s.pdf")


def test_extensao_mentirosa_nao_engana(tmp_path):
    """Um .jpg que é PDF é tratado como PDF, e vice-versa: vale o conteúdo."""
    disfarcado = criar(tmp_path / "na-verdade-pdf.jpg", [150])
    saida = tmp_path / "s.pdf"
    pdf.montar([disfarcado], [(0, 0)], saida)
    assert larguras(saida) == [150]
