"""Segredo em arquivo vale o que a permissão dele vale.

Num desktop o umask costuma ser 002, então banco e notas nasceriam 664 —
legíveis por qualquer conta da máquina. Estes testes fixam o contrário.
"""

import os
import subprocess
from pathlib import Path

import pytest

from aide.storage import connect, migrate
from aide.storage.vault import escrever


def modo(caminho) -> int:
    return Path(caminho).stat().st_mode & 0o777


@pytest.fixture(autouse=True)
def umask_frouxo():
    """Reproduz o umask do desktop: sem ele o teste passaria por acidente."""
    anterior = os.umask(0o002)
    yield
    os.umask(anterior)


def test_banco_nasce_so_para_o_dono(tmp_path):
    conn = connect(tmp_path / "d" / "aide.db")
    migrate(conn)
    conn.execute("INSERT INTO tasks (title) VALUES ('x')")
    conn.close()

    assert modo(tmp_path / "d") == 0o700
    assert modo(tmp_path / "d" / "aide.db") == 0o600


def test_arquivos_wal_tambem(tmp_path):
    """O -wal carrega o mesmo conteúdo do banco; adianta pouco fechar só o .db."""
    caminho = tmp_path / "d" / "aide.db"
    conn = connect(caminho)
    migrate(conn)
    conn.execute("INSERT INTO tasks (title) VALUES ('x')")

    wal = Path(str(caminho) + "-wal")
    assert wal.exists()
    assert modo(wal) == 0o600
    conn.close()


def test_nota_nasce_so_para_o_dono(tmp_path):
    from datetime import datetime

    caminho = tmp_path / "v" / "2026-09" / "n.md"
    escrever(caminho, "T", "corpo", None, datetime(2026, 9, 16, 10, 0))

    assert modo(caminho) == 0o600
    assert modo(caminho.parent) == 0o700


def test_conectar_num_banco_frouxo_aperta(tmp_path):
    """Instalação antiga já tem o arquivo 664; abrir precisa consertar."""
    caminho = tmp_path / "d" / "aide.db"
    caminho.parent.mkdir(parents=True)
    caminho.touch()
    caminho.chmod(0o664)

    connect(caminho).close()
    assert modo(caminho) == 0o600


def test_nunca_afrouxa_o_que_ja_esta_fechado(tmp_path):
    """Testa o helper, e não `connect`: o sqlite nem abre um banco 0400."""
    from aide.storage.db import MODO_ARQUIVO, _restringir

    caminho = tmp_path / "x"
    caminho.touch()
    caminho.chmod(0o400)

    _restringir(caminho, MODO_ARQUIVO)
    assert modo(caminho) == 0o400


@pytest.mark.slow
def test_backup_nasce_fechado(tmp_path):
    """O dump é o banco inteiro em texto legível."""
    script = Path(__file__).parent.parent / "deploy" / "backup.sh"
    origem = tmp_path / "origem"
    (origem / "data").mkdir(parents=True)
    (origem / "vault").mkdir()
    (origem / "vault" / "n.md").write_text("nota\n")
    connect(origem / "data" / "aide.db").close()
    migrate(connect(origem / "data" / "aide.db"))

    (origem / ".venv" / "bin").mkdir(parents=True)
    real = Path(__file__).parent.parent / ".venv" / "bin" / "python"
    (origem / ".venv" / "bin" / "python").symlink_to(real.resolve())

    destino = tmp_path / "backup"
    subprocess.run(
        ["bash", str(script)],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
             "MY_AIDE_DIR": str(origem), "MY_AIDE_BACKUP_DIR": str(destino),
             "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        capture_output=True, text=True, check=True,
    )

    assert modo(destino / "data" / "aide.sql") == 0o600
    assert modo(destino / "vault" / "n.md") == 0o600
