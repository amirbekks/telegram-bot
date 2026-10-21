"""Пользовательские хендлеры: старт, тарифы, генерация ҚМЖ, статус."""

import os
import tempfile
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from config import TARIFFS, ADMIN_ID, PAYMENT_CONTACT, tariff_card
from curriculum import SUBJECTS, all_topics
from kmzh_generator import generate, render_docx

router = Router()

TG_LIMIT = 4000  # запас до лимита Telegram (4096)


class Gen(StatesGroup):
    waiting_topic = State()  # ввод своей темы вручную


# ---------- Утилиты ----------

def split_text(text: str) -> list:
    """Разбивает длинный текст на части по строкам, не превышая лимит."""
    parts, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > TG_LIMIT:
            parts.append(buf)
            buf = ""
        buf += line + "\n"
    if buf.strip():
        parts.append(buf)
    return parts


async def deny_if_no_access(message: Message) -> int | None:
    """Проверка доступа. Возвращает tier или None (и шлёт сообщение)."""
    tier = await db.get_active_tier(message.from_user.id)
    if tier is None:
        await message.answer(
            "🔒 <b>Бот жабық.</b>\n\n"
            "ҚМЖ құру үшін белсенді тариф қажет.\n"
            "«💳 Тарифтер» бөлімінен жазылымды таңдаңыз.",
            reply_markup=kb.main_menu(),
        )
    return tier


# ---------- Старт и меню ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    u = message.from_user
    await db.ensure_user(u.id, u.username or "", u.full_name or "")
    await message.answer(
        f"Сәлеметсіз бе, {u.first_name}! 👋\n\n"
        "📚 Бұл — <b>тарих пәні мұғалімдеріне</b> арналған бот.\n"
        "Қазақ тілінде <b>ҚМЖ (қысқа мерзімді жоспар)</b> дайындайды:\n\n"
        "• Пәндер: Қазақстан тарихы, Дүниежүзі тарихы\n"
        "• Сыныптар: 5–11\n"
        "• Тарифке қарай — толық ҚМЖ, Word файл, слайдтар жоспары\n\n"
        "👇 Төмендегі мәзірден таңдаңыз:",
        reply_markup=kb.main_menu(),
    )


@router.message(F.text == "❓ Көмек")
async def help_cmd(message: Message):
    await message.answer(
        "<b>❓ Көмек</b>\n\n"
        "1️⃣ «💳 Тарифтер» → жазылымды таңдап, белсендіру туралы өтінім жіберіңіз.\n"
        f"2️⃣ Төлем/белсендіру: {PAYMENT_CONTACT}\n"
        "3️⃣ Тариф белсендірілген соң «📝 ҚМЖ құру» батырмасын басыңыз.\n"
        "4️⃣ Пән → сынып → тақырып таңдаңыз (немесе өз тақырыбыңызды жазыңыз).\n\n"
        "ҚМЖ дайын болған соң мәтін (және тарифке қарай Word файлы) жіберіледі.",
        reply_markup=kb.main_menu(),
    )


@router.message(F.text == "👤 Жазылымым")
async def my_subscription(message: Message):
    uid = message.from_user.id
    tier = await db.get_active_tier(uid)
    if tier is None:
        await message.answer(
            "👤 Сізде белсенді тариф жоқ.\n«💳 Тарифтер» бөлімінен таңдаңыз.",
            reply_markup=kb.main_menu(),
        )
        return
    sub = await db.get_subscription(uid)
    _, expires_at = sub
    t = TARIFFS[tier]
    if expires_at:
        exp = datetime.fromisoformat(expires_at).strftime("%d.%m.%Y")
        exp_line = f"📅 Жарамды: {exp} дейін"
    else:
        exp_line = "📅 Мерзімсіз"
    remaining = await db.remaining_quota(uid, tier)
    quota_line = "шексіз" if remaining is None else f"{remaining} ҚМЖ"
    await message.answer(
        f"👤 <b>Менің жазылымым</b>\n\n"
        f"{t['emoji']} Тариф: <b>{t['name']}</b>\n"
        f"{exp_line}\n"
        f"📊 Қалған лимит (30 күн): {quota_line}",
        reply_markup=kb.main_menu(),
    )


# ---------- Тарифы ----------

@router.message(F.text == "💳 Тарифтер")
async def tariffs(message: Message):
    cards = "\n\n".join(tariff_card(tid) for tid in TARIFFS)
    await message.answer(
        f"💳 <b>ТАРИФТЕР</b>\n\n{cards}\n\n"
        "Жазылу үшін төмендегі батырманы басыңыз 👇",
        reply_markup=kb.tariffs_kb(),
    )


@router.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery, bot: Bot):
    tier = int(call.data.split(":")[1])
    t = TARIFFS[tier]
    req_id = await db.create_request(call.from_user.id, tier)
    await call.message.answer(
        f"✅ Өтінім қабылданды: {t['emoji']} <b>{t['name']}</b> ({t['price']:,} ₸)".replace(",", " ")
        + f"\n\n💬 Төлем және белсендіру үшін байланысыңыз: {PAYMENT_CONTACT}\n"
        "Төлемнен кейін әкімші тарифті қосады.",
    )
    # уведомляем админа с кнопками
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🔔 <b>Жаңа өтінім #{req_id}</b>\n"
                f"👤 {call.from_user.full_name} (@{call.from_user.username or '—'})\n"
                f"🆔 <code>{call.from_user.id}</code>\n"
                f"💳 Тариф: {t['emoji']} {t['name']} ({t['price']:,} ₸)".replace(",", " "),
                reply_markup=kb.admin_request_kb(req_id, call.from_user.id, tier),
            )
        except Exception:
            pass
    await call.answer()


