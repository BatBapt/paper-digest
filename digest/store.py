"""Persistent state: seen papers and last run status."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    uid TEXT PRIMARY KEY,
    title TEXT,
    source TEXT,
    url TEXT,
    seen_at REAL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL,
    finished_at REAL,
    status TEXT,
    details TEXT
);
"""


class Store:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def is_seen(self, uid: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM seen WHERE uid = ?", (uid,))
        return cur.fetchone() is not None

    def mark_seen(self, paper: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO seen (uid, title, source, url, seen_at) VALUES (?, ?, ?, ?, ?)",
            (paper["uid"], paper.get("title", ""), paper.get("source", ""), paper.get("url", ""), time.time()),
        )
        self.conn.commit()

    def prune(self, days: int = 400) -> None:
        self.conn.execute("DELETE FROM seen WHERE seen_at < ?", (time.time() - days * 86400,))
        self.conn.commit()

    def start_run(self) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, ?)", (time.time(), "running")
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def end_run(self, run_id: int, status: str, details: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, details = ? WHERE id = ?",
            (time.time(), status, json.dumps(details, ensure_ascii=False), run_id),
        )
        self.conn.commit()

    def last_run(self) -> dict[str, Any] | None:
        cur = self.conn.execute(
            "SELECT id, started_at, finished_at, status, details FROM runs ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "started_at": row[1],
            "finished_at": row[2],
            "status": row[3],
            "details": json.loads(row[4]) if row[4] else {},
        }
