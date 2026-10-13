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
