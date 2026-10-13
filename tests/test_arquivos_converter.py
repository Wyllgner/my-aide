"""Converter documento em PDF: o LibreOffice de verdade, quando há."""

import shutil
import subprocess
import zipfile

import pytest
from pypdf import PdfReader

from aide.arquivos import converter

com_libreoffice = pytest.mark.skipif(not shutil.which("soffice"), reason="sem LibreOffice")


def docx_minimo(caminho, texto="Olá, relatório"):
    """O menor .docx que o LibreOffice abre: três arquivos dentro do zip."""
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/document.xml",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   f'<w:body><w:p><w:r><w:t>{texto}</w:t></w:r></w:p></w:body></w:document>')
    return caminho


@pytest.mark.parametrize("nome, conteudo", [
    ("a.docx", b"%PDF-1.7 disfarcado"),
    ("a.doc", b"PK\x03\x04 zip no lugar de doc antigo"),
    ("a.rtf", b"texto qualquer"),
    ("a.txt", b"texto com \x00 binario"),
])
def test_conteudo_que_nao_bate_com_a_extensao(tmp_path, nome, conteudo):
    entrada = tmp_path / "e"
    entrada.write_bytes(conteudo)
    with pytest.raises(converter.ConversaoFalhou, match="não é o que a extensão diz"):
        converter.confere(entrada, nome)


def test_extensao_desconhecida(tmp_path):
    entrada = tmp_path / "e"
    entrada.write_bytes(b"MZ")
    with pytest.raises(converter.ConversaoFalhou, match="não sei converter .exe"):
        converter.confere(entrada, "programa.exe")


def test_familias_que_batem(tmp_path):
    casos = {"a.docx": converter.ZIP + b"...", "a.xls": converter.OLE + b"...",
             "a.rtf": b"  {\\rtf1 ola}", "a.txt": "acentuação".encode()}
    for nome, conteudo in casos.items():
        entrada = tmp_path / nome
        entrada.write_bytes(conteudo)
        assert converter.confere(entrada, nome) == nome.rsplit(".", 1)[1]


@com_libreoffice
def test_docx_vira_pdf(tmp_path):
    entrada = docx_minimo(tmp_path / "entrada-0")
    pdf = converter.para_pdf(entrada, "relatório.docx", tmp_path / "saida")
    assert pdf.parent == tmp_path / "saida"
    assert "Olá, relatório" in PdfReader(pdf).pages[0].extract_text()


@com_libreoffice
def test_txt_vira_pdf_com_acento(tmp_path):
    entrada = tmp_path / "entrada-0"
    entrada.write_text("Conta de luz: R$ 120,00\nVencimento em março")
    pdf = converter.para_pdf(entrada, "nota.txt", tmp_path / "saida")
    assert "março" in PdfReader(pdf).pages[0].extract_text()


@com_libreoffice
def test_o_perfil_do_libreoffice_e_temporario(tmp_path):
    """O perfil de quem usa o LibreOffice no dia a dia não é tocado: a
    conversão cria o seu ao lado da entrada."""
    entrada = tmp_path / "entrada-0"
    entrada.write_text("x")
    converter.para_pdf(entrada, "x.txt", tmp_path / "saida")
    assert (tmp_path / "perfil-entrada-0").is_dir()


def test_sem_libreoffice_diz_isso(tmp_path, monkeypatch):
    monkeypatch.setattr(converter.shutil, "which", lambda nome: None)
    entrada = tmp_path / "entrada-0"
    entrada.write_text("x")
    with pytest.raises(converter.ConversaoFalhou, match="não está instalado"):
        converter.para_pdf(entrada, "x.txt", tmp_path / "saida")


def test_prazo_estourado_mata_o_grupo_e_avisa(tmp_path, monkeypatch):
    """Um LibreOffice que não volta não pode segurar o servidor."""
    falso = tmp_path / "soffice"
    falso.write_text("#!/bin/sh\nsleep 30\n")
    falso.chmod(0o755)
    monkeypatch.setattr(converter.shutil, "which",
                        lambda nome: str(falso) if nome == "soffice" else None)
    monkeypatch.setattr(converter, "_isolamento", lambda: ())
    monkeypatch.setattr(converter, "PRAZO", 0.5)
    entrada = tmp_path / "entrada-0"
    entrada.write_text("x")
    with pytest.raises(converter.ConversaoFalhou, match="demorou mais de"):
        converter.para_pdf(entrada, "x.txt", tmp_path / "saida")
    vivos = subprocess.run(["pgrep", "-f", str(falso)], capture_output=True, check=False).stdout
    assert not vivos


