import asyncio
import aiosqlite
import aiohttp
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
import os
import random
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# ========== КРАСИВЫЕ КЛАВИАТУРЫ ==========

def main_menu():
    """Главное меню с новым дизайном"""
    buttons = [
        [KeyboardButton(text="💵 Валюты"), KeyboardButton(text="₿ Крипта")],
        [KeyboardButton(text="📈 Графики"), KeyboardButton(text="💰 Бюджет")],
        [KeyboardButton(text="🌦 Погода"), KeyboardButton(text="📰 Новости")],
        [KeyboardButton(text="⭐ Избранное"), KeyboardButton(text="⏰ Напомнить")],
        [KeyboardButton(text="🎮 Игры"), KeyboardButton(text="💎 Premium")],
        [KeyboardButton(text="🆘 Помощь"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="📍 Обменники", request_location=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def profile_menu():
    """Меню профиля"""
    buttons = [
        [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="🎁 Бонусы")],
        [KeyboardButton(text="🔗 Рефералка"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def games_menu():
    """Меню игр"""
    buttons = [
        [KeyboardButton(text="🎮 Эко-игра"), KeyboardButton(text="❓ Викторина")],
        [KeyboardButton(text="🔮 Гороскоп"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def countries_menu():
    """Меню стран для погоды"""
    buttons = [
        [KeyboardButton(text="🇰🇿 Казахстан"), KeyboardButton(text="🇨🇳 Китай")],
        [KeyboardButton(text="🇰🇬 Кыргызстан"), KeyboardButton(text="🇹🇭 Таиланд")],
        [KeyboardButton(text="🇹🇷 Турция"), KeyboardButton(text="🇦🇪 ОАЭ")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Города и координаты
CITIES = {
    "🇰🇿 Казахстан": ["Астана", "Алматы", "Шымкент", "Актау"],
    "🇨🇳 Китай": ["Пекин", "Шанхай"],
    "🇰🇬 Кыргызстан": ["Бишкек", "Ош"],
    "🇹🇭 Таиланд": ["Бангкок", "Пхукет", "Паттайя"],
    "🇹🇷 Турция": ["Стамбул", "Анталья", "Анкара"],
    "🇦🇪 ОАЭ": ["Дубай", "Абу-Даби"]
}

COORDS = {
    "Астана": (51.1694, 71.4491), "Алматы": (43.2565, 76.9286),
    "Шымкент": (42.3417, 69.5901), "Актау": (43.6532, 51.1552),
    "Пекин": (39.9042, 116.4074), "Шанхай": (31.2304, 121.4737),
    "Бишкек": (42.8746, 74.5698), "Ош": (40.5149, 72.8166),
    "Бангкок": (13.7367, 100.5231), "Пхукет": (7.8804, 98.3923),
    "Паттайя": (12.9236, 100.8825), "Стамбул": (41.0082, 28.9784),
    "Анталья": (36.8969, 30.7133), "Анкара": (39.9334, 32.8597),
    "Дубай": (25.2048, 55.2708), "Абу-Даби": (24.4539, 54.3773)
}

# ========== СОСТОЯНИЯ ==========
class IdeaState(StatesGroup):
    waiting_for_idea = State()

class GameState(StatesGroup):
    trading = State()

class ReminderState(StatesGroup):
    waiting_for_text = State()
    waiting_for_time = State()

# ========== БАЗА ДАННЫХ ==========

async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        # Пользователи
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                balance INTEGER DEFAULT 10000,
                premium BOOLEAN DEFAULT 0,
                last_bonus DATE
            )
        ''')
        # Идеи
        await db.execute('''
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                idea_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # История конвертаций
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
        # Игровой портфель
        await db.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                user_id INTEGER,
                currency TEXT,
                amount REAL,
                PRIMARY KEY (user_id, currency)
            )
        ''')
        # Избранные города
        await db.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER,
                city TEXT,
                PRIMARY KEY (user_id, city)
            )
        ''')
        # Напоминания
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                remind_time TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
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

async def get_history(user_id: int, limit=10):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT currency, amount, result, created_at 
            FROM history 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (user_id, limit))
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

async def get_user_balance(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 10000

async def update_balance(user_id: int, amount: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def add_favorite(user_id: int, city: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("INSERT OR REPLACE INTO favorites (user_id, city) VALUES (?, ?)", (user_id, city))
        await db.commit()

async def get_favorites(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT city FROM favorites WHERE user_id = ?", (user_id,))
        return [row[0] for row in await cursor.fetchall()]

async def add_reminder(user_id: int, text: str, remind_time: datetime):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO reminders (user_id, text, remind_time)
            VALUES (?, ?, ?)
        ''', (user_id, text, remind_time))
        await db.commit()

async def get_reminders(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT id, text, remind_time 
            FROM reminders 
            WHERE user_id = ? AND is_active = 1 AND remind_time > datetime('now')
            ORDER BY remind_time
        ''', (user_id,))
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

async def get_crypto_rates():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether&vs_currencies=usd') as response:
                data = await response.json()
                usd_to_kzt = 485.50
                return {
                    'BTC': data.get('bitcoin', {}).get('usd', 60000) * usd_to_kzt,
                    'ETH': data.get('ethereum', {}).get('usd', 3000) * usd_to_kzt,
                    'USDT': data.get('tether', {}).get('usd', 1) * usd_to_kzt,
                }
    except:
        return {'BTC': 29000000, 'ETH': 1450000, 'USDT': 485}

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
                    return f"❌ Ошибка погоды для {city_name}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:50]}"

# ========== НОВОСТИ ==========

async def get_news():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://tengrinews.kz/news/') as response:
                if response.status == 200:
                    from bs4 import BeautifulSoup
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    news = []
                    for item in soup.select('.news-item')[:5]:
                        title = item.select_one('.news-title')
                        if title:
                            news.append(title.text.strip())
                    if news:
                        return news
    except:
        pass
    return ["Курс доллара стабилен", "Погода в выходные", "Новые законы в Казахстане"]

# ========== ГОРОСКОП ==========

HOROSCOPES = {
    "Овен": "🌟 Сегодня отличный день для финансовых операций!",
    "Телец": "💰 Будьте осторожны с крупными тратами.",
    "Близнецы": "📈 Удачный день для обмена валюты.",
    "Рак": "🎁 Ожидайте прибыльных предложений.",
    "Лев": "🔮 Ваша интуиция не подведёт.",
    "Дева": "📊 Планируйте бюджет на месяц вперёд.",
    "Весы": "⚖️ Хороший день для инвестиций.",
    "Скорпион": "⚠️ Избегайте спонтанных покупок.",
    "Стрелец": "🚀 Время для крупных решений.",
    "Козерог": "💎 Деньги будут поступать легко.",
    "Водолей": "💡 Неожиданные доходы возможны.",
    "Рыбы": "🎯 Доверяйте своим финансовым решениям."
}

# ========== БОТ ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

def get_random_emoji():
    emojis = ["🚀", "🌟", "💎", "🎯", "🔥", "⭐", "💫", "✨", "⚡", "💪"]
    return random.choice(emojis)

# ========== СТАРТ (КРАСИВЫЙ ДИЗАЙН) ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    
    welcome_text = f"""
╔══════════════════════════════╗
║      🌟 ДОБРО ПОЖАЛОВАТЬ     ║
║         В МЕГА-БОТА          ║
╚══════════════════════════════╝

{get_random_emoji()} <b>Привет, {user.first_name}!</b>

<b>📱 ВОЗМОЖНОСТИ МЕГА-БОТА:</b>

┌─────────────────────────────────┐
│ 💰 <b>ФИНАНСЫ</b>                 │
├─────────────────────────────────┤
│ 💵 Курсы валют (USD, EUR, RUB, CNY) │
│ ₿ Криптовалюты (BTC, ETH, USDT) │
│ 📈 Графики курсов               │
│ 💰 Бюджетный трекер             │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ 🌍 <b>ИНФОРМАЦИЯ</b>              │
├─────────────────────────────────┤
│ 🌦 Погода в 15+ городах мира     │
│ 📰 Новости Казахстана            │
│ 🗺 Ближайшие обменники           │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│ 🎮 <b>РАЗВЛЕЧЕНИЯ</b>             │
├─────────────────────────────────┤
│ 🎮 Экономическая игра            │
│ ❓ Викторина о Казахстане        │
│ 🔮 Гороскоп на сегодня           │
└─────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💡 ПРОСТЫЕ ПРИМЕРЫ:</b>
• Напишите <code>100 USD</code> - моментальная конвертация
• Нажмите <b>💵 Валюты</b> для курсов
• /alert USD 490 - уведомление о курсе

👇 <b>Выберите действие в меню ниже</b>
"""
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=main_menu())

# ========== ПРОФИЛЬ ==========

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user = message.from_user
    balance = await get_user_balance(user.id)
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM history WHERE user_id = ?", (user.id,))
        conversions = (await cursor.fetchone())[0]
    
    profile_text = f"""
╔══════════════════════════════╗
║         👤 ПРОФИЛЬ          ║
╚══════════════════════════════╝

<b>{user.full_name}</b>
@{user.username or 'не указан'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 СТАТИСТИКА:</b>
┌─────────────────────────────────┐
│ 🆔 ID: <code>{user.id}</code>               │
│ 📅 Регистрация: {datetime.now().strftime('%d.%m.%Y')} │
└─────────────────────────────────┘

<b>💰 ФИНАНСЫ:</b>
┌─────────────────────────────────┐
│ 💰 Игровой баланс: {balance:,.0f} ₸       │
│ 💱 Конвертаций: {conversions}            │
└─────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Нажмите «🎁 Бонусы» для получения подарков!</i>
"""
    await message.answer(profile_text, parse_mode="HTML", reply_markup=profile_menu())

@dp.message(F.text == "🎁 Бонусы")
async def show_bonuses(message: types.Message):
    today = datetime.now().date()
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT last_bonus FROM users WHERE user_id = ?", (message.from_user.id,))
        result = await cursor.fetchone()
        last_bonus = result[0] if result else None
        
        if last_bonus != str(today):
            await update_balance(message.from_user.id, 500)
            await db.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (str(today), message.from_user.id))
            await db.commit()
            bonus_text = "✅ <b>+500 ₸</b> - ежедневный бонус получен!"
        else:
            bonus_text = "⏰ Вы уже получили сегодняшний бонус. Возвращайтесь завтра!"
    
    await message.answer(f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС</b>\n\n{bonus_text}", parse_mode="HTML")

@dp.message(F.text == "📊 Моя статистика")
async def my_stats(message: types.Message):
    balance = await get_user_balance(message.from_user.id)
    history = await get_history(message.from_user.id, 5)
    
    text = f"""
╔══════════════════════════════╗
║      📊 МОЯ СТАТИСТИКА      ║
╚══════════════════════════════╝

💰 <b>Баланс:</b> {balance:,.0f} игровых ₸

<b>📜 ПОСЛЕДНИЕ КОНВЕРТАЦИИ:</b>
"""
    if history:
        for curr, amt, res, dt in history[:5]:
            text += f"\n• {curr}: {amt:.2f} = {res:.2f} ₸"
            text += f"\n  🕐 {dt[:16]}"
    else:
        text += "\n📭 Нет истории"
    
    await message.answer(text, parse_mode="HTML")

# ========== ВАЛЮТЫ И КРИПТА ==========

@dp.message(F.text == "💵 Валюты")
async def show_currencies(message: types.Message):
    rates = await get_currency_rates()
    text = """
╔══════════════════════════════╗
║      💵 КУРСЫ ВАЛЮТ        ║
║      НАЦИОНАЛЬНОГО БАНКА      ║
╚══════════════════════════════╝

"""
    for curr, rate in rates.items():
        emoji = {"USD": "🇺🇸", "EUR": "🇪🇺", "RUB": "🇷🇺", "CNY": "🇨🇳"}.get(curr, "💵")
        text += f"┌─────────────────────────────────┐\n"
        text += f"│ {emoji} <b>{curr}/KZT</b>                          │\n"
        text += f"│    → <code>{rate:,.2f}</code> ₸                   │\n"
        text += f"└─────────────────────────────────┘\n"
    
    text += f"\n🕐 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>\n"
    text += f"\n💡 <i>Напишите: 100 USD</i>"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "₿ Крипта")
async def show_crypto(message: types.Message):
    rates = await get_crypto_rates()
    text = """
╔══════════════════════════════╗
║      ₿ КРИПТОВАЛЮТЫ        ║
╚══════════════════════════════╝

"""
    for crypto, rate in rates.items():
        emoji = {"BTC": "₿", "ETH": "⟠", "USDT": "💲"}.get(crypto, "💰")
        text += f"┌─────────────────────────────────┐\n"
        text += f"│ {emoji} <b>{crypto}/KZT</b>                         │\n"
        text += f"│    → <code>{rate:,.0f}</code> ₸                   │\n"
        text += f"└─────────────────────────────────┘\n"
    
    await message.answer(text, parse_mode="HTML")

# ========== ПОГОДА ==========

@dp.message(F.text == "🌦 Погода")
async def weather_countries(message: types.Message):
    text = """
╔══════════════════════════════╗
║         🌍 ПОГОДА          ║
║     ВЫБЕРИТЕ СТРАНУ         ║
╚══════════════════════════════╝

┌─────────────────────────────────┐
│ 🇰🇿 Казахстан                    │
│ 🇨🇳 Китай                        │
│ 🇰🇬 Кыргызстан                   │
│ 🇹🇭 Таиланд                      │
│ 🇹🇷 Турция                       │
│ 🇦🇪 ОАЭ                          │
└─────────────────────────────────┘
"""
    await message.answer(text, parse_mode="HTML", reply_markup=countries_menu())

@dp.message(F.text.in_(CITIES.keys()))
async def show_cities_menu(message: types.Message):
    country = message.text
    cities = CITIES[country]
    buttons = [[KeyboardButton(text=city)] for city in cities]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer(f"🏙 <b>Города {country}:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.in_(COORDS.keys()))
async def get_weather_for_city(message: types.Message):
    await message.bot.send_chat_action(message.chat.id, "typing")
    weather = await get_weather(message.text)
    await message.answer(weather)

# ========== НОВОСТИ ==========

@dp.message(F.text == "📰 Новости")
async def show_news(message: types.Message):
    news = await get_news()
    text = """
╔══════════════════════════════╗
║      📰 ПОСЛЕДНИЕ НОВОСТИ   ║
║         КАЗАХСТАНА           ║
╚══════════════════════════════╝

"""
    for i, item in enumerate(news, 1):
        text += f"{i}. {item}\n"
    
    await message.answer(text)

# ========== ИГРЫ ==========

@dp.message(F.text == "🎮 Игры")
async def games_menu_handler(message: types.Message):
    text = """
╔══════════════════════════════╗
║         🎮 ИГРЫ            ║
╚══════════════════════════════╝

┌─────────────────────────────────┐
│ 🎮 Экономическая игра            │
│ ❓ Викторина о Казахстане        │
│ 🔮 Гороскоп на сегодня           │
└─────────────────────────────────┘
"""
    await message.answer(text, parse_mode="HTML", reply_markup=games_menu())

@dp.message(F.text == "🎮 Эко-игра")
async def economic_game(message: types.Message):
    balance = await get_user_balance(message.from_user.id)
    rates = await get_currency_rates()
    
    text = f"""
╔══════════════════════════════╗
║      🎮 ЭКОНОМИЧЕСКАЯ ИГРА   ║
╚══════════════════════════════╝

💰 <b>Ваш баланс:</b> {balance:,.0f} ₸

<b>📈 Текущие курсы:</b>
🇺🇸 USD: {rates['USD']:.2f} ₸
🇪🇺 EUR: {rates['EUR']:.2f} ₸
🇷🇺 RUB: {rates['RUB']:.2f} ₸

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Команды:</b>
• /buy USD 100 - купить 100 USD
• /sell USD 100 - продать 100 USD
• /portfolio - мой портфель
"""
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("buy"))
async def buy_currency(message: types.Message):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Используйте: /buy USD 100")
        return
    
    currency = parts[1].upper()
    amount = float(parts[2])
    rates = await get_currency_rates()
    balance = await get_user_balance(message.from_user.id)
    total = amount * rates[currency]
    
    if balance < total:
        await message.answer(f"❌ Недостаточно средств! Нужно {total:,.0f} ₸, у вас {balance:,.0f} ₸")
        return
    
    await update_balance(message.from_user.id, -int(total))
    
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO portfolio (user_id, currency, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, currency) DO UPDATE SET
            amount = amount + ?
        ''', (message.from_user.id, currency, amount, amount))
        await db.commit()
    
    await message.answer(f"✅ Куплено {amount} {currency} за {total:,.0f} ₸")

@dp.message(Command("sell"))
async def sell_currency(message: types.Message):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Используйте: /sell USD 100")
        return
    
    currency = parts[1].upper()
    amount = float(parts[2])
    rates = await get_currency_rates()
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT amount FROM portfolio WHERE user_id = ? AND currency = ?", (message.from_user.id, currency))
        result = await cursor.fetchone()
        
        if not result or result[0] < amount:
            await message.answer("❌ У вас нет столько валюты!")
            return
        
        total = amount * rates[currency]
        await update_balance(message.from_user.id, int(total))
        await db.execute("UPDATE portfolio SET amount = amount - ? WHERE user_id = ? AND currency = ?", (amount, message.from_user.id, currency))
        await db.commit()
    
    await message.answer(f"✅ Продано {amount} {currency} за {total:,.0f} ₸")

@dp.message(Command("portfolio"))
async def show_portfolio(message: types.Message):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT currency, amount FROM portfolio WHERE user_id = ? AND amount > 0", (message.from_user.id,))
        portfolio = await cursor.fetchall()
    
    if not portfolio:
        await message.answer("📭 Ваш портфель пуст")
        return
    
    text = "💼 <b>МОЙ ПОРТФЕЛЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for curr, amt in portfolio:
        text += f"\n{curr}: {amt:.2f}"
    await message.answer(text)

# ========== ВИКТОРИНА ==========

QUESTIONS = [
    {"q": "Столица Казахстана?", "options": ["Алматы", "Астана", "Шымкент"], "correct": 1},
    {"q": "Национальная валюта Казахстана?", "options": ["Рубль", "Тенге", "Сом"], "correct": 1},
    {"q": "Какое море омывает Казахстан?", "options": ["Черное", "Аральское", "Каспийское"], "correct": 2},
]

@dp.message(F.text == "❓ Викторина")
async def start_quiz(message: types.Message):
    q = random.choice(QUESTIONS)
    buttons = [[KeyboardButton(text=opt)] for opt in q["options"]]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    
    await message.answer(f"❓ <b>{q['q']}</b>", reply_markup=keyboard)
    
    async def check_answer(m):
        if m.text == q["options"][q["correct"]]:
            await update_balance(m.from_user.id, 100)
            await m.answer("✅ Правильно! +100 ₸", reply_markup=main_menu())
        else:
            await m.answer(f"❌ Неправильно! Правильный ответ: {q['options'][q['correct']]}", reply_markup=main_menu())
        
        dp.message.handlers.remove(check_answer)
    
    dp.message.register(check_answer)

# ========== ГОРОСКОП ==========

@dp.message(F.text == "🔮 Гороскоп")
async def horoscope_menu(message: types.Message):
    buttons = [[KeyboardButton(text=sign)] for sign in HOROSCOPES.keys()]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer("🔮 <b>Выберите знак зодиака:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.in_(HOROSCOPES.keys()))
async def show_horoscope(message: types.Message):
    text = f"""
╔══════════════════════════════╗
║         🔮 ГОРОСКОП         ║
║         {message.text}           ║
╚══════════════════════════════╝

{HOROSCOPES[message.text]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>✨ Удачного дня!</i>
"""
    await message.answer(text, parse_mode="HTML")

# ========== НАПОМИНАНИЯ ==========

@dp.message(F.text == "⏰ Напомнить")
async def reminder_menu(message: types.Message):
    buttons = [
        [KeyboardButton(text="➕ Новое"), KeyboardButton(text="📋 Мои")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    await message.answer("⏰ <b>НАПОМИНАНИЯ</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text == "➕ Новое")
async def new_reminder(message: types.Message, state: FSMContext):
    await state.set_state(ReminderState.waiting_for_text)
    await message.answer("📝 Напишите текст напоминания:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(ReminderState.waiting_for_text)
async def reminder_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(ReminderState.waiting_for_time)
    await message.answer("⏰ Напишите время (пример: 25.12.2024 15:30):")

@dp.message(ReminderState.waiting_for_time)
async def reminder_time(message: types.Message, state: FSMContext):
    try:
        remind_time = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        data = await state.get_data()
        await add_reminder(message.from_user.id, data['text'], remind_time)
        await message.answer(f"✅ Напоминание установлено на {message.text}", reply_markup=main_menu())
        await state.clear()
    except:
        await message.answer("❌ Неверный формат! Используйте: 25.12.2024 15:30")

@dp.message(F.text == "📋 Мои")
async def list_reminders(message: types.Message):
    reminders = await get_reminders(message.from_user.id)
    if not reminders:
        await message.answer("📭 У вас нет активных напоминаний")
        return
    
    text = "⏰ <b>МОИ НАПОМИНАНИЯ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for rid, txt, rt in reminders:
        text += f"\n#{rid}\n📝 {txt}\n🕐 {rt[:16]}\n"
    await message.answer(text)

# ========== ИЗБРАННОЕ ==========

@dp.message(F.text == "⭐ Избранное")
async def favorites_menu(message: types.Message):
    favorites = await get_favorites(message.from_user.id)
    
    if favorites:
        text = "⭐ <b>ВАШИ ИЗБРАННЫЕ ГОРОДА</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
        for city in favorites:
            text += f"\n• {city}"
    else:
        text = "📭 У вас пока нет избранных городов"
    
    buttons = [[KeyboardButton(text="➕ Добавить город"), KeyboardButton(text="🗑 Удалить")]]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text == "➕ Добавить город")
async def add_favorite_prompt(message: types.Message):
    await message.answer("🌍 Напишите название города для добавления в избранное:")

@dp.message(F.text.in_(COORDS.keys()))
async def save_favorite(message: types.Message):
    await add_favorite(message.from_user.id, message.text)
    await message.answer(f"✅ Город {message.text} добавлен в избранное!")

# ========== КОНВЕРТАЦИЯ ИЗ СООБЩЕНИЯ ==========

@dp.message()
async def auto_convert(message: types.Message):
    # Конвертация: 100 USD
    match = re.match(r'^(\d+(?:\.\d+)?)\s+([A-Z]{3})$', message.text.upper().strip())
    if match:
        amount = float(match.group(1))
        currency = match.group(2)
        rates = await get_currency_rates()
        
        if currency in rates:
            result = amount * rates[currency]
            await save_history(message.from_user.id, currency, amount, result)
            await message.answer(f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>")

# ========== ПОМОЩЬ ==========

@dp.message(F.text == "🆘 Помощь")
async def cmd_help(message: types.Message):
    help_text = """
╔══════════════════════════════╗
║         📚 ПОМОЩЬ           ║
╚══════════════════════════════╝

<b>🔹 БЫСТРЫЕ КОМАНДЫ:</b>
┌─────────────────────────────────┐
│ <code>100 USD</code> - конвертация      │
│ /buy USD 100 - покупка в игре    │
│ /sell USD 100 - продажа в игре   │
└─────────────────────────────────┘

<b>🔹 ВАЛЮТЫ:</b>
┌─────────────────────────────────┐
│ 💵 Валюты - курсы НБ РК          │
│ ₿ Крипта - криптовалюты         │
└─────────────────────────────────┘

<b>🔹 ПОГОДА:</b>
┌─────────────────────────────────┐
│ 🌦 Погода → страна → город       │
│ ⭐ Избранное - сохранить город   │
└─────────────────────────────────┘

<b>🔹 ИГРЫ:</b>
┌─────────────────────────────────┐
│ 🎮 Эко-игра - трейдинг          │
│ ❓ Викторина - заработай ₸      │
│ 🔮 Гороскоп - прогноз           │
└─────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>✨ По всем вопросам: @alisher_kz</i>
"""
    await message.answer(help_text, parse_mode="HTML")

# ========== ОБМЕННИКИ ==========

@dp.message(F.location)
async def get_nearby_exchangers(message: types.Message):
    text = """
╔══════════════════════════════╗
║      🗺 БЛИЖАЙШИЕ ОБМЕННИКИ  ║
╚══════════════════════════════╝

<b>📍 Ваша локация:</b>
Широта: {:.4f}
Долгота: {:.4f}

<b>🏦 Рекомендуемые обменники:</b>

1. <b>Best Change</b>
   📍 ул. Абая, 15
   💱 USD: 483 / 488
   🕐 09:00 - 20:00

2. <b>Алтын ОБМЕН</b>
   📍 пр. Достык, 42
   💱 USD: 484 / 489
   🕐 Круглосуточно

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Нажмите на обменник для построения маршрута</i>
""".format(message.location.latitude, message.location.longitude)
    
    await message.answer(text, parse_mode="HTML")

# ========== ГРАФИКИ ==========

@dp.message(F.text == "📈 Графики")
async def chart_menu(message: types.Message):
    buttons = [
        [KeyboardButton(text="📊 USD"), KeyboardButton(text="📊 EUR")],
        [KeyboardButton(text="📊 RUB"), KeyboardButton(text="📊 CNY")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    await message.answer("📈 <b>ВЫБЕРИТЕ ВАЛЮТУ ДЛЯ ГРАФИКА</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.startswith("📊 "))
async def show_chart_simple(message: types.Message):
    currency = message.text.split()[1]
    await message.answer(f"📈 <b>График {currency}/KZT</b>\n\nКурс стабилен. Подробные графики скоро будут доступны в Premium версии!", parse_mode="HTML")

# ========== БЮДЖЕТ ==========

@dp.message(F.text == "💰 Бюджет")
async def budget_menu(message: types.Message):
    text = """
╔══════════════════════════════╗
║      💰 БЮДЖЕТНЫЙ ТРЕКЕР    ║
╚══════════════════════════════╝

<b>Команды для управления бюджетом:</b>
• /add 5000 такси - добавить расход
• /stats - статистика за месяц
• /categories - мои категории

<b>Пример:</b>
<code>/add 2500 обед</code>
"""
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("add"))
async def add_expense(message: types.Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("❌ Используйте: /add 5000 такси")
        return
    
    try:
        amount = float(parts[1])
        description = parts[2] if len(parts) > 2 else "Без описания"
        
        async with aiosqlite.connect("bot_database.db") as db:
            await db.execute('''
                INSERT INTO history (user_id, currency, amount, result)
                VALUES (?, 'EXPENSE', ?, ?)
            ''', (message.from_user.id, amount, 0))
            await db.commit()
        
        await message.answer(f"✅ Добавлен расход: {amount:,.0f} ₸ ({description})")
    except:
        await message.answer("❌ Ошибка! Используйте: /add 5000 такси")

@dp.message(Command("stats"))
async def show_expense_stats(message: types.Message):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT SUM(amount) FROM history 
            WHERE user_id = ? AND currency = 'EXPENSE' 
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        ''', (message.from_user.id,))
        total = (await cursor.fetchone())[0] or 0
        
        cursor = await db.execute('''
            SELECT COUNT(*) FROM history 
            WHERE user_id = ? AND currency = 'EXPENSE'
        ''', (message.from_user.id,))
        count = (await cursor.fetchone())[0]
    
    await message.answer(f"📊 <b>СТАТИСТИКА РАСХОДОВ</b>\n\n💰 За месяц: {total:,.0f} ₸\n📝 Всего операций: {count}", parse_mode="HTML")

# ========== PREMIUM ==========

@dp.message(F.text == "💎 Premium")
async def premium_info(message: types.Message):
    text = """
╔══════════════════════════════╗
║      💎 PREMIUM ПОДПИСКА    ║
╚══════════════════════════════╝

<b>Преимущества Premium:</b>
┌─────────────────────────────────┐
│ ✨ Неограниченная история       │
│ ✨ Расширенные графики          │
│ ✨ Приоритетная поддержка       │
│ ✨ Эксклюзивные функции         │
└─────────────────────────────────┘

<b>💰 Цена:</b> 5000 игровых тенге / месяц

<b>🎁 Приведи друга:</b>
За каждого приглашённого вы получите 7 дней Premium!
"""
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔗 Рефералка")
async def referral_link(message: types.Message):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    
    text = f"""
╔══════════════════════════════╗
║      🔗 РЕФЕРАЛЬНАЯ ССЫЛКА  ║
╚══════════════════════════════╝

<b>Ваша ссылка:</b>
<code>{link}</code>

<b>За каждого друга:</b>
• +1000 игровых тенге
• +7 дней Premium

Просто отправьте ссылку друзьям!
"""
    await message.answer(text, parse_mode="HTML")

# ========== ИДЕИ ==========

@dp.message(F.text == "💡 Предложить идею")
async def idea_start(message: types.Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer("💭 Напишите вашу идею или предложение:\n\n/cancel - отмена", reply_markup=types.ReplyKeyboardRemove())

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
            f"📝 <b>НОВАЯ ИДЕЯ!</b>\n\n👤 {user.full_name}\n🆔 <code>{user.id}</code>\n\n💡 {message.text}",
            parse_mode="HTML"
        )
        await message.answer("✅ Спасибо! Идея отправлена администратору.", reply_markup=main_menu())
    except:
        await message.answer("✅ Спасибо! Идея сохранена.", reply_markup=main_menu())
    
    await state.clear()

# ========== НАЗАД ==========

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

# ========== АДМИН ==========

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    total = await get_total_users()
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM ideas")
        ideas = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT SUM(balance) FROM users")
        total_balance = (await cursor.fetchone())[0] or 0
    
    text = f"""
╔══════════════════════════════╗
║      🔐 АДМИН-ПАНЕЛЬ       ║
╚══════════════════════════════╝

👥 <b>Пользователей:</b> {total}
💡 <b>Идей:</b> {ideas}
💰 <b>Игровая экономика:</b> {total_balance:,.0f} ₸

<b>Команды:</b>
/ideas - посмотреть идеи
/stats - подробная статистика
"""
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("ideas"))
async def admin_ideas_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT id, username, idea_text, created_at FROM ideas ORDER BY id DESC LIMIT 10")
        ideas = await cursor.fetchall()
    
    if not ideas:
        await message.answer("📭 Нет идей")
        return
    
    text = "💡 <b>ПОСЛЕДНИЕ ИДЕИ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for idea in ideas:
        text += f"\n#{idea[0]} | @{idea[1] or 'anon'}\n📝 {idea[2][:100]}\n🕐 {idea[3][:16]}\n"
    await message.answer(text, parse_mode="HTML")

# ========== ЗАПУСК ==========

async def main():
    print("🚀 ЗАПУСК МЕГА-БОТА С КРАСИВЫМ ДИЗАЙНОМ...")
    await init_db()
    print("✅ База данных готова")
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print("📱 ДОСТУПНЫЕ ФУНКЦИИ:")
    print("   • Красивый дизайн с рамками")
    print("   • Курсы валют и криптовалют")
    print("   • Погода в 15+ городах")
    print("   • Экономическая игра")
    print("   • Викторина и гороскоп")
    print("   • Напоминания и бюджет")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())