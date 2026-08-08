import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path):
        self.path = path

    def connect(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self):
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY, username TEXT,
                    first_name TEXT NOT NULL, last_name TEXT,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS podcast_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL, text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id));
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER, action TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """)

    def upsert_user(self, user):
        with self.connect() as connection:
            connection.execute("""
                INSERT INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username,
                first_name=excluded.first_name, last_name=excluded.last_name,
                last_seen_at=CURRENT_TIMESTAMP
            """, (user.id, user.username, user.first_name or "", user.last_name))

    def save_proposal(self, user, text):
        self.upsert_user(user)
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO podcast_proposals (telegram_id, text) VALUES (?, ?)",
                (user.id, text))
            connection.execute(
                "INSERT INTO audit_log (telegram_id, action) VALUES (?, ?)",
                (user.id, "podcast_proposal_created"))
            return cursor.lastrowid

    def log_action(self, telegram_id, action):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO audit_log (telegram_id, action) VALUES (?, ?)",
                (telegram_id, action))
