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
