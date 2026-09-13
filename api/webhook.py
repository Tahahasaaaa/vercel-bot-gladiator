"""
اندپوینت webhook تلگرام روی Vercel.
تلگرام برای هر آپدیت (پیام، کلیک دکمه و...) یک درخواست POST به این آدرس می‌فرستد:
    https://<your-app>.vercel.app/api/webhook
"""
import asyncio
import json
import sys
import os
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update  # noqa: E402

from config import WEBHOOK_SECRET  # noqa: E402
from app import build_application  # noqa: E402
import database as db  # noqa: E402
from cleanup import cleanup_due_deletions  # noqa: E402


async def _process(update_data: dict) -> None:
    await db.init_db()
    application = build_application()
    await application.initialize()
    try:
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
        # حذف فرصت‌طلبانه‌ی پیام‌های زمان‌دارِ سررسیده (علاوه بر cron)
        await cleanup_due_deletions(application.bot)
    finally:
        await application.shutdown()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if WEBHOOK_SECRET:
            secret_header = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if secret_header != WEBHOOK_SECRET:
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"unauthorized")
                return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            update_data = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"bad request")
            return

        try:
            asyncio.run(_process(update_data))
        except Exception as e:
            # هرگز خطا را به تلگرام برنگردان (باعث retry بی‌پایان می‌شود)؛ فقط لاگ کن
            print(f"webhook processing error: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("GLADIATOR webhook is alive ✅ (فقط POST از تلگرام پردازش می‌شود)".encode("utf-8"))
