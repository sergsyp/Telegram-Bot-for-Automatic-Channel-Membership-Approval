"""Одноразово находит кандидаты ссылок в первых Telegram-постах выпусков.

Печатает CSV в stdout. Результат нельзя загружать в базу без ручной проверки.
"""
import asyncio
import argparse
import csv
import html
import re
import sys
from urllib.parse import urlparse

import httpx

from podcasts import PODCASTS


DOMAIN_PLATFORM = {
    "youtube.com": "youtube", "www.youtube.com": "youtube", "youtu.be": "youtube",
    "vkvideo.ru": "vk_video", "vk.com": "vk_video",
    "rutube.ru": "rutube", "www.rutube.ru": "rutube",
    "dzen.ru": "dzen", "www.dzen.ru": "dzen",
    "music.yandex.ru": "yandex_music",
    "max.ru": "max", "www.max.ru": "max",
}


def classify_url(url):
    parsed = urlparse(url)
    platform = DOMAIN_PLATFORM.get(parsed.netloc.casefold())
    path = parsed.path.casefold()
    if platform == "youtube" and parsed.netloc.casefold() != "youtu.be" and path != "/watch":
        return None
    if platform == "vk_video" and "video" not in path:
        return None
    if platform in ("rutube", "dzen") and "/video" not in path:
        return None
    if platform == "yandex_music" and "/track/" not in path:
        return None
    return platform


def post_block(page, post_id):
    marker = f'data-post="sergsyp/{post_id}"'
    marker_at = page.find(marker)
    start = page.rfind('<div class="tgme_widget_message ', 0, marker_at)
    end = page.find('<div class="tgme_widget_message_footer', marker_at)
    if marker_at < 0 or start < 0 or end < 0:
        raise RuntimeError(f"Не найден Telegram-пост {post_id}")
    return page[start:end]


def candidates(block):
    found = {}
    for raw_url in re.findall(r'href="([^"]+)"', block):
        url = html.unescape(raw_url)
        platform = classify_url(url)
        if platform and platform not in found:
            found[platform] = url
    return found


async def main(output):
    stream = output.open("w", encoding="utf-8", newline="") if output else sys.stdout
    writer = csv.writer(stream)
    writer.writerow(("telegram_post_id", "season", "episode", "title", "platform", "url", "approved"))
    async with httpx.AsyncClient(follow_redirects=True, timeout=20,
                                 headers={"User-Agent": "Mir1CLinkDiscovery/1.0"}) as client:
        for season, episodes in PODCASTS.items():
            for position, episode in enumerate(episodes, 1):
                title, _description, post_id, *custom_number = episode
                number = custom_number[0] if custom_number else position
                page = (await client.get(f"https://t.me/s/sergsyp/{post_id}")).text
                links = candidates(post_block(page, post_id))
                for platform, url in links.items():
                    writer.writerow((post_id, season, number, title, platform, url, ""))
                await asyncio.sleep(0.2)
    if output:
        stream.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=__import__("pathlib").Path)
    args = parser.parse_args()
    asyncio.run(main(args.output))
