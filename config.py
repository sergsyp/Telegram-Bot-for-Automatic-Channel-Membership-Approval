import os

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "127626487"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "/app/data/bot.db")
VK_SERVICE_TOKEN = os.getenv("VK_SERVICE_TOKEN")
ANALYTICS_API_URL = os.getenv("ANALYTICS_API_URL", "")
ANALYTICS_INGEST_TOKEN = os.getenv("ANALYTICS_INGEST_TOKEN", "")

if not TOKEN:
    raise RuntimeError("Добавьте BOT_TOKEN в переменные окружения BotHost.")
