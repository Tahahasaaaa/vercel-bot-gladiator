from telegram import InlineKeyboardButton, InlineKeyboardMarkup

CATEGORIES = {
    "suggestion": "💡 پیشنهاد",
    "criticism": "⚠️ انتقاد",
    "romantic": "❤️ عاشقانه",
    "question": "❓ سوال",
    "other": "✉️ سایر",
}

# گزینه‌های حذف خودکار پیام (به ثانیه)
DELETE_TIMERS = {
    "1h": ("1 ساعت", 3600),
    "6h": ("6 ساعت", 6 * 3600),
    "24h": ("24 ساعت", 24 * 3600),
    "none": ("بدون حذف خودکار", None),
}


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """منوی اصلی: انتخاب بین حالت ناشناس و بخش چالش‌ها"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎭 حالت ناشناس", callback_data="section:anon")],
        [InlineKeyboardButton("⚔️ GLADIATOR Challenges", callback_data="section:challenge")],
        [InlineKeyboardButton("📊 آمار شما", callback_data="section:mystats")],
        [InlineKeyboardButton("📖 راهنما", callback_data="menu:help"),
         InlineKeyboardButton("ℹ️ درباره ربات", callback_data="menu:about")],
    ])


def category_keyboard() -> InlineKeyboardMarkup:
    items = list(CATEGORIES.items())
    rows = []
    for i in range(0, len(items), 2):
        pair = items[i:i + 2]
        rows.append([InlineKeyboardButton(label, callback_data=f"cat:{code}") for code, label in pair])
    return InlineKeyboardMarkup(rows)


def delete_timer_keyboard() -> InlineKeyboardMarkup:
    items = list(DELETE_TIMERS.items())
    rows = []
    for i in range(0, len(items), 2):
        pair = items[i:i + 2]
        rows.append([
            InlineKeyboardButton(f"⏱ {label}", callback_data=f"del:{code}") for code, (label, _) in pair
        ])
    return InlineKeyboardMarkup(rows)


def challenge_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ انجام دادم", callback_data="challenge_done")],
    ])


def admin_keyboard(user_id: int, thread_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✉️ پاسخ", callback_data=f"reply:{user_id}:{thread_id}"),
            InlineKeyboardButton("⛔ مسدود", callback_data=f"block_confirm:{user_id}"),
        ],
        [
            InlineKeyboardButton("🔓 رفع مسدودیت", callback_data=f"unblock:{user_id}"),
            InlineKeyboardButton("🚩 گزارش", callback_data=f"report:{user_id}"),
        ],
    ])
