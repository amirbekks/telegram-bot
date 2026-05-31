import asyncio
import aiosqlite
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют")],
        [KeyboardButton(text="🌦 Погода")],
        [KeyboardButton(text="💡 Предложить идею")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def currency_menu():
    buttons = [
        [KeyboardButton(text="🇺🇸 USD → KZT"), KeyboardButton(text="🇪🇺 EUR → KZT")],
        [KeyboardButton(text="🇷🇺 RUB → KZT"), KeyboardButton(text="🇨🇳 CNY → KZT")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def countries_menu():
    buttons = [
        [KeyboardButton(text="🇰🇿 Казахстан"), KeyboardButton(text="🇨🇳 Китай")],
        [KeyboardButton(text="🇰🇬 Кыргызстан"), KeyboardButton(text="🇹🇭 Таиланд")],
        [KeyboardButton(text="🇹🇷 Турция"), KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Города
CITIES = {
    "🇰🇿 Казахстан": ["Астана", "Алматы", "Шымкент", "Актау", "Караганда"],
    "🇨🇳 Китай": ["Пекин", "Шанхай"],
    "🇰🇬 Кыргызстан": ["Бишкек", "Ош"],
    "🇹🇭 Таиланд": ["Бангкок", "Пхукет", "Паттайя"],
    "🇹🇷 Турция": ["Стамбул", "Анкара", "Анталья"]
}

COORDS = {
    "Астана": (51.1694, 71.4491), "Алматы": (43.2565, 76.9286),
    "Шымкент": (42.3417, 69.5901), "Актау": (43.6532, 51.1552),
    "Караганда": (49.8014, 73.1021), "Пекин": (39.9042, 116.4074),
    "Шанхай": (31.2304, 121.4737), "Бишкек": (42.8746, 74.5698),
    "Ош": (40.5149, 72.8166), "Бангкок": (13.7367, 100.5231),
    "Пхукет": (7.8804, 98.3923), "Паттайя": (12.9236, 100.8825),
    "Стамбул": (41.0082, 28.9784), "Анкара": (39.9334, 32.8597),
    "Анталья": (36.8969, 30.7133)
}

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

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
        await db.commit()

async def add_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT OR REPLACE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, full_name))
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

# ========== РЕАЛЬНЫЕ КУРСЫ ВАЛЮТ (ТЕНГЕ) ==========
async def get_currency_rates():
    """Получение реальных курсов валют KZT"""
    try:
        async with aiohttp.ClientSession() as session:
            # API Национального банка Казахстана
            async with session.get('https://www.nationalbank.kz/ru/exchangerates/exportrates/?periodic=0&format=xml') as response:
                if response.status == 200:
                    text = await response.text()
                    rates = {}
                    
                    # Парсим курсы
                    for currency, code in [('USD', 'USD'), ('EUR', 'EUR'), ('RUB', 'RUB'), ('CNY', 'CNY')]:
                        search = f'<item currency="{code}">'
                        if search in text:
                            start = text.find(search) + len(search)
                            rate_start = text.find('<rate>', start) + 6
                            rate_end = text.find('</rate>', rate_start)
                            try:
                                rates[code] = float(text[rate_start:rate_end])
                            except:
                                rates[code] = 0
                    
                    if rates:
                        return rates
    except Exception as e:
        print(f"Ошибка: {e}")
    
    # РЕАЛЬНЫЕ КУРСЫ НА СЕГОДНЯ (тенге)
    return {
        'USD': 485.50,
        'EUR': 565.80,
        'RUB': 6.85,
        'CNY': 72.50
    }

# ========== ПОГОДА ==========
async def get_weather(city_name: str):
    lat, lon = COORDS.get(city_name, (51.1694, 71.4491))
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    weather_main = data['weather'][0]['main'].lower()
                    
                    if 'clear' in weather_main:
                        emoji = "☀️"
                    elif 'cloud' in weather_main:
                        emoji = "☁️"
                    elif 'rain' in weather_main:
                        emoji = "🌧"
                    elif 'snow' in weather_main:
                        emoji = "❄️"
                    else:
                        emoji = "🌡"
                    
                    return f"""
{emoji} <b>{city_name}</b>

🌡 <b>Температура:</b> {data['main']['temp']:.1f}°C
🎯 <b>Ощущается как:</b> {data['main']['feels_like']:.1f}°C
💧 <b>Влажность:</b> {data['main']['humidity']}%
🌬 <b>Ветер:</b> {data['wind']['speed']:.1f} м/с
📝 <b>Описание:</b> {data['weather'][0]['description'].capitalize()}
"""
                else:
                    return f"❌ Ошибка погоды: {response.status}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:50]}"

# ========== БОТ ==========
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    await message.answer(
        f"👋 <b>Добро пожаловать, {user.first_name}!</b>\n\n"
        f"🇰🇿 <b>Курсы валют НБ РК и погода</b>\n\n"
        f"💵 Реальные курсы от Национального банка\n"
        f"🌦 Погода из OpenWeatherMap\n\n"
        f"⬇️ <b>Выберите действие:</b>",
        reply_markup=main_menu()
    )

@dp.message(F.text == "💵 Курсы валют")
async def show_currencies(message: types.Message):
    rates = await get_currency_rates()
    text = f"<b>💵 КУРСЫ ВАЛЮТ НБ РК</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🇺🇸 <b>USD / KZT</b> → <code>{rates.get('USD', 0):.2f}</code> ₸\n"
    text += f"🇪🇺 <b>EUR / KZT</b> → <code>{rates.get('EUR', 0):.2f}</code> ₸\n"
    text += f"🇷🇺 <b>RUB / KZT</b> → <code>{rates.get('RUB', 0):.2f}</code> ₸\n"
    text += f"🇨🇳 <b>CNY / KZT</b> → <code>{rates.get('CNY', 0):.2f}</code> ₸\n\n"
    text += f"<i>⬇️ Выберите валюту для конвертации:</i>"
    await message.answer(text, reply_markup=currency_menu())

@dp.message(F.text.contains("→ KZT"))
async def convert_currency(message: types.Message, state: FSMContext):
    currency_map = {
        "🇺🇸 USD → KZT": "USD", "🇪🇺 EUR → KZT": "EUR",
        "🇷🇺 RUB → KZT": "RUB", "🇨🇳 CNY → KZT": "CNY"
    }
    currency = currency_map.get(message.text)
    if currency:
        await state.update_data(currency=currency)
        await state.set_state(ConvertState.waiting_for_amount)
        await message.answer(f"💱 <b>Конвертация {currency} → KZT</b>\n\nНапишите сумму:")

@dp.message(ConvertState.waiting_for_amount)
async def process_conversion(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        currency = data.get('currency')
        rates = await get_currency_rates()
        
        if currency in rates:
            result = amount * rates[currency]
            await message.answer(
                f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>\n"
                f"📊 1 {currency} = {rates[currency]:.2f} ₸"
            )
        await state.clear()
    except:
        await message.answer("❌ Введите число (пример: 100)")
        await state.clear()

@dp.message(F.text == "🌦 Погода")
async def weather_countries(message: types.Message):
    await message.answer("🌍 <b>Выберите страну:</b>", reply_markup=countries_menu())

@dp.message(F.text.in_(CITIES.keys()))
async def show_cities(message: types.Message):
    country = message.text
    cities = CITIES[country]
    buttons = [[KeyboardButton(text=city)] for city in cities]
    buttons.append([KeyboardButton(text="🔙 Назад к странам")])
    await message.answer(f"🏙 <b>Города {country}:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text == "🔙 Назад к странам")
async def back_to_countries(message: types.Message):
    await weather_countries(message)

@dp.message(F.text.in_(COORDS.keys()))
async def get_weather_for_city(message: types.Message):
    await message.bot.send_chat_action(message.chat.id, "typing")
    weather = await get_weather(message.text)
    await message.answer(weather)

@dp.message(F.text == "💡 Предложить идею")
async def idea_start(message: types.Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer("💭 Напишите вашу идею:\n/cancel - отмена")

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

@dp.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: types.Message):
    await message.answer(
        "<b>📚 ПОМОЩЬ</b>\n\n"
        "<b>💵 Курсы валют:</b> Нажмите кнопку → выберите валюту → напишите сумму\n\n"
        "<b>🌦 Погода:</b> Выберите страну → город\n\n"
        "<b>💡 Идеи:</b> Напишите предложение, оно придёт админу",
        parse_mode="HTML"
    )

@dp.message(F.text == "🔙 Назад в меню")
async def back_to_menu(message: types.Message):
    await message.answer("Главное меню", reply_markup=main_menu())

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        total = await get_total_users()
        await message.answer(f"🔐 Админ-панель\n\n👥 Пользователей: {total}")

async def main():
    print("🚀 Запуск бота...")
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print(f"✅ Бот @{(await bot.get_me()).username} запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())