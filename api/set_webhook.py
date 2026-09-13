"""
اندپوینت کمکی برای ثبت آدرس webhook در تلگرام — فقط یک بار بعد از هر دیپلوی لازم است.

استفاده (در مرورگر یا با curl):
    https://<your-app>.vercel.app/api/set_webhook?token=<CRON_SECRET>

اگر پارامتر url داده نشود، از دامنه‌ی خودکار Vercel (VERCEL_URL) استفاده می‌شود.
"""
import asyncio
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot  # noqa: E402

from config import BOT_TOKEN, WEBHOOK_SECRET, CRON_SECRET  # noqa: E402


async def _set_webhook(target_url: str) -> dict:
    bot = Bot(token=BOT_TOKEN)
    ok = await bot.set_webhook(url=target_url, secret_token=WEBHOOK_SECRET or None)
    info = await bot.get_webhook_info()
    return {"ok": ok, "url": target_url, "webhook_info": info.to_dict()}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        token = query.get("token", [""])[0]

        if CRON_SECRET and token != CRON_SECRET:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized: query param ?token=<CRON_SECRET> is required")
            return

        custom_url = query.get("url", [""])[0]
        if custom_url:
            target_url = custom_url
        else:
            host = os.environ.get("VERCEL_URL", "")
            if not host:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"VERCEL_URL not found; pass ?url=https://yourdomain/api/webhook explicitly")
                return
            target_url = f"https://{host}/api/webhook"

        try:
            result = asyncio.run(_set_webhook(target_url))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))
            return

        import json
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
