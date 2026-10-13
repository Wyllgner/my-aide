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
