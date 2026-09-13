"""
اجرای ربات با polling — فقط برای تست لوکال روی سیستم خودت.
روی Vercel از این فایل استفاده نمی‌شه؛ آنجا webhook از طریق api/webhook.py کار می‌کند.

اجرا:
    python local_polling.py
"""
import asyncio
import logging

from app import build_application
import database as db

logger = logging.getLogger(__name__)


def main() -> None:
    asyncio.run(db.init_db())
    app = build_application()
    logger.info("ربات با موفقیت راه‌اندازی شد (حالت polling — فقط برای تست لوکال) ✅")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
