import asyncio
import aiosqlite
import aiohttp
import re
import random
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

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class GameState(StatesGroup):
    buying = State()
    selling = State()

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют")],
        [KeyboardButton(text="🌍 Погода"), KeyboardButton(text="🎮 Игра")],
        [KeyboardButton(text="💡 Идея"), KeyboardButton(text="📊 Профиль")],
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

def weather_countries_menu():
    buttons = [
        [KeyboardButton(text="🇰🇿 Казахстан"), KeyboardButton(text="🇨🇳 Китай")],
        [KeyboardButton(text="🇰🇬 Кыргызстан"), KeyboardButton(text="🇹🇭 Таиланд")],
        [KeyboardButton(text="🇹🇷 Турция"), KeyboardButton(text="🇦🇪 ОАЭ")],
        [KeyboardButton(text="🇪🇬 Египет"), KeyboardButton(text="🇮🇳 Индия")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def game_menu():
    buttons = [
        [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📈 Курсы")],
        [KeyboardButton(text="🛒 Купить"), KeyboardButton(text="💸 Продать")],
        [KeyboardButton(text="📊 Портфель"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ВСЕ ГОРОДА ПО СТРАНАМ ==========

COUNTRIES = {
    "🇰🇿 Казахстан": ["Астана", "Алматы", "Шымкент", "Актау", "Караганда", "Уральск"],
    "🇨🇳 Китай": ["Пекин", "Шанхай", "Гуанчжоу", "Сиань", "Чэнду"],
    "🇰🇬 Кыргызстан": ["Бишкек", "Ош", "Джалал-Абад", "Каракол", "Токмок"],
    "🇹🇭 Таиланд": ["Бангкок", "Пхукет", "Паттайя", "Чиангмай", "Краби", "Самуи"],
    "🇹🇷 Турция": ["Стамбул", "Анкара", "Анталья", "Измир", "Бодрум", "Каппадокия"],
    "🇦🇪 ОАЭ": ["Дубай", "Абу-Даби", "Шарджа", "Рас-эль-Хайма"],
    "🇪🇬 Египет": ["Каир", "Хургада", "Шарм-эль-Шейх", "Луксор"],
    "🇮🇳 Индия": ["Дели", "Гоа", "Мумбаи", "Джайпур", "Агра"]
}

# КООРДИНАТЫ ВСЕХ ГОРОДОВ
COORDS = {
    # Казахстан
    "Астана": (51.1694, 71.4491), "Алматы": (43.2565, 76.9286),
    "Шымкент": (42.3417, 69.5901), "Актау": (43.6532, 51.1552),
    "Караганда": (49.8014, 73.1021), "Уральск": (51.2167, 51.3667),
    # Китай
    "Пекин": (39.9042, 116.4074), "Шанхай": (31.2304, 121.4737),
    "Гуанчжоу": (23.1291, 113.2644), "Сиань": (34.3416, 108.9402), "Чэнду": (30.5728, 104.0668),
    # Кыргызстан
    "Бишкек": (42.8746, 74.5698), "Ош": (40.5149, 72.8166),
    "Джалал-Абад": (40.9334, 73.0027), "Каракол": (42.4907, 78.3936), "Токмок": (42.8373, 75.2930),
    # Таиланд
    "Бангкок": (13.7367, 100.5231), "Пхукет": (7.8804, 98.3923),
    "Паттайя": (12.9236, 100.8825), "Чиангмай": (18.7883, 98.9853),
    "Краби": (8.0863, 98.9069), "Самуи": (9.5120, 100.0136),
    # Турция
    "Стамбул": (41.0082, 28.9784), "Анкара": (39.9334, 32.8597),
    "Анталья": (36.8969, 30.7133), "Измир": (38.4192, 27.1287),
    "Бодрум": (37.0344, 27.4305), "Каппадокия": (38.6435, 34.8289),
    # ОАЭ
    "Дубай": (25.2048, 55.2708), "Абу-Даби": (24.4539, 54.3773),
    "Шарджа": (25.3463, 55.4209), "Рас-эль-Хайма": (25.7895, 55.9432),
    # Египет
    "Каир": (30.0444, 31.2357), "Хургада": (27.2574, 33.8128),
    "Шарм-эль-Шейх": (27.9158, 34.33), "Луксор": (25.6809, 32.6394),
    # Индия
    "Дели": (28.6139, 77.2090), "Гоа": (15.2993, 74.1240),
    "Мумбаи": (19.0760, 72.8777), "Джайпур": (26.9124, 75.7873), "Агра": (27.1767, 78.0081)
}

# ========== БАЗА ДАННЫХ ==========

async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                game_balance INTEGER DEFAULT 10000
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
            CREATE TABLE IF NOT EXISTS portfolio (
                user_id INTEGER,
                currency TEXT,
                amount REAL,
                PRIMARY KEY (user_id, currency)
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

async def save_history(user_id: int, currency: str, amount: float, result: float):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO history (user_id, currency, amount, result)
            VALUES (?, ?, ?, ?)
        ''', (user_id, currency, amount, result))
        await db.commit()

async def get_history(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT currency, amount, result, created_at 
            FROM history 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
        ''', (user_id,))
        return await cursor.fetchall()

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

# ========== ИГРОВЫЕ ФУНКЦИИ ==========

async def get_game_balance(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT game_balance FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 10000

async def update_game_balance(user_id: int, amount: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET game_balance = game_balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def buy_currency_game(user_id: int, currency: str, amount: float, price: float):
    total_cost = int(amount * price)
    balance = await get_game_balance(user_id)
    
    if balance < total_cost:
        return False, f"❌ Не хватает! Нужно {total_cost} ₸, у вас {balance} ₸"
    
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO portfolio (user_id, currency, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, currency) DO UPDATE SET
            amount = amount + ?
        ''', (user_id, currency, amount, amount))
        await db.execute("UPDATE users SET game_balance = game_balance - ? WHERE user_id = ?", (total_cost, user_id))
        await db.commit()
    
    return True, f"✅ Куплено {amount} {currency} за {total_cost} ₸"

async def sell_currency_game(user_id: int, currency: str, amount: float, price: float):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT amount FROM portfolio WHERE user_id = ? AND currency = ?", (user_id, currency))
        result = await cursor.fetchone()
        
        if not result or result[0] < amount:
            return False, f"❌ У вас нет столько {currency}! Есть: {result[0] if result else 0}"
        
        total_income = int(amount * price)
        await db.execute("UPDATE portfolio SET amount = amount - ? WHERE user_id = ? AND currency = ?", (amount, user_id, currency))
        await db.execute("UPDATE users SET game_balance = game_balance + ? WHERE user_id = ?", (total_income, user_id))
        await db.commit()
    
    return True, f"✅ Продано {amount} {currency} за {total_income} ₸"

async def get_portfolio(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT currency, amount FROM portfolio WHERE user_id = ? AND amount > 0", (user_id,))
        return await cursor.fetchall()

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

🌡 Температура: {data['main']['temp']:.1f}°C
🎯 Ощущается: {data['main']['feels_like']:.1f}°C
💧 Влажность: {data['main']['humidity']}%
🌬 Ветер: {data['wind']['speed']:.1f} м/с
📝 {data['weather'][0]['description'].capitalize()}
"""
                else:
                    return f"❌ Ошибка погоды для {city_name}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:50]}"

# ========== БОТ ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== СТАРТ ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🇰🇿 <b>Мой бот поможет:</b>\n"
        f"• Узнать курс валют 💵\n"
        f"• Конвертировать деньги 💱\n"
        f"• Посмотреть погоду в 40+ городах 🌍\n"
        f"• Поиграть в экономическую игру 🎮\n"
        f"• Отправить идею 💡\n\n"
        f"⬇️ <b>Выберите действие:</b>",
        reply_markup=main_menu()
    )

# ========== КУРСЫ ВАЛЮТ ==========

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
        "🇺🇸 USD → KZT": "USD",
        "🇪🇺 EUR → KZT": "EUR", 
        "🇷🇺 RUB → KZT": "RUB",
        "🇨🇳 CNY → KZT": "CNY"
    }
    currency = currency_map[message.text]
    await state.update_data(currency=currency)
    await state.set_state(ConvertState.waiting_for_amount)
    await message.answer(f"💱 <b>Конвертация {currency} → KZT</b>\n\nВведите сумму (например: 100):")

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
                f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>\n"
                f"📊 Курс: 1 {currency} = {rates[currency]:.2f} ₸",
                reply_markup=currency_menu()
            )
        else:
            await message.answer("❌ Ошибка курса", reply_markup=currency_menu())
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число! Например: 100", reply_markup=currency_menu())

# ========== ПОГОДА (ВСЕ СТРАНЫ И ГОРОДА) ==========

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
    city = message.text
    await message.bot.send_chat_action(message.chat.id, "typing")
    weather = await get_weather(city)
    await message.answer(weather)

# ========== ЭКОНОМИЧЕСКАЯ ИГРА ==========

@dp.message(F.text == "🎮 Игра")
async def game_menu_handler(message: types.Message):
    balance = await get_game_balance(message.from_user.id)
    text = f"""
🎮 <b>ЭКОНОМИЧЕСКАЯ ИГРА</b>
━━━━━━━━━━━━━━━━━━━━━

💰 Ваш баланс: {balance} ₸

<b>Как играть:</b>
• Следите за курсами валют
• Покупайте дёшево, продавайте дорого
• Зарабатывайте на разнице курсов

<b>Доступные валюты:</b>
🇺🇸 USD, 🇪🇺 EUR, 🇷🇺 RUB, 🇨🇳 CNY
"""
    await message.answer(text, reply_markup=game_menu())

@dp.message(F.text == "💰 Баланс")
async def game_balance(message: types.Message):
    balance = await get_game_balance(message.from_user.id)
    await message.answer(f"💰 <b>Ваш игровой баланс:</b> {balance} ₸")

@dp.message(F.text == "📈 Курсы")
async def game_rates(message: types.Message):
    rates = await get_currency_rates()
    text = f"<b>📈 Текущие курсы в игре:</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🇺🇸 USD: {rates['USD']:.2f} ₸\n"
    text += f"🇪🇺 EUR: {rates['EUR']:.2f} ₸\n"
    text += f"🇷🇺 RUB: {rates['RUB']:.2f} ₸\n"
    text += f"🇨🇳 CNY: {rates['CNY']:.2f} ₸\n\n"
    text += f"<i>Используйте кнопки Купить/Продать</i>"
    await message.answer(text)

@dp.message(F.text == "🛒 Купить")
async def game_buy_start(message: types.Message, state: FSMContext):
    await state.set_state(GameState.buying)
    await message.answer(
        "🛒 <b>Покупка валюты</b>\n\n"
        "Напишите в формате: <code>USD 100</code>\n"
        "Пример: USD 50\n\n"
        "<i>/cancel - отмена</i>"
    )

@dp.message(GameState.buying)
async def game_buy(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=game_menu())
        return
    
    parts = message.text.upper().split()
    if len(parts) != 2:
        await message.answer("❌ Неверный формат! Используйте: USD 100")
        return
    
    currency = parts[0]
    try:
        amount = float(parts[1])
    except:
        await message.answer("❌ Введите число!")
        return
    
    rates = await get_currency_rates()
    if currency not in rates:
        await message.answer(f"❌ Неизвестная валюта. Доступны: USD, EUR, RUB, CNY")
        return
    
    result, msg = await buy_currency_game(message.from_user.id, currency, amount, rates[currency])
    await message.answer(msg)
    await state.clear()

@dp.message(F.text == "💸 Продать")
async def game_sell_start(message: types.Message, state: FSMContext):
    await state.set_state(GameState.selling)
    await message.answer(
        "💸 <b>Продажа валюты</b>\n\n"
        "Напишите в формате: <code>USD 100</code>\n"
        "Пример: USD 50\n\n"
        "<i>/cancel - отмена</i>"
    )

@dp.message(GameState.selling)
async def game_sell(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=game_menu())
        return
    
    parts = message.text.upper().split()
    if len(parts) != 2:
        await message.answer("❌ Неверный формат! Используйте: USD 100")
        return
    
    currency = parts[0]
    try:
        amount = float(parts[1])
    except:
        await message.answer("❌ Введите число!")
        return
    
    rates = await get_currency_rates()
    if currency not in rates:
        await message.answer(f"❌ Неизвестная валюта. Доступны: USD, EUR, RUB, CNY")
        return
    
    result, msg = await sell_currency_game(message.from_user.id, currency, amount, rates[currency])
    await message.answer(msg)
    await state.clear()

@dp.message(F.text == "📊 Портфель")
async def game_portfolio(message: types.Message):
    portfolio = await get_portfolio(message.from_user.id)
    balance = await get_game_balance(message.from_user.id)
    
    if not portfolio:
        await message.answer(f"📊 <b>Ваш портфель пуст</b>\n\n💰 Баланс: {balance} ₸")
        return
    
    text = f"📊 <b>ВАШ ПОРТФЕЛЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for curr, amt in portfolio:
        text += f"• {curr}: {amt:.2f}\n"
    text += f"\n💰 Баланс: {balance} ₸"
    await message.answer(text)

# ========== ИДЕИ ==========

@dp.message(F.text == "💡 Идея")
async def idea_start(message: types.Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer("💭 Напишите вашу идею или предложение:\n\n/cancel - отмена")

@dp.message(IdeaState.waiting_for_idea)
async def idea_save(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())
        return
    
    user = message.from_user
    await save_idea(user.id, user.username or "no_username", message.text)
    
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📝 НОВАЯ ИДЕЯ!\n\nОт: {user.full_name}\nID: {user.id}\n\n{message.text}"
        )
        await message.answer("✅ Спасибо! Идея отправлена администратору.", reply_markup=main_menu())
    except:
        await message.answer("✅ Спасибо! Идея сохранена.", reply_markup=main_menu())
    
    await state.clear()

# ========== ПРОФИЛЬ ==========

@dp.message(F.text == "📊 Профиль")
async def show_profile(message: types.Message):
    user = message.from_user
    balance = await get_game_balance(user.id)
    history = await get_history(user.id)
    
    text = f"<b>👤 Профиль</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"Имя: {user.full_name}\n"
    text += f"ID: <code>{user.id}</code>\n"
    text += f"🎮 Игровой баланс: {balance} ₸\n\n"
    
    if history:
        text += "<b>📜 Последние операции:</b>\n"
        for curr, amt, res, dt in history[:5]:
            text += f"• {curr}: {amt:.2f} = {res:.2f} ₸\n"
    else:
        text += "📭 Нет истории конвертаций"
    
    await message.answer(text)

# ========== ПОМОЩЬ ==========

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    help_text = """
<b>📚 Помощь</b>
━━━━━━━━━━━━━━━━━━━━━

<b>💵 Курсы валют:</b>
• Нажмите "Курсы валют"
• Выберите валюту
• Напишите сумму

<b>🌍 Погода:</b>
• Выберите страну → город

<b>🎮 Экономическая игра:</b>
• Покупайте и продавайте валюту
• Зарабатывайте на разнице курсов
• Команды: Купить USD 100, Продать USD 50

<b>💡 Идея:</b>
• Напишите предложение
• Оно придёт админу

<b>📊 Профиль:</b>
• Просмотр статистики
• История конвертаций

━━━━━━━━━━━━━━━━━━━━━
<i>Также можно написать: 100 USD</i>
"""
    await message.answer(help_text)

# ========== НАЗАД ==========

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

# ========== КОНВЕРТАЦИЯ ИЗ СООБЩЕНИЯ ==========

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

# ========== АДМИН ==========

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    total = await get_total_users()
    await message.answer(f"🔐 <b>Админ-панель</b>\n\n👥 Пользователей: {total}\n\n/ideas - идеи")

@dp.message(Command("ideas"))
async def admin_ideas(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT id, username, idea_text, created_at FROM ideas ORDER BY id DESC LIMIT 10")
        ideas = await cursor.fetchall()
    
    if not ideas:
        await message.answer("📭 Нет идей")
        return
    
    text = "💡 Последние идеи:\n\n"
    for idea in ideas:
        text += f"#{idea[0]} | @{idea[1] or 'anon'}\n📝 {idea[2][:100]}\n🕐 {idea[3][:16]}\n━━━━━━━━━\n"
    await message.answer(text)

@dp.message(Command("bonus"))
async def give_bonus(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    parts = message.text.split()
    if len(parts) == 2:
        user_id = int(parts[1])
        await update_game_balance(user_id, 1000)
        await message.answer(f"✅ Пользователю {user_id} начислено 1000 бонусов")

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота...")
    await init_db()
    print("✅ База данных готова")
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print("📱 ДОСТУПНЫЕ ФУНКЦИИ:")
    print("   • Курсы валют и конвертация")
    print("   • Погода в 40+ городах мира")
    print("   • Экономическая игра")
    print("   • Отправка идей админу")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())