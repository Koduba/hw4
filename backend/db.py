"""SQLite access for the Campus Customs API.

Two kinds of connection:
- read_only(): catalogue/inventory reads. The file is opened with mode=ro so
  these code paths physically cannot modify data.
- read_write(): accounts and sessions only.

Every query uses ? placeholders; never build SQL from user input.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
# CAMPUS_DB_PATH lets tests run against a throwaway copy of the database.
DB_PATH = Path(os.getenv("CAMPUS_DB_PATH", DATA_DIR / "campus_customs.db"))
IMAGES_DIR = DATA_DIR / "products"
MODEL_SHOTS_DIR = DATA_DIR / "model_shots"  # AI on-model photos (generate_model_shots.py)


def _connect(mode: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode={mode}", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def read_only() -> Iterator[sqlite3.Connection]:
    conn = _connect("ro")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def read_write() -> Iterator[sqlite3.Connection]:
    conn = _connect("rw")
    try:
        with conn:  # commit on success, roll back on error
            yield conn
    finally:
        conn.close()


def init_schema() -> None:
    """Create the users/sessions tables if missing. Safe to run on every start."""
    with read_write() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                first_name TEXT,
                last_name TEXT
            )
            """
        )
        # Older copies of the DB may predate the first/last name columns.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        for col in ("first_name", "last_name"):
            if col not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")

        # Server-side sessions. Only a SHA-256 of the token is stored, so a
        # leaked database can't be used to hijack anyone's login.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")

        # Customer memory: one row per chat message, logged-in users only (guests are
        # kept in server memory, never written here). Same shape as the seed table.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                products_json TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        # Page context for each user message (e.g. which product page they were on),
        # so "do you have this in pink?" still makes sense when the chat is reloaded.
        chat_cols = {r["name"] for r in conn.execute("PRAGMA table_info(chat_messages)")}
        if "context_json" not in chat_cols:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN context_json TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id)")
