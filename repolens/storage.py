"""The only module that touches the database (SQLite now, Postgres at V4: see D11).

Never store user API keys here.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(".cache/repolens.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    repo    TEXT NOT NULL,
    sha     TEXT NOT NULL,
    kind    TEXT NOT NULL,        -- 'analysis' | 'narrative'
    data    TEXT NOT NULL,        -- JSON
    created REAL NOT NULL,
    PRIMARY KEY (repo, sha, kind)
)"""


class Store:
    def __init__(self, path: Path | str = DEFAULT_DB):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute(_SCHEMA)
        self.db.commit()

    def get(self, repo: str, sha: str, kind: str) -> dict | None:
        row = self.db.execute("SELECT data FROM artifacts WHERE repo=? AND sha=? AND kind=?",
                              (repo, sha, kind)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except ValueError:
            return None  # corrupt row: behave as a cache miss

    def put(self, repo: str, sha: str, kind: str, data: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?)",
                        (repo, sha, kind, json.dumps(data), time.time()))
        self.db.commit()

    def close(self) -> None:
        self.db.close()
