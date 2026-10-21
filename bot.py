"""Точка входа: бот для учителей истории — генерация ҚМЖ на казахском.

Закрытый (платный) бот. Доступ к генерации — только с активным тарифом.
Запуск:  python bot.py   (требуются BOT_TOKEN и ADMIN_ID в .env)
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

import database as db
from config import BOT_TOKEN, ADMIN_ID
from handlers import admin, user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN табылмады. .env файлын толтырыңыз (.env.example қараңыз).")

    await db.init_db()
    logger.info("✅ Дерекқор дайын")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    # admin сначала — чтобы команды/колбэки админа имели приоритет
    dp.include_router(admin.router)
    dp.include_router(user.router)

    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    logger.info("🚀 Бот @%s іске қосылды (ADMIN_ID=%s)", me.username, ADMIN_ID)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот тоқтатылды")
