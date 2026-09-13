"""
اندپوینت پاکسازی پیام‌های زمان‌دار.

روی Vercel Hobby، Cron Jobs معمولاً فقط یک‌بار در روز اجرا می‌شوند که برای
حذف با دقت "۱ ساعته" کافی نیست. برای دقت بهتر (بدون نیاز به پلن Pro)، این
اندپوینت را با یک سرویس رایگان مثل cron-job.org هر ۵-۱۰ دقیقه یک‌بار پینگ کن:

    GET https://<your-app>.vercel.app/api/cron?token=<CRON_SECRET>

(حذف فرصت‌طلبانه در هر پیام ورودی هم در api/webhook.py انجام می‌شود، پس حتی
بدون کرون هم پیام‌ها دیر یا زود پاک می‌شوند — این اندپوینت فقط برای دقت
بیشتر روی زمان‌بندی است.)
"""
import asyncio
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import BOT_TOKEN, CRON_SECRET  # noqa: E402
from telegram import Bot  # noqa: E402
import database as db  # noqa: E402
from cleanup import cleanup_due_deletions  # noqa: E402


async def _run_cleanup() -> int:
    await db.init_db()
    bot = Bot(token=BOT_TOKEN)
    return await cleanup_due_deletions(bot)


class handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        if not CRON_SECRET:
            return True  # هشدار: تنظیم نکردن CRON_SECRET یعنی این اندپوینت عمومی و باز است
        auth_header = self.headers.get("Authorization", "")
        if auth_header == f"Bearer {CRON_SECRET}":
            return True  # درخواست از طرف Vercel Cron
        query = parse_qs(urlparse(self.path).query)
        return query.get("token", [""])[0] == CRON_SECRET

    def do_GET(self):
        if not self._authorized():
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return
        try:
            deleted = asyncio.run(_run_cleanup())
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(f'{{"ok": true, "deleted": {deleted}}}'.encode("utf-8"))

    def do_POST(self):
        self.do_GET()
