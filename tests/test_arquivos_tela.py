"""A tela Arquivos: a moldura que o servidor monta."""

import pytest
from fastapi.testclient import TestClient

from aide.storage import connect, migrate
from aide.web.app import criar_app


@pytest.fixture
def cliente(config, tmp_path):
    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return TestClient(criar_app(config, conn_factory), base_url="http://127.0.0.1:8787")


def test_a_tela_entra_no_menu_logo_depois_das_notas(cliente):
    html = cliente.get("/arquivos").text
    assert '<a href="/arquivos" aria-current="page">' in html
    assert html.index('href="/notas"') < html.index('href="/arquivos"') < html.index('href="/gastos"')


def test_tem_onde_soltar_e_escolher_varios(cliente):
    html = cliente.get("/arquivos").text
    assert 'id="arq-soltar"' in html
    assert '<input type="file" id="arq-escolher" multiple hidden>' in html
    assert "nada fica guardado" in html


def test_as_acoes_nascem_desligadas(cliente):
    """Sem arquivo marcado, nenhuma ação tem sobre o que agir: quem liga é o
    script, conforme o tipo do que você marcou."""
    from aide.web.arquivos_tela import ACOES

    html = cliente.get("/arquivos").text
    for chave, rotulo, *_ in ACOES:
        assert f'data-acao="{chave}" disabled' in html
        assert rotulo in html
    assert len(ACOES) == 6



def test_o_script_e_arquivo_da_casa(cliente):
    """A CSP só deixa rodar script daqui; embutido na página não rodaria."""
    html = cliente.get("/arquivos").text
    assert '<script type="module" src="/arquivos.js"></script>' in html
    resposta = cliente.get("/arquivos.js")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/javascript")
    assert "dataTransfer" in resposta.text


def test_soltar_nao_manda_nada_ao_servidor(cliente):
    """Até você escolher a ação, os arquivos ficam na página: o único envio
    é o do botão de baixar."""
    import re

    js = cliente.get("/arquivos.js").text
    assert re.findall(r'fetch\(([^,]+),', js) == ['"/api/arquivos/montar"']
    assert "innerHTML" not in js  # nome de arquivo é texto, nunca marcação


def test_o_pdf_e_lido_no_navegador_pelo_pdfjs_da_casa(cliente):
    js = cliente.get("/arquivos.js").text
    assert 'from "/vendor/pdfjs/pdf.js"' in js
    assert 'workerSrc = "/vendor/pdfjs/pdf.worker.js"' in js
    # WebAssembly precisaria de 'wasm-unsafe-eval' na CSP
    assert "useWasm: false" in js


def test_a_grade_de_paginas_nasce_escondida(cliente):
    html = cliente.get("/arquivos").text
    assert '<section class="card editor-pdf" id="arq-editor" hidden>' in html


def test_nenhum_id_da_tela_e_procurado_pelo_app_js(cliente):
    """O /app.js roda em toda página e liga o editor de notas se achar
    #editor: um id repetido aqui dispara código das notas nesta tela."""
    import re

    html = cliente.get("/arquivos").text
    ids = set(re.findall(r'id="([^"]+)"', html))
    procurados = set(re.findall(r'getElementById\("([^"]+)"\)', cliente.get("/app.js").text))
    assert ids and procurados
    assert not ids & procurados


def test_o_editor_traz_desfazer_recomecar_e_baixar(cliente):
    html = cliente.get("/arquivos").text
    assert 'id="arq-desfazer" disabled' in html
    assert 'id="arq-recomecar" disabled' in html
    assert 'id="arq-baixar"' in html
    assert "Baixar PDF" in html


def test_a_folha_vem_de_um_modelo_com_lixeira_desenhada(cliente):
    """O ícone sai do servidor, como os outros: o script só clona o modelo."""
    html = cliente.get("/arquivos").text
    modelo = html[html.index('<template id="arq-modelo-folha">'):html.index("</template>")]
    assert 'draggable="true"' in modelo and 'tabindex="0"' in modelo
    assert 'class="tirar-pagina"' in modelo and "<svg" in modelo


def test_baixar_manda_as_fontes_para_a_rota_de_montar(cliente):
    js = cliente.get("/arquivos.js").text
    assert 'fetch("/api/arquivos/montar"' in js
    assert '"X-Aide": "1"' in js
    # a página é contada do 1 na tela e do 0 no servidor
    assert "p.pagina - 1" in js


def test_inserir_oferece_outro_pdf_ou_uma_imagem(cliente):
    html = cliente.get("/arquivos").text
    caixa = html[html.index('id="arq-inserir"'):html.index('id="arq-inserir-imagem"') + 200]
    assert 'data-inserir="pdf"' in caixa and 'data-inserir="imagem"' in caixa
    assert 'accept=".pdf,application/pdf"' in caixa
    assert 'accept=".jpg,.jpeg,.png,image/jpeg,image/png"' in caixa
    assert 'id="arq-inserir-fim"' in html
    modelo = html[html.index('<template id="arq-modelo-folha">'):html.index("</template>")]
    assert 'class="inserir-antes"' in modelo


def test_miniatura_de_imagem_nao_usa_blob_em_img(cliente):
    """img-src da CSP é 'self' e data:; um <img src="blob:..."> some calado."""
    js = cliente.get("/arquivos.js").text
    assert "createImageBitmap" in js
    assert "createObjectURL" in js  # só para entregar o download
    assert ".src = URL.createObjectURL" not in js


def test_juntar_tem_lista_arrastavel_e_botoes_de_subir_e_descer(cliente):
    html = cliente.get("/arquivos").text
    assert '<section class="card juntar" id="arq-juntar" hidden>' in html
    modelo = html[html.index('<template id="arq-modelo-juntar">'):]
    modelo = modelo[:modelo.index("</template>")]
    assert 'draggable="true"' in modelo and 'tabindex="0"' in modelo
    assert 'data-mover="-1"' in modelo and 'data-mover="1"' in modelo
    assert "Baixar PDF juntado" in html


def test_organizar_e_juntar_usam_a_mesma_rota(cliente):
    """Juntar é montar com todas as páginas de cada um, em sequência."""
    import re

    js = cliente.get("/arquivos.js").text
    assert len(re.findall(r"fetch\(", js)) == 1
    assert js.count("await montar(") == 2
