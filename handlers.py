import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, ForceReply
from telegram.error import Forbidden, BadRequest
from telegram.ext import ContextTypes

from config import ADMIN_IDS, MAX_MESSAGES_PER_MINUTE
import database as db
from challenges import get_today_challenge
from keyboards import (
    CATEGORIES,
    DELETE_TIMERS,
    main_menu_keyboard,
    category_keyboard,
    delete_timer_keyboard,
    challenge_keyboard,
    admin_keyboard,
)

logger = logging.getLogger(__name__)
UTC = timezone.utc


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def notify_all_admins(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, exclude: int | None = None):
    for admin_id in ADMIN_IDS:
        if admin_id == exclude:
            continue
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"خطا در ارسال پیام به ادمین {admin_id}: {e}")


# ==================================================================
# /start و /menu
# ==================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if await db.is_blocked(user.id):
        return
    await db.touch_user(user.id, user.username or "NoUsername")
    await update.message.reply_text(
        "سلام ❤️\n"
        "به GLADIATOR خوش اومدی.\n\n"
        "🎭 می‌تونی پیام ناشناس بفرستی\n"
        "⚔️ یا یک چالش روزانه بگیری و روی خودت کار کنی\n\n"
        "از منوی زیر انتخاب کن، یا همین الان پیامت رو بنویس تا به صورت ناشناس ارسال شه.",
        reply_markup=main_menu_keyboard(),
    )
    logger.info(f"کاربر {user.id} (@{user.username}) استارت زد.")


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📋 منو:", reply_markup=main_menu_keyboard())


# ==================================================================
# ⚔️ چالش روزانه
# ==================================================================

async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_today_challenge(update.message, update.effective_user.id)


async def send_today_challenge(message_target, user_id: int) -> None:
    ch = get_today_challenge()
    progress = await db.get_challenge_progress(user_id)
    text = (
        "⚔️ چالش امروز\n\n"
        f"{ch['text']}\n\n"
        f"⏱ زمان تقریبی: {ch['minutes']} دقیقه\n"
        f"🔥 استریک فعلی: {progress['streak']} روز | مجموع چالش‌های انجام‌شده: {progress['total']}\n\n"
        "وقتی تمومش کردی، دکمه زیر رو بزن 👇"
    )
    await message_target.reply_text(text, reply_markup=challenge_keyboard())


async def handle_challenge_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    already, streak = await db.complete_challenge(user_id, datetime.now(UTC).date())
    if already:
        await query.edit_message_text(
            f"✅ چالش امروز رو قبلاً ثبت کرده بودی. استریک فعلی: {streak} روز 🔥"
        )
    else:
        await query.edit_message_text(
            f"🎉 آفرین! چالش امروز ثبت شد.\n🔥 استریک: {streak} روز\n\nفردا دوباره سراغت میایم 💪"
        )


# ==================================================================
# 📊 آمار شخصی کاربر
# ==================================================================

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_my_stats(update.message, update.effective_user.id)


async def send_my_stats(message_target, user_id: int) -> None:
    s = await db.get_user_stats(user_id)
    progress = await db.get_challenge_progress(user_id)

    sent = s["sent_count"]
    if sent >= 20:
        activity = "🔥 بالا"
    elif sent >= 5:
        activity = "🙂 متوسط"
    else:
        activity = "🌱 کم"

    text = (
        "📊 آمار شما\n\n"
        f"📤 پیام‌های ارسالی: {sent}\n"
        f"📨 پاسخ‌های دریافتی: {s['received_count']}\n"
        f"👤 گزارش‌ها: {s['reports_count']}\n"
        f"🔥 فعالیت: {activity}\n\n"
        f"⚔️ استریک چالش‌ها: {progress['streak']} روز\n"
        f"✅ مجموع چالش‌های انجام‌شده: {progress['total']}"
    )
    await message_target.reply_text(text)


# ==================================================================
# دستورات ادمین
# ==================================================================

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    s = await db.get_stats()
    text = (
        "📊 آمار ربات\n\n"
        f"📩 کل پیام‌ها: {s['total_messages']}\n"
        f"👥 کاربران منحصربه‌فرد: {s['unique_users']}\n"
        f"⛔ کاربران مسدود: {s['blocked_count']}\n"
        f"📭 پیام‌های بی‌پاسخ: {s['unanswered']}\n"
    )
    cat_stats = await db.get_category_stats()
    if cat_stats:
        text += "\n🏷 دسته‌بندی پیام‌ها:\n"
        for code, cnt in cat_stats.items():
            text += f"{CATEGORIES.get(code, code)}: {cnt}\n"
    await update.message.reply_text(text)


