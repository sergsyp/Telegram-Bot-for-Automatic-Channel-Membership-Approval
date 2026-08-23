"""Probe one saved publication per supported statistics platform."""

import asyncio
import json

import httpx

from config import DATABASE_PATH
from database import Database
from view_stats import collect_publication


async def main():
    database = Database(DATABASE_PATH)
    database.initialize()
    selected = {}
    for publication in database.active_publications():
        selected.setdefault(publication["platform_code"], publication)

    results = []
    timeout = httpx.Timeout(12.0, connect=6.0)
    limits = httpx.Limits(max_connections=2, max_keepalive_connections=1)
    headers = {"User-Agent": "Mir1CStatsBot/1.0 (+https://t.me/sergsyp)"}
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, limits=limits, headers=headers
    ) as client:
        for code, publication in selected.items():
            try:
                count, elapsed = await collect_publication(client, publication)
                results.append({"platform": code, "ok": True, "count": count, "ms": elapsed})
            except Exception as error:
                results.append(
                    {"platform": code, "ok": False, "error": f"{type(error).__name__}: {error}"}
                )
    print(json.dumps(results, ensure_ascii=False))
    print("STATS_RUN_DONE")
    if any(not result["ok"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
