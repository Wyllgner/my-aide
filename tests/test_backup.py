"""O ciclo de backup: copiar, restaurar e conferir.

É o teste com a pior consequência se faltar — uma quebra aqui só apareceria no
dia em que você precisasse do backup, que é o pior dia possível para descobrir.

Marcado `slow` porque roda o shell script de verdade: um dublê testaria a
minha ideia do script, não o script.
"""

import shutil
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


def rodar(origem, destino, check=True, **extra):
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env={"PATH": "/usr/bin:/bin", "HOME": str(origem.parent),
             "MY_AIDE_DIR": str(origem), "MY_AIDE_BACKUP_DIR": str(destino),
             "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", **extra},
        capture_output=True, text=True, check=check,
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


# ---------- o cofre: só criptografado sai da máquina ----------

com_age = pytest.mark.skipif(not shutil.which("age"), reason="sem age instalado")


def remoto_vazio(caminho):
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(caminho)], check=True)
    return caminho


def commits(remoto) -> list[str]:
    feito = subprocess.run(["git", "-C", str(remoto), "log", "--format=%H", "main"],
                           capture_output=True, text=True, check=False)
    return feito.stdout.split()


def test_copia_local_nunca_e_enviada(origem, destino, tmp_path):
    """Antes, um `origin` na cópia local empurrava o banco inteiro em texto
    puro. Agora a cópia local não sai, com ou sem remoto."""
    remoto = remoto_vazio(tmp_path / "remoto-local.git")
    subprocess.run(["git", "init", "-q", "-b", "main", str(destino)], check=True)
    subprocess.run(["git", "-C", str(destino), "remote", "add", "origin", str(remoto)], check=True)
    rodar(origem, destino)
    assert commits(remoto) == []


def test_sem_chave_nao_ha_cofre(origem, destino, tmp_path):
    saida = rodar(origem, destino, MY_AIDE_BACKUP_COFRE=str(tmp_path / "cofre")).stdout
    assert "backup só local" in saida
    assert not (tmp_path / "cofre").exists()


@pytest.fixture
def chave(tmp_path):
    caminho = tmp_path / "chave" / "backup.key"
    caminho.parent.mkdir()
    subprocess.run(["age-keygen", "-o", str(caminho)], capture_output=True, check=True)
    caminho.chmod(0o600)
    return caminho


@pytest.fixture
def cofre(tmp_path):
    return tmp_path / "cofre"


def com_cofre(origem, destino, chave, cofre, check=True, **extra):
    return rodar(origem, destino, check=check, MY_AIDE_BACKUP_CHAVE=str(chave),
                 MY_AIDE_BACKUP_COFRE=str(cofre), **extra)


@com_age
def test_cofre_abre_com_a_chave_e_nao_tem_texto_puro(origem, destino, chave, cofre, tmp_path):
    com_cofre(origem, destino, chave, cofre)
    pacotes = sorted((cofre / "backups").glob("*.age"))
    assert len(pacotes) == 1
    assert b"Boleto" not in pacotes[0].read_bytes()      # criptografado de fato
    aberto = tmp_path / "aberto"
    aberto.mkdir()
    subprocess.run(f"age -d -i {chave} {pacotes[0]} | tar -xz -C {aberto}",
                   shell=True, check=True)
    assert "Boleto" in (aberto / "data" / "aide.sql").read_text()
    assert (aberto / "vault" / "2026-09" / "nota.md").exists()


@com_age
def test_envio_e_um_commit_so_com_os_pacotes(origem, destino, chave, cofre, tmp_path):
    remoto = remoto_vazio(tmp_path / "remoto.git")
    com_cofre(origem, destino, chave, cofre)
    subprocess.run(["git", "-C", str(cofre), "remote", "add", "origin", str(remoto)], check=True)
    for titulo in ("Mais uma", "E outra"):
        conn = sqlite3.connect(origem / "data" / "aide.db")
        conn.execute("INSERT INTO tasks (title) VALUES (?)", (titulo,))
        conn.commit()
        conn.close()
        assert "cofre enviado" in com_cofre(origem, destino, chave, cofre).stdout
    # o remoto tem um commit só, e nele só pacote criptografado
    assert len(commits(remoto)) == 1
    arquivos = subprocess.run(["git", "-C", str(remoto), "ls-tree", "-r", "--name-only", "main"],
                              capture_output=True, text=True, check=True).stdout.split()
    assert arquivos and all(a.startswith("backups/") and a.endswith(".age") for a in arquivos)


@com_age
def test_guarda_so_os_ultimos(origem, destino, chave, cofre):
    for i in range(4):
        conn = sqlite3.connect(origem / "data" / "aide.db")
        conn.execute("INSERT INTO tasks (title) VALUES (?)", (f"t{i}",))
        conn.commit()
        conn.close()
        com_cofre(origem, destino, chave, cofre, MY_AIDE_BACKUP_MANTER="2")
        __import__("time").sleep(1.1)     # o nome do pacote vai até o segundo
    assert len(list((cofre / "backups").glob("*.age"))) == 2


@com_age
def test_chave_com_permissao_aberta_para_tudo(origem, destino, chave, cofre):
    chave.chmod(0o644)
    feito = com_cofre(origem, destino, chave, cofre, check=False)
    assert feito.returncode != 0
    assert "precisa de permissão 600" in feito.stderr
    assert not (cofre / "backups").exists()


def test_com_chave_mas_sem_age_falha_em_vez_de_enviar(origem, destino, tmp_path, cofre):
    chave = tmp_path / "k"
    chave.write_text("AGE-SECRET-KEY-falsa")
    chave.chmod(0o600)
    vazio = tmp_path / "bin-vazio"
    vazio.mkdir()
    for programa in ("bash", "git", "rsync", "mkdir", "stat", "date", "ls", "sort", "head",
                     "xargs", "rm", "mv", "tar", "grep", "cat", "dirname", "basename"):
        real = shutil.which(programa)
        if real:
            (vazio / programa).symlink_to(real)
    feito = rodar(origem, destino, check=False, PATH=str(vazio),
                  MY_AIDE_BACKUP_CHAVE=str(chave), MY_AIDE_BACKUP_COFRE=str(cofre))
    assert feito.returncode != 0
    assert "age não está instalado" in feito.stderr