def test_libreoffice_que_falha_vira_erro_legivel(tmp_path, monkeypatch):
    falso = tmp_path / "soffice"
    falso.write_text("#!/bin/sh\necho quebrou >&2\nexit 1\n")
    falso.chmod(0o755)
    monkeypatch.setattr(converter.shutil, "which",
                        lambda nome: str(falso) if nome == "soffice" else None)
    monkeypatch.setattr(converter, "_isolamento", lambda: ())
    entrada = tmp_path / "entrada-0"
    entrada.write_text("x")
    with pytest.raises(converter.ConversaoFalhou, match="não conseguiu converter x.txt"):
        converter.para_pdf(entrada, "x.txt", tmp_path / "saida")


# ---------- PDF → imagens ----------

com_pdftoppm = pytest.mark.skipif(not shutil.which("pdftoppm"), reason="sem pdftoppm")


def pdf_de(caminho, paginas):
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=200, height=300)
    with caminho.open("wb") as f:
        escritor.write(f)
    return caminho


@com_pdftoppm
def test_cada_pagina_vira_um_png_na_ordem(tmp_path):
    from PIL import Image

    imagens = converter.para_imagens(pdf_de(tmp_path / "e.pdf", 12), "e.pdf", tmp_path / "saida")
    assert len(imagens) == 12
    # p-01 … p-12, ordenadas pelo número e não pelo texto
    assert [int(i.stem.rsplit("-", 1)[1]) for i in imagens] == list(range(1, 13))
    with Image.open(imagens[0]) as primeira:
        # 200 pt a 150 dpi
        assert primeira.size == (round(200 / 72 * converter.DPI), round(300 / 72 * converter.DPI))


def test_pdf_com_senha_nao_vira_imagem(tmp_path):
    from pypdf import PdfWriter

    escritor = PdfWriter(clone_from=pdf_de(tmp_path / "a.pdf", 1))
    escritor.encrypt("segredo")
    protegido = tmp_path / "p.pdf"
    with protegido.open("wb") as f:
        escritor.write(f)
    from aide.arquivos import pdf

    with pytest.raises(pdf.PdfInvalido, match="senha"):
        converter.para_imagens(protegido, "p.pdf", tmp_path / "saida")


def test_limite_de_paginas_para_imagem(tmp_path, monkeypatch):
    monkeypatch.setattr(converter, "MAXIMO_DE_IMAGENS", 3)
    with pytest.raises(converter.ConversaoFalhou, match="mais de 3 páginas"):
        converter.para_imagens(pdf_de(tmp_path / "e.pdf", 4), "e.pdf", tmp_path / "saida")


# ---------- PDF → Word ----------

def pdf_com_texto(tmp_path, texto="Cláusula primeira: o aluguel vence no dia 5."):
    entrada = tmp_path / "fonte.txt"
    entrada.write_text(texto)
    return converter.para_pdf(entrada, "fonte.txt", tmp_path / "pdf")


def texto_do_docx(caminho):
    import re

    xml = zipfile.ZipFile(caminho).read("word/document.xml").decode()
    return " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


@com_libreoffice
@pytest.mark.parametrize("modo", ["aparencia", "texto"])
def test_pdf_vira_docx_nos_dois_modos(tmp_path, modo):
    origem = pdf_com_texto(tmp_path)
    entrada = tmp_path / "entrada-0"
    origem.rename(entrada)
    docx = converter.para_word(entrada, "contrato.pdf", tmp_path / "saida", modo)
    assert docx.suffix == ".docx"
    assert "aluguel vence no dia 5" in texto_do_docx(docx)


@com_libreoffice
def test_aparencia_usa_caixas_e_texto_usa_paragrafos(tmp_path):
    """É a diferença que justifica ter os dois: caixa por linha num, texto
    corrido no outro."""
    for modo, caixas in (("aparencia", True), ("texto", False)):
        pasta = tmp_path / modo
        pasta.mkdir()
        entrada = pasta / "entrada-0"
        pdf_com_texto(pasta).rename(entrada)
        docx = converter.para_word(entrada, "c.pdf", pasta / "saida", modo)
        xml = zipfile.ZipFile(docx).read("word/document.xml").decode()
        assert ("<w:txbxContent" in xml) is caixas, modo


@com_libreoffice
def test_pdf_sem_texto_avisa_que_parece_escaneado(tmp_path):
    from pypdf import PdfWriter

    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    entrada = tmp_path / "entrada-0"
    with entrada.open("wb") as f:
        escritor.write(f)
    with pytest.raises(converter.ConversaoFalhou, match="escaneada"):
        converter.para_word(entrada, "foto.pdf", tmp_path / "saida", "texto")


def test_modo_desconhecido(tmp_path):
    with pytest.raises(converter.ConversaoFalhou, match="modo desconhecido"):
        converter.para_word(tmp_path / "x", "x.pdf", tmp_path / "saida", "ocr")
