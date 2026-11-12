from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class StoredMessage:
    chat_id: int
    message_id: int
    thread_id: int
    sent_at: str
    local_date: str
    local_time: str
    author_name: str
    author_username: str | None
    text: str


class ArchiveDatabase:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS topics (
                chat_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, thread_id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                thread_id INTEGER NOT NULL,
                sent_at TEXT NOT NULL,
                local_date TEXT NOT NULL,
                local_time TEXT NOT NULL,
                author_name TEXT NOT NULL,
                author_username TEXT,
                text TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS messages_by_topic_date
                ON messages(chat_id, thread_id, local_date, sent_at, message_id);
            CREATE TABLE IF NOT EXISTS exports (
                path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                exported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS telegram_groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                slug TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                notification_sent_at TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def bootstrap_approved_group(self, chat_id: int, title: str, slug: str) -> None:
        now = datetime.now().astimezone().isoformat()
        self.connection.execute(
            """INSERT INTO telegram_groups(chat_id, title, slug, status, updated_at)
               VALUES (?, ?, ?, 'approved', ?)
               ON CONFLICT(chat_id) DO NOTHING""",
            (chat_id, title, slug, now),
        )
        self.connection.commit()

    def register_pending_group(self, chat_id: int, title: str, slug: str) -> bool:
        now = datetime.now().astimezone().isoformat()
        cursor = self.connection.execute(
            """INSERT INTO telegram_groups(chat_id, title, slug, status, updated_at)
               VALUES (?, ?, ?, 'pending', ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 title=excluded.title, slug=excluded.slug, updated_at=excluded.updated_at""",
            (chat_id, title, slug, now),
        )
        self.connection.commit()
        row = self.group(chat_id)
        return bool(cursor.rowcount and row and row["status"] == "pending" and row["notification_sent_at"] is None)

    def group(self, chat_id: int) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM telegram_groups WHERE chat_id=?", (chat_id,)).fetchone()

    def group_is_approved(self, chat_id: int) -> bool:
        row = self.group(chat_id)
        return bool(row and row["status"] == "approved")

    def set_group_status(self, chat_id: int, status: str) -> bool:
        if status not in {"approved", "rejected"}:
            raise ValueError("invalid group status")
        cursor = self.connection.execute(
            "UPDATE telegram_groups SET status=?, updated_at=? WHERE chat_id=?",
            (status, datetime.now().astimezone().isoformat(), chat_id),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def mark_group_notified(self, chat_id: int) -> None:
        self.connection.execute(
            "UPDATE telegram_groups SET notification_sent_at=? WHERE chat_id=?",
            (datetime.now().astimezone().isoformat(), chat_id),
        )
        self.connection.commit()

    def upsert_topic(self, chat_id: int, thread_id: int, name: str, slug: str) -> None:
        now = datetime.now().astimezone().isoformat()
        self.connection.execute(
            """INSERT INTO topics(chat_id, thread_id, name, slug, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(chat_id, thread_id) DO UPDATE SET
                 name=excluded.name, updated_at=excluded.updated_at""",
            (chat_id, thread_id, name, slug, now),
        )
        self.connection.commit()

    def topic(self, chat_id: int, thread_id: int) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM topics WHERE chat_id=? AND thread_id=?", (chat_id, thread_id)
        ).fetchone()

    def upsert_message(self, message: StoredMessage) -> None:
        now = datetime.now().astimezone().isoformat()
        self.connection.execute(
            """INSERT INTO messages(
                 chat_id, message_id, thread_id, sent_at, local_date, local_time,
                 author_name, author_username, text, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chat_id, message_id) DO UPDATE SET
                 thread_id=excluded.thread_id, sent_at=excluded.sent_at,
                 local_date=excluded.local_date, local_time=excluded.local_time,
                 author_name=excluded.author_name, author_username=excluded.author_username,
                 text=excluded.text, updated_at=excluded.updated_at""",
            (*message.__dict__.values(), now),
        )
        self.connection.commit()

    def export_groups(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            """SELECT m.chat_id, m.thread_id, m.local_date, t.name, t.slug,
                      g.title AS group_title, g.slug AS group_slug
               FROM messages m JOIN topics t
                 ON t.chat_id=m.chat_id AND t.thread_id=m.thread_id
               JOIN telegram_groups g ON g.chat_id=m.chat_id AND g.status='approved'
               GROUP BY m.chat_id, m.thread_id, m.local_date, t.name, t.slug, g.title, g.slug
               ORDER BY m.local_date, m.thread_id"""
        ).fetchall()

    def messages_for(self, chat_id: int, thread_id: int, local_date: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """SELECT * FROM messages
               WHERE chat_id=? AND thread_id=? AND local_date=?
               ORDER BY sent_at, message_id""",
            (chat_id, thread_id, local_date),
        ).fetchall()

    def exported_hash(self, path: str) -> str | None:
        row = self.connection.execute("SELECT content_hash FROM exports WHERE path=?", (path,)).fetchone()
        return row[0] if row else None

    def mark_exported(self, path: str, content_hash: str) -> None:
        self.connection.execute(
            """INSERT INTO exports(path, content_hash, exported_at) VALUES (?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                 content_hash=excluded.content_hash, exported_at=excluded.exported_at""",
            (path, content_hash, datetime.now().astimezone().isoformat()),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
