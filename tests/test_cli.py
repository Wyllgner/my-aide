"""Comandos da CLI que nunca tinham teste.

Todos rodam contra uma raiz isolada por `AIDE_ROOT`: sem isso o teste abriria
o banco real do dono e, pior, o `.env` com as credenciais de verdade.
"""

import pytest
from typer.testing import CliRunner

from aide.cli import app


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    """Uma instalação vazia do my-aide, longe dos dados reais."""
    (tmp_path / "config.yaml").write_text(
        "timezone: America/Sao_Paulo\nuser_name: Teste\n"
        "paths:\n  data_dir: data\n  vault_dir: vault\n"
    )
    (tmp_path / ".env").write_text("")
    monkeypatch.setenv("AIDE_ROOT", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return tmp_path


@pytest.fixture
def run(raiz):
    runner = CliRunner()

    def invocar(*args):
        resultado = runner.invoke(app, list(args))
        if resultado.exception and not isinstance(resultado.exception, SystemExit):
            raise resultado.exception
        return resultado

    invocar("init")
    return invocar


# ---------- doctor ----------

def test_doctor_lista_as_verificacoes(run):
    saida = run("doctor").output
    for esperado in ("config.yaml lido", "banco", "tools", "telegram", "embeddings"):
        assert esperado in saida


def test_doctor_acusa_chave_faltando(run):
    assert "faltando" in run("doctor").output


def test_doctor_acusa_embedding_de_outro_modelo(run, raiz):
    """A checagem que faz a falha silenciosa dos vetores aparecer sem buscar."""
    import sqlite3

    conn = sqlite3.connect(raiz / "data" / "aide.db")
    conn.execute(
        "INSERT INTO notes (id, title, path) VALUES (1, 'X', ?)", (str(raiz / "x.md"),))
    conn.execute(
        "INSERT INTO embeddings (ref_type, ref_id, chunk, vector, model)"
        " VALUES ('note', 1, 'x', X'00', 'modelo-antigo')")
    conn.commit()
    conn.close()

    saida = run("doctor").output
    assert "modelo-antigo" in saida
    assert "reindexar" in saida


# ---------- pessoas ----------

def test_pessoas_vazio_diz_que_nao_ha_ninguem(run):
    assert "Ninguém registrado" in run("pessoas").output


def _cadastrar(raiz, nome, cadencia=None, ultimo=None):
    """A CLI não cria pessoa — só `people.add`, por chat ou MCP. Ver test abaixo."""
    import sqlite3

    conn = sqlite3.connect(raiz / "data" / "aide.db")
    conn.execute(
        "INSERT INTO people (name, relation, cadence_days, last_contact_at)"
        " VALUES (?, 'irmão', ?, ?)", (nome, cadencia, ultimo))
    conn.commit()
    conn.close()


def test_pessoas_lista_quem_esta_cadastrado(run, raiz):
    _cadastrar(raiz, "Pedro", cadencia=14)
    saida = run("pessoas").output
    assert "Pedro" in saida
    assert "a cada 14d" in saida


def test_pessoas_atrasados_mostra_so_quem_passou_da_cadencia(run, raiz):
    _cadastrar(raiz, "Pedro", cadencia=7, ultimo="2020-01-01T10:00")
    _cadastrar(raiz, "Ana", cadencia=None)

    todos = run("pessoas").output
    assert "Pedro" in todos and "Ana" in todos

    atrasados = run("pessoas", "--atrasados").output
    assert "Pedro" in atrasados
    assert "Ana" not in atrasados


def test_falei_marca_o_contato(run, raiz):
    _cadastrar(raiz, "Pedro", cadencia=7, ultimo="2020-01-01T10:00")
    assert "ok" in run("falei", "Pedro", "vai se mudar").output
    # deixou de estar em atraso, e a conversa virou memória
    assert "Pedro" not in run("pessoas", "--atrasados").output


def test_falei_com_desconhecido_diz_que_nao_conhece(run):
    """A CLI não cadastra ninguém: registrar pessoa é `people.add`, por chat ou MCP."""
    resultado = run("falei", "Fulano")
    assert resultado.exit_code == 1
    assert "não conheço" in resultado.output


# ---------- enfileirar ----------

def test_enfileirar_cria_ordem_e_aparece_na_fila(run):
    assert "enfileirada" in run("enfileirar", "Organizar notas fiscais").output
    assert "Organizar notas fiscais" in run("fila").output


def test_enfileirar_guarda_o_contexto(run):
    run("enfileirar", "Fazer X", "-c", "os arquivos estão em ~/Downloads")
    assert "~/Downloads" in run("fila").output


# ---------- checar ----------

def test_checar_sem_nada_nao_inventa_cobranca(run):
    saida = run("checar").output
    assert "atrasadas" not in saida


def test_checar_mostra_o_que_a_regra_ve(run):
    run("add", "Boleto", "-d", "2020-01-01T09:00")
    saida = run("checar").output
    assert "atrasadas" in saida
    assert "Boleto" in saida


# ---------- mcp-config ----------

def test_mcp_config_imprime_bloco_colavel(run):
    import json
    import re

    saida = run("mcp-config").output
    bloco = json.loads(re.search(r"\{.*\}", saida, re.DOTALL).group())
    assert "my-aide" in bloco["mcpServers"]
    assert bloco["mcpServers"]["my-aide"]["command"].endswith("myaide-mcp")


def test_mcp_config_aponta_para_um_binario_que_existe(run):
    """Bloco com caminho errado só falha depois, dentro do cliente MCP."""
    import json
    import pathlib
    import re

    bloco = json.loads(re.search(r"\{.*\}", run("mcp-config").output, re.DOTALL).group())
    assert pathlib.Path(bloco["mcpServers"]["my-aide"]["command"]).exists()


# ---------- fuso ----------

def test_prazo_aparece_no_fuso_de_hoje():
    """Prazo gravado noutro fuso — mudança de cidade, ou feed iCal — precisa
    ser convertido antes de exibir, senão você lê a hora de lá achando que é a
    sua. A comparação de atraso sempre usou o instante e não depende disto."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from aide.comandos.base import _fmt_due

    agora = datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo("America/Porto_Velho"))

    # 08:00 em São Paulo (-03) são 07:00 em Porto Velho (-04)
    texto, cor = _fmt_due("2026-09-04T08:00-03:00", agora)
    assert texto == "04/09 (há 16 dias)"
    assert cor == "red"  # já venceu

    # gravado no fuso local, aparece na hora de lá
    assert _fmt_due("2026-09-21T08:00-04:00", agora)[0] == "21/09 (amanhã 08:00)"


def test_prazo_sem_fuso_e_lido_como_local():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from aide.comandos.base import _fmt_due

    agora = datetime(2026, 9, 20, 12, 0, tzinfo=ZoneInfo("America/Porto_Velho"))
    assert _fmt_due("2026-09-25T08:00", agora)[0] == "25/09 (sexta 08:00)"


# ---------- gastos ----------

def test_gasto_registra_com_texto_solto(run):
    """O caso que motivou a ferramenta."""
    saida = run("gasto", "10,50 almoço com a KA").output
    assert "R$ 10,50" in saida
    assert "almoço com a KA" in saida


def test_gasto_nao_gasta_llm(run, raiz):
    """Registrar é parse determinístico: sem chave da OpenAI tem de funcionar."""
    assert "R$ 32,00" in run("gasto", "R$ 32 uber").output
    import sqlite3
    conn = sqlite3.connect(raiz / "data" / "aide.db")
    assert conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0] == 0


def test_gasto_sem_valor_explica_o_formato(run):
    resultado = run("gasto", "almoço com a KA")
    assert resultado.exit_code == 1
    assert "10,50 almoço" in resultado.output


def test_quanto_soma_o_periodo(run):
    run("gasto", "10,50 almoço", "-c", "alimentação")
    run("gasto", "200 mercado", "-c", "mercado")
    saida = run("quanto", "mes").output
    assert "R$ 210,50" in saida
    assert "mercado" in saida


def test_gastos_lista_os_lancamentos(run):
    run("gasto", "10,50 almoço")
    saida = run("gastos").output
    assert "almoço" in saida
    assert "R$ 10,50" in saida


def test_quanto_sem_gasto_nenhum(run):
    assert "Nenhum gasto" in run("quanto", "hoje").output


# ---------- status ----------

def test_status_nao_conta_atrasada_como_vencendo_hoje(run):
    """Dizia "2 atrasadas · 2 vencem hoje" sobre as mesmas duas tarefas."""
    run("init")
    run("add", "tarefa velha", "--prazo", "2020-01-01T09:00")
    saida = run("status").stdout

    linhas = {l.split(maxsplit=1)[1].strip(): l.split(maxsplit=1)[0]
              for l in saida.splitlines() if l.strip() and l.split()[0].isdigit()}
    assert linhas["atrasadas"] == "1"
    assert linhas["vencem hoje"] == "0"


def test_status_conta_o_que_vence_hoje(run):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    run("init")
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(hour=23, minute=0)
    run("add", "tarefa de hoje", "--prazo", hoje.isoformat(timespec="minutes"))
    saida = run("status").stdout
    assert "1  vencem hoje" in " ".join(saida.split("\n"))


def test_status_mostra_a_ultima_atividade_na_hora_daqui(run, raiz):
    """O carimbo do audit é UTC: cru, ele adianta 3h e pode virar o dia."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    run("init")
    run("add", "qualquer coisa")
    saida = run("status").stdout

    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    esperado = {(agora - timedelta(minutes=2)).strftime("%d/%m %H:%M"),
                (agora - timedelta(minutes=1)).strftime("%d/%m %H:%M"),
                agora.strftime("%d/%m %H:%M")}
    assert any(f"última atividade: {e}" in saida for e in esperado), saida


def test_numero_grande_sai_com_ponto_no_milhar(run, raiz):
    """654,638 é o número inglês; ao lado de R$ escrito certo fica incoerente."""
    import sqlite3

    run("init")
    conn = sqlite3.connect(raiz / "data" / "aide.db")
    conn.execute("INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
                 " VALUES ('gpt-4.1', 'chat', 654638, 5003)")
    conn.commit()
    conn.close()

    saida = run("status").stdout
    assert "654.638" in saida
    assert "654,638" not in saida


# ---------- histórico ----------

def test_historico_mostra_a_hora_daqui_e_o_dia_no_cabecalho(run, raiz):
    """`created_at` é UTC: cru, a conversa das 19:17 aparecia às 22:17."""
    import sqlite3

    run("init")
    conn = sqlite3.connect(raiz / "data" / "aide.db")
    conn.execute("INSERT INTO messages (session_id, role, content, created_at)"
                 " VALUES ('tg:1', 'user', 'oi', '2026-09-17 22:17:00')")
    conn.commit()
    conn.close()

    saida = run("historico").stdout
    assert "Quinta, 17 de setembro" in saida
    assert "19:17" in saida
    assert "2026-09-17 22:17:00" not in saida


def test_historico_nao_repete_a_data_em_cada_linha(run, raiz):
    import sqlite3

    run("init")
    conn = sqlite3.connect(raiz / "data" / "aide.db")
    for hora in ("12:00", "12:05", "12:09"):
        conn.execute("INSERT INTO messages (session_id, role, content, created_at)"
                     " VALUES ('cli', 'user', 'oi', ?)", (f"2026-09-17 {hora}:00",))
    conn.commit()
    conn.close()

    saida = run("historico").stdout
    assert saida.count("17 de setembro") == 1


def test_usage_mostra_quanto_custou(run, raiz):
    """A pergunta que se faz olhando consumo é quanto ele custou."""
    import sqlite3

    run("init")
    conn = sqlite3.connect(raiz / "data" / "aide.db")
    conn.execute("INSERT INTO llm_usage (model, purpose, input_tokens, output_tokens)"
                 " VALUES ('gpt-4.1', 'chat', 1000000, 0)")
    conn.commit()
    conn.close()

    saida = run("usage").stdout
    assert "US$" in saida
    assert "total" in saida


def test_barra_de_custo_diz_o_que_mede(run, raiz):
    """Barra sem legenda não diz se o cheio é o que sobrou ou o que já foi."""
    run("init")
    run("saldo", "4,22")
    saida = run("saldo").stdout
    assert "já foi" in saida
    assert "US$ 4,22" in saida
    assert "US$ 4.22" not in saida


def test_ajuda_agrupa_os_comandos_por_assunto(run):
    """Trinta e oito comandos numa lista só obrigam a ler tudo para achar um."""
    saida = run("--help").stdout
    for painel in ("Tarefas", "Dinheiro", "Notas e memória", "Diagnóstico", "Instalação"):
        assert painel in saida, painel
    # o que se usa todo dia aparece antes da instalação
    assert saida.index("Tarefas") < saida.index("Instalação")
