"""Durably deliver collected platform counters to sergsyp.ru."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone


SOURCES = {"youtube", "vk_video", "rutube", "dzen"}


def _connect(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def _initialize(database):
    database.executescript("""
        CREATE TABLE IF NOT EXISTS analytics_outbox (
            record_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            delivered_at TEXT,
            receipt TEXT,
            last_error TEXT
        );
        CREATE INDEX IF NOT EXISTS analytics_outbox_pending_idx
            ON analytics_outbox(delivered_at,next_attempt_at);
    """)


def _utc_iso(value):
    text = str(value or "").replace(" ", "T")
    if text.endswith("Z") or "+" in text[10:]:
        return text
    return text + "Z"


def enqueue_history(database_path):
    with _connect(database_path) as database:
        _initialize(database)
        rows = database.execute("""
            SELECT h.id AS history_id,h.view_count,h.collected_at,
                   ep.id AS publication_id,ep.episode_id,p.code AS source
            FROM publication_stats_history h
            JOIN episode_publications ep ON ep.id=h.publication_id
            JOIN platforms p ON p.id=ep.platform_id
            WHERE p.code IN ('youtube','vk_video','rutube','dzen')
            ORDER BY h.id
        """).fetchall()
        inserted = 0
        for row in rows:
            record = {
                "recordId": f"{row['source']}:publication:{row['publication_id']}:history:{row['history_id']}",
                "kind": "metric",
                "source": row["source"],
                "contentId": f"bothost:episode:{row['episode_id']}",
                "occurredAt": _utc_iso(row["collected_at"]),
                "metrics": {"views": row["view_count"]},
            }
            payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            inserted += database.execute(
                "INSERT OR IGNORE INTO analytics_outbox(record_id,source,payload) VALUES(?,?,?)",
                (record["recordId"], record["source"], payload),
            ).rowcount
        return inserted


def _post_json(url, token, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "Mir1CAnalyticsDelivery/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _deliver_batch(database_path, api_url, token, limit=500, transport=None):
    with _connect(database_path) as database:
        _initialize(database)
        rows = database.execute("""
            SELECT * FROM analytics_outbox
            WHERE delivered_at IS NULL AND next_attempt_at<=CURRENT_TIMESTAMP
            ORDER BY created_at,record_id LIMIT ?
        """, (limit,)).fetchall()
        if not rows:
            pending = database.execute(
                "SELECT count(*) FROM analytics_outbox WHERE delivered_at IS NULL"
            ).fetchone()[0]
            return {"status": "empty", "sent": 0, "pending": pending}
        records = [json.loads(row["payload"]) for row in rows]
        sources = sorted({row["source"] for row in rows})
        seed = "\n".join(row["record_id"] for row in rows)
        batch_id = "bothost:" + hashlib.sha256(seed.encode()).hexdigest()[:32]
        remaining = database.execute(
            "SELECT count(*) FROM analytics_outbox WHERE delivered_at IS NULL"
        ).fetchone()[0] - len(rows)
        payload = {
            "batchId": batch_id,
            "source": sources[0] if len(sources) == 1 else "import",
            "collectedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "records": records,
            "states": [{
                "source": source,
                "status": "healthy",
                "lastCollectedAt": max(record["occurredAt"] for record in records if record["source"] == source),
                "queueDepth": max(remaining, 0),
                "consecutiveErrors": 0,
            } for source in sources],
        }
        try:
            receipt = (transport or _post_json)(
                api_url.rstrip("/") + "/api/v1/analytics/ingest", token, payload
            )
        except Exception as error:
            message = f"{type(error).__name__}:{error}"[:500]
            database.executemany("""
                UPDATE analytics_outbox
                SET attempts=attempts+1,
                    next_attempt_at=datetime('now','+' || min(3600,30*(1 << min(attempts,7))) || ' seconds'),
                    last_error=?
                WHERE record_id=?
            """, [(message, row["record_id"]) for row in rows])
            raise
        database.executemany(
            "UPDATE analytics_outbox SET delivered_at=CURRENT_TIMESTAMP,receipt=?,last_error=NULL WHERE record_id=?",
            [(json.dumps(receipt, sort_keys=True), row["record_id"]) for row in rows],
        )
        pending = database.execute(
            "SELECT count(*) FROM analytics_outbox WHERE delivered_at IS NULL"
        ).fetchone()[0]
        return {"status": "delivered", "sent": len(rows), "pending": pending}


def deliver_history(database_path, api_url, token, max_batches=50, transport=None):
    if not api_url:
        raise ValueError("missing_analytics_api_url")
    if not token:
        raise ValueError("missing_analytics_ingest_token")
    enqueue_history(database_path)
    sent = 0
    for _ in range(max_batches):
        result = _deliver_batch(database_path, api_url, token, transport=transport)
        sent += result["sent"]
        if result["status"] == "empty" or result["pending"] == 0:
            return {"status": "delivered", "sent": sent, "pending": result["pending"]}
    return {"status": "partial", "sent": sent, "pending": result["pending"]}


if __name__ == "__main__":
    result = deliver_history(
        os.getenv("DATABASE_PATH", "/app/data/bot.db"),
        os.getenv("ANALYTICS_API_URL", ""),
        os.getenv("ANALYTICS_INGEST_TOKEN", ""),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("STATS_RUN_DONE")
