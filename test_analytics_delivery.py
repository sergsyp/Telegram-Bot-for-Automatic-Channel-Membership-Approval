import sqlite3
import tempfile
import unittest

from analytics_delivery import deliver_history, enqueue_history


class AnalyticsDeliveryTest(unittest.TestCase):
    def test_cms_episode_key_repairs_pending_outbox_without_duplicates(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as database_file:
            db = sqlite3.connect(database_file.name)
            db.executescript("""
                CREATE TABLE platforms(id INTEGER PRIMARY KEY,code TEXT);
                CREATE TABLE podcast_episodes(id INTEGER PRIMARY KEY,telegram_post_id INTEGER);
                CREATE TABLE episode_publications(id INTEGER PRIMARY KEY,episode_id INTEGER,platform_id INTEGER);
                CREATE TABLE publication_stats_history(id INTEGER PRIMARY KEY,publication_id INTEGER,run_id INTEGER,view_count INTEGER,collected_at TEXT);
                INSERT INTO platforms VALUES(1,'youtube');
                INSERT INTO podcast_episodes VALUES(856,379);
                INSERT INTO episode_publications VALUES(8,856,1);
                INSERT INTO publication_stats_history VALUES(9,8,1,473,'2026-11-16T04:06:03+00:00');
            """)
            db.close()
            enqueue_history(database_file.name)
            with sqlite3.connect(database_file.name) as db:
                db.execute("UPDATE analytics_outbox SET payload=replace(payload, 'telegram:post:379', 'bothost:episode:856'),attempts=2,last_error='HTTP 400'")
            self.assertEqual(enqueue_history(database_file.name), 1)
            self.assertEqual(enqueue_history(database_file.name), 0)
            with sqlite3.connect(database_file.name) as db:
                payload, attempts, count = db.execute("SELECT payload,attempts,(SELECT count(*) FROM analytics_outbox) FROM analytics_outbox").fetchone()
            self.assertIn('"contentId":"telegram:post:379"', payload)
            self.assertEqual((attempts, count), (0, 1))
            receipts = []
            def transport(url, token, body):
                receipts.append(body["records"][0])
                return {"status": "accepted"}
            self.assertEqual(deliver_history(database_file.name, "https://sergsyp.ru", "secret", transport=transport)["pending"], 0)
            self.assertEqual(len(receipts), 1)

    def test_enqueues_delivers_and_deduplicates_history(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as database_file:
            database = sqlite3.connect(database_file.name)
            database.executescript("""
                CREATE TABLE platforms(id INTEGER PRIMARY KEY,code TEXT);
                CREATE TABLE podcast_episodes(id INTEGER PRIMARY KEY,telegram_post_id INTEGER);
                CREATE TABLE episode_publications(id INTEGER PRIMARY KEY,episode_id INTEGER,platform_id INTEGER);
                CREATE TABLE publication_stats_history(id INTEGER PRIMARY KEY,publication_id INTEGER,run_id INTEGER,view_count INTEGER,collected_at TEXT);
                INSERT INTO platforms VALUES(1,'youtube');
                INSERT INTO podcast_episodes VALUES(507,359);
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