async def blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    blocked = await db.get_all_blocked()
    if not blocked:
        await update.message.reply_text("هیچ کاربری مسدود نشده ✅")
        return
    lines = ["⛔ کاربران مسدود شده:\n"]
    for b in blocked:
        lines.append(f"🆔 {b['user_id']} — {b['blocked_at'][:10]}")
    await update.message.reply_text("\n".join(lines))


async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("فرمت صحیح:\n/unblock 123456789")
        return
    uid = int(args[0])
    if await db.unblock_user(uid):
        await update.message.reply_text(f"✅ کاربر {uid} از مسدودیت خارج شد.")
    else:
        await update.message.reply_text(f"⚠️ کاربر {uid} در لیست مسدودها نبود.")


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    lines = ["👮 ادمین‌های فعلی ربات:\n"]
    for admin_id in ADMIN_IDS:
        lines.append(f"🆔 {admin_id}")
    lines.append(
        "\nبرای افزودن یا حذف ادمین، متغیر ADMIN_IDS را در تنظیمات Vercel ویرایش کن."
    )
    await update.message.reply_text("\n".join(lines))


# ==================================================================
# پیام متنی کاربران
# ==================================================================

async def user_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        return
    if await db.is_blocked(user.id):
        await update.message.reply_text("⛔ شما توسط ادمین مسدود شده‌اید.")
        return
    if await db.is_rate_limited(user.id, MAX_MESSAGES_PER_MINUTE):
        await update.message.reply_text("⚠️ خیلی سریع پیام می‌فرستی! لطفاً چند لحظه صبر کن.")
        return

    text = update.message.text
    username = user.username or "NoUsername"
    await db.touch_user(user.id, username)

    reply_to = update.message.reply_to_message
    thread_id = await db.get_thread_link(reply_to.message_id, user.id) if reply_to else None

    if thread_id:
        # ادامه گفتگو — بدون دسته‌بندی و بدون گزینه‌ی حذف خودکار (سرعت گفتگو حفظ می‌شود)
        _, thread_id = await db.save_message(user.id, username, text, media_type="text", thread_id=thread_id)
        await db.increment_sent(user.id)
        msg = (
            f"💬 پاسخ جدید در گفتگو #{thread_id}\n\n"
            f"👤 @{username} | 🆔 {user.id}\n\n"
            f"✉️ متن:\n{text}"
        )
        for admin_id in ADMIN_IDS:
            try:
                sent = await context.bot.send_message(chat_id=admin_id, text=msg, reply_markup=admin_keyboard(user.id, thread_id))
                await db.save_admin_forward(admin_id, sent.message_id, user.id, thread_id, delete_at=None)
            except Exception as e:
                logger.error(f"خطا در ارسال پیام به ادمین {admin_id}: {e}")
        await update.message.reply_text("✅ پاسخ شما در ادامه گفتگو ارسال شد.")
        return

    # پیام جدید — ابتدا دسته‌بندی، سپس گزینه‌ی حذف خودکار
    await db.set_pending_state(user.id, "await_category", {"kind": "text", "text": text})
    await update.message.reply_text(
        "این پیام رو در چه دسته‌ای قرار می‌دی؟",
        reply_markup=category_keyboard(),
    )


# ==================================================================
# پیام مدیا (عکس، ویس، ویدیو، فایل)
# ==================================================================

