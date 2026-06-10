import asyncio
import aiosqlite
import aiohttp
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEATHERAPI_KEY = os.getenv('WEATHERAPI_KEY')

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class BanState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_reason = State()

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют")],
        [KeyboardButton(text="🌍 Погода")],
        [KeyboardButton(text="🔔 Уведомления")],
        [KeyboardButton(text="💡 Предложить идею")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def currency_menu():
    buttons = [
        [KeyboardButton(text="🇺🇸 USD → KZT"), KeyboardButton(text="🇪🇺 EUR → KZT")],
        [KeyboardButton(text="🇷🇺 RUB → KZT"), KeyboardButton(text="🇨🇳 CNY → KZT")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_menu():
    buttons = [
        [KeyboardButton(text="👥 Пользователи"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🚫 Забанить"), KeyboardButton(text="✅ Разбанить")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="💡 Идеи")],
        [KeyboardButton(text="🔙 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def notifications_menu():
    buttons = [
        [KeyboardButton(text="🌅 Утро 9:00"), KeyboardButton(text="🌙 Вечер 19:00")],
        [KeyboardButton(text="🔕 Отключить всё"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def weather_forecast_menu():
    buttons = [
        [KeyboardButton(text="🌡️ Сейчас"), KeyboardButton(text="📅 Почасовой прогноз")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ВСЕ СТРАНЫ И ГОРОДА ==========

COUNTRIES = {
    "🇰🇿 Казахстан": ["Астана", "Алматы", "Шымкент", "Актау", "Караганда", "Көкшетау"],
    "🇨🇳 Китай": ["Пекин", "Шанхай", "Гуанчжоу"],
    "🇰🇬 Кыргызстан": ["Бишкек", "Ош"],
    "🇹🇭 Таиланд": ["Бангкок", "Пхукет", "Паттайя"],
    "🇹🇷 Турция": ["Стамбул", "Анталья", "Анкара"],
    "🇦🇪 ОАЭ": ["Дубай", "Абу-Даби"],
}

def weather_countries_menu():
    buttons = [[KeyboardButton(text=country)] for country in COUNTRIES.keys()]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

CITY_ENGLISH = {
    "Астана": "Astana", "Алматы": "Almaty", "Шымкент": "Shymkent",
    "Актау": "Aktau", "Караганда": "Karaganda", "Көкшетау": "Kokshetau",
    "Пекин": "Beijing", "Шанхай": "Shanghai", "Гуанчжоу": "Guangzhou",
    "Бишкек": "Bishkek", "Ош": "Osh",
    "Бангкок": "Bangkok", "Пхукет": "Phuket", "Паттайя": "Pattaya",
    "Стамбул": "Istanbul", "Анталья": "Antalya", "Анкара": "Ankara",
    "Дубай": "Dubai", "Абу-Даби": "Abu Dhabi",
}

# ========== КУРСЫ ВАЛЮТ ==========

async def get_currency_rates():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.exchangerate.host/latest?base=USD') as response:
                if response.status == 200:
                    data = await response.json()
                    usd_to_kzt = 489.50
                    return {
                        'USD': usd_to_kzt,
                        'EUR': usd_to_kzt * data['rates'].get('EUR', 0.93),
                        'RUB': usd_to_kzt * data['rates'].get('RUB', 0.011),
                        'CNY': usd_to_kzt * data['rates'].get('CNY', 7.25)
                    }
    except:
        pass
    return {'USD': 489.50, 'EUR': 573.00, 'RUB': 7.15, 'CNY': 73.80}

# ========== ПОГОДА ==========

async def get_current_weather(city_name: str):
    city_en = CITY_ENGLISH.get(city_name, city_name)
    url = f"http://api.weatherapi.com/v1/current.json?key={WEATHERAPI_KEY}&q={city_en}&lang=ru"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    current = data['current']
                    return f"""
🌡️ <b>{city_name}</b> — сейчас
━━━━━━━━━━━━━━━━━━━━━
🌡️ Температура: {current['temp_c']:.1f}°C
🎯 Ощущается: {current['feelslike_c']:.1f}°C
💧 Влажность: {current['humidity']}%
🌬️ Ветер: {current['wind_kph']:.1f} км/ч
📝 {current['condition']['text']}
"""
    except:
        return f"❌ Ошибка погоды для {city_name}"

async def get_hourly_forecast(city_name: str):
    city_en = CITY_ENGLISH.get(city_name, city_name)
    url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHERAPI_KEY}&q={city_en}&hours=24&lang=ru"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    forecast = data['forecast']['forecastday'][0]['hour']
                    result = f"🌤️ <b>{city_name}</b> — почасовой прогноз\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                    for h in forecast[:12]:
                        hour = h['time'].split()[-1][:5]
                        temp = h['temp_c']
                        rain = h.get('chance_of_rain', 0)
                        result += f"<b>{hour}</b>  {temp:.1f}°C  💧{rain:.0f}%\n"
                    return result
    except:
        return f"❌ Ошибка прогноза"

# ========== БАЗА ДАННЫХ ==========

async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned BOOLEAN DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                idea_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                currency TEXT,
                amount REAL,
                result REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                user_id INTEGER PRIMARY KEY,
                morning BOOLEAN DEFAULT 0,
                evening BOOLEAN DEFAULT 0
            )
        ''')
        await db.commit()

async def add_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name, is_banned)
            VALUES (?, ?, ?, 0)
        ''', (user_id, username, full_name))
        await db.execute('''
            INSERT OR IGNORE INTO notifications (user_id, morning, evening)
            VALUES (?, 0, 0)
        ''', (user_id,))
        await db.commit()

async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] == 1 if result else False

async def get_all_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id, username, full_name, registered_at, is_banned FROM users ORDER BY registered_at DESC")
        return await cursor.fetchall()

async def ban_user(user_id: int, reason: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def unban_user(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        await db.commit()

async def save_idea(user_id: int, username: str, idea_text: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO ideas (user_id, username, idea_text)
            VALUES (?, ?, ?)
        ''', (user_id, username, idea_text))
        await db.commit()

async def get_all_ideas():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT id, username, idea_text, created_at FROM ideas ORDER BY id DESC LIMIT 20")
        return await cursor.fetchall()

async def get_total_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_banned_count():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_unbanned_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
        return [row[0] for row in await cursor.fetchall()]

async def get_notify_settings(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT morning, evening FROM notifications WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return {"morning": result[0] if result else False, "evening": result[1] if result else False}

async def update_notify(user_id: int, morning: bool = None, evening: bool = None):
    async with aiosqlite.connect("bot_database.db") as db:
        cur = await get_notify_settings(user_id)
        new_m = morning if morning is not None else cur["morning"]
        new_e = evening if evening is not None else cur["evening"]
        await db.execute("UPDATE notifications SET morning = ?, evening = ? WHERE user_id = ?", (new_m, new_e, user_id))
        await db.commit()

async def get_subscribed():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id FROM notifications WHERE morning = 1 OR evening = 1")
        return [row[0] for row in await cursor.fetchall()]

# ========== СОЗДАЕМ БОТА ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()
selected_city = {}

# ========== ЗАЩИТА ОТ БАНА (MIDDLEWARE) ==========

@dp.message()
async def check_ban(message: types.Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены!")
        return True
    return False

# ========== ОБЫЧНЫЕ КОМАНДЫ ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🇰🇿 <b>Бот помощник</b>\n\n"
        f"• Курсы валют 💵\n"
        f"• Погода 🌍\n"
        f"• Уведомления 🔔\n"
        f"• Идеи 💡\n\n"
        f"⬇️ Выберите действие:",
        reply_markup=main_menu()
    )

@dp.message(F.text == "💵 Курсы валют")
async def show_rates(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    rates = await get_currency_rates()
    text = f"<b>💵 КУРСЫ ВАЛЮТ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🇺🇸 USD: <code>{rates['USD']:.2f}</code> ₸\n"
    text += f"🇪🇺 EUR: <code>{rates['EUR']:.2f}</code> ₸\n"
    text += f"🇷🇺 RUB: <code>{rates['RUB']:.2f}</code> ₸\n"
    text += f"🇨🇳 CNY: <code>{rates['CNY']:.2f}</code> ₸\n\n"
    await message.answer(text, reply_markup=currency_menu())

@dp.message(F.text.in_(["🇺🇸 USD → KZT", "🇪🇺 EUR → KZT", "🇷🇺 RUB → KZT", "🇨🇳 CNY → KZT"]))
async def convert_start(message: types.Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        return
    m = {"🇺🇸 USD → KZT": "USD", "🇪🇺 EUR → KZT": "EUR", "🇷🇺 RUB → KZT": "RUB", "🇨🇳 CNY → KZT": "CNY"}
    await state.update_data(currency=m[message.text])
    await state.set_state(ConvertState.waiting_for_amount)
    await message.answer(f"💱 Введите сумму:")

@dp.message(ConvertState.waiting_for_amount)
async def convert_do(message: types.Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        return
    try:
        amt = float(message.text.replace(",", "."))
        data = await state.get_data()
        cur = data.get('currency')
        rates = await get_currency_rates()
        if cur in rates:
            res = amt * rates[cur]
            await message.answer(f"💱 {amt:,.2f} {cur} = {res:,.2f} ₸", reply_markup=currency_menu())
        await state.clear()
    except:
        await message.answer("❌ Введите число!", reply_markup=currency_menu())
        await state.clear()

@dp.message(F.text == "🌍 Погода")
async def weather_country(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    await message.answer("🌍 Выберите страну:", reply_markup=weather_countries_menu())

@dp.message(F.text.in_(COUNTRIES.keys()))
async def show_city_list(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    cities = COUNTRIES[message.text]
    buttons = [[KeyboardButton(text=c)] for c in cities]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer(f"🏙 Города {message.text}:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.in_(CITY_ENGLISH.keys()))
async def city_choose(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    selected_city[message.from_user.id] = message.text
    await message.answer(f"🏙️ {message.text}\n\nЧто хотите узнать?", reply_markup=weather_forecast_menu())

@dp.message(F.text == "🌡️ Сейчас")
async def get_now(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    city = selected_city.get(message.from_user.id)
    if not city:
        await message.answer("❌ Выберите город")
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    w = await get_current_weather(city)
    await message.answer(w)

@dp.message(F.text == "📅 Почасовой прогноз")
async def get_hour(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    city = selected_city.get(message.from_user.id)
    if not city:
        await message.answer("❌ Выберите город")
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    f = await get_hourly_forecast(city)
    await message.answer(f)

@dp.message(F.text == "💡 Предложить идею")
async def idea_start(message: types.Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        return
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer("💭 Напишите вашу идею:\n/cancel - отмена")

@dp.message(IdeaState.waiting_for_idea)
async def idea_save(message: types.Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())
        return
    await save_idea(message.from_user.id, message.from_user.username or "no", message.text)
    await message.answer("✅ Спасибо! Идея отправлена администратору.", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "🔔 Уведомления")
async def notify_menu(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    s = await get_notify_settings(message.from_user.id)
    await message.answer(
        f"🔔 Уведомления\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌅 Утро: {'✅' if s['morning'] else '❌'}\n"
        f"🌙 Вечер: {'✅' if s['evening'] else '❌'}\n",
        reply_markup=notifications_menu()
    )

@dp.message(F.text == "🌅 Утро 9:00")
async def enable_morn(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    await update_notify(message.from_user.id, morning=True)
    await message.answer("✅ Утренние уведомления включены!")

@dp.message(F.text == "🌙 Вечер 19:00")
async def enable_eve(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    await update_notify(message.from_user.id, evening=True)
    await message.answer("✅ Вечерние уведомления включены!")

@dp.message(F.text == "🔕 Отключить всё")
async def disable_notify(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    await update_notify(message.from_user.id, morning=False, evening=False)
    await message.answer("✅ Все уведомления отключены!")

@dp.message(F.text == "❓ Помощь")
async def help_cmd(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    await message.answer(
        "<b>📚 ПОМОЩЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>💵 Курсы:</b> Выберите валюту → напишите сумму\n"
        "<b>🌤️ Погода:</b> Страна → город\n"
        "<b>🔔 Уведомления:</b> Включите утро/вечер\n"
        "<b>💡 Идеи:</b> Напишите предложение\n\n"
        "<i>Напишите: 100 USD</i>"
    )

@dp.message(F.text == "🔙 Назад")
async def back(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

@dp.message()
async def auto_convert(message: types.Message):
    if await is_banned(message.from_user.id):
        return
    m = re.match(r'^(\d+(?:\.\d+)?)\s+([A-Z]{3})$', message.text.upper().strip())
    if m:
        amt = float(m.group(1))
        cur = m.group(2)
        rates = await get_currency_rates()
        if cur in rates:
            res = amt * rates[cur]
            await message.answer(f"💱 {amt:,.2f} {cur} = {res:,.2f} ₸")

# ========== АДМИН КОМАНДЫ ==========

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    await message.answer("🔐 <b>АДМИН-ПАНЕЛЬ</b>\nВыберите действие:", reply_markup=admin_menu())

@dp.message(F.text == "👥 Пользователи")
async def list_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    total = await get_total_users()
    banned = await get_banned_count()
    text = f"👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n✅ Активных: {total}\n🚫 Забаненных: {banned}\n📊 Всего: {len(users)}\n\n"
    for u in users[:15]:
        uid, uname, fname, reg, banned_flag = u
        status = "🚫" if banned_flag else "✅"
        text += f"{status} <code>{uid}</code> | {fname}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📊 Статистика")
async def stats_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    total = await get_total_users()
    banned = await get_banned_count()
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM ideas")
        ideas = (await cursor.fetchone())[0]
    await message.answer(
        f"📊 <b>СТАТИСТИКА</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Пользователей: {total}\n"
        f"🚫 Забанено: {banned}\n"
        f"💡 Идей: {ideas}"
    )

@dp.message(F.text == "🚫 Забанить")
async def ban_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BanState.waiting_for_user_id)
    await message.answer("🚫 Введите ID пользователя:")

@dp.message(BanState.waiting_for_user_id)
async def ban_get_id(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text)
        await state.update_data(user_id=uid)
        await state.set_state(BanState.waiting_for_reason)
        await message.answer("📝 Причина бана:")
    except:
        await message.answer("❌ Неверный ID!")

@dp.message(BanState.waiting_for_reason)
async def ban_do(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    uid = data.get('user_id')
    reason = message.text
    await ban_user(uid, reason)
    try:
        await bot.send_message(uid, f"🚫 Вы забанены!\nПричина: {reason}")
    except:
        pass
    await message.answer(f"✅ Пользователь {uid} ЗАБАНЕН!")
    await state.clear()

@dp.message(F.text == "✅ Разбанить")
async def unban_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🚫 Введите ID пользователя для разбана:")
    
    @dp.message()
    async def unban_do(msg: types.Message):
        if msg.from_user.id != ADMIN_ID:
            return
        try:
            uid = int(msg.text)
            await unban_user(uid)
            try:
                await bot.send_message(uid, "✅ Вы разбанены!")
            except:
                pass
            await msg.answer(f"✅ Пользователь {uid} РАЗБАНЕН!")
            dp.message.handlers.remove(unban_do)
        except:
            await msg.answer("❌ Неверный ID!")

@dp.message(F.text == "📢 Рассылка")
async def broadcast_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 Введите текст для рассылки:")
    
    @dp.message()
    async def broadcast_send(msg: types.Message):
        if msg.from_user.id != ADMIN_ID:
            return
        users = await get_unbanned_users()
        ok = 0
        for uid in users:
            try:
                await bot.send_message(uid, f"📢 РАССЫЛКА\n\n{msg.text}")
                ok += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await msg.answer(f"✅ Отправлено: {ok} пользователям")
        dp.message.handlers.remove(broadcast_send)

@dp.message(F.text == "💡 Идеи")
async def ideas_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    ideas = await get_all_ideas()
    if not ideas:
        await message.answer("📭 Нет идей")
        return
    text = "💡 <b>ИДЕИ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for idea in ideas:
        text += f"👤 @{idea[1] or 'anon'}\n📝 {idea[2][:100]}\n🕐 {idea[3][:16]}\n━━━━━━━━━\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔙 Главное меню")
async def back_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

# ========== РАССЫЛКА УВЕДОМЛЕНИЙ ==========

async def send_morning():
    users = await get_subscribed()
    rates = await get_currency_rates()
    text = f"🌅 Доброе утро!\n\n💰 Курсы:\n" + "\n".join([f"{k}: {v:.2f} ₸" for k, v in rates.items()])
    for uid in users:
        if not await is_banned(uid):
            try:
                await bot.send_message(uid, text)
            except:
                pass

async def send_evening():
    users = await get_subscribed()
    rates = await get_currency_rates()
    text = f"🌙 Вечерний дайджест\n\n💰 Курсы:\n" + "\n".join([f"{k}: {v:.2f} ₸" for k, v in rates.items()])
    for uid in users:
        if not await is_banned(uid):
            try:
                await bot.send_message(uid, text)
            except:
                pass

async def update_rates_job():
    await get_currency_rates()
    print(f"✅ Курсы обновлены {datetime.now().strftime('%H:%M:%S')}")

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота с админ-панелью...")
    await init_db()
    print("✅ База данных готова")
    
    scheduler.add_job(update_rates_job, 'interval', hours=1)
    scheduler.add_job(send_morning, 'cron', hour=9, minute=0)
    scheduler.add_job(send_evening, 'cron', hour=19, minute=0)
    scheduler.start()
    print("✅ Планировщик запущен")
    
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print("🔐 Админ-панель: /admin")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())