# ---------- Генерация ҚМЖ ----------

@router.message(F.text == "📝 ҚМЖ құру")
async def start_generation(message: Message, state: FSMContext):
    if await deny_if_no_access(message) is None:
        return
    await state.clear()
    await message.answer("📚 Пәнді таңдаңыз:", reply_markup=kb.subjects_kb())


@router.callback_query(F.data.startswith("subj:"))
async def choose_subject(call: CallbackQuery, state: FSMContext):
    subject = call.data.split(":")[1]
    await state.update_data(subject=subject)
    await call.message.edit_text(
        f"✅ Пән: <b>{SUBJECTS[subject]}</b>\n\nСыныпты таңдаңыз:",
        reply_markup=kb.grades_kb(subject),
    )
    await call.answer()


@router.callback_query(F.data == "back:subjects")
async def back_subjects(call: CallbackQuery):
    await call.message.edit_text("📚 Пәнді таңдаңыз:", reply_markup=kb.subjects_kb())
    await call.answer()


@router.callback_query(F.data.startswith("grade:"))
async def choose_grade(call: CallbackQuery, state: FSMContext):
    _, subject, grade = call.data.split(":")
    grade = int(grade)
    await state.update_data(subject=subject, grade=grade)
    await call.message.edit_text(
        f"✅ {SUBJECTS[subject]}, {grade}-сынып\n\nТақырыпты таңдаңыз:",
        reply_markup=kb.topics_kb(subject, grade),
    )
    await call.answer()


@router.callback_query(F.data.startswith("back:grades:"))
async def back_grades(call: CallbackQuery, state: FSMContext):
    subject = call.data.split(":")[2]
    await call.message.edit_text(
        f"✅ Пән: <b>{SUBJECTS[subject]}</b>\n\nСыныпты таңдаңыз:",
        reply_markup=kb.grades_kb(subject),
    )
    await call.answer()


@router.callback_query(F.data == "topic:custom")
async def topic_custom(call: CallbackQuery, state: FSMContext):
    await state.set_state(Gen.waiting_topic)
    await call.message.answer("✍️ Сабақтың тақырыбын жазыңыз:")
    await call.answer()


@router.callback_query(F.data.startswith("topic:"))
async def topic_picked(call: CallbackQuery, state: FSMContext, bot: Bot):
    idx = call.data.split(":")[1]
    if idx == "custom":
        return  # обработано в topic_custom
    data = await state.get_data()
    subject, grade = data.get("subject"), data.get("grade")
    topics = all_topics(subject, grade)
    try:
        topic = topics[int(idx)]
    except (ValueError, IndexError):
        await call.answer("Тақырып табылмады", show_alert=True)
        return
    await call.answer("Дайындалып жатыр…")
    await _produce(call.message, call.from_user.id, subject, grade, topic, bot)
    await state.clear()


@router.message(Gen.waiting_topic)
async def topic_typed(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    subject, grade = data.get("subject"), data.get("grade")
    topic = message.text.strip()
    if not subject or not grade:
        await state.clear()
        await message.answer("Қайтадан «📝 ҚМЖ құру» батырмасын басыңыз.", reply_markup=kb.main_menu())
        return
    await _produce(message, message.from_user.id, subject, grade, topic, bot)
    await state.clear()


async def _produce(message: Message, user_id: int, subject: str, grade: int, topic: str, bot: Bot):
    """Проверка лимита, генерация и отправка ҚМЖ."""
    tier = await db.get_active_tier(user_id)
    if tier is None:
        await message.answer("🔒 Тариф мерзімі аяқталған. «💳 Тарифтер» бөлімін қараңыз.")
        return

    remaining = await db.remaining_quota(user_id, tier)
    if remaining is not None and remaining <= 0:
        await message.answer(
            "⚠️ Айлық лимит таусылды. Жоғарырақ тарифке көтерілуге болады (💳 Тарифтер).",
            reply_markup=kb.main_menu(),
        )
        return

    await bot.send_chat_action(message.chat.id, "typing")
    depth = TARIFFS[tier]["depth"]
    result = generate(subject, grade, topic, depth)

    # текст (с разбивкой при необходимости)
    for part in split_text(result["text"]):
        await message.answer(part)

    # Word-файл для тарифов, где доступно
    if TARIFFS[tier]["docx"]:
        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.close()
        try:
            render_docx(result["data"], tmp.name)
            safe_topic = "".join(c for c in topic if c.isalnum() or c in " -_")[:40].strip()
            fname = f"QMZH_{grade}syn_{safe_topic or 'sabaq'}.docx"
            await message.answer_document(FSInputFile(tmp.name, filename=fname))
        except Exception as e:
            await message.answer(f"⚠️ Word файлын жасау кезінде қате: {e}")
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    await db.log_generation(user_id, subject, grade, topic, tier)

    remaining = await db.remaining_quota(user_id, tier)
    tail = "" if remaining is None else f"\n📊 Қалған лимит: {remaining} ҚМЖ"
    await message.answer(
        f"✅ ҚМЖ дайын! Қажет болса, өңдеп толықтырыңыз.{tail}",
        reply_markup=kb.main_menu(),
    )