async def user_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id):
        return
    if await db.is_blocked(user.id):
        await update.message.reply_text("⛔ شما توسط ادمین مسدود شده‌اید.")
        return
    if await db.is_rate_limited(user.id, MAX_MESSAGES_PER_MINUTE):
        await update.message.reply_text("⚠️ خیلی سریع پیام می‌فرستی! لطفاً صبر کن.")
        return

    username = user.username or "NoUsername"
    await db.touch_user(user.id, username)

    if update.message.photo:
        media_type = "photo"
        file_id = update.message.photo[-1].file_id
    elif update.message.voice:
        media_type = "voice"
        file_id = update.message.voice.file_id
    elif update.message.video:
        media_type = "video"
        file_id = update.message.video.file_id
    elif update.message.document:
        media_type = "document"
        file_id = update.message.document.file_id
    else:
        media_type = "other"
        file_id = None

    caption = update.message.caption or ""

    reply_to = update.message.reply_to_message
    existing_thread_id = await db.get_thread_link(reply_to.message_id, user.id) if reply_to else None

    if existing_thread_id:
        # ادامه گفتگو با مدیا — فوری فوروارد می‌شود (بدون گزینه‌ی حذف خودکار)
        _, thread_id = await db.save_message(
            user.id, username, caption or f"[{media_type}]",
            media_type=media_type, thread_id=existing_thread_id
        )
        await db.increment_sent(user.id)
        header = (
            f"💬 پاسخ جدید (مدیا) در گفتگو #{thread_id}\n"
            f"👤 @{username} | 🆔 {user.id}\nنوع: {media_type}"
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=header)
                fwd = await update.message.forward(chat_id=admin_id)
                sent = await context.bot.send_message(
                    chat_id=admin_id, text="⬆️ پیام بالا", reply_markup=admin_keyboard(user.id, thread_id)
                )
                await db.save_admin_forward(admin_id, fwd.message_id, user.id, thread_id, delete_at=None)
                await db.save_admin_forward(admin_id, sent.message_id, user.id, thread_id, delete_at=None)
            except Exception as e:
                logger.error(f"خطا در forward مدیا به ادمین {admin_id}: {e}")
        await update.message.reply_text("✅ پیام شما به صورت ناشناس ارسال شد.")
        return

    # پیام مدیای جدید — قبل از ارسال، گزینه‌ی حذف خودکار را می‌پرسیم
    await db.set_pending_state(user.id, "await_timer", {
        "kind": "media",
        "media_type": media_type,
        "file_id": file_id,
        "caption": caption,
    })
    await update.message.reply_text(
        "⏱ این پیام بعد از چه مدت از چت ادمین‌ها پاک شود؟",
        reply_markup=delete_timer_keyboard(),
    )


# ==================================================================
# نهایی‌سازی و ارسال پیام به ادمین‌ها (متن یا مدیا) بعد از انتخاب تایمر
# ==================================================================

async def _finalize_and_forward(context: ContextTypes.DEFAULT_TYPE, query, payload: dict, delete_seconds: int | None) -> None:
    user = query.from_user
    username = user.username or "NoUsername"
    delete_at = (datetime.now(UTC) + timedelta(seconds=delete_seconds)) if delete_seconds else None

    if payload["kind"] == "text":
        text = payload["text"]
        category = payload.get("category")
        _, thread_id = await db.save_message(user.id, username, text, media_type="text", category=category)
        label = CATEGORIES.get(category, "✉️ سایر")
        admin_msg = (
            f"📩 پیام جدید — گفتگو #{thread_id}\n"
            f"🏷 دسته: {label}\n\n"
            f"👤 @{username} | 🆔 {user.id}\n\n"
            f"✉️ متن:\n{text}"
        )
        for admin_id in ADMIN_IDS:
            try:
                sent = await context.bot.send_message(chat_id=admin_id, text=admin_msg, reply_markup=admin_keyboard(user.id, thread_id))
                await db.save_admin_forward(admin_id, sent.message_id, user.id, thread_id, delete_at)
            except Exception as e:
                logger.error(f"خطا در ارسال پیام به ادمین {admin_id}: {e}")
        await db.increment_sent(user.id)
        timer_note = f"\n⏱ این پیام تا {delete_seconds // 3600} ساعت دیگر از چت ادمین پاک می‌شود." if delete_seconds else ""
        await query.edit_message_text(f"✅ پیام شما (دسته: {label}) به صورت ناشناس ارسال شد.{timer_note}")

    else:  # media
        media_type = payload["media_type"]
        file_id = payload["file_id"]
        caption = payload.get("caption") or ""
        _, thread_id = await db.save_message(user.id, username, caption or f"[{media_type}]", media_type=media_type)
        header = (
            f"📩 پیام جدید (مدیا) — گفتگو #{thread_id}\n"
            f"👤 @{username} | 🆔 {user.id}\nنوع: {media_type}"
        )
        send_map = {
            "photo": context.bot.send_photo,
            "voice": context.bot.send_voice,
            "video": context.bot.send_video,
            "document": context.bot.send_document,
        }
        sender = send_map.get(media_type)
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=header)
                if sender and file_id:
                    fwd = await sender(chat_id=admin_id, **{media_type: file_id})
                    await db.save_admin_forward(admin_id, fwd.message_id, user.id, thread_id, delete_at)
                sent = await context.bot.send_message(
                    chat_id=admin_id, text="⬆️ پیام بالا", reply_markup=admin_keyboard(user.id, thread_id)
                )
                await db.save_admin_forward(admin_id, sent.message_id, user.id, thread_id, delete_at)
            except Exception as e:
                logger.error(f"خطا در forward مدیا به ادمین {admin_id}: {e}")
        await db.increment_sent(user.id)
        timer_note = f"\n⏱ این پیام تا {delete_seconds // 3600} ساعت دیگر از چت ادمین پاک می‌شود." if delete_seconds else ""
        await query.edit_message_text(f"✅ پیام شما به صورت ناشناس ارسال شد.{timer_note}")


