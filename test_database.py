import tempfile
import unittest
from pathlib import Path

from database import Database
from podcasts import PODCASTS


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tempdir.name) / "bot.db"))
        self.db.initialize()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_logs_structured_action_and_builds_stats(self):
        self.db.log_action(123, "podcast_search", {"query": "1С", "results": 2})
        self.db.log_action(123, "podcast_search_invalid", {"query_length": 1}, False)

        report = self.db.stats(1)

        self.assertEqual(report["events"], 2)
        self.assertEqual(report["users"], 1)
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["actions"][0], ("podcast_search", 1))

    def test_migrates_existing_audit_log(self):
        legacy_path = Path(self.tempdir.name) / "legacy.db"
        import sqlite3
        with sqlite3.connect(legacy_path) as connection:
            connection.execute("""CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER, action TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        legacy = Database(str(legacy_path))
        legacy.initialize()
        legacy.log_action(1, "menu", {"source": "button"})
        self.assertEqual(legacy.stats(1)["events"], 1)

    def test_syncs_catalog_platforms_and_first_telegram_posts(self):
        self.db.sync_podcast_catalog(PODCASTS)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM platforms").fetchone()[0], 7)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM podcast_episodes").fetchone()[0], 56)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM episode_publications").fetchone()[0], 56)
            self.assertEqual(connection.execute(
                "SELECT type FROM platforms WHERE code='yandex_music'").fetchone()[0], "audio")
            self.assertEqual(connection.execute(
                "SELECT stats_status FROM platforms WHERE code='yandex_music'"
            ).fetchone()[0], "unsupported")

    def test_saves_history_latest_value_and_run_result(self):
        self.db.sync_podcast_catalog({1: [("Выпуск", "Описание", 999)]})
        publication = self.db.active_publications()[0]
        run_id = self.db.start_stats_run(1)
        self.db.save_publication_stat(run_id, publication["id"], 123, 45)
        self.assertEqual(self.db.finish_stats_run(run_id, 1, 0), "success")
        with self.db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT view_count FROM publication_latest_stats").fetchone()[0], 123)
            self.assertEqual(connection.execute(
                "SELECT view_count FROM publication_stats_history").fetchone()[0], 123)

    def test_syncs_approved_external_publication_links(self):
        self.db.sync_podcast_catalog({1: [("Выпуск", "Описание", 999)]})
        self.db.sync_publication_links({999: {"youtube": "https://youtu.be/abc123"}})
        rows = self.db.active_publications()
        self.assertEqual({row["platform_code"] for row in rows}, {"telegram", "youtube"})

    def test_failed_run_does_not_replace_latest_value(self):
        self.db.sync_podcast_catalog({1: [("Выпуск", "Описание", 999)]})
        publication = self.db.active_publications()[0]
        first = self.db.start_stats_run(1)
        self.db.save_publication_stat(first, publication["id"], 100, 20)
        self.db.finish_stats_run(first, 1, 0)
        failed = self.db.start_stats_run(1)
        self.db.save_stats_error(failed, publication["id"], 3, "Timeout", "timeout")
        self.db.finish_stats_run(failed, 0, 1)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT view_count FROM publication_latest_stats").fetchone()[0], 100)

    def test_collection_status_reports_run_platforms_and_errors(self):
        self.db.sync_podcast_catalog({1: [("Выпуск", "Описание", 999)]})
        publication = self.db.active_publications()[0]
        run_id = self.db.start_stats_run(1)
        self.db.save_publication_stat(run_id, publication["id"], 321, 40)
        self.db.finish_stats_run(run_id, 1, 0)

        report = self.db.collection_status()

        self.assertEqual(report["last_run"]["id"], run_id)
        self.assertEqual(report["last_run"]["status"], "success")
        self.assertEqual(report["platforms"][0]["name"], "Telegram")
        self.assertEqual(report["platforms"][0]["success_count"], 1)
        self.assertEqual(report["latest"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
