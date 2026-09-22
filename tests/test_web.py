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
    assert "0 compromissos no mês" in html
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


# ---------- conversas ----------

@pytest.fixture
def com_conversa(app):
    conn = app.state.conn_factory()
    for papel, texto, chamadas in (
        ("user", "o que está atrasado?", None),
        ("assistant", "", '[{"function":{"name":"tasks_list","arguments":"{\\"filter\\":\\"overdue\\"}"}}]'),
        ("assistant", "Quatro coisas passaram do prazo.", None),
    ):
        conn.execute("INSERT INTO messages (session_id, role, content, tool_calls)"
                     " VALUES ('s1', ?, ?, ?)", (papel, texto, chamadas))
    conn.execute("INSERT INTO messages (session_id, role, content) VALUES ('tg9-1', 'user', 'oi')")
    return app


def test_conversas_lista_as_sessoes(cliente, com_conversa):
    html = cliente.get("/conversas").text
    assert "o que está atrasado?" in html
    assert "telegram" in html and "aqui" in html


def test_a_chamada_de_tool_aparece_no_meio_da_conversa(cliente, com_conversa):
    """É onde ela acontece; separá-la esconderia por que ele respondeu aquilo."""
    html = cliente.get("/conversas?sessao=s1").text
    assert "tasks_list" in html
    assert "Quatro coisas passaram do prazo." in html


def test_sessao_desconhecida_cai_na_mais_recente(cliente, com_conversa):
    assert cliente.get("/conversas?sessao=nao-existe").status_code == 200


def test_sem_conversa_nenhuma_diz_onde_falar(cliente):
    html = cliente.get("/conversas").text
    assert "Nenhuma conversa ainda" in html
    assert "myaide chat" in html


def test_mensagem_com_html_e_escapada(cliente, app):
    """O conteúdo vem do que você digitou e do que o modelo escreveu."""
    app.state.conn_factory().execute(
        "INSERT INTO messages (session_id, role, content)"
        " VALUES ('x', 'user', '<img src=x onerror=alert(1)>')")
    html = cliente.get("/conversas").text
    assert "<img src=x" not in html
    assert "&lt;img" in html


# ---------- ferramentas ----------

def test_ferramentas_lista_todas_as_familias(cliente, registry):
    html = cliente.get("/ferramentas").text
    assert f"{len(registry.names())} registradas" in html
    for familia in ("tasks", "notes", "expenses", "usage"):
        assert familia in html


def test_toda_familia_tem_icone_proprio(registry):
    """A família é nome técnico e o ícone tem nome de tela; sem o mapa,
    metade dos cartões cai no traço genérico."""
    from aide.web.telas import ICONE_DA_FAMILIA

    familias = {n.split(".")[0] for n in registry.names()}
    assert familias <= set(ICONE_DA_FAMILIA), familias - set(ICONE_DA_FAMILIA)


def test_a_tool_que_pede_confirmacao_e_marcada(cliente):
    html = cliente.get("/ferramentas").text
    assert "confirma" in html
    assert "não são expostas por MCP" in html


# ---------- auditoria ----------

def test_auditoria_mostra_e_filtra_por_ator(cliente, app, registry, ctx):
    """A web não entra na trilha, então a linha aqui vem do terminal."""
    from aide.tools.registry import ToolContext

    terminal = ToolContext(config=ctx.config, conn=app.state.conn_factory(), actor="cli")
    registry.call("tasks.create", {"title": "X"}, terminal)

    html = cliente.get("/auditoria").text
    assert "tasks.create" in html
    assert "cli" in html

    filtrada = cliente.get("/auditoria?ator=cli").text
    assert "tasks.create" in filtrada


def test_ator_inexistente_volta_para_todos(cliente, app, registry, ctx):
    from aide.tools.registry import ToolContext

    registry.call("tasks.create", {"title": "X"},
                  ToolContext(config=ctx.config, conn=app.state.conn_factory(), actor="cli"))
    assert cliente.get("/auditoria?ator=fulano").status_code == 200


def test_auditoria_vazia_nao_quebra(cliente):
    assert "Nada registrado ainda" in cliente.get("/auditoria").text


# ---------- notas, memória, pessoas, fila ----------

@pytest.fixture
def com_nota(app, registry, tmp_path):
    ctx = app.state.contexto()
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Manutenção do carro",
                                   "body": "trocar o óleo antes da viagem",
                                   "tags": "carro,viagem"}, ctx)
    registry.call("notes.create", {"title": "Reunião de orçamento",
                                   "body": "cortar 20% da nuvem"}, ctx)
    return app