# ==================================================================
# دکمه‌ها
# ==================================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(":")
    action = parts[0]

    # ---- بخش‌های منوی اصلی ----
    if action == "section":
        section = parts[1]
        if section == "anon":
            await query.message.reply_text(
                "🎭 حالت ناشناس فعاله.\nهمین الان پیامت رو بنویس تا به صورت ناشناس برای ادمین ارسال شه."
            )
        elif section == "challenge":
            await send_today_challenge(query.message, query.from_user.id)
        elif section == "mystats":
            await send_my_stats(query.message, query.from_user.id)
        return

    if action == "challenge_done":
        await handle_challenge_done(update, context)
        return

    if action == "menu":
        section = parts[1]
        if section == "help":
            text = (
                "📖 راهنما:\n\n"
                "🎭 حالت ناشناس:\n"
                "• پیامت رو بنویس\n"
                "• دسته‌بندی رو انتخاب کن\n"
                "• مدت زمان حذف خودکار پیام (اختیاری) رو انتخاب کن\n"
                "• پیام کاملاً ناشناس برای ادمین ارسال می‌شه\n"
                "• وقتی ادمین جواب داد، روی همون پیام Reply بزن تا گفتگو ادامه پیدا کنه\n\n"
                "⚔️ GLADIATOR Challenges:\n"
                "• هر روز یک چالش کوتاه (۱۰ تا ۳۰ دقیقه) می‌گیری\n"
                "• وقتی انجامش دادی، دکمه «✅ انجام دادم» رو بزن\n\n"
                "📊 با /mystats آمار شخصیت رو ببین."
            )
        else:
            text = "ℹ️ GLADIATOR یک ربات چت ناشناس + چالش‌های روزانه‌ست. پیام‌هایت بدون مشخصات شخصی برای ادمین ارسال می‌شه ❤️"
        await query.message.reply_text(text)
        return

    # ---- انتخاب دسته‌بندی پیام متنی جدید ----
    if action == "cat":
        code = parts[1]
        state = await db.get_pending_state(query.from_user.id)
        if not state or state["state_type"] != "await_category":
            await query.edit_message_text("⚠️ این پیام منقضی شده. لطفاً پیام جدیدی بفرست.")
            return
        payload = state["payload"]
        payload["category"] = code
        await db.set_pending_state(query.from_user.id, "await_timer", payload)
        await query.edit_message_text(
            "⏱ این پیام بعد از چه مدت از چت ادمین‌ها پاک شود؟",
            reply_markup=delete_timer_keyboard(),
        )
        return

    # ---- انتخاب تایمر حذف خودکار (برای متن یا مدیا) ----
    if action == "del":
        code = parts[1]
        state = await db.get_pending_state(query.from_user.id)
        if not state or state["state_type"] != "await_timer":
            await query.edit_message_text("⚠️ این پیام منقضی شده. لطفاً پیام جدیدی بفرست.")
            return
        _, seconds = DELETE_TIMERS.get(code, (None, None))
        await _finalize_and_forward(context, query, state["payload"], seconds)
        await db.clear_pending_state(query.from_user.id)
        return

    # ---- از این به بعد فقط ادمین‌ها ----
    if not is_admin(query.from_user.id):
        return

    if action == "reply":
        user_id = int(parts[1])
        thread_id = int(parts[2])
        await db.set_pending_state(
            -query.from_user.id,  # کلید جدا برای حالت ادمین (منفی تا تداخلی با آیدی کاربر عادی نداشته باشد)
            "admin_reply",
            {"user_id": user_id, "thread_id": thread_id},
        )
        sent = await query.message.reply_text(
            f"✏️ پاسخ به گفتگو #{thread_id} را بنویسید:",
            reply_markup=ForceReply(selective=True),
        )
        await db.set_pending_state(
            -query.from_user.id, "admin_reply",
            {"user_id": user_id, "thread_id": thread_id, "force_reply_msg_id": sent.message_id},
        )

    elif action == "block_confirm":
        user_id = int(parts[1])
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        confirm_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ بله، مسدود کن", callback_data=f"block:{user_id}"),
                InlineKeyboardButton("❌ انصراف", callback_data="cancel"),
            ]
        ])
        await query.message.reply_text(
            f"⚠️ آیا مطمئنی که می‌خوای کاربر {user_id} را مسدود کنی؟",
            reply_markup=confirm_keyboard,
        )

    elif action == "block":
        user_id = int(parts[1])
        await db.block_user(user_id)
        await query.message.reply_text(f"⛔ کاربر {user_id} مسدود شد.")
        await notify_all_admins(
            context, f"ℹ️ کاربر {user_id} توسط ادمین دیگری مسدود شد.", exclude=query.from_user.id
        )

    elif action == "unblock":
        user_id = int(parts[1])
        if await db.unblock_user(user_id):
            await query.message.reply_text(f"✅ مسدودیت کاربر {user_id} برداشته شد.")
            await notify_all_admins(
                context, f"ℹ️ مسدودیت کاربر {user_id} توسط ادمین دیگری برداشته شد.", exclude=query.from_user.id
            )
        else:
            await query.message.reply_text(f"ℹ️ کاربر {user_id} مسدود نبود.")

    elif action == "report":
        user_id = int(parts[1])
        await db.increment_reports(user_id)
        s = await db.get_user_stats(user_id)
        await query.message.reply_text(f"🚩 کاربر {user_id} گزارش شد. (مجموع گزارش‌ها: {s['reports_count']})")
        await notify_all_admins(
            context, f"🚩 کاربر {user_id} توسط ادمین دیگری گزارش شد.", exclude=query.from_user.id
        )

    elif action == "cancel":
        await query.message.reply_text("❌ عملیات لغو شد.")


