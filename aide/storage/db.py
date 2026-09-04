"""Conexão SQLite e migrations por arquivo .sql numerado."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_NAME_RE = re.compile(r"^(\d+)_")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
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