def test_notas_lista_e_abre_o_conteudo(cliente, com_nota):
    html = cliente.get("/notas").text
    assert "Manutenção do carro" in html
    assert "trocar o óleo antes da viagem" in html


def test_abrir_outra_nota_pela_url(cliente, com_nota):
    html = cliente.get("/notas?nota=2").text
    assert "cortar 20% da nuvem" in html


def test_nota_inexistente_cai_na_primeira(cliente, com_nota):
    assert cliente.get("/notas?nota=999").status_code == 200


def test_a_busca_e_um_get(cliente, com_nota):
    """Formulário GET: continua leitura, e o resultado tem URL própria."""
    html = cliente.get("/notas").text
    assert 'method="get"' in html
    assert cliente.get("/notas?busca=carro").status_code == 200


def test_nota_privada_aparece_para_o_dono(cliente, app, registry, tmp_path):
    ctx = app.state.contexto()
    object.__setattr__(ctx.config, "vault_dir", tmp_path / "v")
    registry.call("notes.create", {"title": "Laudo", "body": "SEGREDO",
                                   "private": True}, ctx)
    assert "SEGREDO" in cliente.get("/notas").text


def test_memoria_separa_perfil_de_episodico(cliente, app, registry):
    ctx = app.state.contexto()
    registry.call("memory.save", {"kind": "profile", "key": "treino",
                                  "value": "todo dia às 6h"}, ctx)
    registry.call("memory.save", {"kind": "episodic", "key": "pedro",
                                  "value": "vai se mudar"}, ctx)
    html = cliente.get("/memoria").text
    assert "Perfil" in html and "Episódico" in html
    assert "todo dia às 6h" in html and "vai se mudar" in html


def test_pessoas_marca_quem_esta_em_atraso(cliente, app):
    app.state.conn_factory().execute(
        "INSERT INTO people (name, relation, cadence_days, last_contact_at)"
        " VALUES ('Pedro', 'irmão', 7, '2020-01-01T10:00')")
    html = cliente.get("/pessoas").text
    assert "Pedro" in html
    assert "1 em atraso" in html


def test_sem_pessoa_nenhuma_diz_como_registrar(cliente):
    assert "Ninguém registrado" in cliente.get("/pessoas").text


def test_a_fila_mostra_o_resultado_gravado(cliente, app, registry):
    """É o que faz trabalho feito fora virar memória aqui."""
    ctx = app.state.contexto()
    ordem = registry.call("work_orders.create", {"goal": "Triar atrasadas"}, ctx).data
    registry.call("work_orders.complete",
                  {"id": ordem["id"], "result_summary": "Quatro itens revisados."}, ctx)
    html = cliente.get("/fila").text
    assert "Triar atrasadas" in html
    assert "Quatro itens revisados." in html
    assert "concluída" in html


def test_fila_vazia_diz_como_enfileirar(cliente):
    assert "myaide enfileirar" in cliente.get("/fila").text


# ---------- a trilha de auditoria ----------

def test_abrir_uma_tela_nao_escreve_na_auditoria(cliente, app, registry):
    """A trilha registra o que aconteceu; olhar uma lista não é um acontecimento.

    A janela antiga em PySide6 chegou a responder por 413 de 572 linhas
    consultando em laço, e uma aba deixada aberta faria o mesmo.
    """
    conn = app.state.conn_factory()
    registry.call("tasks.create", {"title": "X"}, app.state.contexto())
    antes = conn.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"]

    for rota in ("/", "/hoje", "/gastos", "/notas", "/ferramentas"):
        assert cliente.get(rota).status_code == 200

    depois = conn.execute("SELECT COUNT(*) c FROM audit").fetchone()["c"]
    assert depois == antes


def test_quem_escreve_continua_sendo_registrado(ctx, registry):
    """Não é um interruptor geral: o padrão audita, e só quem lê desliga."""
    from aide.tools.registry import ToolContext

    assert ToolContext(config=ctx.config, conn=ctx.conn).auditar is True

    registry.call("tasks.create", {"title": "Do terminal"}, ctx)
    linhas = ctx.conn.execute("SELECT tool FROM audit").fetchall()
    assert any(r["tool"] == "tasks.create" for r in linhas)


def test_a_web_so_pode_calar_a_trilha_porque_nao_escreve(app):
    """Se ganhar uma rota de escrita, esta suposição cai — e o teste de
    métodos quebra antes, que é a ordem certa de descobrir."""
    assert app.state.contexto().auditar is False
    metodos = set()
    for rota in app.routes:
        metodos |= getattr(rota, "methods", set())
    assert metodos <= {"GET", "HEAD"}


