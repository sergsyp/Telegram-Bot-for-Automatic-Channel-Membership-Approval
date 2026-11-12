from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from .database import ArchiveDatabase, StoredMessage
from .github import GitHubContentsClient
from .render import archive_path, content_hash, render_markdown, slugify
from .security import contains_credential

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchiveSettings:
    owner_id: int
    database_path: str
    repository: str
    branch: str
    token: str | None
    interval: int

    @classmethod
    def from_env(cls, owner_id: int, default_database_path: str) -> ArchiveSettings:
        return cls(
            owner_id=owner_id,
            database_path=os.getenv("ARCHIVE_DATABASE_PATH", default_database_path),
            repository=os.getenv("ARCHIVE_GITHUB_REPOSITORY", "sergsyp/sergsyp-ru"),
            branch=os.getenv("ARCHIVE_GITHUB_BRANCH", "communications-archive-test"),
            token=os.getenv("ARCHIVE_GITHUB_TOKEN") or None,
            interval=max(60, int(os.getenv("ARCHIVE_EXPORT_INTERVAL_SECONDS", "300"))),
        )


class ArchiveService:
    def __init__(self, settings: ArchiveSettings):
        self.settings = settings
        self.database = ArchiveDatabase(settings.database_path)
        self.zone = ZoneInfo("Europe/Moscow")
        self._blocked_paths: set[str] = set()
        self._newly_blocked: list[str] = []
        self.github = (
            GitHubContentsClient(settings.token, settings.repository, settings.branch, "main")
            if settings.token else None
        )

    def is_approved(self, chat_id: int) -> bool:
        return self.database.group_is_approved(chat_id)

    async def discover(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if not chat or chat.type not in {"group", "supergroup"}:
            return
        current = self.database.group(chat.id)
        if current and (current["status"] != "pending" or current["notification_sent_at"] is not None):
            return
        title = chat.title or "Без названия"
        slug = f"{slugify(title)}--{abs(chat.id)}"
        if not self.database.register_pending_group(chat.id, title, slug):
            return
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Разрешить", callback_data=f"archive:approve:{chat.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"archive:reject:{chat.id}"),
        ]])
        try:
            await context.bot.send_message(
                self.settings.owner_id,
                f"Новая группа: {title} (ID: {chat.id}). Разрешить архивирование текста в приватный GitHub?",
                reply_markup=buttons,
            )
            self.database.mark_group_notified(chat.id)
        except Exception:
            logger.exception("Could not request archive approval for group %s", chat.id)

    async def membership(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        event = update.my_chat_member
        if event and event.new_chat_member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR}:
            await self.discover(update, context)

    async def decision(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        parts = (query.data or "").split(":")
        if len(parts) != 3 or parts[1] not in {"approve", "reject"} or not parts[2].lstrip("-").isdigit():
            await query.answer("Некорректная команда")
            return
        if not update.effective_user or update.effective_user.id != self.settings.owner_id:
            await query.answer("Доступно только владельцу", show_alert=True)
            return
        chat_id = int(parts[2])
        if not self.database.group(chat_id) or not self.database.set_group_status(chat_id, "approved" if parts[1] == "approve" else "rejected"):
            await query.answer("Группа не найдена", show_alert=True)
            return
        await query.answer("Решение сохранено")
        await query.edit_message_text(f"Группа {chat_id}: архивирование {'разрешено' if parts[1] == 'approve' else 'отклонено'}.")

    def register_topic(self, chat_id: int, thread_id: int, name: str) -> None:
        if self.is_approved(chat_id) and name.strip():
            self.database.upsert_topic(chat_id, thread_id, name.strip(), slugify(name))

    async def topic_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if not message or not message.message_thread_id or not self.is_approved(message.chat_id):
            return
        user = update.effective_user
        if not user:
            return
        member = await context.bot.get_chat_member(message.chat_id, user.id)
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
            await message.reply_text("Название темы может задать администратор.")
            return
        name = " ".join(context.args).strip()
        if not name:
            await message.reply_text("Укажи название: /topic_name Название темы")
            return
        self.register_topic(message.chat_id, message.message_thread_id, name)
        sent = await message.reply_text(f"Название темы сохранено: {name}")
        self.store_message(sent)

    def store_message(self, message) -> bool:
        if not self.is_approved(message.chat_id):
            return False
        if message.forum_topic_created:
            self.register_topic(message.chat_id, message.message_thread_id or message.message_id, message.forum_topic_created.name)
            return False
        if message.forum_topic_edited and message.forum_topic_edited.name:
            self.register_topic(message.chat_id, message.message_thread_id or 1, message.forum_topic_edited.name)
            return False
        text = message.text if message.text is not None else message.caption
        if not text or not text.strip():
            return False
        thread_id = message.message_thread_id
        if thread_id is None and message.chat.is_forum:
            thread_id = 1
        if thread_id is None:
            return False
        if thread_id == 1 and not self.database.topic(message.chat_id, 1):
            self.register_topic(message.chat_id, 1, "Общая")
        local = message.date.replace(tzinfo=message.date.tzinfo or timezone.utc).astimezone(self.zone)
        user = message.from_user
        name = user.full_name if user else (message.sender_chat.title if message.sender_chat else "Неизвестный автор")
        self.database.upsert_message(StoredMessage(
            chat_id=message.chat_id, message_id=message.message_id, thread_id=thread_id,
            sent_at=message.date.isoformat(), local_date=local.date().isoformat(),
            local_time=local.strftime("%H:%M"), author_name=name,
            author_username=user.username if user else None, text=text,
        ))
        return True

    async def incoming(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if not message or message.chat.type not in {"group", "supergroup"}:
            return
        await self.discover(update, context)
        self.store_message(message)

    async def export_once(self) -> int:
        if not self.github:
            return 0
        await self.github.ensure_branch()
        count = 0
        for group in self.database.export_groups():
            messages = self.database.messages_for(group["chat_id"], group["thread_id"], group["local_date"])
            path = archive_path(group["group_slug"], group["slug"], group["thread_id"], group["local_date"])
            if any(contains_credential(item["text"]) for item in messages):
                if path not in self._blocked_paths:
                    self._blocked_paths.add(path)
                    self._newly_blocked.append(path)
                    logger.error("Credential-like text detected; archive export withheld for %s", path)
                continue
            self._blocked_paths.discard(path)
            content = render_markdown(group["group_title"], group["chat_id"], group["name"], group["thread_id"], group["local_date"], messages)
            digest = content_hash(content)
            if self.database.exported_hash(path) == digest:
                continue
            await self.github.put_file(path, content)
            self.database.mark_exported(path, digest)
            count += 1
        return count

    async def export_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.github:
            logger.warning("ARCHIVE_GITHUB_TOKEN missing; messages remain in local SQLite")
            return
        try:
            count = await self.export_once()
            while self._newly_blocked:
                path = self._newly_blocked[0]
                await context.bot.send_message(self.settings.owner_id, f"Экспорт архива приостановлен: в тексте обнаружены данные, похожие на секрет. Файл: {path}. Данные остались в SQLite.")
                self._newly_blocked.pop(0)
            if count:
                logger.info("Archived %s Telegram files", count)
        except Exception:
            logger.exception("Telegram archive export failed; retrying at next interval")
