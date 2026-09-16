"""A interface web: esqueleto e, sobretudo, a fronteira.

A página mostra tudo — inclusive o que está marcado como `private` — e não pede
senha. O que a torna segura é escutar só em 127.0.0.1. Esse é o teste que não
pode falhar em silêncio, porque a falha dele vaza dado pessoal na rede.
"""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aide.storage import connect, migrate
from aide.web import ENDERECO, criar_app


@pytest.fixture
def app(config, tmp_path):
    def conn_factory():
        conn = connect(tmp_path / "w.db")
        migrate(conn)
        return conn

    return criar_app(config, conn_factory)


@pytest.fixture
def cliente(app):
    return TestClient(app)


# ---------- a fronteira ----------

def test_o_endereco_e_loopback():
    """Constante, não configuração: endereço em arquivo se troca e se esquece."""
    import ipaddress

    assert ipaddress.ip_address(ENDERECO).is_loopback


def test_o_endereco_nao_vem_de_configuracao(config):
    """Se virar opção, a única defesa da interface passa a ser um valor editável."""
    import aide.web.app as modulo

    assert not hasattr(config, "web_host")
    assert modulo.ENDERECO == "127.0.0.1"


def test_o_servidor_so_escuta_em_loopback(monkeypatch, config, tmp_path):
    """O que chega ao uvicorn, e não só o que a constante diz."""
    capturado = {}

    class FakeConfig:
        def __init__(self, app, **kw):
            capturado.update(kw)

    class FakeServer:
        def __init__(self, cfg):
            self.should_exit = False

        def run(self):
            pass

    import uvicorn
    monkeypatch.setattr(uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(uvicorn, "Server", FakeServer)

    from aide.web.servidor import ServidorWeb

    ServidorWeb(config, lambda: connect(tmp_path / "s.db"))
    assert capturado["host"] == "127.0.0.1"
    assert capturado["host"] not in ("0.0.0.0", "::", "")


def test_a_url_anunciada_e_local(config, tmp_path, monkeypatch):
    from aide.web.servidor import ServidorWeb

    monkeypatch.setattr("uvicorn.Server", lambda cfg: type(
        "S", (), {"should_exit": False, "run": lambda self: None})())
    servidor = ServidorWeb(config, lambda: connect(tmp_path / "s.db"), porta=9999)
    assert servidor.url == "http://127.0.0.1:9999"


# ---------- só leitura ----------

def test_nenhuma_rota_escreve(app):
    """Sem POST não há confirmação a pedir nem clique errado a temer."""
    metodos = set()
    for rota in app.routes:
        metodos |= getattr(rota, "methods", set())
    assert metodos <= {"GET", "HEAD"}, f"rota de escrita exposta: {metodos}"


def test_a_api_nao_publica_documentacao(cliente):
    """/docs montaria um formulário de chamada — superfície sem motivo."""
    for caminho in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(caminho).status_code == 404


# ---------- o esqueleto ----------

def test_a_raiz_responde_html(cliente):
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/html")
    assert "my-aide" in resposta.text


def test_a_pagina_declara_fuso_e_idioma(cliente):
    assert 'lang="pt-BR"' in cliente.get("/").text


def test_saude_responde(cliente):
    dados = cliente.get("/saude").json()
    assert dados["ok"] is True
    assert dados["escutando"] == "127.0.0.1"


def test_caminho_desconhecido_e_404(cliente):
    assert cliente.get("/nao-existe").status_code == 404


# ---------- o contexto que as telas vão usar ----------

def test_o_contexto_ve_o_privado(app):
    """É o dono, na máquina dele, numa porta local — como o terminal."""
    ctx = app.state.contexto()
    assert ctx.ver_privado is True
    assert ctx.actor == "web"


def test_cada_pedido_abre_sua_conexao(app):
    """O uvicorn atende em thread; sqlite recusa conexão criada noutra."""
    assert app.state.contexto().conn is not app.state.contexto().conn


# ---------- a moldura ----------

def test_toda_tela_tem_rota(cliente):
    """A navegação mostra 12 links; um deles em 404 é um beco sem saída."""
    from aide.web.paginas import TELAS

    for tela in TELAS:
        resposta = cliente.get(tela.caminho)
        assert resposta.status_code == 200, tela.caminho
        assert tela.rotulo in resposta.text


def test_a_tela_aberta_se_marca_na_navegacao(cliente):
    """aria-current diz ao leitor de tela onde ele está, não só a cor."""
    html = cliente.get("/gastos").text
    assert '<a href="/gastos" aria-current="page">' in html
    assert '<a href="/notas" aria-current="page">' not in html


def test_o_estilo_e_servido_uma_vez(cliente):
    """Inline em cada página, o navegador reprocessaria o mesmo texto a cada clique."""
    resposta = cliente.get("/app.css")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/css")
    assert "--accent:#C4432B" in resposta.text
    assert '<link rel="stylesheet" href="/app.css">' in cliente.get("/").text


def test_o_titulo_da_aba_diz_onde_voce_esta(cliente):
    assert "<title>Calendário · my-aide</title>" in cliente.get("/calendario").text


def test_sem_saldo_anotado_a_lateral_convida_a_anotar(cliente):
    """Melhor pedir o número do que inventar um."""
    html = cliente.get("/").text
    assert "nenhum anotado" in html
    assert "myaide saldo" in html


def test_com_saldo_anotado_a_lateral_mostra(cliente, app):
    from aide.llm import custo as calculo

    calculo.anotar_saldo(app.state.conn_factory(), 4.22, "2026-09-16T17:00-04:00")
    html = cliente.get("/").text
    assert "US$&nbsp;4,22" in html or "4.22" in html


def test_saldo_quebrado_nao_derruba_a_pagina(cliente, app, monkeypatch):
    """A lateral é enfeite perto do conteúdo; ela falha sozinha."""
    monkeypatch.setattr("aide.llm.custo.saldo_estimado",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "Saldo API" in resposta.text


def test_o_texto_da_tela_e_escapado():
    """Título de nota com < ou & não pode virar marcação."""
    from aide.web.paginas import cabecalho

    assert "&lt;script&gt;" in cabecalho("<script>")


def test_icone_e_desenhado_nao_emoji():
    """Emoji vira bloco em tema/fonte que não tem o glifo."""
    from aide.web.icones import icone

    marcacao = icone("gastos")
    assert marcacao.startswith("<svg")
    assert "currentColor" in marcacao  # recolore junto com o texto


def test_valor_usa_virgula_como_a_pagina_toda():
    """A interface é em português; 'US$ 4.21' destoa de 'R$ 10,50' no resto."""
    from aide.web.paginas import usd

    assert usd(4.21) == "US$ 4,21"
    assert usd(0) == "US$ 0,00"


# ---------- painel e hoje ----------

@pytest.fixture
def com_dados(app, registry):
    """Um estado parecido com o real: atrasada, de hoje, nota, gasto."""
    ctx = app.state.contexto()
    registry.call("tasks.create", {"title": "Pagar o IPVA", "due": "2020-01-01T09:00"}, ctx)
    registry.call("tasks.create", {"title": "Comprar pão"}, ctx)
    registry.call("expenses.add", {"amount": "10,50", "description": "almoço",
                                   "category": "alimentação"}, ctx)
    ctx.conn.execute("INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
                     " VALUES ('gpt-5-nano', 'chat', 100, 10)")
    return app


def test_o_painel_mostra_os_numeros_reais(cliente, com_dados):
    html = cliente.get("/").text
    assert "Tarefas abertas" in html
    assert "Regras disparando" in html
    assert "R$ 10,50" in html


def test_hoje_lista_o_que_passou_do_prazo(cliente, com_dados):
    html = cliente.get("/hoje").text
    assert "Pagar o IPVA" in html
    assert "há" in html and "dias" in html


def test_a_data_do_cabecalho_e_em_portugues(cliente):
    """strftime depende do locale do sistema; numa máquina em C sai 'Wednesday'."""
    html = cliente.get("/").text
    for ingles in ("Monday", "Wednesday", "September", "January"):
        assert ingles not in html
    assert " de " in html


def test_o_grafico_aparece_mesmo_sem_dado(cliente, app):
    """Decisão do dono: a moldura fica, para não mudar de forma quando encher."""
    html = cliente.get("/").text
    assert "Chamadas de LLM por dia" in html
    assert "Tarefas criadas por dia" in html
    assert "nenhuma chamada nos últimos 14 dias" in html


def test_grafico_vazio_nao_parece_quebrado():
    from aide.web import graficos

    vazio = graficos.area([], 300, 80, vazio="sem uso ainda")
    assert "<svg" in vazio and "sem uso ainda" in vazio
    assert graficos.colunas([]).count("<svg") == 1


def test_o_eixo_aparece_mesmo_com_a_serie_zerada():
    """Sem rótulo, uma série toda em zero não diz nem de que período é."""
    from aide.web import graficos

    saida = graficos.area([("14", 0), ("15", 0), ("16", 0)], 300, 80)
    assert ">14<" in saida and ">16<" in saida


def test_eixo_denso_e_ralo_para_nao_borrar():
    """14 rótulos lado a lado se encavalam; um sim, um não continua legível."""
    from aide.web import graficos

    pares = [(f"{d:02d}", d) for d in range(1, 15)]
    saida = graficos.area(pares, 600, 96)
    assert ">01<" in saida
    assert ">02<" not in saida  # pulado
    assert ">03<" in saida


def test_serie_de_um_ponto_nao_estoura():
    """Com um dia só, a divisão por (n-1) seria divisão por zero."""
    from aide.web import graficos

    assert "<svg" in graficos.area([("16", 5)], 300, 80)


def test_cada_gradiente_tem_id_proprio():
    """Dois gráficos com o mesmo id: o segundo herda o gradiente do primeiro."""
    from aide.web import graficos

    a = graficos.area([("1", 1), ("2", 2), ("3", 3)], 200, 60)
    b = graficos.area([("1", 3), ("2", 2), ("3", 1)], 200, 60)
    id_a = a.split('id="')[1].split('"')[0]
    id_b = b.split('id="')[1].split('"')[0]
    assert id_a != id_b


def test_a_serie_inclui_dia_sem_nada(app):
    """Dia vazio precisa virar zero; sumir da série encurta o eixo e mente."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from aide.web import consultas

    agora = datetime(2026, 9, 16, 12, 0, tzinfo=ZoneInfo("America/Porto_Velho"))
    serie = consultas.chamadas_por_dia(app.state.conn_factory(), agora, dias=14)
    assert len(serie) == 14
    assert all(v == 0 for _, v in serie)


def test_titulo_de_tarefa_e_escapado(cliente, app, registry):
    ctx = app.state.contexto()
    registry.call("tasks.create", {"title": "<script>alert(1)</script>",
                                   "due": "2020-01-01T09:00"}, ctx)
    html = cliente.get("/hoje").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ---------- calendário ----------

def test_o_mes_mostra_o_que_esta_marcado(cliente, app, registry):
    ctx = app.state.contexto()
    registry.call("tasks.create", {"title": "Pagar o condomínio",
                                   "due": "2026-09-20T09:00"}, ctx)
    html = cliente.get("/calendario").text
    assert "Pagar o condomínio" in html
    assert "Setembro" in html or "setembro" in html.lower()


def test_a_grade_deixa_o_dia_encolher(cliente):
    """Item de grid nasce com min-width:auto — a largura do texto sem quebra.
    Sem min-width:0 a grade transborda e a coluna de domingo sai da tela."""
    html = cliente.get("/calendario").text
    assert "min-width:0" in html


def test_a_semana_tem_os_sete_dias(cliente):
    html = cliente.get("/calendario").text
    for dia in ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"):
        assert f">{dia}<" in html.upper() or dia.lower() in html


def test_junta_tarefa_evento_e_lembrete_no_mesmo_dia(app, registry):
    """O dia acontece junto: você não separa o que veio da agenda do que anotou."""
    from zoneinfo import ZoneInfo

    from aide.web import consultas

    tz = ZoneInfo("America/Porto_Velho")
    ctx = app.state.contexto()
    conn = ctx.conn
    registry.call("tasks.create", {"title": "Tarefa", "due": "2026-09-20T09:00"}, ctx)
    conn.execute("INSERT INTO events (title, start_at, source) "
                 "VALUES ('Evento', '2026-09-20T14:00-04:00', 'ical')")
    conn.execute("INSERT INTO reminders (text, fire_at) "
                 "VALUES ('Lembrete', '2026-09-20T18:00-04:00')")

    dia = consultas.planejado_no_mes(conn, 2026, 9, tz)[20]
    assert {i["tipo"] for i in dia} == {"tarefa", "evento", "lembrete"}


def test_dia_cheio_corta_e_avisa_quantos_faltam(app, registry):
    """Cabem três marcas no quadrado; empilhar mais rompe a altura da linha."""
    ctx = app.state.contexto()
    for nome in ("Dentista", "Mercado", "Oficina", "Contador", "Academia"):
        ctx.conn.execute("INSERT INTO reminders (text, fire_at) VALUES (?, ?)",
                         (nome, "2026-09-20T09:00-04:00"))

    from datetime import datetime
    from zoneinfo import ZoneInfo

    from aide.web import telas

    html = telas.calendario(ctx, registry,
                            datetime(2026, 9, 16, 12, tzinfo=ZoneInfo("America/Porto_Velho")))
    assert "+2" in html


def test_mes_sem_nada_ainda_desenha_a_grade(cliente):
    """A grade é a informação: mostra que a semana está livre."""
    html = cliente.get("/calendario").text
    assert "0 compromisso(s) no mês" in html
    assert html.count("border-radius:12px") > 20


# ---------- gastos ----------

def test_gastos_soma_o_periodo(cliente, app, registry):
    ctx = app.state.contexto()
    registry.call("expenses.add", {"amount": "10,50", "description": "almoço",
                                   "category": "alimentação"}, ctx)
    registry.call("expenses.add", {"amount": "200", "description": "mercado",
                                   "category": "mercado"}, ctx)
    html = cliente.get("/gastos").text
    assert "R$ 210,50" in html
    assert "almoço" in html and "mercado" in html


def test_o_periodo_vem_da_url_e_volta_no_historico(cliente):
    """Link, não botão: a página é de leitura e o voltar do navegador funciona."""
    html = cliente.get("/gastos?periodo=ano").text
    assert 'href="/gastos?periodo=hoje"' in html
    assert cliente.get("/gastos?periodo=hoje").status_code == 200


def test_periodo_invalido_cai_no_mes_em_vez_de_quebrar(cliente):
    assert cliente.get("/gastos?periodo=decada").status_code == 200


def test_o_periodo_e_escrito_por_extenso(cliente):
    """'2026/09/01 a 2026/09/16' é formato de máquina."""
    html = cliente.get("/gastos").text
    assert "2026/09/01" not in html
    assert " de " in html


def test_gastos_vazio_mantem_os_graficos(cliente):
    """Decisão do dono: a moldura fica para não mudar de forma quando encher."""
    html = cliente.get("/gastos").text
    assert "Por categoria" in html
    assert "R$ 0,00" in html
    assert "Nenhum gasto neste período" in html


def test_gasto_privado_aparece_para_o_dono(cliente, app, registry):
    """A web é o dono na máquina dele: ver_privado é True, como no terminal."""
    ctx = app.state.contexto()
    registry.call("expenses.add", {"amount": "199,90", "description": "SEGREDO",
                                   "private": True}, ctx)
    assert "SEGREDO" in cliente.get("/gastos").text


def test_o_acumulado_soma_a_serie():
    from aide.web.consultas import acumulado

    assert acumulado([("1", 10), ("2", 0), ("3", 5)]) == [("1", 10), ("2", 10), ("3", 15)]


# ---------- custo e saldo ----------

def test_custo_mostra_modelo_e_finalidade(cliente, app):
    app.state.conn_factory().execute(
        "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
        " VALUES ('gpt-5-nano', 'chat', 1000000, 0)")
    html = cliente.get("/custo").text
    assert "gpt-5-nano" in html
    assert "Para quê" in html


def test_sem_saldo_anotado_explica_por_que(cliente):
    """A OpenAI não expõe saldo; dizer isso é melhor que mostrar um número falso."""
    html = cliente.get("/custo").text
    assert "não expõe saldo" in html
    assert "myaide saldo" in html


def test_com_saldo_anotado_mostra_a_estimativa(cliente, app):
    from aide.llm import custo as calculo

    calculo.anotar_saldo(app.state.conn_factory(), 4.22, "2026-09-16T17:00-04:00")
    html = cliente.get("/custo").text
    assert "Saldo estimado" in html
    assert "estimativa" in html


def test_o_valor_da_barra_usa_virgula():
    """0.0406 ao lado de US$ 4,21 é o mesmo defeito que a data em inglês."""
    from aide.web import graficos

    saida = graficos.barras([("gpt-5-nano", 0.0406)],
                            formatar=lambda v: f"{v:.4f}".replace(".", ","))
    assert "0,0406" in saida
    assert "0.0406" not in saida
