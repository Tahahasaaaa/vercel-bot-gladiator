import logging

from telegram import Bot
from telegram.error import TelegramError

import database as db

logger = logging.getLogger(__name__)


async def cleanup_due_deletions(bot: Bot) -> int:
    """پیام‌های زمان‌دار که موعد حذفشان رسیده را از چت ادمین‌ها پاک می‌کند.

    این تابع هم از cron (برای دقت بیشتر) و هم به‌صورت فرصت‌طلبانه بعد از هر
    وبهوک صدا زده می‌شود؛ پس نیازی به یک worker همیشه‌روشن نیست.
    """
    due = await db.get_due_forwards()
    deleted_count = 0
    for row in due:
        try:
            await bot.delete_message(chat_id=row["admin_id"], message_id=row["admin_message_id"])
            deleted_count += 1
        except TelegramError as e:
            logger.warning(f"حذف پیام زمان‌دار {row['id']} ناموفق بود: {e}")
        await db.mark_forward_deleted(row["id"])
    return deleted_count
