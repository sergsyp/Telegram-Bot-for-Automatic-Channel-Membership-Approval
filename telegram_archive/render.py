from __future__ import annotations

import hashlib
import html
import re
import unicodedata


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    slug = re.sub(r"[\W_]+", "-", normalized, flags=re.UNICODE).strip("-")
    if not slug:
        slug = "tema"
    return slug[:80]


def archive_path(group_slug: str, topic_slug: str, thread_id: int, local_date: str) -> str:
    return f"communications/telegram/{group_slug}/{topic_slug}--{thread_id}/{local_date}.md"


def render_markdown(group_name: str, group_id: int, topic_name: str, thread_id: int, local_date: str, messages) -> str:
    parts = [
        f"# {topic_name} — {local_date}",
        "",
        f"Telegram-группа: {group_name} (ID: {group_id})  ",
        f"Telegram-тема: {topic_name} (ID: {thread_id})",
        "",
    ]
    for message in messages:
        username = f" (@{message['author_username']})" if message["author_username"] else ""
        parts.extend(
            [
                f"## {message['local_time']} мск — {message['author_name']}{username}",
                "",
                "<pre>",
                html.escape(message["text"], quote=False),
                "</pre>",
                "",
            ]
        )
    return "\n".join(parts).rstrip() + "\n"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
