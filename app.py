import logging

from telegram.ext import (
    ApplicationBuilder,
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import BOT_TOKEN, ADMIN_IDS
import handlers

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

_application: Application | None = None


def build_application() -> Application:
    """ساخت Application با تمام هندلرها. روی سرورلس هر بار از نو ساخته می‌شود
    (initialize/shutdown سبک است)، و برای اجرای لوکال با polling هم استفاده می‌شود."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("menu", handlers.menu_command))
    app.add_handler(CommandHandler("challenge", handlers.challenge_command))
    app.add_handler(CommandHandler("mystats", handlers.mystats_command))
    app.add_handler(CommandHandler("stats", handlers.stats_command))
    app.add_handler(CommandHandler("blocked", handlers.blocked_command))
    app.add_handler(CommandHandler("unblock", handlers.unblock_command))
    app.add_handler(CommandHandler("admins", handlers.admins_command))

    # پاسخ ادمین — باید قبل از user_text_message باشد
    app.add_handler(MessageHandler(filters.REPLY & filters.TEXT & filters.User(user_id=ADMIN_IDS), handlers.admin_reply))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.user_text_message))

    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VOICE | filters.VIDEO | filters.Document.ALL,
        handlers.user_media_message
    ))

    app.add_handler(CallbackQueryHandler(handlers.button_handler))

    return app


def get_application() -> Application:
    """نمونه‌ی singleton برای استفاده‌ی مجدد در یک instance گرم Vercel (اختیاری)."""
    global _application
    if _application is None:
        _application = build_application()
    return _application
