import sqlite3
import tempfile
import unittest

from analytics_delivery import deliver_history


class AnalyticsDeliveryTest(unittest.TestCase):
    def test_enqueues_delivers_and_deduplicates_history(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as database_file:
            database = sqlite3.connect(database_file.name)
            database.executescript("""
                CREATE TABLE platforms(id INTEGER PRIMARY KEY,code TEXT);
                CREATE TABLE podcast_episodes(id INTEGER PRIMARY KEY);
                CREATE TABLE episode_publications(id INTEGER PRIMARY KEY,episode_id INTEGER,platform_id INTEGER);
                CREATE TABLE publication_stats_history(id INTEGER PRIMARY KEY,publication_id INTEGER,run_id INTEGER,view_count INTEGER,collected_at TEXT);
                INSERT INTO platforms VALUES(1,'youtube');
                INSERT INTO podcast_episodes VALUES(507);
                INSERT INTO episode_publications VALUES(8,507,1);
                INSERT INTO publication_stats_history VALUES(9,8,1,1800,'2026-10-23T20:50:00+00:00');
            """)
            database.commit()
            database.close()
            batches = []

            def transport(url, token, payload):
                batches.append((url, token, payload))
                return {"status": "accepted", "batchId": payload["batchId"]}

            first = deliver_history(database_file.name, "https://sergsyp.ru", "secret", transport=transport)
            second = deliver_history(database_file.name, "https://sergsyp.ru", "secret", transport=transport)
            self.assertEqual(first, {"status": "delivered", "sent": 1, "pending": 0})
            self.assertEqual(second, {"status": "delivered", "sent": 0, "pending": 0})
            self.assertEqual(len(batches), 1)
            record = batches[0][2]["records"][0]
            self.assertEqual(record["contentId"], "bothost:episode:507")
            self.assertEqual(record["metrics"], {"views": 1800})


if __name__ == "__main__":
    unittest.main()
