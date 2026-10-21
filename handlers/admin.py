"""Админ-панель: статистика, выдача доступа, заявки, рассылка.

Управление через команды (надёжнее, чем вложенные хендлеры):
  /admin                     — панель + статистика
  /users                     — последние пользователи
  /requests                  — заявки в ожидании
  /grant <user_id> <tier> [days]  — выдать тариф (days=0 → бессрочно)
  /revoke <user_id>          — снять доступ
  /broadcast                 — рассылка всем
"""

import asyncio

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import database as db
from config import ADMIN_ID, TARIFFS


router = Router()


class AdminState(StatesGroup):
    broadcast = State()


def is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"⛔ Тек әкімшіге. Сіздің ID: <code>{message.from_user.id}</code>")
        return
    s = await db.stats()
    by_tier = ", ".join(
        f"{TARIFFS[t]['name']}:{c}" for t, c in s["by_tier"].items()
    ) or "—"
    await message.answer(
        "🔐 <b>ӘКІМШІ ПАНЕЛІ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Қолданушылар: {s['total_users']}\n"
        f"💳 Белсенді жазылым: {s['active_subs']} ({by_tier})\n"
        f"📝 Жасалған ҚМЖ: {s['total_gen']}\n"
        f"🔔 Жаңа өтінімдер: {s['pending']}\n\n"
        "<b>Командалар:</b>\n"
        "/users — соңғы қолданушылар\n"
        "/requests — өтінімдер\n"
        "/grant <code>user_id tier [days]</code> — тариф беру (days=0 → мерзімсіз)\n"
        "/revoke <code>user_id</code> — доступты алу\n"
        "/broadcast — барлығына хабарлама"
    )


@router.message(Command("users"))
async def users_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    rows = await db.list_users(30)
    if not rows:
        await message.answer("📭 Қолданушы жоқ.")
        return
    text = "👥 <b>ҚОЛДАНУШЫЛАР</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for uid, uname, fname, created, tier, expires in rows:
        tariff = TARIFFS[tier]["name"] if tier else "жоқ"
        text += (
            f"\n🆔 <code>{uid}</code> — {fname or '—'} (@{uname or '—'})\n"
            f"   💳 {tariff}"
        )
    await message.answer(text)


@router.message(Command("requests"))
async def requests_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    rows = await db.pending_requests()
    if not rows:
        await message.answer("📭 Жаңа өтінім жоқ.")
        return
    text = "🔔 <b>ӨТІНІМДЕР</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for rid, uid, tier, created, uname, fname in rows:
        text += (
            f"\n#{rid} — {fname or '—'} (@{uname or '—'})\n"
            f"   🆔 <code>{uid}</code> | 💳 {TARIFFS[tier]['name']}\n"
            f"   Беру: /grant {uid} {tier} 30"
        )
    await message.answer(text)


@router.message(Command("grant"))
async def grant_cmd(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Қолданылуы: /grant <code>user_id tier [days]</code>\nМысалы: /grant 123456 2 30")
        return
    try:
        uid = int(parts[1])
        tier = int(parts[2])
        days = int(parts[3]) if len(parts) > 3 else 30
    except ValueError:
        await message.answer("❌ Параметрлер сан болуы керек.")
        return
    if tier not in TARIFFS:
        await message.answer(f"❌ Тариф 1–{max(TARIFFS)} аралығында болуы керек.")
        return
    await db.grant_subscription(uid, tier, None if days == 0 else days)
    t = TARIFFS[tier]
    period = "мерзімсіз" if days == 0 else f"{days} күн"
    await message.answer(f"✅ {uid} → {t['emoji']} {t['name']} ({period}) берілді.")
    try:
        await bot.send_message(
            uid,
            f"🎉 Тарифіңіз белсендірілді: {t['emoji']} <b>{t['name']}</b> ({period}).\n"
            "«📝 ҚМЖ құру» батырмасын басып, бастаңыз!",
        )
    except Exception:
        await message.answer("(Қолданушыға хабарлама жеткізілмеді.)")


@router.message(Command("revoke"))
async def revoke_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Қолданылуы: /revoke <code>user_id</code>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("❌ user_id сан болуы керек.")
        return
    await db.revoke_subscription(uid)
    await message.answer(f"✅ {uid} доступы алынды.")


@router.message(Command("broadcast"))
async def broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminState.broadcast)
    await message.answer("📢 Таратылатын хабарламаны жіберіңіз.\n/cancel — болдырмау")


@router.message(AdminState.broadcast)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Болдырылмады.")
        return
    await state.clear()
    user_ids = await db.get_all_user_ids()
    sent = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, f"📢 <b>Хабарлама</b>\n\n{message.html_text}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Жіберілді: {sent}/{len(user_ids)}")


# ---------- Callback: одобрение/отклонение заявок ----------

@router.callback_query(F.data.startswith("appr:"))
async def approve(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, rid, uid, tier = call.data.split(":")
    rid, uid, tier = int(rid), int(uid), int(tier)
    await db.grant_subscription(uid, tier, TARIFFS[tier]["days"])
    await db.set_request_status(rid, "done")
    t = TARIFFS[tier]
    await call.message.edit_text(
        call.message.html_text + f"\n\n✅ <b>Белсендірілді</b> ({t['name']}, {t['days']} күн)"
    )
    try:
        await bot.send_message(
            uid,
            f"🎉 Тарифіңіз белсендірілді: {t['emoji']} <b>{t['name']}</b> ({t['days']} күн).\n"
            "«📝 ҚМЖ құру» батырмасын басып, бастаңыз!",
        )
    except Exception:
        pass
    await call.answer("Белсендірілді")


@router.callback_query(F.data.startswith("rej:"))
async def reject(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    _, rid, uid = call.data.split(":")
    await db.set_request_status(int(rid), "rejected")
    await call.message.edit_text(call.message.html_text + "\n\n❌ <b>Бас тартылды</b>")
    await call.answer("Бас тартылды")
