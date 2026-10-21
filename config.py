"""Конфигурация бота: переменные окружения и тарифы.

Бот предназначен для учителей истории (Қазақстан тарихы / Дүниежүзі тарихы)
и генерирует ҚМЖ (қысқа мерзімді жоспар) на казахском языке для 5–11 классов.

Доступ закрытый: без активного тарифа генерация недоступна.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ---------- Основные переменные ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Имя файла базы данных (SQLite)
DB_PATH = os.getenv("DB_PATH", "qmzh_bot.db")

# Контакт для оплаты/активации (показывается пользователю)
PAYMENT_CONTACT = os.getenv("PAYMENT_CONTACT", "@admin")

# ---------- Тарифы ----------
# price      — цена в тенге за период
# period     — период подписки
# days       — на сколько дней активируется тариф при оплате
# monthly_limit — сколько ҚМЖ можно сгенерировать за 30 дней (None = без лимита)
# docx       — доступна ли выгрузка .docx
# slides     — доступен ли план слайдов (презентация)
# depth      — уровень детализации генерации: "basic" | "standard" | "premium"
TARIFFS = {
    1: {
        "id": 1,
        "name": "Бастауыш",
        "emoji": "🥉",
        "price": 2990,
        "period": "ай",
        "days": 30,
        "monthly_limit": 15,
        "docx": False,
        "slides": False,
        "depth": "basic",
        "features": [
            "ҚМЖ қаңқасы (стандарт құрылымы)",
            "Сабақтың кезеңдері мен уақыт бөлінісі",
            "Айына 15 ҚМЖ-ға дейін",
        ],
    },
    2: {
        "id": 2,
        "name": "Стандарт",
        "emoji": "🥈",
        "price": 5990,
        "period": "ай",
        "days": 30,
        "monthly_limit": 50,
        "docx": True,
        "slides": False,
        "depth": "standard",
        "features": [
            "Толық ҚМЖ (мақсаттар, бағалау критерийлері)",
            "Саралау мен рефлексия бөлімдері",
            "Word (.docx) форматында жүктеу",
            "Айына 50 ҚМЖ-ға дейін",
        ],
    },
    3: {
        "id": 3,
        "name": "Премиум",
        "emoji": "🥇",
        "price": 9990,
        "period": "ай",
        "days": 30,
        "monthly_limit": None,  # шексіз
        "docx": True,
        "slides": True,
        "depth": "premium",
        "features": [
            "Кеңейтілген ҚМЖ + пәнаралық байланыс",
            "Презентация слайдтарының жоспары",
            "Қосымша тапсырмалар мен ресурстар",
            "Word (.docx) форматында жүктеу",
            "Шексіз ҚМЖ саны",
        ],
    },
}


def tariff_card(tier_id: int) -> str:
    """Текст-карточка одного тарифа (на казахском)."""
    t = TARIFFS[tier_id]
    limit = "шексіз" if t["monthly_limit"] is None else f"{t['monthly_limit']} ҚМЖ/ай"
    lines = [
        f"{t['emoji']} <b>{t['name']}</b> — <b>{t['price']:,} ₸</b>/{t['period']}".replace(",", " "),
        f"📊 Лимит: {limit}",
        "",
    ]
    lines += [f"• {f}" for f in t["features"]]
    return "\n".join(lines)