# ---------- a janela antiga ----------

def test_a_gui_pyside6_nao_existe_mais():
    """Substituída pela web em 16/09. Ficar meia viva seria pior que as duas."""
    import importlib.util
    from pathlib import Path

    assert importlib.util.find_spec("aide.gui") is None
    assert not (Path(__file__).parent.parent / "aide" / "gui").exists()


def test_nenhum_entry_point_aponta_para_a_gui():
    from pathlib import Path

    texto = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    assert "myaide-gui" not in texto
    assert "pyside6" not in texto.lower()


def test_tarefa_descartada_sai_do_calendario(cliente, app, registry):
    """`tasks.drop` marca status, não apaga a linha. Filtrar só por deleted_at
    deixava a tarefa ocupando o dia depois de você tê-la descartado."""
    ctx = app.state.contexto()
    fica = registry.call("tasks.create", {"title": "Condomínio",
                                          "due": "2026-09-20T09:00"}, ctx).data
    sai = registry.call("tasks.create", {"title": "Descartada",
                                         "due": "2026-09-21T09:00"}, ctx).data
    registry.call("tasks.drop", {"id": sai["id"]}, ctx)

    html = cliente.get("/calendario").text
    assert "Condomínio" in html
    assert "Descartada" not in html
    assert fica["id"]


def test_tarefa_concluida_continua_no_calendario(cliente, app, registry):
    """Saber o que foi feito naquele dia é metade do que o mês conta."""
    ctx = app.state.contexto()
    feita = registry.call("tasks.create", {"title": "Boleto da luz",
                                           "due": "2026-09-18T09:00"}, ctx).data
    registry.call("tasks.complete", {"id": feita["id"]}, ctx)
    assert "Boleto da luz" in cliente.get("/calendario").text


def test_a_fila_separa_o_que_espera_do_que_ja_foi(cliente, app, registry):
    """Misturadas, o histórico empurra para baixo o que ainda espera — e
    parece que a fila não atualizou."""
    ctx = app.state.contexto()
    feita = registry.call("work_orders.create", {"goal": "Já feita"}, ctx).data
    registry.call("work_orders.complete", {"id": feita["id"],
                                           "result_summary": "ok"}, ctx)
    registry.call("work_orders.create", {"goal": "Ainda esperando"}, ctx)

    html = cliente.get("/fila").text
    assert "Esperando um executor" in html
    assert "Já feitas" in html
    assert html.index("Ainda esperando") < html.index("Já feita")


def test_fila_sem_nada_esperando_explica(cliente, app, registry):
    ctx = app.state.contexto()
    ordem = registry.call("work_orders.create", {"goal": "Antiga"}, ctx).data
    registry.call("work_orders.complete", {"id": ordem["id"], "result_summary": "x"}, ctx)

    html = cliente.get("/fila").text
    assert "Nada esperando" in html
    assert "0 esperando · 1 no histórico" in html


# ---------- navegar no calendário ----------

def test_da_para_ir_e_voltar_de_mes(cliente):
    setembro = cliente.get("/calendario?ano=2026&mes=9").text
    assert "Setembro" in setembro
    assert "ano=2026&mes=8" in setembro   # anterior
    assert "ano=2026&mes=10" in setembro  # próximo

    assert "Outubro" in cliente.get("/calendario?ano=2026&mes=10").text


def test_a_virada_do_ano_anda_certo():
    """Dezembro → janeiro do ano seguinte, e janeiro → dezembro do anterior."""
    from aide.web.telas import _mes_vizinho

    assert _mes_vizinho(2026, 12, 1) == (2027, 1)
    assert _mes_vizinho(2026, 1, -1) == (2025, 12)
    assert _mes_vizinho(2026, 9, 1) == (2026, 10)


def test_fora_do_mes_atual_aparece_o_atalho_para_hoje(cliente):
    assert ">hoje</a>" in cliente.get("/calendario?ano=2026&mes=10").text
    assert ">hoje</a>" not in cliente.get("/calendario").text


def test_mes_ou_ano_sem_sentido_cai_no_atual(cliente):
    for bagunca in ("?mes=99", "?mes=0", "?ano=99999", "?ano=abc"):
        assert cliente.get("/calendario" + bagunca).status_code in (200, 422)


def test_clicar_no_dia_abre_o_detalhe(cliente, app, registry):
    ctx = app.state.contexto()
    registry.call("tasks.create", {"title": "Reunião com o contador",
                                   "due": "2026-09-20T14:30"}, ctx)

    html = cliente.get("/calendario?ano=2026&mes=9&dia=20").text
    assert "20/09/2026" in html
    assert "Reunião com o contador" in html
    assert "14:30" in html
    assert "tarefa" in html


