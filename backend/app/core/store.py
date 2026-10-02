import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS transactions (
                    key TEXT PRIMARY KEY, verifier TEXT, challenge TEXT, redirect TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS users (
                    github_id INTEGER PRIMARY KEY, login TEXT, avatar_url TEXT, credentials TEXT);
                CREATE TABLE IF NOT EXISTS handoffs (
                    key TEXT PRIMARY KEY, github_id INTEGER, challenge TEXT, expires REAL, session_ttl INTEGER);
                CREATE TABLE IF NOT EXISTS sessions (
                    key TEXT PRIMARY KEY, github_id INTEGER, expires REAL);
                CREATE TABLE IF NOT EXISTS limits (
                    key TEXT PRIMARY KEY, count INTEGER, expires REAL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def consume(self, table, key):
        queries = {
            "transactions": (
                "SELECT * FROM transactions WHERE key = ?",
                "DELETE FROM transactions WHERE key = ?",
            ),
            "handoffs": (
                "SELECT * FROM handoffs WHERE key = ?",
                "DELETE FROM handoffs WHERE key = ?",
            ),
        }
        if table not in queries:
            raise ValueError("Unknown one-use table")
        select, delete = queries[table]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(select, (digest(key),)).fetchone()
            db.execute(delete, (digest(key),))
            if row and row["expires"] > time.time():
                return dict(row)
        return None

    def throttle(self, key, limit, window):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Expired ephemeral records are removed on every limited request.
            for delete in (
                "DELETE FROM limits WHERE expires <= ?",
                "DELETE FROM transactions WHERE expires <= ?",
                "DELETE FROM handoffs WHERE expires <= ?",
                "DELETE FROM sessions WHERE expires <= ?",
            ):
                db.execute(delete, (now,))
            row = db.execute("SELECT * FROM limits WHERE key = ?", (key,)).fetchone()
            if row and row["count"] >= limit:
                return max(1, int(row["expires"] - now) + 1)
            if row:
                db.execute("UPDATE limits SET count = count + 1 WHERE key = ?", (key,))
            else:
                db.execute("INSERT INTO limits VALUES (?, 1, ?)", (key, now + window))
        return None
