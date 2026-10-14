"""A rota que monta PDF: recebe, devolve e não guarda nada."""

import io
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from aide.storage import connect, migrate
from aide.web.app import criar_app

ROTA = "/api/arquivos/montar"
ESCRITA = {"X-Aide": "1", "Origin": "http://127.0.0.1:8787",
           "Content-Type": "application/octet-stream"}


def pdf_com(larguras) -> bytes:
    escritor = PdfWriter()
    for largura in larguras:
        escritor.add_blank_page(width=largura, height=200)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def corpo(arquivos: list[bytes], paginas) -> bytes:
    plano = {"arquivos": [len(a) for a in arquivos], "paginas": paginas}
    return json.dumps(plano).encode() + b"\n" + b"".join(arquivos)


def larguras(resposta) -> list[int]:
    return [int(p.mediabox.width) for p in PdfReader(io.BytesIO(resposta.content)).pages]


@pytest.fixture
def app(config, tmp_path):
    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app, base_url="http://127.0.0.1:8787")


@pytest.fixture
def temporarios(monkeypatch, tmp_path):
    """As pastas que a rota cria, num lugar onde o teste consegue olhar."""
    base = tmp_path / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    return base


def test_monta_na_ordem_pedida_com_dois_arquivos(cliente, temporarios):
    a, b = pdf_com([101, 102, 103]), pdf_com([201, 202])
    resposta = cliente.post(ROTA, content=corpo([a, b], [[0, 2], [1, 0], [0, 0]]), headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["cache-control"] == "no-store"
    assert larguras(resposta) == [103, 201, 101]


def test_nao_sobra_nada_depois_da_resposta(cliente, temporarios):
    a = pdf_com([101])
    assert cliente.post(ROTA, content=corpo([a], [[0, 0]]), headers=ESCRITA).status_code == 200
    assert list(temporarios.iterdir()) == []


def test_nem_quando_o_pedido_falha(cliente, temporarios):
    resposta = cliente.post(ROTA, content=corpo([b"nao sou pdf"], [[0, 0]]), headers=ESCRITA)
    assert resposta.status_code == 422
    assert "não é um PDF" in resposta.json()["detail"]
    assert list(temporarios.iterdir()) == []


def test_nao_toca_no_vault_nem_na_auditoria(cliente, app, config):
    antes = sorted(Path(config.vault_dir).rglob("*")) if Path(config.vault_dir).exists() else []
    conn = app.state.conn_factory()
    trilha = conn.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"]
    cliente.post(ROTA, content=corpo([pdf_com([101])], [[0, 0]]), headers=ESCRITA)
    depois = sorted(Path(config.vault_dir).rglob("*")) if Path(config.vault_dir).exists() else []
    assert depois == antes
    assert conn.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"] == trilha


@pytest.mark.parametrize("bruto, motivo", [
    (b"sem plano nenhum", "não começa com o plano"),
    (b"{nao e json}\n", "plano ilegível"),
    (b'{"arquivos": [], "paginas": []}\n', "de 1 a"),
    (b'{"arquivos": [0], "paginas": [[0, 0]]}\n', "nenhum vazio"),
    (b'{"arquivos": [5], "paginas": "tudo"}\nabcde', "páginas ilegível"),
    (b'{"arquivos": [5], "paginas": [[0, 0]]}\nabc', "menos bytes"),
    (b'{"arquivos": [2], "paginas": [[0, 0]]}\nabcdef', "mais bytes"),
])
def test_pedido_que_nao_fecha(cliente, temporarios, bruto, motivo):
    resposta = cliente.post(ROTA, content=bruto, headers=ESCRITA)
    assert resposta.status_code == 400
    assert motivo in resposta.json()["detail"]
    assert list(temporarios.iterdir()) == []


def test_pagina_que_nao_existe_e_422(cliente):
    resposta = cliente.post(ROTA, content=corpo([pdf_com([101])], [[0, 3]]), headers=ESCRITA)
    assert resposta.status_code == 422
    assert "não tem a página 4" in resposta.json()["detail"]


def test_plano_que_promete_demais_e_recusado_antes_de_ler(cliente, monkeypatch):
    from aide import arquivos

    monkeypatch.setattr(arquivos, "TAMANHO_MAXIMO", 10)
    monkeypatch.setattr("aide.web.arquivos_api.TAMANHO_MAXIMO", 10)
    resposta = cliente.post(ROTA, content=b'{"arquivos": [11], "paginas": [[0, 0]]}\n',
                            headers=ESCRITA)
    assert resposta.status_code == 413


def test_corpo_acima_do_limite_nem_entra(cliente):
    from aide import arquivos

    tamanho = str(arquivos.TAMANHO_MAXIMO + arquivos.PLANO_MAXIMO + 1)
    resposta = cliente.post(ROTA, content=b"x", headers={**ESCRITA, "Content-Length": tamanho})
    assert resposta.status_code == 413


def test_o_limite_desta_tela_e_maior_que_o_das_notas():
    """PDF escaneado passa fácil dos 3 MB do corpo comum."""
    from aide import arquivos
    from aide.web import seguranca

    assert seguranca.limite_do_corpo("POST", ROTA) == arquivos.TAMANHO_MAXIMO + arquivos.PLANO_MAXIMO
    assert seguranca.limite_do_corpo("POST", "/api/notas/arquivo") == seguranca.CORPO_MAXIMO


@pytest.mark.parametrize("cabecalhos", [
    {"Origin": "http://127.0.0.1:8787"},                     # sem X-Aide
    {"X-Aide": "1", "Origin": "http://evil.example"},        # de outro site
])
def test_vale_a_fronteira_de_escrita(cliente, cabecalhos):
    resposta = cliente.post(ROTA, content=corpo([pdf_com([101])], [[0, 0]]), headers=cabecalhos)
    assert resposta.status_code == 403


# ---------- converter documentos ----------

CONVERTER = "/api/arquivos/converter"
com_libreoffice = pytest.mark.skipif(not __import__("shutil").which("soffice"),
                                     reason="sem LibreOffice")


def corpo_conversao(arquivos: dict[str, bytes]) -> bytes:
    plano = {"arquivos": [len(c) for c in arquivos.values()], "nomes": list(arquivos)}
    return json.dumps(plano).encode() + b"\n" + b"".join(arquivos.values())


@com_libreoffice
def test_um_documento_volta_como_pdf(cliente, temporarios):
    resposta = cliente.post(CONVERTER, content=corpo_conversao({"nota.txt": "Olá março".encode()}),
                            headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/pdf"
    assert "março" in PdfReader(io.BytesIO(resposta.content)).pages[0].extract_text()
    assert list(temporarios.iterdir()) == []


@com_libreoffice
def test_varios_voltam_num_zip_sem_nome_repetido(cliente, temporarios):
    import zipfile

    arquivos = {"a.txt": b"um", "a.rtf": b"{\\rtf1 dois}", "pasta/b.txt": b"tres"}
    resposta = cliente.post(CONVERTER, content=corpo_conversao(arquivos), headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/zip"
    nomes = zipfile.ZipFile(io.BytesIO(resposta.content)).namelist()
    # "pasta/b.txt" não vira pasta dentro do zip
    assert nomes == ["a.pdf", "a (2).pdf", "pasta_b.pdf"]
    assert list(temporarios.iterdir()) == []


def test_conteudo_que_mente_a_extensao_e_422(cliente, temporarios):
    resposta = cliente.post(CONVERTER, content=corpo_conversao({"x.docx": b"%PDF-1.7 nao e docx"}),
                            headers=ESCRITA)
    assert resposta.status_code == 422
    assert "não é o que a extensão diz" in resposta.json()["detail"]
    assert list(temporarios.iterdir()) == []


@pytest.mark.parametrize("nomes", [None, [], ["a.txt", "b.txt"], [""], [3]])
def test_um_nome_para_cada_arquivo(cliente, nomes):
    plano = {"arquivos": [2]}
    if nomes is not None:
        plano["nomes"] = nomes
    resposta = cliente.post(CONVERTER, content=json.dumps(plano).encode() + b"\nab", headers=ESCRITA)
    assert resposta.status_code == 400
    assert "um nome para cada arquivo" in resposta.json()["detail"]


def test_converter_tambem_tem_o_limite_desta_tela():
    from aide import arquivos
    from aide.web import seguranca

    assert seguranca.limite_do_corpo("POST", CONVERTER) == arquivos.TAMANHO_MAXIMO + arquivos.PLANO_MAXIMO


def test_sem_repetir():
    from aide.web.arquivos_api import sem_repetir

    assert sem_repetir(["a.pdf", "A.pdf", "b.pdf", "a.pdf"]) == ["a.pdf", "A (2).pdf", "b.pdf", "a (3).pdf"]


def test_montar_imagens_com_orientacao_propria(cliente):
    from PIL import Image

    def jpg(tamanho):
        bruto = io.BytesIO()
        Image.new("RGB", tamanho, "white").save(bruto, "JPEG")
        return bruto.getvalue()

    deitada, em_pe = jpg((800, 600)), jpg((600, 800))
    plano = {"arquivos": [len(deitada), len(em_pe)], "paginas": [[0, 0], [1, 0]], "imagens": "proprias"}
    resposta = cliente.post(ROTA, content=json.dumps(plano).encode() + b"\n" + deitada + em_pe,
                            headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    paginas = PdfReader(io.BytesIO(resposta.content)).pages
    assert [round(float(p.mediabox.width)) for p in paginas] == [842, 595]


# ---------- PDF → imagens ----------

IMAGENS = "/api/arquivos/imagens"
com_pdftoppm = pytest.mark.skipif(not __import__("shutil").which("pdftoppm"), reason="sem pdftoppm")


@com_pdftoppm
def test_uma_pagina_volta_como_png(cliente, temporarios):
    resposta = cliente.post(IMAGENS, content=corpo_conversao({"a.pdf": pdf_com([300])}),
                            headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "image/png"
    assert resposta.content.startswith(b"\x89PNG")
    assert list(temporarios.iterdir()) == []


@com_pdftoppm
def test_varias_paginas_voltam_num_zip_com_numero(cliente, temporarios):
    import zipfile

    arquivos = {"contrato.pdf": pdf_com([300, 300, 300]), "outro/contrato.pdf": pdf_com([300])}
    resposta = cliente.post(IMAGENS, content=corpo_conversao(arquivos), headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == "application/zip"
    nomes = zipfile.ZipFile(io.BytesIO(resposta.content)).namelist()
    assert nomes == ["contrato-p01.png", "contrato-p02.png", "contrato-p03.png",
                     "outro_contrato-p01.png"]
    assert list(temporarios.iterdir()) == []


def test_o_que_nao_e_pdf_nao_vira_imagem(cliente):
    resposta = cliente.post(IMAGENS, content=corpo_conversao({"a.pdf": b"nada"}), headers=ESCRITA)
    assert resposta.status_code == 422
    assert "não é um PDF" in resposta.json()["detail"]


# ---------- PDF → Word ----------

WORD = "/api/arquivos/word"


def corpo_word(arquivos: dict[str, bytes], modo=None) -> bytes:
    plano = {"arquivos": [len(c) for c in arquivos.values()], "nomes": list(arquivos)}
    if modo:
        plano["modo"] = modo
    return json.dumps(plano).encode() + b"\n" + b"".join(arquivos.values())


@com_libreoffice
def test_um_pdf_volta_como_docx(cliente, temporarios):
    from aide.web.arquivos_api import DOCX

    resposta = cliente.post(WORD, content=corpo_word({"a.pdf": pdf_com([300])}), headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert resposta.headers["content-type"] == DOCX
    assert resposta.content.startswith(b"PK")
    assert list(temporarios.iterdir()) == []


@com_libreoffice
def test_varios_pdfs_voltam_num_zip_de_docx(cliente):
    import zipfile

    arquivos = {"a.pdf": pdf_com([300]), "b.pdf": pdf_com([300])}
    resposta = cliente.post(WORD, content=corpo_word(arquivos), headers=ESCRITA)
    assert resposta.status_code == 200, resposta.text
    assert zipfile.ZipFile(io.BytesIO(resposta.content)).namelist() == ["a.docx", "b.docx"]


def test_modo_invalido_e_400(cliente):
    resposta = cliente.post(WORD, content=corpo_word({"a.pdf": pdf_com([300])}, "ocr"),
                            headers=ESCRITA)
    assert resposta.status_code == 400
    assert "aparencia ou texto" in resposta.json()["detail"]


# ---------- nada fica para trás ----------

@pytest.mark.parametrize("faixa", ["bytes=abc", "bytes=999999-", "bytes=0-10"])
def test_range_nao_pula_a_limpeza_nem_corta_o_arquivo(cliente, temporarios, faixa):
    """A revisão de 13/10 achou: Range inválido respondia 400/416 sem apagar
    a pasta, com os seus documentos dentro."""
    resposta = cliente.post(ROTA, content=corpo([pdf_com([101, 102])], [[0, 1], [0, 0]]),
                            headers={**ESCRITA, "Range": faixa})
    assert resposta.status_code == 200
    assert larguras(resposta) == [102, 101]          # o arquivo inteiro
    assert list(temporarios.iterdir()) == []


def test_conexao_caida_no_meio_tambem_apaga(temporarios):
    """Quem baixava fecha a aba no meio: o envio falha e a pasta some igual."""
    import asyncio

    from aide.web.arquivos_api import resposta_que_limpa

    pasta = temporarios / "aide-arquivos-caiu"
    pasta.mkdir()
    (pasta / "resultado.pdf").write_bytes(b"%PDF-1.7" + b"x" * 200_000)
    resposta = resposta_que_limpa()(pasta / "resultado.pdf", pasta, media_type="application/pdf")

    async def envio_que_cai(mensagem):
        if mensagem["type"] == "http.response.body":
            raise OSError("conexão fechada")

    async def receber():
        return {"type": "http.request"}

    escopo = {"type": "http", "method": "POST", "headers": [], "path": ROTA}
    with pytest.raises(OSError):
        asyncio.run(resposta(escopo, receber, envio_que_cai))
    assert not pasta.exists()


def test_varredura_apaga_so_as_nossas_esquecidas(tmp_path):
    import os
    import time

    from aide.web.arquivos_api import varrer

    velha = tmp_path / "aide-arquivos-velha"
    nova = tmp_path / "aide-arquivos-nova"
    alheia = tmp_path / "outro-programa-velho"
    alvo = tmp_path / "alvo-do-link"
    for pasta in (velha, nova, alheia, alvo):
        pasta.mkdir()
    (velha / "contrato.pdf").write_bytes(b"segredo")
    (alvo / "nao-apague.txt").write_text("x")
    link = tmp_path / "aide-arquivos-link"
    link.symlink_to(alvo)
    duas_horas = time.time() - 7200
    for caminho in (velha, alheia, alvo):
        os.utime(caminho, (duas_horas, duas_horas))
    os.utime(link, (duas_horas, duas_horas), follow_symlinks=False)

    assert varrer(tmp_path) == 1
    assert not velha.exists()                       # esquecida: some
    assert nova.exists()                            # em uso: fica
    assert alheia.exists()                          # não é nossa: fica
    assert (alvo / "nao-apague.txt").exists()       # link nunca é seguido


def test_varre_ao_subir(config, tmp_path, monkeypatch):
    import os
    import time

    from aide.web.app import criar_app

    base = tmp_path / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    sobra = base / "aide-arquivos-do-desligamento"
    sobra.mkdir()
    os.utime(sobra, (time.time() - 7200,) * 2)
    criar_app(config)
    assert not sobra.exists()


# ---------- a fila ----------

def test_conversoes_esperam_sem_ocupar_thread(app, monkeypatch):
    """Duas conversões ao mesmo tempo: a segunda espera a vez no laço de
    eventos, e a fila (uma vaga) nunca deixa duas rodarem juntas."""
    import threading
    import time

    from aide.web import arquivos_api

    rodando, maximo, trava = 0, 0, threading.Lock()

    def conversao_lenta(caminhos, nomes, pasta):
        nonlocal rodando, maximo
        with trava:
            rodando += 1
            maximo = max(maximo, rodando)
        time.sleep(0.3)
        with trava:
            rodando -= 1
        saida = pasta / "r.pdf"
        saida.write_bytes(b"%PDF-1.7")
        return saida, "application/pdf"

    monkeypatch.setattr(arquivos_api, "converter_todos", conversao_lenta)
    respostas = []
    # `with`: um laço de eventos só para todos os pedidos, como no servidor
    with TestClient(app, base_url="http://127.0.0.1:8787") as cliente:
        def pedir():
            respostas.append(cliente.post("/api/arquivos/converter",
                                          content=corpo_conversao({"a.txt": b"x"}),
                                          headers=ESCRITA))

        fios = [threading.Thread(target=pedir) for _ in range(3)]
        for fio in fios:
            fio.start()
        for fio in fios:
            fio.join(timeout=20)
    assert [r.status_code for r in respostas] == [200, 200, 200]
    assert maximo == 1


def test_fila_cheia_responde_na_hora(app, monkeypatch):
    from aide.web import arquivos_api

    monkeypatch.setattr(arquivos_api, "FILA_MAXIMA", 0)
    cliente = TestClient(app, base_url="http://127.0.0.1:8787")
    resposta = cliente.post("/api/arquivos/converter", content=corpo_conversao({"a.txt": b"x"}),
                            headers=ESCRITA)
    assert resposta.status_code == 503
    assert "tente de novo" in resposta.json()["detail"]
