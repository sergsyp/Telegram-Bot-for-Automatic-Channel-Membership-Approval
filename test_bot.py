import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN_FOR_LOCAL_TESTS_ONLY")
os.environ.setdefault("DATABASE_PATH", ":memory:")

from database import Database
from main import ABOUT_TEXT, CLUB_TEXT, CONTACTS_TEXT, SOCIAL_TEXT, WELCOME_TEXT, build_application, main_menu, podcasts_menu, _msk_time
from podcasts import GUESTS, PODCASTS, search_text, season_text, stats_text


class BotTests(unittest.TestCase):
    def test_catalog_is_complete(self):
        self.assertEqual(list(PODCASTS), list(range(1, 12)))
        self.assertEqual(sum(len(items) for items in PODCASTS.values()), 56)
        self.assertEqual([len(PODCASTS[i]) for i in range(1, 12)], [5]*8+[6,5,5])

    def test_season_messages_fit_telegram_limit(self):
        for season in PODCASTS:
            text = season_text(season)
            self.assertLessEqual(len(text), 4096)
            self.assertIn(f"Сезон {season}", text)
            for episode in PODCASTS[season]:
                self.assertIn(f"https://t.me/sergsyp/{episode[2]}", text)

    def test_all_texts_fit_telegram_limit(self):
        for text in (WELCOME_TEXT, CLUB_TEXT, ABOUT_TEXT, SOCIAL_TEXT, CONTACTS_TEXT):
            self.assertLessEqual(len(text), 4096)

    def test_main_menu_has_five_sections(self):
        self.assertEqual(len(main_menu().inline_keyboard), 5)
        self.assertEqual(podcasts_menu().inline_keyboard[0][0].callback_data, "all_seasons")
        self.assertTrue(any(button.callback_data == "podcast_search" for row in podcasts_menu().inline_keyboard for button in row))

    def test_guests_and_search(self):
        self.assertEqual(GUESTS[260], "Кирилл Комаров, Александр Гречушкин")
        result = "\n".join(search_text("дорошкевич"))
        self.assertIn("Антон Дорошкевич", result)
        self.assertIn("https://t.me/sergsyp/253", result)
        self.assertIn("Ничего не найдено", search_text("несуществующая-тема-xyz")[0])
        broad_results = search_text("1с")
        self.assertGreater(len(broad_results), 1)
        self.assertTrue(all(len(message) <= 4096 for message in broad_results))

    def test_view_stats_format(self):
        text = stats_text({
            "youtube": 1240, "vk_video": 980, "rutube": 630,
            "dzen": 570, "telegram": 1430,
        })
        self.assertEqual(
            text,
            "YouTube 1 240 | VK Видео 980 | RuTube 630 | Дзен 570 | "
            "Telegram 1 430 | Всего 4 850 просмотров",
        )
        self.assertNotIn("—", text)

    def test_collection_time_is_shown_in_moscow_timezone(self):
        self.assertEqual(_msk_time("2026-08-23 12:00:00"), "23.08.2026 15:00 мск")

    def test_email_is_explicit_link(self):
        self.assertIn('href="mailto:s@sypachev.ru"', CONTACTS_TEXT)
        self.assertIn('>s@sypachev.ru</a>', CONTACTS_TEXT)

    def test_application_registers_all_handler_groups(self):
        app = build_application()
        names = {handler.__class__.__name__ for handler in app.handlers[0]}
        self.assertEqual(names, {"CommandHandler", "CallbackQueryHandler", "MessageHandler", "ChatJoinRequestHandler"})

    def test_database_persists_user_proposal_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bot.db")
            database = Database(path); database.initialize()
            user = SimpleNamespace(id=42, username="tester", first_name="Test", last_name="User")
            proposal_id = database.save_proposal(user, "Интересная тема для нового выпуска подкаста")
            self.assertEqual(proposal_id, 1)
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM podcast_proposals").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
