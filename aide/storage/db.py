"""Conexão SQLite e migrations por arquivo .sql numerado."""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME_RE = re.compile(r"^(\d+)_")


# O banco guarda tarefas, notas, memória e a conversa inteira. Num desktop com
# umask 002 ele nasceria 664 — legível por qualquer conta da máquina. Segredo em
# arquivo é só tão bom quanto a permissão dele.
MODO_DIR = 0o700
MODO_ARQUIVO = 0o600


def _restringir(caminho: Path, modo: int) -> None:
    """Aperta a permissão se estiver frouxa. Nunca afrouxa o que já está apertado."""
    try:
        atual = caminho.stat().st_mode & 0o777
        if atual & ~modo:
            caminho.chmod(atual & modo)
    except OSError:
        # sistema de arquivos sem permissão POSIX não é motivo para não abrir
        log.debug("não consegui ajustar a permissão de %s", caminho, exc_info=True)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=MODO_DIR)
    _restringir(db_path.parent, MODO_DIR)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # o -wal e o -shm carregam o mesmo conteúdo do banco
    for sufixo in ("", "-wal", "-shm"):
        _restringir(Path(str(db_path) + sufixo), MODO_ARQUIVO)
    return conn


def _applied_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _migrations() -> list[tuple[int, Path]]:
    found = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = _NAME_RE.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    return sorted(found)


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Aplica as migrations pendentes. Devolve os nomes aplicados."""
    current = _applied_version(conn)
    applied: list[str] = []

    for version, path in _migrations():
        if version <= current:
            continue
        # executescript já roda em sua própria transação; se o .sql quebrar no
        # meio, a versão não avança e a migration é reaplicada na próxima vez.
        conn.executescript(path.read_text())
        conn.execute(f"PRAGMA user_version = {version}")
        applied.append(path.name)

    return applied
