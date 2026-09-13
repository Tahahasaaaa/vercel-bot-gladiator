"""
لایه دیتابیس — روی Postgres (مثلاً Neon، از طریق Vercel Storage).

نکته مهم دربارهٔ اجرای سرورلس:
هر Function روی Vercel در یک پروسه‌ی جدا (یا کوتاه‌مدت) اجرا می‌شود، پس هیچ متغیر
در حافظه (مثل context.user_data در نسخه‌ی قبلی روی Railway) بین درخواست‌ها باقی
نمی‌ماند. به همین دلیل تمام «حالت‌های موقت» (مثلاً این‌که کاربر منتظر انتخاب
دسته‌بندی است یا ادمین در حال پاسخ‌دادن است) هم در همین دیتابیس نگه‌داری می‌شود
(جدول pending_states) نه در حافظه.

از psycopg (نسخه ۳) به‌صورت sync استفاده شده و توابع async با
asyncio.to_thread به آن دسترسی دارند، چون هندلرهای python-telegram-bot
async هستند ولی درایور psycopg2/3 استاندارد sync است — این ساده‌ترین و
پایدارترین راه روی Vercel است (بدون نیاز به کامپایل افزونه‌های async مثل
asyncpg که گاهی روی بیلد سرورلس مشکل‌ساز می‌شوند).
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL

UTC = timezone.utc


@contextmanager
def get_connection():
    """اتصال sync به Postgres (برای استفاده داخل asyncio.to_thread)."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


async def _run(fn, *args, **kwargs):
    """اجرای یک تابع sync دیتابیسی در ترد جدا، بدون بلاک کردن event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


# ==================================================================
# ساخت جداول
# ==================================================================

def _init_db_sync() -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id     BIGINT PRIMARY KEY,
                blocked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                reason      TEXT DEFAULT 'مسدود شده توسط ادمین'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id          SERIAL PRIMARY KEY,
                thread_id   INTEGER,
                user_id     BIGINT NOT NULL,
                username    TEXT,
                text        TEXT,
                media_type  TEXT,
                category    TEXT,
                direction   TEXT NOT NULL DEFAULT 'in',
                timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
                replied     BOOLEAN DEFAULT false
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS thread_links (
                bot_message_id BIGINT NOT NULL,
                user_id        BIGINT NOT NULL,
                thread_id      INTEGER NOT NULL,
                PRIMARY KEY (bot_message_id, user_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_states (
                user_id     BIGINT PRIMARY KEY,
                state_type  TEXT NOT NULL,
                payload     JSONB,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_forward_map (
                id                SERIAL PRIMARY KEY,
                admin_id          BIGINT NOT NULL,
                admin_message_id  BIGINT NOT NULL,
                user_id           BIGINT NOT NULL,
                thread_id         INTEGER NOT NULL,
                delete_at         TIMESTAMPTZ,
                deleted           BOOLEAN DEFAULT false,
                created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id         BIGINT PRIMARY KEY,
                username        TEXT,
                sent_count      INTEGER NOT NULL DEFAULT 0,
                received_count  INTEGER NOT NULL DEFAULT 0,
                reports_count   INTEGER NOT NULL DEFAULT 0,
                last_active     TIMESTAMPTZ
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS challenge_completions (
                user_id         BIGINT NOT NULL,
                challenge_date  DATE NOT NULL,
                completed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                streak          INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, challenge_date)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit (
                user_id       BIGINT PRIMARY KEY,
                window_start  TIMESTAMPTZ NOT NULL,
                count         INTEGER NOT NULL DEFAULT 0
            )
        """)


async def init_db() -> None:
    await _run(_init_db_sync)


# ==================================================================
# blocked_users
# ==================================================================

def _block_user_sync(user_id: int, reason: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO blocked_users (user_id, blocked_at, reason) VALUES (%s, now(), %s) "
            "ON CONFLICT (user_id) DO UPDATE SET blocked_at = now(), reason = EXCLUDED.reason",
            (user_id, reason),
        )


async def block_user(user_id: int, reason: str = "مسدود شده توسط ادمین") -> None:
    await _run(_block_user_sync, user_id, reason)


def _unblock_user_sync(user_id: int) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM blocked_users WHERE user_id = %s", (user_id,))
        return cur.rowcount > 0


async def unblock_user(user_id: int) -> bool:
    return await _run(_unblock_user_sync, user_id)


def _is_blocked_sync(user_id: int) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM blocked_users WHERE user_id = %s", (user_id,))
        return cur.fetchone() is not None


async def is_blocked(user_id: int) -> bool:
    return await _run(_is_blocked_sync, user_id)


