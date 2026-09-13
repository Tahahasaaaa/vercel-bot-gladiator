# فایل config.py — همه مقادیر مستقیم داخل کد قرار گرفته‌اند.

# توکن ربات
BOT_TOKEN = "8955432875:AAGcFxi1Bfaj4sXrgmAPpbeEd7wLXFJV9bo"
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

# آیدی عددی ادمین‌ها
ADMIN_IDS: list[int] = [1953490397, 98064300]
if not ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS تنظیم نشده است.")

# برای سازگاری با کدهای قدیمی‌تر
ADMIN_ID = ADMIN_IDS[0]

# محدودیت پیام در دقیقه
MAX_MESSAGES_PER_MINUTE = 5

# رشته اتصال دیتابیس Postgres (از Neon)
# از حالت pooler استفاده شده چون برای محیط سرورلس Vercel مناسب‌تره.
DATABASE_URL = "postgresql://neondb_owner:npg_1PzKiOEScJ3v@ep-aged-credit-aer3e7bb-pooler.c-2.us-east-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL تنظیم نشده است.")

# توکن مخفی برای اعتبارسنجی وبهوک تلگرام
WEBHOOK_SECRET = "whsec_a7f3c9e1b45d8276f0a2c8e4d9b1f6a3"

# توکن مخفی برای محافظت از /api/set_webhook و /api/cron
CRON_SECRET = "cron_5b8e2f1a9c4d7e3f6a0b8c2d5e9f1a4b"
