import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path


class Database:
    def __init__(self, path):
        self.path = path
        self._memory_connection = None

    def connect(self):
        if self.path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = sqlite3.connect(":memory:")
                self._memory_connection.execute("PRAGMA foreign_keys=ON")
            return self._memory_connection
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
                CREATE TABLE IF NOT EXISTS platforms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL CHECK(type IN ('video','audio','text')),
                    stats_status TEXT NOT NULL DEFAULT 'collect'
                        CHECK(stats_status IN ('collect','unsupported')),
                    stats_status_reason TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS podcast_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    season_number INTEGER NOT NULL,
                    episode_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    telegram_post_id INTEGER NOT NULL UNIQUE,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS episode_publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id INTEGER NOT NULL,
                    platform_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    external_id TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(episode_id, platform_id, url),
                    FOREIGN KEY (episode_id) REFERENCES podcast_episodes(id),
                    FOREIGN KEY (platform_id) REFERENCES platforms(id));
                CREATE TABLE IF NOT EXISTS stats_update_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    status TEXT NOT NULL DEFAULT 'running'
                        CHECK(status IN ('running','success','partial_failure','failure')),
                    planned_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    summary TEXT);
                CREATE TABLE IF NOT EXISTS publication_latest_stats (
                    publication_id INTEGER PRIMARY KEY,
                    view_count INTEGER NOT NULL CHECK(view_count >= 0),
                    collected_at TEXT NOT NULL,
                    source_status TEXT NOT NULL,
                    response_time_ms INTEGER,
                    FOREIGN KEY (publication_id) REFERENCES episode_publications(id));
                CREATE TABLE IF NOT EXISTS publication_stats_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    publication_id INTEGER NOT NULL,
                    run_id INTEGER NOT NULL,
                    view_count INTEGER NOT NULL CHECK(view_count >= 0),
                    collected_at TEXT NOT NULL,
                    UNIQUE(publication_id, run_id),
                    FOREIGN KEY (publication_id) REFERENCES episode_publications(id),
                    FOREIGN KEY (run_id) REFERENCES stats_update_runs(id));
                CREATE TABLE IF NOT EXISTS stats_update_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    publication_id INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES stats_update_runs(id),
                    FOREIGN KEY (publication_id) REFERENCES episode_publications(id));
                CREATE INDEX IF NOT EXISTS idx_history_collected_at
                    ON publication_stats_history(collected_at);
                CREATE INDEX IF NOT EXISTS idx_publications_platform
                    ON episode_publications(platform_id, is_active);
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
            platform_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(platforms)")
            }
            if "stats_status" not in platform_columns:
                connection.execute(
                    "ALTER TABLE platforms ADD COLUMN stats_status TEXT NOT NULL DEFAULT 'collect'"
                )
            if "stats_status_reason" not in platform_columns:
                connection.execute(
                    "ALTER TABLE platforms ADD COLUMN stats_status_reason TEXT"
                )

    def sync_podcast_catalog(self, podcasts):
        platforms = (
            ("youtube", "YouTube", "video", "collect", None),
            ("vk_video", "VK Видео", "video", "collect", None),
            ("rutube", "RuTube", "video", "collect", None),
            ("dzen", "Дзен Видео", "video", "collect", None),
            ("yandex_music", "Яндекс Музыка", "audio", "unsupported",
             "Публичный счётчик прослушиваний выпусков отсутствует"),
            ("telegram", "Telegram", "text", "collect", None),
            ("max", "MAX", "text", "unsupported",
             "Публичный стабильный счётчик сообщений пока недоступен"),
        )
        with self.connect() as connection:
            connection.executemany(
                """INSERT INTO platforms(code,name,type,stats_status,stats_status_reason)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(code) DO UPDATE SET name=excluded.name,
                   type=excluded.type, stats_status=excluded.stats_status,
                   stats_status_reason=excluded.stats_status_reason,
                   updated_at=CURRENT_TIMESTAMP""", platforms)
            telegram_platform_id = connection.execute(
                "SELECT id FROM platforms WHERE code='telegram'"
            ).fetchone()[0]
            for season, episodes in podcasts.items():
                for position, episode in enumerate(episodes, 1):
                    title, description, post_id, *custom_number = episode
                    number = custom_number[0] if custom_number else position
                    connection.execute(
                        """INSERT INTO podcast_episodes
                           (season_number,episode_number,title,description,telegram_post_id)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(telegram_post_id) DO UPDATE SET
                           season_number=excluded.season_number,
                           episode_number=excluded.episode_number,
                           title=excluded.title, description=excluded.description,
                           updated_at=CURRENT_TIMESTAMP""",
                        (season, number, title, description, post_id))
                    episode_id = connection.execute(
                        "SELECT id FROM podcast_episodes WHERE telegram_post_id=?", (post_id,)
                    ).fetchone()[0]
                    url = f"https://t.me/sergsyp/{post_id}"
                    connection.execute(
                        """INSERT OR IGNORE INTO episode_publications
                           (episode_id,platform_id,url,external_id) VALUES(?,?,?,?)""",
                        (episode_id, telegram_platform_id, url, str(post_id)))

    def sync_publication_links(self, links):
        with self.connect() as connection:
            for post_id, publications in links.items():
                episode = connection.execute(
                    "SELECT id FROM podcast_episodes WHERE telegram_post_id=?", (post_id,)
                ).fetchone()
                if not episode:
                    raise ValueError(f"Неизвестный Telegram post ID: {post_id}")
                for platform_code, url in publications.items():
                    platform = connection.execute(
                        "SELECT id FROM platforms WHERE code=?", (platform_code,)
                    ).fetchone()
                    if not platform:
                        raise ValueError(f"Неизвестная площадка: {platform_code}")
                    external_id = url.rstrip("/").rsplit("/", 1)[-1]
                    connection.execute("""INSERT INTO episode_publications
                        (episode_id,platform_id,url,external_id) VALUES(?,?,?,?)
                        ON CONFLICT(episode_id,platform_id,url) DO UPDATE SET
                        external_id=excluded.external_id,is_active=1,
                        updated_at=CURRENT_TIMESTAMP""",
                        (episode[0], platform[0], url, external_id))

    def active_publications(self):
        with self.connect() as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute("""
                SELECT ep.id, ep.url, ep.external_id, p.code AS platform_code,
                       p.name AS platform_name, pe.title, pe.season_number,
                       pe.episode_number, ls.view_count AS previous_view_count,
                       ls.collected_at AS last_success_at
                FROM episode_publications ep
                JOIN platforms p ON p.id=ep.platform_id
                JOIN podcast_episodes pe ON pe.id=ep.episode_id
                LEFT JOIN publication_latest_stats ls ON ls.publication_id=ep.id
                WHERE ep.is_active=1 AND p.is_active=1 AND pe.is_active=1
                  AND p.stats_status='collect'
                ORDER BY p.id, pe.season_number, pe.episode_number
            """)]

    def latest_episode_view_stats(self):
        """Return the latest available counters grouped by Telegram post ID."""
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT pe.telegram_post_id, p.code, ls.view_count
                FROM podcast_episodes pe
                JOIN episode_publications ep ON ep.episode_id=pe.id
                JOIN platforms p ON p.id=ep.platform_id
                JOIN publication_latest_stats ls ON ls.publication_id=ep.id
                WHERE pe.is_active=1 AND ep.is_active=1 AND p.is_active=1
                  AND p.stats_status='collect' AND ls.source_status='ok'
            """)
            result = {}
            for post_id, platform_code, view_count in rows:
                result.setdefault(post_id, {})[platform_code] = view_count
            return result

    def start_stats_run(self, planned_count):
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO stats_update_runs(planned_count) VALUES(?)", (planned_count,))
            return cursor.lastrowid

    def save_publication_stat(self, run_id, publication_id, view_count, response_time_ms):
        collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.connect() as connection:
            connection.execute("""INSERT INTO publication_stats_history
                (publication_id,run_id,view_count,collected_at) VALUES(?,?,?,?)""",
                (publication_id, run_id, view_count, collected_at))
            connection.execute("""INSERT INTO publication_latest_stats
                (publication_id,view_count,collected_at,source_status,response_time_ms)
                VALUES(?,?,?,'ok',?) ON CONFLICT(publication_id) DO UPDATE SET
                view_count=excluded.view_count,collected_at=excluded.collected_at,
                source_status='ok',response_time_ms=excluded.response_time_ms""",
                (publication_id, view_count, collected_at, response_time_ms))

    def save_stats_error(self, run_id, publication_id, attempts, error_type, message):
        with self.connect() as connection:
            connection.execute("""INSERT INTO stats_update_errors
                (run_id,publication_id,attempts,error_type,error_message)
                VALUES(?,?,?,?,?)""", (run_id, publication_id, attempts, error_type, message[:500]))

    def finish_stats_run(self, run_id, success_count, error_count):
        status = "success" if not error_count else ("partial_failure" if success_count else "failure")
        summary = json.dumps({"success": success_count, "errors": error_count}, separators=(",", ":"))
        with self.connect() as connection:
            connection.execute("""UPDATE stats_update_runs SET finished_at=CURRENT_TIMESTAMP,
                status=?,success_count=?,error_count=?,summary=? WHERE id=?""",
                (status, success_count, error_count, summary, run_id))
        return status

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
