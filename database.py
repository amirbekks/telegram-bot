"""Слой базы данных (SQLite через aiosqlite).

Таблицы:
  users         — пользователи бота
  subscriptions — активные подписки (тариф + срок действия)
  generations   — журнал сгенерированных ҚМЖ (для лимитов и статистики)
  requests      — заявки на доступ/оплату
"""

import aiosqlite
from datetime import datetime, timedelta

from config import DB_PATH, TARIFFS


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                full_name   TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id     INTEGER PRIMARY KEY,
                tier        INTEGER NOT NULL,
                expires_at  TEXT,              -- NULL = бессрочно
                granted_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS generations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                subject     TEXT,
                grade       INTEGER,
                topic       TEXT,
                tier        INTEGER,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                tier        INTEGER,
                status      TEXT DEFAULT 'pending',  -- pending | done | rejected
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()


# ---------- Пользователи ----------

async def ensure_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name),
        )
        # обновляем имя/username на случай изменений
        await db.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
            (username, full_name, user_id),
        )
        await db.commit()


async def get_all_user_ids() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        return [r[0] for r in await cur.fetchall()]


async def list_users(limit: int = 30) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT u.user_id, u.username, u.full_name, u.created_at,
                   s.tier, s.expires_at
            FROM users u
            LEFT JOIN subscriptions s ON s.user_id = u.user_id
            ORDER BY u.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return await cur.fetchall()


# ---------- Подписки ----------

async def get_subscription(user_id: int):
    """Возвращает (tier, expires_at) или None, если подписки нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT tier, expires_at FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        return await cur.fetchone()


async def get_active_tier(user_id: int):
    """Возвращает id активного тарифа или None (с учётом срока действия)."""
    sub = await get_subscription(user_id)
    if not sub:
        return None
    tier, expires_at = sub
    if expires_at is None:  # бессрочно
        return tier
    try:
        if datetime.fromisoformat(expires_at) > datetime.now():
            return tier
    except (ValueError, TypeError):
        return None
    return None


async def grant_subscription(user_id: int, tier: int, days: int | None):
    """Выдать/продлить тариф. days=None или days<=0 — бессрочно."""
    expires_at = None
    if days is not None and days > 0:
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscriptions (user_id, tier, expires_at, granted_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                tier = excluded.tier,
                expires_at = excluded.expires_at,
                granted_at = CURRENT_TIMESTAMP
            """,
            (user_id, tier, expires_at),
        )
        await db.commit()


async def revoke_subscription(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        await db.commit()


# ---------- Генерации и лимиты ----------

async def log_generation(user_id: int, subject: str, grade: int, topic: str, tier: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO generations (user_id, subject, grade, topic, tier) VALUES (?, ?, ?, ?, ?)",
            (user_id, subject, grade, topic, tier),
        )
        await db.commit()


async def generations_last_30d(user_id: int) -> int:
    since = (datetime.now() - timedelta(days=30)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM generations WHERE user_id = ? AND created_at >= ?",
            (user_id, since),
        )
        return (await cur.fetchone())[0]


async def remaining_quota(user_id: int, tier: int):
    """Сколько ҚМЖ осталось за 30 дней. None = без лимита."""
    limit = TARIFFS[tier]["monthly_limit"]
    if limit is None:
        return None
    used = await generations_last_30d(user_id)
    return max(0, limit - used)


# ---------- Заявки ----------

async def create_request(user_id: int, tier: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO requests (user_id, tier) VALUES (?, ?)", (user_id, tier)
        )
        await db.commit()
        return cur.lastrowid


async def set_request_status(request_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE requests SET status = ? WHERE id = ?", (status, request_id)
        )
        await db.commit()


async def pending_requests() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT r.id, r.user_id, r.tier, r.created_at, u.username, u.full_name
            FROM requests r
            LEFT JOIN users u ON u.user_id = r.user_id
            WHERE r.status = 'pending'
            ORDER BY r.id DESC
            LIMIT 30
            """
        )
        return await cur.fetchall()


# ---------- Статистика ----------

async def stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        total_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        active_subs = (await (await db.execute("SELECT COUNT(*) FROM subscriptions")).fetchone())[0]
        total_gen = (await (await db.execute("SELECT COUNT(*) FROM generations")).fetchone())[0]
        pending = (await (await db.execute("SELECT COUNT(*) FROM requests WHERE status='pending'")).fetchone())[0]
        by_tier = {}
        cur = await db.execute("SELECT tier, COUNT(*) FROM subscriptions GROUP BY tier")
        for tier, cnt in await cur.fetchall():
            by_tier[tier] = cnt
    return {
        "total_users": total_users,
        "active_subs": active_subs,
        "total_gen": total_gen,
        "pending": pending,
        "by_tier": by_tier,
    }