def test_o_dia_inteiro_e_clicavel_nao_so_a_etiqueta(cliente):
    """Mirar numa tarja de 11px é pior do que não poder clicar."""
    html = cliente.get("/calendario?ano=2026&mes=9").text
    assert 'href="/calendario?ano=2026&mes=9&dia=1"' in html


def test_dia_sem_nada_diz_que_esta_livre(cliente):
    html = cliente.get("/calendario?ano=2026&mes=9&dia=7").text
    assert "Nada marcado neste dia" in html


def test_dia_que_nao_existe_no_mes_e_ignorado(cliente):
    """31 de setembro não existe; melhor mostrar o mês que estourar."""
    html = cliente.get("/calendario?ano=2026&mes=9&dia=31").text
    assert html.count("Nada marcado neste dia") == 0
    assert "Setembro" in html


def test_o_detalhe_diz_de_onde_o_item_veio(cliente, app):
    """Tarefa, agenda e lembrete caem no mesmo dia; qual é qual importa."""
    conn = app.state.conn_factory()
    conn.execute("INSERT INTO events (title, start_at, source) "
                 "VALUES ('Dentista', '2026-09-21T15:00-04:00', 'ical')")
    conn.execute("INSERT INTO reminders (text, fire_at) "
                 "VALUES ('Ligar para a KA', '2026-09-21T18:00-04:00')")

    html = cliente.get("/calendario?ano=2026&mes=9&dia=21").text
    assert "agenda" in html and "lembrete" in html
    assert "Dentista" in html and "Ligar para a KA" in html


def test_a_semana_comeca_no_domingo(cliente):
    """Como se lê calendário no Brasil."""
    html = cliente.get("/calendario?ano=2026&mes=9").text
    ordem = [d for d in ("dom", "seg", "ter", "qua", "qui", "sex", "sáb")]
    posicoes = [html.index(f">{d}<") for d in ordem]
    assert posicoes == sorted(posicoes), "o cabeçalho não está em ordem"


def test_o_cabecalho_gira_junto_com_a_grade():
    """O `calendar` conta a semana da segunda; trocar um e esquecer o outro
    põe cada dia na coluna errada, e sem erro nenhum."""
    import datetime
    from calendar import Calendar

    from aide.web.telas import DIAS_CURTOS, PRIMEIRO_DIA

    nomes = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
    semanas = Calendar(firstweekday=PRIMEIRO_DIA).monthdayscalendar(2026, 9)
    for semana in semanas:
        for coluna, dia in enumerate(semana):
            if dia:
                real = nomes[datetime.date(2026, 9, dia).weekday()]
                assert DIAS_CURTOS[coluna] == real, f"dia {dia} na coluna errada"


# ---------- custo por mensagem ----------

def _gravar_uso(conn, sessao, turno, modelo="gpt-5-nano", entrada=1_000_000, saida=0):
    conn.execute(
        "INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens,"
        " session_id, turn_id) VALUES (?, 'chat', ?, ?, ?, ?)",
        (modelo, entrada, saida, sessao, turno))


def test_a_volta_inteira_conta_para_a_pergunta(app):
    """Uma pergunta gera várias chamadas — o laço de tools. Separar por chamada
    diria quanto custou um passo; o que interessa é quanto custou a pergunta."""
    from aide.web import consultas

    conn = app.state.conn_factory()
    _gravar_uso(conn, "s1", 10)
    _gravar_uso(conn, "s1", 10)
    _gravar_uso(conn, "s1", 20)

    por_turno = consultas.custo_por_turno(conn, "s1", app.state.config.llm.precos)
    assert por_turno[10]["chamadas"] == 2
    assert por_turno[10]["tokens"] == 2_000_000
    assert por_turno[20]["chamadas"] == 1


def test_o_selo_aparece_ao_lado_da_resposta(cliente, app):
    conn = app.state.conn_factory()
    conn.execute("INSERT INTO messages (id, session_id, role, content)"
                 " VALUES (10, 's1', 'user', 'quantas tarefas?')")
    conn.execute("INSERT INTO messages (session_id, role, content)"
                 " VALUES ('s1', 'assistant', 'Você tem 5.')")
    _gravar_uso(conn, "s1", 10)

    html = cliente.get("/conversas?sessao=s1").text
    assert "1.000.000 tokens" in html
    assert "US$ 0,0500" in html  # nano: 0,05 por 1M de entrada