def _get_all_blocked_sync() -> list[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id, blocked_at, reason FROM blocked_users ORDER BY blocked_at DESC")
        rows = cur.fetchall()
        for r in rows:
            r["blocked_at"] = r["blocked_at"].isoformat()
        return rows


async def get_all_blocked() -> list[dict]:
    return await _run(_get_all_blocked_sync)


# ==================================================================
# messages & threads
# ==================================================================

def _save_message_sync(user_id, username, text, media_type, category, thread_id, direction) -> tuple[int, int]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO messages (thread_id, user_id, username, text, media_type, category, direction) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (thread_id, user_id, username, text, media_type, category, direction),
        )
        new_id = cur.fetchone()["id"]
        if thread_id is None:
            cur.execute("UPDATE messages SET thread_id = %s WHERE id = %s", (new_id, new_id))
            thread_id = new_id
        return new_id, thread_id


async def save_message(user_id, username, text, media_type=None, category=None,
                        thread_id=None, direction: str = "in") -> tuple[int, int]:
    return await _run(_save_message_sync, user_id, username, text, media_type, category, thread_id, direction)


def _mark_thread_replied_sync(thread_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE messages SET replied = true WHERE thread_id = %s", (thread_id,))


async def mark_thread_replied(thread_id: int) -> None:
    await _run(_mark_thread_replied_sync, thread_id)


def _save_thread_link_sync(bot_message_id: int, user_id: int, thread_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO thread_links (bot_message_id, user_id, thread_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (bot_message_id, user_id) DO UPDATE SET thread_id = EXCLUDED.thread_id",
            (bot_message_id, user_id, thread_id),
        )


async def save_thread_link(bot_message_id: int, user_id: int, thread_id: int) -> None:
    await _run(_save_thread_link_sync, bot_message_id, user_id, thread_id)


def _get_thread_link_sync(bot_message_id: int, user_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT thread_id FROM thread_links WHERE bot_message_id = %s AND user_id = %s",
            (bot_message_id, user_id),
        )
        row = cur.fetchone()
        return row["thread_id"] if row else None


async def get_thread_link(bot_message_id: int, user_id: int):
    return await _run(_get_thread_link_sync, bot_message_id, user_id)


def _get_stats_sync() -> dict:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM messages")
        total_messages = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(DISTINCT user_id) AS c FROM messages")
        unique_users = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM blocked_users")
        blocked_count = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM messages WHERE replied = false")
        unanswered = cur.fetchone()["c"]
        return {
            "total_messages": total_messages,
            "unique_users": unique_users,
            "blocked_count": blocked_count,
            "unanswered": unanswered,
        }


async def get_stats() -> dict:
    return await _run(_get_stats_sync)


def _get_category_stats_sync() -> dict:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT category, COUNT(*) AS cnt FROM messages WHERE category IS NOT NULL GROUP BY category"
        )
        return {r["category"]: r["cnt"] for r in cur.fetchall()}


async def get_category_stats() -> dict:
    return await _run(_get_category_stats_sync)


# ==================================================================
# pending_states (جایگزین context.user_data)
# ==================================================================

def _set_pending_state_sync(user_id: int, state_type: str, payload: dict) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pending_states (user_id, state_type, payload, created_at) "
            "VALUES (%s, %s, %s, now()) "
            "ON CONFLICT (user_id) DO UPDATE SET state_type = EXCLUDED.state_type, "
            "payload = EXCLUDED.payload, created_at = now()",
            (user_id, state_type, json.dumps(payload)),
        )


async def set_pending_state(user_id: int, state_type: str, payload: dict) -> None:
    await _run(_set_pending_state_sync, user_id, state_type, payload)


def _get_pending_state_sync(user_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state_type, payload FROM pending_states WHERE user_id = %s", (user_id,)
        )
        row = cur.fetchone()
        return row if row else None


async def get_pending_state(user_id: int):
    return await _run(_get_pending_state_sync, user_id)


