import sqlite3
import json
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
                    details TEXT, success INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE INDEX IF NOT EXISTS idx_audit_log_created_at
                    ON audit_log(created_at);
                CREATE INDEX IF NOT EXISTS idx_audit_log_action
                    ON audit_log(action);
                CREATE INDEX IF NOT EXISTS idx_audit_log_telegram_id
                    ON audit_log(telegram_id);
            """)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(audit_log)")
            }
            if "details" not in columns:
                connection.execute("ALTER TABLE audit_log ADD COLUMN details TEXT")
            if "success" not in columns:
                connection.execute(
                    "ALTER TABLE audit_log ADD COLUMN success INTEGER NOT NULL DEFAULT 1"
                )

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

    def log_action(self, telegram_id, action, details=None, success=True):
        serialized = None
        if details:
            serialized = json.dumps(details, ensure_ascii=False, separators=(",", ":"))
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO audit_log (telegram_id, action, details, success)
                   VALUES (?, ?, ?, ?)""",
                (telegram_id, action, serialized, int(success)))

    def stats(self, days):
        modifier = f"-{int(days)} days"
        with self.connect() as connection:
            totals = connection.execute("""
                SELECT COUNT(*), COUNT(DISTINCT telegram_id),
                       COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0)
                FROM audit_log
                WHERE created_at >= datetime('now', ?)
            """, (modifier,)).fetchone()
            actions = connection.execute("""
                SELECT action, COUNT(*) AS amount
                FROM audit_log
                WHERE created_at >= datetime('now', ?)
                GROUP BY action
                ORDER BY amount DESC, action
                LIMIT 10
            """, (modifier,)).fetchall()
        return {
            "events": totals[0],
            "users": totals[1],
            "errors": totals[2],
            "actions": actions,
        }