def test_conversa_antiga_nao_ganha_custo_zero(cliente, app):
    """Antes de 16/09 a chamada não era ligada à conversa. Zero ali afirmaria
    que foi de graça; some é honesto."""
    conn = app.state.conn_factory()
    conn.execute("INSERT INTO messages (id, session_id, role, content)"
                 " VALUES (10, 's1', 'user', 'oi')")
    conn.execute("INSERT INTO messages (session_id, role, content)"
                 " VALUES ('s1', 'assistant', 'olá')")
    conn.execute("INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
                 " VALUES ('gpt-5-nano', 'chat', 500, 0)")  # sem sessão nem turno

    html = cliente.get("/conversas?sessao=s1").text
    assert "tokens" not in html


def test_modelo_sem_preco_e_dito_em_vez_de_virar_zero(cliente, app):
    conn = app.state.conn_factory()
    conn.execute("INSERT INTO messages (id, session_id, role, content)"
                 " VALUES (10, 's1', 'user', 'oi')")
    conn.execute("INSERT INTO messages (session_id, role, content)"
                 " VALUES ('s1', 'assistant', 'olá')")
    _gravar_uso(conn, "s1", 10, modelo="modelo-novo")

    assert "sem preço no config" in cliente.get("/conversas?sessao=s1").text


def test_valor_minusculo_nao_vira_zero_redondo(cliente, app):
    conn = app.state.conn_factory()
    conn.execute("INSERT INTO messages (id, session_id, role, content)"
                 " VALUES (10, 's1', 'user', 'oi')")
    conn.execute("INSERT INTO messages (session_id, role, content)"
                 " VALUES ('s1', 'assistant', 'olá')")
    _gravar_uso(conn, "s1", 10, entrada=100)

    assert "menos de US$ 0,0001" in cliente.get("/conversas?sessao=s1").text


# ---------- tetos de gasto na página ----------

@pytest.fixture
def com_tetos(app):
    """Tetos postos aqui, e com categorias que ninguém teria de verdade: lendo do
    `config.local.yaml` do dono o teste passaria nesta máquina e falharia num
    clone limpo, ou o contrário."""
    from aide.config import GastosConfig

    object.__setattr__(app.state.config, "gastos",
                       GastosConfig(tetos_centavos={"cinema": 42_00, "barbearia": 17_00}))
    return app


def test_gastos_mostra_o_medidor_de_cada_teto(cliente, com_dados, com_tetos):
    html = cliente.get("/gastos").text
    assert "Tetos do mês" in html
    assert "cinema" in html and "R$ 42,00" in html
    assert "barbearia" in html and "R$ 17,00" in html


def test_gasto_em_categoria_sem_teto_aparece_mesmo_assim(cliente, com_dados, com_tetos):
    """É o ponto cego: sem esta linha o mês estoura em categoria que a tela
    não mostra."""
    html = cliente.get("/gastos").text
    assert "sem teto:" in html
    assert "alimentação" in html


def test_sem_teto_declarado_a_pagina_ensina_a_declarar(cliente, com_dados):
    from aide.config import GastosConfig

    object.__setattr__(com_dados.state.config, "gastos", GastosConfig())
    html = cliente.get("/gastos").text
    assert "Nenhum teto declarado" in html
    assert "gastos.tetos" in html


def test_painel_lista_todas_as_regras_registradas(cliente, com_dados):
    """A lista era escrita à mão e as duas regras de dinheiro ficariam de fora
    sem ninguém notar."""
    from aide.scheduler import rules

    html = cliente.get("/").text
    assert "teto de gasto" in html
    assert "gasto atípico" in html
    # nenhuma regra registrada fica fora da tela
    assert len(rules.rule_names()) == html.count('style="width:18px;')


def test_hoje_marca_a_tarefa_que_se_repete(cliente, app, registry):
    ctx = app.state.contexto()
    registry.call("tasks.create", {"title": "pagar o aluguel", "due": "2020-01-10T09:00",
                                   "recurrence": "monthly"}, ctx)
    html = cliente.get("/hoje").text
    assert "todo mês" in html


def test_notas_conta_o_que_esta_na_lixeira(cliente, app, registry, tmp_path):
    """Apagar move o arquivo para lá; sem mostrar, é pasta que só cresce."""
    vault = tmp_path / "v"
    (vault / ".trash").mkdir(parents=True)
    (vault / ".trash" / "velha.md").write_text("---\ntitle: Velha\n---\n\ncorpo\n")
    object.__setattr__(app.state.config, "vault_dir", vault)

    html = cliente.get("/notas").text
    assert "1 arquivo na lixeira" in html
