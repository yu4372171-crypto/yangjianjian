"""Minimal project database handle used by the recovered video modules."""

from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path
from types import SimpleNamespace


class DatabaseManager:
    def __init__(self):
        self.path: Path | None = None
        self.engine = SimpleNamespace(url=SimpleNamespace(database=""))

    def open(self, db_path: str | Path) -> Path:
        path = Path(db_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS project_metadata "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        self.path = path
        self.engine = SimpleNamespace(url=SimpleNamespace(database=str(path)))
        return path

    def close(self) -> None:
        self.path = None
        self.engine = SimpleNamespace(url=SimpleNamespace(database=""))
