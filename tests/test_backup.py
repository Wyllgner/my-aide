"""O ciclo de backup: copiar, restaurar e conferir.

É o teste com a pior consequência se faltar — uma quebra aqui só apareceria no
dia em que você precisasse do backup, que é o pior dia possível para descobrir.

Marcado `slow` porque roda o shell script de verdade: um dublê testaria a
minha ideia do script, não o script.
"""

import sqlite3
import subprocess
from pathlib import Path

import pytest

from aide.storage import connect, migrate

SCRIPT = Path(__file__).parent.parent / "deploy" / "backup.sh"

pytestmark = pytest.mark.slow


@pytest.fixture
def origem(tmp_path):
    """Uma instalação com dado dentro: banco migrado e uma nota no vault."""
    raiz = tmp_path / "origem"
    (raiz / "data").mkdir(parents=True)
    (raiz / "vault" / "2026-09").mkdir(parents=True)
    (raiz / "vault" / "2026-09" / "nota.md").write_text("---\ntitle: X\n---\n\ncorpo\n")

    conn = connect(raiz / "data" / "aide.db")
    migrate(conn)
    conn.execute("INSERT INTO tasks (title, due_at) VALUES ('Boleto', '2026-09-20T09:00')")
    conn.execute("INSERT INTO notes (id, title, path) VALUES (1, 'X', ?)",
                 (str(raiz / "vault" / "2026-09" / "nota.md"),))
    conn.execute("INSERT INTO notes_fts (rowid, title, body) VALUES (1, 'X', 'corpo')")
    conn.close()

    # o .venv do projeto é o python que o script usa
    (raiz / ".venv" / "bin").mkdir(parents=True)
    real = Path(__file__).parent.parent / ".venv" / "bin" / "python"
    (raiz / ".venv" / "bin" / "python").symlink_to(real.resolve())
    return raiz


def rodar(origem, destino):
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin", "HOME": str(origem.parent),
             "MY_AIDE_DIR": str(origem), "MY_AIDE_BACKUP_DIR": str(destino),
             "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        capture_output=True, text=True, check=True,
    )


@pytest.fixture
def destino(tmp_path):
    return tmp_path / "backup"


def test_backup_grava_dump_e_vault(origem, destino):
    saida = rodar(origem, destino).stdout
    assert "backup gravado" in saida
    assert (destino / "data" / "aide.sql").exists()
    assert (destino / "vault" / "2026-09" / "nota.md").exists()
    # o .db binário não entra: bytes instáveis encheriam o histórico
    assert not (destino / "data" / "aide.db").exists()


def test_rodar_de_novo_sem_mudanca_nao_comita(origem, destino):
    """Se o dump fosse binário, todo dia geraria um commit sem mudança nenhuma."""
    rodar(origem, destino)
    assert "nada mudou" in rodar(origem, destino).stdout


def test_mudanca_no_banco_vira_commit(origem, destino):
    rodar(origem, destino)
    conn = sqlite3.connect(origem / "data" / "aide.db")
    conn.execute("INSERT INTO tasks (title) VALUES ('Nova')")
    conn.commit()
    conn.close()

    assert "backup gravado" in rodar(origem, destino).stdout
    assert "Nova" in (destino / "data" / "aide.sql").read_text()


def test_nota_apagada_some_do_backup(origem, destino):
    rodar(origem, destino)
    (origem / "vault" / "2026-09" / "nota.md").unlink()
    rodar(origem, destino)
    assert not (destino / "vault" / "2026-09" / "nota.md").exists()


def test_dump_restaura_num_banco_vazio(origem, destino, tmp_path):
    """O que de fato importa: o dump volta a ser um banco que o projeto abre."""
    rodar(origem, destino)

    restaurado = tmp_path / "restaurado.db"
    conn = sqlite3.connect(restaurado)
    conn.executescript((destino / "data" / "aide.sql").read_text())
    conn.row_factory = sqlite3.Row

    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert [r["title"] for r in conn.execute("SELECT title FROM tasks")] == ["Boleto"]

    # a migration não pode achar que é banco novo e reaplicar tudo por cima
    assert migrate(conn) == []

    # o índice FTS volta vazio de propósito; `myaide reindexar` o repovoa
    assert conn.execute("SELECT COUNT(*) c FROM notes_fts").fetchone()["c"] == 0
    conn.execute("INSERT INTO notes_fts (rowid, title, body) VALUES (1, 'X', 'corpo')")
    assert conn.execute(
        "SELECT COUNT(*) c FROM notes_fts WHERE notes_fts MATCH 'corpo'").fetchone()["c"] == 1


def test_backup_nao_leva_segredo(origem, destino):
    """O .env fica de fora: o backup vai para um repositório remoto."""
    (origem / ".env").write_text("OPENAI_API_KEY=sk-secreta\n")
    rodar(origem, destino)

    tudo = " ".join(p.read_text() for p in destino.rglob("*")
                    if p.is_file() and ".git" not in p.parts)
    assert "sk-secreta" not in tudo
    assert not (destino / ".env").exists()
