import asyncio
import logging
import re
import time
from datetime import time as clock_time
from html import unescape
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 1_500_000


class ViewCountError(RuntimeError):
    pass


def _number(value):
    cleaned = unescape(value).replace("\xa0", " ").replace(" ", "").replace(",", ".")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KkКкMmМм]?)", cleaned)
    if not match:
        raise ViewCountError(f"Некорректный счётчик: {value!r}")
    amount = float(match.group(1))
    suffix = match.group(2).casefold()
    if suffix in ("k", "к"):
        amount *= 1_000
    elif suffix in ("m", "м"):
        amount *= 1_000_000
    return int(amount)


PATTERNS = {
    "telegram": (
        r'tgme_widget_message_views[^>]*>([\d\s.,KkКкMmМм]+)<',
    ),
    "youtube": (
        r'"viewCount"\s*:\s*"(\d+)"',
        r'"view_count"\s*:\s*(\d+)',
    ),
    "vk_video": (
        r'"views"\s*:\s*(\d+)',
        r'"view_count"\s*:\s*(\d+)',
    ),
    "rutube": (
        r'ya:ovs:views_total(?:\\?"|&quot;)\s+content(?:\\?"|&quot;)?\s*[=:]\s*(?:\\?"|&quot;)(\d+)',
        r'"view_count"\s*:\s*(\d+)',
        r'"views"\s*:\s*(\d+)',
    ),
    "dzen": (
        r'"viewsCount"\s*:\s*(\d+)',
        r'"views"\s*:\s*(\d+)',
    ),
    "max": (
        r'"viewsCount"\s*:\s*(\d+)',
        r'"views"\s*:\s*(\d+)',
    ),
    "yandex_music": (
        r'"(?:view|listen|play)Count"\s*:\s*(\d+)',
    ),
}


def extract_view_count(platform_code, body, external_id=None):
    if platform_code == "telegram" and external_id:
        message = re.search(
            rf'data-post="[^"]+/{re.escape(str(external_id))}"[\s\S]*?'
            r'tgme_widget_message_views[^>]*>([\d\s.,KkКкMmМм]+)<',
            body, re.IGNORECASE)
        if message:
            return _number(message.group(1))
        raise ViewCountError(f"Telegram-пост {external_id} не найден в публичной странице")
    for pattern in PATTERNS.get(platform_code, ()):
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return _number(match.group(1))
    raise ViewCountError(f"Счётчик {platform_code} не найден в ответе")


async def fetch_limited(client, url):
    headers = {"Range": f"bytes=0-{MAX_RESPONSE_BYTES - 1}"}
    async with client.stream("GET", url, headers=headers) as response:
        response.raise_for_status()
        chunks, size = [], 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ViewCountError("Ответ площадки превышает лимит 1 МБ")
            chunks.append(chunk)
        return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")


async def collect_publication(client, publication):
    started = time.monotonic()
    url = publication["url"]
    if publication["platform_code"] == "telegram":
        url = re.sub(r"https://t\.me/([^/]+)/", r"https://t.me/s/\1/", url)
    body = await fetch_limited(client, url)
    count = extract_view_count(publication["platform_code"], body, publication["external_id"])
    return count, int((time.monotonic() - started) * 1000)


async def run_daily_collection(database, bot, admin_chat_id):
    publications = database.active_publications()
    run_id = database.start_stats_run(len(publications))
    successes, errors, warnings = 0, [], []
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
    timeout = httpx.Timeout(12.0, connect=6.0)
    headers = {"User-Agent": "Mir1CStatsBot/1.0 (+https://t.me/sergsyp)"}
    async with httpx.AsyncClient(follow_redirects=True, limits=limits, timeout=timeout, headers=headers) as client:
        for publication in publications:
            last_error = None
            for attempt in range(1, 4):
                try:
                    count, elapsed = await collect_publication(client, publication)
                    database.save_publication_stat(run_id, publication["id"], count, elapsed)
                    if publication["previous_view_count"] is not None and count < publication["previous_view_count"]:
                        warnings.append(f"{publication['platform_name']}: {publication['title']} — счётчик уменьшился")
                    successes += 1
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 3:
                        await asyncio.sleep(attempt * 2)
            else:
                database.save_stats_error(run_id, publication["id"], 3, type(last_error).__name__, str(last_error))
                errors.append((publication, last_error))
    status = database.finish_stats_run(run_id, successes, len(errors))
    if errors:
        from datetime import datetime
        started_msk = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M мск")
        lines = [f"⚠️ Сбор статистики {started_msk}: {status}", f"Успешно: {successes}; ошибок: {len(errors)}"]
        for publication, error in errors[:10]:
            last = publication["last_success_at"] or "ещё не было"
            lines.append(f"• {publication['platform_name']} — {publication['title']}\n{publication['url']}\n3 попытки; {type(error).__name__}: {error}; последний успех: {last}")
        if len(errors) > 10:
            lines.append(f"• Ещё ошибок: {len(errors) - 10}")
        if warnings:
            lines.append(f"Предупреждений: {len(warnings)}")
        await bot.send_message(admin_chat_id, "\n".join(lines)[:4000], disable_web_page_preview=True)


async def scheduled_collection(context):
    await run_daily_collection(context.application.bot_data["database"], context.bot,
                               context.application.bot_data["admin_chat_id"])


def schedule_collection(application, database, admin_chat_id):
    application.bot_data["database"] = database
    application.bot_data["admin_chat_id"] = admin_chat_id
    application.job_queue.run_daily(
        scheduled_collection,
        time=clock_time(hour=23, minute=50, tzinfo=ZoneInfo("Europe/Moscow")),
        name="daily-podcast-view-stats",
    )
