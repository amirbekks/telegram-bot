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
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют")],
        [KeyboardButton(text="🌍 Погода")],
        [KeyboardButton(text="🔔 Уведомления")],
        [KeyboardButton(text="💡 Идея")],
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

def notifications_menu():
    buttons = [
        [KeyboardButton(text="🌅 Включить утренние"), KeyboardButton(text="🌙 Включить вечерние")],
        [KeyboardButton(text="🔕 Отключить всё"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def weather_countries_menu():
    buttons = [
        [KeyboardButton(text="🇰🇿 Казахстан"), KeyboardButton(text="🇨🇳 Китай")],
        [KeyboardButton(text="🇹🇭 Таиланд"), KeyboardButton(text="🇹🇷 Турция")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ГОРОДА ==========

COUNTRIES = {
    "🇰🇿 Казахстан": ["Астана", "Алматы", "Шымкент"],
    "🇨🇳 Китай": ["Пекин", "Шанхай"],
    "🇹🇭 Таиланд": ["Бангкок", "Пхукет"],
    "🇹🇷 Турция": ["Стамбул", "Анталья"]
}

COORDS = {
    "Астана": (51.1694, 71.4491), "Алматы": (43.2565, 76.9286),
    "Шымкент": (42.3417, 69.5901), "Пекин": (39.9042, 116.4074),
    "Шанхай": (31.2304, 121.4737), "Бангкок": (13.7367, 100.5231),
    "Пхукет": (7.8804, 98.3923), "Стамбул": (41.0082, 28.9784),
    "Анталья": (36.8969, 30.7133)
}

# ========== БАЗА ДАННЫХ ==========

async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            INSERT OR REPLACE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, full_name))
        await db.execute('''
            INSERT OR IGNORE INTO notifications (user_id, morning, evening)
            VALUES (?, 0, 0)
        ''', (user_id,))
        await db.commit()

async def save_history(user_id: int, currency: str, amount: float, result: float):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO history (user_id, currency, amount, result)
            VALUES (?, ?, ?, ?)
        ''', (user_id, currency, amount, result))
        await db.commit()

async def save_idea(user_id: int, username: str, idea_text: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO ideas (user_id, username, idea_text)
            VALUES (?, ?, ?)
        ''', (user_id, username, idea_text))
        await db.commit()

async def get_total_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        result = await cursor.fetchone()
        return result[0] if result else 0

# ========== УВЕДОМЛЕНИЯ ==========

async def get_notification_settings(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT morning, evening FROM notifications WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return {"morning": result[0] if result else False, "evening": result[1] if result else False}

async def update_notifications(user_id: int, morning: bool = None, evening: bool = None):
    async with aiosqlite.connect("bot_database.db") as db:
        current = await get_notification_settings(user_id)
        new_morning = morning if morning is not None else current["morning"]
        new_evening = evening if evening is not None else current["evening"]
        await db.execute('''
            UPDATE notifications SET morning = ?, evening = ? WHERE user_id = ?
        ''', (new_morning, new_evening, user_id))
        await db.commit()

async def get_all_subscribed():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id FROM notifications WHERE morning = 1 OR evening = 1")
        return [row[0] for row in await cursor.fetchall()]

# ========== КУРСЫ ВАЛЮТ ==========

async def get_currency_rates():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://www.nationalbank.kz/ru/exchangerates/exportrates/?periodic=0&format=xml') as response:
                if response.status == 200:
                    text = await response.text()
                    rates = {}
                    for code in ['USD', 'EUR', 'RUB', 'CNY']:
                        search = f'<item currency="{code}">'
                        if search in text:
                            start = text.find(search) + len(search)
                            rate_start = text.find('<rate>', start) + 6
                            rate_end = text.find('</rate>', rate_start)
                            try:
                                rates[code] = float(text[rate_start:rate_end])
                            except:
                                rates[code] = 0
                    if rates.get('USD'):
                        return rates
    except:
        pass
    return {'USD': 485.50, 'EUR': 565.80, 'RUB': 6.85, 'CNY': 72.50}

# ========== ПОГОДА ==========

async def get_weather(city_name: str):
    lat, lon = COORDS.get(city_name, (51.1694, 71.4491))
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    emoji = "☀️" if 'clear' in data['weather'][0]['main'].lower() else "☁️"
                    return f"{emoji} {city_name}: {data['main']['temp']:.1f}°C, {data['weather'][0]['description']}"
    except:
        pass
    return None

# ========== РАССЫЛКА ==========

async def send_morning():
    print("🌅 Отправка утренних уведомлений...")
    users = await get_all_subscribed()
    rates = await get_currency_rates()
    
    text = f"🌅 <b>Доброе утро!</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"<b>💰 Курсы валют:</b>\n"
    text += f"🇺🇸 USD: {rates['USD']:.2f} ₸\n"
    text += f"🇪🇺 EUR: {rates['EUR']:.2f} ₸\n"
    text += f"🇷🇺 RUB: {rates['RUB']:.2f} ₸\n"
    text += f"🇨🇳 CNY: {rates['CNY']:.2f} ₸\n"
    text += f"\n<i>Хорошего дня!</i>"
    
    for user_id in users:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            print(f"✅ Отправлено {user_id}")
        except:
            print(f"❌ Ошибка {user_id}")
    print("🌅 Утренняя рассылка завершена")

async def send_evening():
    print("🌙 Отправка вечерних уведомлений...")
    users = await get_all_subscribed()
    rates = await get_currency_rates()
    
    text = f"🌙 <b>Вечерний дайджест</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"<b>💰 Курсы валют:</b>\n"
    text += f"🇺🇸 USD: {rates['USD']:.2f} ₸\n"
    text += f"🇪🇺 EUR: {rates['EUR']:.2f} ₸\n"
    text += f"🇷🇺 RUB: {rates['RUB']:.2f} ₸\n"
    text += f"🇨🇳 CNY: {rates['CNY']:.2f} ₸\n"
    text += f"\n<i>Спокойной ночи!</i>"
    
    for user_id in users:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            print(f"✅ Отправлено {user_id}")
        except:
            print(f"❌ Ошибка {user_id}")
    print("🌙 Вечерняя рассылка завершена")

# ========== БОТ ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ========== КОМАНДЫ ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🇰🇿 <b>Мой бот поможет:</b>\n"
        f"• Узнать курс валют 💵\n"
        f"• Посмотреть погоду 🌍\n"
        f"• Настроить уведомления 🔔\n"
        f"• Отправить идею 💡\n\n"
        f"⬇️ <b>Выберите действие:</b>",
        reply_markup=main_menu()
    )

@dp.message(F.text == "💵 Курсы валют")
async def show_currencies(message: types.Message):
    rates = await get_currency_rates()
    text = f"<b>💵 Курсы валют НБ РК</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🇺🇸 USD / KZT → {rates['USD']:.2f} ₸\n"
    text += f"🇪🇺 EUR / KZT → {rates['EUR']:.2f} ₸\n"
    text += f"🇷🇺 RUB / KZT → {rates['RUB']:.2f} ₸\n"
    text += f"🇨🇳 CNY / KZT → {rates['CNY']:.2f} ₸\n\n"
    text += f"<i>Нажмите на валюту для конвертации</i>"
    await message.answer(text, reply_markup=currency_menu())

@dp.message(F.text.in_(["🇺🇸 USD → KZT", "🇪🇺 EUR → KZT", "🇷🇺 RUB → KZT", "🇨🇳 CNY → KZT"]))
async def convert_start(message: types.Message, state: FSMContext):
    currency_map = {
        "🇺🇸 USD → KZT": "USD", "🇪🇺 EUR → KZT": "EUR",
        "🇷🇺 RUB → KZT": "RUB", "🇨🇳 CNY → KZT": "CNY"
    }
    currency = currency_map[message.text]
    await state.update_data(currency=currency)
    await state.set_state(ConvertState.waiting_for_amount)
    await message.answer(f"💱 <b>Конвертация {currency} → KZT</b>\n\nВведите сумму:")

@dp.message(ConvertState.waiting_for_amount)
async def convert_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        currency = data.get('currency')
        rates = await get_currency_rates()
        
        if currency in rates:
            result = amount * rates[currency]
            await save_history(message.from_user.id, currency, amount, result)
            await message.answer(
                f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>",
                reply_markup=currency_menu()
            )
        await state.clear()
    except:
        await message.answer("❌ Введите число!", reply_markup=currency_menu())
        await state.clear()

@dp.message(F.text == "🌍 Погода")
async def weather_countries(message: types.Message):
    await message.answer("🌍 <b>Выберите страну:</b>", reply_markup=weather_countries_menu())

@dp.message(F.text.in_(COUNTRIES.keys()))
async def show_cities(message: types.Message):
    country = message.text
    cities = COUNTRIES[country]
    buttons = [[KeyboardButton(text=city)] for city in cities]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer(f"🏙 <b>Города {country}:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.in_(COORDS.keys()))
async def get_weather_city(message: types.Message):
    await message.bot.send_chat_action(message.chat.id, "typing")
    weather = await get_weather(message.text)
    await message.answer(weather if weather else "❌ Ошибка погоды")

@dp.message(F.text == "🔔 Уведомления")
async def notifications_menu_handler(message: types.Message):
    settings = await get_notification_settings(message.from_user.id)
    morning = "✅ Вкл" if settings["morning"] else "❌ Выкл"
    evening = "✅ Вкл" if settings["evening"] else "❌ Выкл"
    await message.answer(
        f"🔔 <b>Уведомления</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌅 Утро (9:00): {morning}\n"
        f"🌙 Вечер (19:00): {evening}\n\n"
        f"<i>Выберите действие:</i>",
        reply_markup=notifications_menu()
    )

@dp.message(F.text == "🌅 Включить утренние")
async def enable_morning(message: types.Message):
    await update_notifications(message.from_user.id, morning=True)
    await message.answer("✅ Утренние уведомления ВКЛЮЧЕНЫ! (в 9:00)")

@dp.message(F.text == "🌙 Включить вечерние")
async def enable_evening(message: types.Message):
    await update_notifications(message.from_user.id, evening=True)
    await message.answer("✅ Вечерние уведомления ВКЛЮЧЕНЫ! (в 19:00)")

@dp.message(F.text == "🔕 Отключить всё")
async def disable_all(message: types.Message):
    await update_notifications(message.from_user.id, morning=False, evening=False)
    await message.answer("✅ Все уведомления ОТКЛЮЧЕНЫ!")

@dp.message(F.text == "💡 Идея")
async def idea_start(message: types.Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer("💭 Напишите вашу идею:\n\n/cancel - отмена")

@dp.message(IdeaState.waiting_for_idea)
async def idea_save(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())
        return
    user = message.from_user
    await save_idea(user.id, user.username or "no_username", message.text)
    try:
        await bot.send_message(ADMIN_ID, f"📝 НОВАЯ ИДЕЯ!\n\nОт: {user.full_name}\nID: {user.id}\n\n{message.text}")
        await message.answer("✅ Спасибо! Идея отправлена.", reply_markup=main_menu())
    except:
        await message.answer("✅ Спасибо! Идея сохранена.", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    await message.answer(
        "<b>📚 ПОМОЩЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>💵 Курсы валют:</b>\n"
        "• Выберите валюту → напишите сумму\n\n"
        "<b>🌍 Погода:</b>\n"
        "• Выберите страну → город\n\n"
        "<b>🔔 Уведомления:</b>\n"
        "• Включите утренние (9:00) и/или вечерние (19:00)\n"
        "• Каждый день будет приходить курс валют\n\n"
        "<b>💡 Идея:</b>\n"
        "• Напишите предложение\n\n"
        "<i>Также можно написать: 100 USD</i>"
    )

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

@dp.message()
async def auto_convert(message: types.Message):
    match = re.match(r'^(\d+(?:\.\d+)?)\s+([A-Z]{3})$', message.text.upper().strip())
    if match:
        amount = float(match.group(1))
        currency = match.group(2)
        rates = await get_currency_rates()
        if currency in rates:
            result = amount * rates[currency]
            await save_history(message.from_user.id, currency, amount, result)
            await message.answer(f"💱 {amount:,.2f} {currency} = {result:,.2f} ₸")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    total = await get_total_users()
    await message.answer(f"🔐 Админ-панель\n\n👥 Пользователей: {total}")

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота...")
    await init_db()
    print("✅ База данных готова")
    
    # Запускаем планировщик
    scheduler.add_job(send_morning, 'cron', hour=9, minute=0, id='morning')
    scheduler.add_job(send_evening, 'cron', hour=19, minute=0, id='evening')
    scheduler.start()
    print("✅ Планировщик запущен (9:00 и 19:00)")
    
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())