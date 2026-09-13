import os

# توکن ربات — فقط از Environment Variable خوانده می‌شود (هرگز مقدار پیش‌فرض هاردکد نکن!)
BOT_TOKEN = "8955432875:AAGcFxi1Bfaj4sXrgmAPpbeEd7wLXFJV9bo"
if not BOT_TOKEN:
    raise RuntimeError(
        "متغیر محیطی BOT_TOKEN تنظیم نشده است. "
        "آن را در تنظیمات Vercel (Project Settings → Environment Variables) اضافه کن."
    )

# ---- پشتیبانی از چند ادمین ----
# در Vercel، متغیر ADMIN_IDS را با کاما جدا کن، مثلا: 1953490397,987654321
_admin_ids_raw = os.environ.get("ADMIN_IDS", os.environ.get("ADMIN_ID", ""))
ADMIN_IDS: list[int] = [int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip()]
if not ADMIN_IDS:
    raise RuntimeError("متغیر محیطی ADMIN_IDS تنظیم نشده است.")

# برای سازگاری با کدهای قدیمی‌تر که فقط یک ادمین اصلی می‌خواهند
ADMIN_ID = ADMIN_IDS[0]

# محدودیت rate limiting (تعداد پیام مجاز در هر دقیقه)
MAX_MESSAGES_PER_MINUTE = int(os.environ.get("MAX_MESSAGES_PER_MINUTE", "5"))

# رشته اتصال دیتابیس Postgres (از Neon / Vercel Postgres)
# در Vercel معمولاً به صورت خودکار به عنوان POSTGRES_URL یا DATABASE_URL ست می‌شود.
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "متغیر محیطی DATABASE_URL (یا POSTGRES_URL) تنظیم نشده است. "
        "یک دیتابیس Postgres (مثلاً Neon از تب Storage در Vercel) بساز و آن را وصل کن."
    )

# توکن مخفی برای اعتبارسنجی درخواست‌های webhook تلگرام (X-Telegram-Bot-Api-Secret-Token)
# یک رشته دلخواه و تصادفی بساز و همینجا و هنگام ثبت وبهوک استفاده کن.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

# توکن ساده برای محافظت از اندپوینت /api/set_webhook و /api/cron در برابر فراخوانی عمومی
CRON_SECRET = os.environ.get("CRON_SECRET", "")