def _clear_pending_state_sync(user_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM pending_states WHERE user_id = %s", (user_id,))


async def clear_pending_state(user_id: int) -> None:
    await _run(_clear_pending_state_sync, user_id)


# ==================================================================
# admin_forward_map — برای پیام‌های زمان‌دار (حذف خودکار)
# ==================================================================

def _save_admin_forward_sync(admin_id, admin_message_id, user_id, thread_id, delete_at) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO admin_forward_map (admin_id, admin_message_id, user_id, thread_id, delete_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (admin_id, admin_message_id, user_id, thread_id, delete_at),
        )


async def save_admin_forward(admin_id: int, admin_message_id: int, user_id: int,
                              thread_id: int, delete_at: datetime | None) -> None:
    await _run(_save_admin_forward_sync, admin_id, admin_message_id, user_id, thread_id, delete_at)


def _get_due_forwards_sync() -> list[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, admin_id, admin_message_id FROM admin_forward_map "
            "WHERE deleted = false AND delete_at IS NOT NULL AND delete_at <= now()"
        )
        return cur.fetchall()


async def get_due_forwards() -> list[dict]:
    return await _run(_get_due_forwards_sync)


def _mark_forward_deleted_sync(row_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE admin_forward_map SET deleted = true WHERE id = %s", (row_id,))


async def mark_forward_deleted(row_id: int) -> None:
    await _run(_mark_forward_deleted_sync, row_id)


# ==================================================================
# user_stats — آمار شخصی کاربر
# ==================================================================

def _touch_user_sync(user_id: int, username: str) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO user_stats (user_id, username, last_active) VALUES (%s, %s, now()) "
            "ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username, last_active = now()",
            (user_id, username),
        )


async def touch_user(user_id: int, username: str) -> None:
    await _run(_touch_user_sync, user_id, username)


def _increment_sent_sync(user_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE user_stats SET sent_count = sent_count + 1, last_active = now() WHERE user_id = %s",
            (user_id,),
        )


async def increment_sent(user_id: int) -> None:
    await _run(_increment_sent_sync, user_id)


def _increment_received_sync(user_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE user_stats SET received_count = received_count + 1 WHERE user_id = %s",
            (user_id,),
        )


async def increment_received(user_id: int) -> None:
    await _run(_increment_received_sync, user_id)


def _increment_reports_sync(user_id: int) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE user_stats SET reports_count = reports_count + 1 WHERE user_id = %s",
            (user_id,),
        )


async def increment_reports(user_id: int) -> None:
    await _run(_increment_reports_sync, user_id)


def _get_user_stats_sync(user_id: int) -> dict:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT sent_count, received_count, reports_count, last_active "
            "FROM user_stats WHERE user_id = %s", (user_id,)
        )
        row = cur.fetchone()
        if not row:
            return {"sent_count": 0, "received_count": 0, "reports_count": 0, "last_active": None}
        return row


async def get_user_stats(user_id: int) -> dict:
    return await _run(_get_user_stats_sync, user_id)


# ==================================================================
# challenge_completions
# ==================================================================

def _complete_challenge_sync(user_id: int, challenge_date) -> tuple[bool, int]:
    """ثبت انجام چالش امروز. خروجی: (آیا قبلاً انجام شده بود، استریک فعلی)"""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT streak, challenge_date FROM challenge_completions WHERE user_id = %s "
            "ORDER BY challenge_date DESC LIMIT 1",
            (user_id,),
        )
        last = cur.fetchone()

        cur.execute(
            "SELECT streak FROM challenge_completions WHERE user_id = %s AND challenge_date = %s",
            (user_id, challenge_date),
        )
        already_row = cur.fetchone()
        if already_row:
            return True, already_row["streak"]

        streak = 1
        if last and (challenge_date - last["challenge_date"]) == timedelta(days=1):
            streak = last["streak"] + 1

        cur.execute(
            "INSERT INTO challenge_completions (user_id, challenge_date, streak) VALUES (%s, %s, %s)",
            (user_id, challenge_date, streak),
        )
        return False, streak


async def complete_challenge(user_id: int, challenge_date) -> tuple[bool, int]:
    return await _run(_complete_challenge_sync, user_id, challenge_date)


def _get_challenge_progress_sync(user_id: int) -> dict:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS total FROM challenge_completions WHERE user_id = %s", (user_id,)
        )
        total = cur.fetchone()["total"]
        cur.execute(
            "SELECT streak FROM challenge_completions WHERE user_id = %s "
            "ORDER BY challenge_date DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        streak = row["streak"] if row else 0
        return {"total": total, "streak": streak}


async def get_challenge_progress(user_id: int) -> dict:
    return await _run(_get_challenge_progress_sync, user_id)


# ==================================================================
# rate limiting (بین درخواست‌های مختلف سرورلس)
# ==================================================================

def _check_rate_limit_sync(user_id: int, max_per_minute: int) -> bool:
    """True یعنی کاربر باید بلاک شود (rate limited)."""
    now = datetime.now(UTC)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT window_start, count FROM rate_limit WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row or (now - row["window_start"]) > timedelta(minutes=1):
            cur.execute(
                "INSERT INTO rate_limit (user_id, window_start, count) VALUES (%s, %s, 1) "
                "ON CONFLICT (user_id) DO UPDATE SET window_start = EXCLUDED.window_start, count = 1",
                (user_id, now),
            )
            return False
        if row["count"] >= max_per_minute:
            return True
        cur.execute("UPDATE rate_limit SET count = count + 1 WHERE user_id = %s", (user_id,))
        return False


async def is_rate_limited(user_id: int, max_per_minute: int) -> bool:
    return await _run(_check_rate_limit_sync, user_id, max_per_minute)
