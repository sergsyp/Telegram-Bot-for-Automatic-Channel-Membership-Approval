"""Run one podcast statistics collection cycle from the command line."""

import asyncio
import json

from telegram import Bot

from config import ADMIN_CHAT_ID, DATABASE_PATH, TOKEN
from database import Database
from view_stats import run_daily_collection


async def main():
    database = Database(DATABASE_PATH)
    database.initialize()
    await run_daily_collection(database, Bot(TOKEN), ADMIN_CHAT_ID)
    with database.connect() as connection:
        row = connection.execute(
            """SELECT id, status, planned_count, success_count, error_count
               FROM stats_update_runs ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    result = {
        "run_id": row[0],
        "status": row[1],
        "planned": row[2],
        "successes": row[3],
        "errors": row[4],
    }
    print(json.dumps(result, ensure_ascii=False))
    print("STATS_RUN_DONE")
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
