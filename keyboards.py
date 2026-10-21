"""Клавиатуры (reply + inline)."""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import TARIFFS
from curriculum import SUBJECTS, GRADES, get_sections


# ---------- Reply (главное меню) ----------

def main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📝 ҚМЖ құру")],
        [KeyboardButton(text="💳 Тарифтер"), KeyboardButton(text="👤 Жазылымым")],
        [KeyboardButton(text="❓ Көмек")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


# ---------- Inline (поток генерации) ----------

def subjects_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, name in SUBJECTS.items():
        b.button(text=name, callback_data=f"subj:{code}")
    b.adjust(1)
    return b.as_markup()


def grades_kb(subject: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for g in GRADES:
        b.button(text=f"{g}-сынып", callback_data=f"grade:{subject}:{g}")
    b.button(text="⬅️ Артқа", callback_data="back:subjects")
    b.adjust(3, 3, 1, 1)
    return b.as_markup()


def topics_kb(subject: str, grade: int) -> InlineKeyboardMarkup:
    """Темы по индексу (индекс соответствует плоскому списку all_topics)."""
    b = InlineKeyboardBuilder()
    idx = 0
    for section, topics in get_sections(subject, grade).items():
        for t in topics:
            b.button(text=t, callback_data=f"topic:{idx}")
            idx += 1
    b.button(text="✍️ Өз тақырыбым", callback_data="topic:custom")
    b.button(text="⬅️ Артқа", callback_data=f"back:grades:{subject}")
    b.adjust(1)
    return b.as_markup()


def tariffs_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tid, t in TARIFFS.items():
        b.button(
            text=f"{t['emoji']} {t['name']} — {t['price']:,} ₸".replace(",", " "),
            callback_data=f"buy:{tid}",
        )
    b.adjust(1)
    return b.as_markup()


def admin_request_kb(request_id: int, user_id: int, tier: int) -> InlineKeyboardMarkup:
    """Кнопки под заявкой для админа."""
    b = InlineKeyboardBuilder()
    b.button(text="✅ Белсендіру (30 күн)", callback_data=f"appr:{request_id}:{user_id}:{tier}")
    b.button(text="❌ Бас тарту", callback_data=f"rej:{request_id}:{user_id}")
    b.adjust(1)
    return b.as_markup()
