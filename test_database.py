import tempfile
import unittest
from pathlib import Path

from database import Database


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


if __name__ == "__main__":
    unittest.main()