# ==================================================================
# پاسخ ادمین (reply به ForceReply)
# ==================================================================

async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return

    replying_admin_id = update.effective_user.id
    state = await db.get_pending_state(-replying_admin_id)

    reply_to = update.message.reply_to_message
    if not state or state["state_type"] != "admin_reply" or not reply_to:
        return
    payload = state["payload"]
    if reply_to.message_id != payload.get("force_reply_msg_id"):
        return

    user_id = payload["user_id"]
    thread_id = payload["thread_id"]
    text = update.message.text

    try:
        sent = await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"✉️ جواب پیامت رسید:\n\n{text}\n\n"
                f"💬 برای ادامه گفتگو، روی همین پیام Reply بزن."
            ),
        )
        await db.save_thread_link(sent.message_id, user_id, thread_id)
        await db.mark_thread_replied(thread_id)
        await db.increment_received(user_id)
        await update.message.reply_text("✅ پاسخ ارسال شد.")
        logger.info(f"ادمین {replying_admin_id} به گفتگو #{thread_id} (کاربر {user_id}) پاسخ داد.")
        await notify_all_admins(
            context,
            f"ℹ️ گفتگو #{thread_id} توسط ادمین دیگری پاسخ داده شد.",
            exclude=replying_admin_id,
        )
    except Forbidden:
        await update.message.reply_text("⚠️ کاربر ربات را بلاک کرده و پیام نرسید.")
        logger.warning(f"کاربر {user_id} ربات را بلاک کرده.")
    except BadRequest as e:
        await update.message.reply_text(f"⚠️ خطا در ارسال: {e}")
        logger.error(f"BadRequest برای کاربر {user_id}: {e}")
    finally:
        await db.clear_pending_state(-replying_admin_id)
