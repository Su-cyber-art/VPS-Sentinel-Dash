from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Database:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "sentinel.sqlite3"
        with self.connect() as db:
            db.executescript(Path(__file__).with_name("schema.sql").read_text())
            db.execute("PRAGMA journal_mode=WAL")
            # Additive, transactional migrations preserve v0.1 nodes and task history.
            db.execute("BEGIN IMMEDIATE")
            columns = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
            if "cancel_requested" not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
            if self.get(db, "schema_version", 1) < 2:
                if self.get(db, "password"):
                    self.set(db, "must_change_password", True)
                    self.set(db, "username", self.get(db, "username", "admin"))
                    db.execute("DELETE FROM sessions")
                self.set(db, "schema_version", 2)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                if write:
                    db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    @staticmethod
    def get(db, key, default=None):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def set(db, key, value):
        db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, encode(value)))
