import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from telegram_archive.service import ArchiveService, ArchiveSettings


CHAT = -1001234567890
OWNER = 127626487


def message(message_id, text, thread_id=42, **other):
    attrs = dict(chat_id=CHAT, chat=SimpleNamespace(id=CHAT, title="Пробная группа", type="supergroup", is_forum=True),
                 message_id=message_id, message_thread_id=thread_id, text=text, caption=None,
                 date=datetime(2026, 11, 12, 8, 30, tzinfo=timezone.utc),
                 from_user=SimpleNamespace(full_name="Тест Участник", username="tester"), sender_chat=None,
                 forum_topic_created=None, forum_topic_edited=None)
    attrs.update(other)
    return SimpleNamespace(**attrs)


class FakeGitHub:
    def __init__(self):
        self.files = {}
        self.ensure_calls = 0
        self.fail_once = False

    async def ensure_branch(self):
        self.ensure_calls += 1

    async def put_file(self, path, content):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("GitHub unavailable")
        self.files[path] = content


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ArchiveService(ArchiveSettings(OWNER, os.path.join(self.temp.name, "archive.db"),
                                                       "sergsyp/sergsyp-ru", "communications-archive-test", "test-not-a-token", 300))
        self.addCleanup(self.service.database.close)
        self.github = FakeGitHub()
        self.service.github = self.github
        self.chat = message(1, "").chat
        self.sent = []

        async def send_message(*args, **kwargs):
            self.sent.append((args, kwargs))
        self.context = SimpleNamespace(bot=SimpleNamespace(send_message=send_message))
        self.update = SimpleNamespace(effective_chat=self.chat)

    def approve(self):
        asyncio.run(self.service.discover(self.update, self.context))
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(self.service.store_message(message(2, "До подтверждения")))
        self.service.database.set_group_status(CHAT, "approved")

    def test_requires_owner_approval_and_preserves_topic_text_and_edits(self):
        self.approve()
        asyncio.run(self.service.discover(self.update, self.context))
        self.assertEqual(len(self.sent), 1)
        self.service.store_message(message(3, None, forum_topic_created=SimpleNamespace(name="Новости")))
        self.service.store_message(message(4, None, thread_id=43, forum_topic_created=SimpleNamespace(name="Вопросы")))
        self.service.store_message(message(5, "Первая версия", thread_id=42))
        self.service.store_message(message(5, "Исправленная версия", thread_id=42))
        self.service.store_message(message(6, None, thread_id=43, caption="Текстовая подпись"))
        self.service.store_message(message(7, None, thread_id=43, caption=None))
        self.service.store_message(message(8, "Общее сообщение", thread_id=None))
        count = asyncio.run(self.service.export_once())
        self.assertEqual(count, 3)
        self.assertTrue(all(x.startswith("communications/telegram/пробная-группа--1001234567890/") for x in self.github.files))
        body = next(x for x in self.github.files.values() if "Исправленная версия" in x)
        self.assertNotIn("Первая версия", body)
        self.assertIn("11:30 мск", body)
        self.assertEqual(asyncio.run(self.service.export_once()), 0)
        self.assertEqual(len(self.github.files), 3)

    def test_credentials_are_not_exported_and_edits_can_unblock(self):
        self.approve()
        self.service.register_topic(CHAT, 42, "Новости")
        self.service.store_message(message(5, "github_pat_" + "x" * 35))
        self.assertEqual(asyncio.run(self.service.export_once()), 0)
        self.assertEqual(len(self.github.files), 0)
        self.assertEqual(len(self.service._newly_blocked), 1)
        self.service.store_message(message(5, "Секрет удалён из сообщения"))
        self.assertEqual(asyncio.run(self.service.export_once()), 1)
        self.assertTrue(all("github_pat_" not in body for body in self.github.files.values()))

    def test_existing_topics_export_without_commands(self):
        self.approve()
        self.service.store_message(message(10, "Первое сообщение", thread_id=42))
        self.service.store_message(message(11, "Второе сообщение", thread_id=43))
        self.assertEqual(asyncio.run(self.service.export_once()), 2)
        self.assertTrue(any("тема-42--42" in path for path in self.github.files))
        self.assertTrue(any("тема-43--43" in path for path in self.github.files))
        self.service.register_topic(CHAT, 42, "Позднее название")
        self.assertEqual(asyncio.run(self.service.export_once()), 1)
        self.assertEqual(len(self.github.files), 2)
        self.assertTrue(any("Позднее название" in body for body in self.github.files.values()))

    def test_failed_export_retries_without_losing_data(self):
        self.approve()
        self.service.register_topic(CHAT, 42, "Новости")
        self.service.store_message(message(5, "Текст"))
        self.github.fail_once = True
        with self.assertRaises(RuntimeError):
            asyncio.run(self.service.export_once())
        self.assertEqual(asyncio.run(self.service.export_once()), 1)
        self.assertEqual(asyncio.run(self.service.export_once()), 0)
