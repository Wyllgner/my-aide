"""Converter documento em PDF: o LibreOffice de verdade, quando há."""

import shutil
import subprocess
import zipfile
from pathlib import Path

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
    monkeypatch.setattr(converter, "_isolamento", lambda: "")
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
    monkeypatch.setattr(converter, "_isolamento", lambda: "")
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


# ---------- a caixa ----------

com_bwrap = pytest.mark.skipif(converter._isolamento() != "bwrap", reason="sem bwrap")


def odt_com_imagem_ligada(caminho, alvo):
    """Um .odt cuja imagem é um link para um arquivo da máquina: o
    LibreOffice embute a imagem ao converter, se conseguir ler."""
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.2">
<office:body><office:text><text:p>Imagem:<draw:frame draw:name="i" text:anchor-type="paragraph" svg:width="6cm" svg:height="4cm"><draw:image xlink:href="file://{alvo}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></text:p></office:text></office:body></office:document-content>'''
    manifest = ('<?xml version="1.0" encoding="UTF-8"?><manifest:manifest '
                'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
                '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
                '</manifest:manifest>')
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", content)
        z.writestr("META-INF/manifest.xml", manifest)
    return caminho


@com_libreoffice
@com_bwrap
def test_documento_nao_puxa_imagem_de_fora_da_pasta_da_conversao(tmp_path):
    """O ataque que a revisão de 13/10 achou: sem a caixa, o PDF saía com a
    foto da máquina dentro."""
    from PIL import Image

    fora = tmp_path / "fora"
    fora.mkdir()
    Image.new("RGB", (300, 200), (255, 0, 0)).save(fora / "foto-privada.png")
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    entrada = odt_com_imagem_ligada(trabalho / "entrada-0", fora / "foto-privada.png")
    pdf = converter.para_pdf(entrada, "convite.odt", trabalho / "saida")
    imagens = [img for pagina in PdfReader(pdf).pages for img in pagina.images]
    assert not imagens


@com_bwrap
def test_a_caixa_nao_ve_home_nem_rede(tmp_path):
    """Só o sistema, as fontes e a pasta da conversão."""
    script = (f"test ! -e {Path.home()}/.ssh && test ! -e {Path.home()}/Documentos"
              " && test ! -e /sys/class/net/eth0 && touch ok")
    assert converter._rodar(["sh", "-c", script], "x", tmp_path)
    assert (tmp_path / "ok").exists()
    rede = converter._rodar(["sh", "-c", "cat /proc/net/dev | grep -v ' lo:' | tail -n +3 | grep -q ."],
                            "x", tmp_path)
    assert not rede  # só a interface de loopback


@com_bwrap
def test_a_caixa_escreve_so_na_pasta_da_conversao(tmp_path):
    assert converter._rodar(["sh", "-c", "echo oi > dentro.txt"], "x", tmp_path)
    assert (tmp_path / "dentro.txt").read_text() == "oi\n"
    # fora da pasta, o /tmp da caixa é memória descartável: o que se escreve
    # ali some com ela e nunca chega ao disco
    converter._rodar(["sh", "-c", f"echo oi > {tmp_path.parent}/fora.txt"], "x", tmp_path)
    assert not (tmp_path.parent / "fora.txt").exists()
    assert not converter._rodar(["sh", "-c", "echo oi > /usr/fora.txt"], "x", tmp_path)


@com_bwrap
def test_prazo_estourado_mata_tambem_o_que_esta_na_caixa(tmp_path, monkeypatch):
    monkeypatch.setattr(converter, "PRAZO", 0.5)
    with pytest.raises(converter.ConversaoFalhou, match="demorou"):
        converter._rodar(["sh", "-c", "sleep 30; touch tarde"], "x", tmp_path)
    vivos = subprocess.run(["pgrep", "-f", "sleep 30; touch tarde"], capture_output=True,
                           check=False).stdout
    assert not vivos


@com_libreoffice
def test_o_perfil_nasce_com_as_macros_desligadas(tmp_path):
    entrada = tmp_path / "entrada-0"
    entrada.write_text("x")
    converter.para_pdf(entrada, "x.txt", tmp_path / "saida")
    ajustes = (tmp_path / "perfil-entrada-0" / "user" / "registrymodifications.xcu").read_text()
    assert 'oor:name="DisableMacrosExecution"' in ajustes
    assert "<value>true</value>" in ajustes


def test_sem_bwrap_cai_para_unshare_e_avisa(monkeypatch, caplog):
    converter._isolamento.cache_clear()
    monkeypatch.setattr(converter.shutil, "which",
                        lambda nome: None if nome == "bwrap" else f"/usr/bin/{nome}")
    try:
        with caplog.at_level("WARNING"):
            modo = converter._isolamento()
        assert modo in ("unshare", "")
        assert "vê os seus arquivos" in caplog.text or "sem isolamento" in caplog.text
    finally:
        converter._isolamento.cache_clear()
