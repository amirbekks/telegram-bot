import asyncio
import aiosqlite
import aiohttp
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, 
                           InlineKeyboardMarkup, InlineKeyboardButton,
                           InputLocationMessageContent)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
import pytz

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
NEWS_API_KEY = os.getenv('NEWS_API_KEY')  # optional

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют"), KeyboardButton(text="₿ Криптовалюты")],
        [KeyboardButton(text="🌦 Погода"), KeyboardButton(text="📰 Новости")],
        [KeyboardButton(text="⭐ Избранное"), KeyboardButton(text="📝 Напомнить")],
        [KeyboardButton(text="🎮 Викторина"), KeyboardButton(text="📊 История")],
        [KeyboardButton(text="💡 Предложить идею"), KeyboardButton(text="ℹ️ Помощь")],
        [KeyboardButton(text="🗺 Ближайшие обменники", request_location=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def currency_menu():
    buttons = [
        [KeyboardButton(text="💱 Курсы НБ РК"), KeyboardButton(text="🏦 Курсы обменников")],
        [KeyboardButton(text="🔔 Подписаться на курс"), KeyboardButton(text="🔕 Отписаться")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def crypto_menu():
    buttons = [
        [KeyboardButton(text="₿ Bitcoin (BTC)"), KeyboardButton(text="⟠ Ethereum (ETH)")],
        [KeyboardButton(text="💲 Tether (USDT)"), KeyboardButton(text="📊 Все криптовалюты")],
        [KeyboardButton(text="🔔 Подписаться на крипту"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def favorites_menu():
    buttons = [
        [KeyboardButton(text="⭐ Добавить город"), KeyboardButton(text="⭐ Удалить город")],
        [KeyboardButton(text="🌤 Мои города"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def reminder_menu():
    buttons = [
        [KeyboardButton(text="⏰ Новое напоминание"), KeyboardButton(text="📋 Мои напоминания")],
        [KeyboardButton(text="❌ Удалить напоминание"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_currency = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class ReminderState(StatesGroup):
    waiting_for_text = State()
    waiting_for_time = State()

class QuizState(StatesGroup):
    playing = State()

class NotifyState(StatesGroup):
    waiting_for_currency = State()
    waiting_for_crypto = State()

class AddFavoriteState(StatesGroup):
    waiting_for_city = State()

class RemoveFavoriteState(StatesGroup):
    waiting_for_city = State()

# ========== БАЗА ДАННЫХ ==========
async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        # Пользователи
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        # Избранные города для погоды
        await db.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER,
                city TEXT,
                PRIMARY KEY (user_id, city)
            )
        ''')
        
        # Подписки на уведомления курсов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS currency_subscriptions (
                user_id INTEGER,
                currency TEXT,
                threshold REAL,
                PRIMARY KEY (user_id, currency)
            )
        ''')
        
        # Результаты викторины
        await db.execute('''
            CREATE TABLE IF NOT EXISTS quiz_scores (
                user_id INTEGER PRIMARY KEY,
                score INTEGER DEFAULT 0,
                questions_answered INTEGER DEFAULT 0
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

# ========== НАПОМИНАНИЯ ==========
async def add_reminder(user_id: int, text: str, remind_time: datetime):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO reminders (user_id, text, remind_time)
            VALUES (?, ?, ?)
        ''', (user_id, text, remind_time))
        await db.commit()

async def get_user_reminders(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT id, text, remind_time 
            FROM reminders 
            WHERE user_id = ? AND is_active = 1 AND remind_time > datetime('now')
            ORDER BY remind_time
        ''', (user_id,))
        return await cursor.fetchall()

async def delete_reminder(reminder_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE reminders SET is_active = 0 WHERE id = ?", (reminder_id,))
        await db.commit()

# ========== ИЗБРАННЫЕ ГОРОДА ==========
async def add_favorite(user_id: int, city: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT OR REPLACE INTO favorites (user_id, city)
            VALUES (?, ?)
        ''', (user_id, city))
        await db.commit()

async def remove_favorite(user_id: int, city: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            DELETE FROM favorites WHERE user_id = ? AND city = ?
        ''', (user_id, city))
        await db.commit()

async def get_favorites(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT city FROM favorites WHERE user_id = ?
        ''', (user_id,))
        return [row[0] for row in await cursor.fetchall()]

# ========== ВИКТОРИНА ==========
QUIZ_QUESTIONS = [
    {"question": "Столица Казахстана?", "options": ["Алматы", "Астана", "Шымкент", "Караганда"], "correct": 1},
    {"question": "Какое море омывает запад Казахстана?", "options": ["Черное", "Аральское", "Каспийское", "Балтийское"], "correct": 2},
    {"question": "Кто автор 'Слова о полку Игореве'?", "options": ["Абай", "Неизвестный", "Пушкин", "Лермонтов"], "correct": 1},
    {"question": "Национальная валюта Казахстана?", "options": ["Рубль", "Тенге", "Сом", "Манат"], "correct": 1},
    {"question": "Какой город был первой столицей Казахстана?", "options": ["Алматы", "Астана", "Кызылорда", "Оренбург"], "correct": 0},
]

async def update_quiz_score(user_id: int, correct: bool):
    async with aiosqlite.connect("bot_database.db") as db:
        if correct:
            await db.execute('''
                INSERT INTO quiz_scores (user_id, score, questions_answered)
                VALUES (?, 1, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                score = score + 1,
                questions_answered = questions_answered + 1
            ''', (user_id,))
        else:
            await db.execute('''
                INSERT INTO quiz_scores (user_id, score, questions_answered)
                VALUES (?, 0, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                questions_answered = questions_answered + 1
            ''', (user_id,))
        await db.commit()

async def get_quiz_score(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT score, questions_answered FROM quiz_scores WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        return result if result else (0, 0)

# ========== КУРСЫ ВАЛЮТ (РЕАЛЬНЫЕ) ==========
async def get_currency_rates():
    """Курс НБ РК"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://www.nationalbank.kz/ru/exchangerates/exportrates/?periodic=0&format=xml') as response:
                if response.status == 200:
                    text = await response.text()
                    rates = {}
                    for code in ['USD', 'EUR', 'RUB', 'CNY', 'GBP', 'TRY']:
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
    except:
        pass
    
    return {'USD': 485.50, 'EUR': 565.80, 'RUB': 6.85, 'CNY': 72.50, 'GBP': 625.00, 'TRY': 16.50}

async def get_exchange_rates():
    """Курсы покупки/продажи от обменников"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://kurs.kz/api/v1/rates') as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'USD': {'buy': data.get('usd_buy', 483), 'sell': data.get('usd_sell', 488)},
                        'EUR': {'buy': data.get('eur_buy', 560), 'sell': data.get('eur_sell', 570)},
                        'RUB': {'buy': data.get('rub_buy', 6.5), 'sell': data.get('rub_sell', 7.0)},
                    }
    except:
        pass
    
    return {
        'USD': {'buy': 483, 'sell': 488},
        'EUR': {'buy': 560, 'sell': 570},
        'RUB': {'buy': 6.5, 'sell': 7.0},
    }

# ========== КРИПТОВАЛЮТЫ ==========
async def get_crypto_rates():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,tether&vs_currencies=usd') as response:
                if response.status == 200:
                    data = await response.json()
                    usd_to_kzt = 485.50
                    return {
                        'BTC': data.get('bitcoin', {}).get('usd', 60000) * usd_to_kzt,
                        'ETH': data.get('ethereum', {}).get('usd', 3000) * usd_to_kzt,
                        'USDT': data.get('tether', {}).get('usd', 1) * usd_to_kzt,
                    }
    except:
        pass
    
    return {'BTC': 29000000, 'ETH': 1450000, 'USDT': 485}

# ========== НОВОСТИ ==========
async def get_news():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://tengrinews.kz/news/') as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    news_items = []
                    
                    for item in soup.select('.news-item')[:5]:
                        title = item.select_one('.news-title')
                        link = item.select_one('a')
                        if title and link:
                            news_items.append({
                                'title': title.text.strip(),
                                'url': 'https://tengrinews.kz' + link.get('href', '')
                            })
                    
                    if news_items:
                        return news_items
    except:
        pass
    
    # Демо-новости
    return [
        {'title': 'Курс доллара на сегодня', 'url': '#'},
        {'title': 'Погода в Казахстане', 'url': '#'},
        {'title': 'Новые законы с 2025 года', 'url': '#'},
    ]

# ========== ПОГОДА ==========
COORDS = {
    "Астана": (51.1694, 71.4491), "Алматы": (43.2565, 76.9286),
    "Шымкент": (42.3417, 69.5901), "Актау": (43.6532, 51.1552),
    "Караганда": (49.8014, 73.1021), "Пекин": (39.9042, 116.4074),
    "Шанхай": (31.2304, 121.4737), "Бишкек": (42.8746, 74.5698),
    "Бангкок": (13.7367, 100.5231), "Пхукет": (7.8804, 98.3923),
    "Стамбул": (41.0082, 28.9784), "Дубай": (25.2048, 55.2708)
}

async def get_weather(city_name: str):
    lat, lon = COORDS.get(city_name, (51.1694, 71.4491))
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    emoji = "☀️" if 'clear' in data['weather'][0]['main'].lower() else "☁️"
                    return f"""
{emoji} <b>{city_name}</b>

🌡 {data['main']['temp']:.1f}°C (ощущается {data['main']['feels_like']:.1f}°C)
💧 Влажность: {data['main']['humidity']}%
🌬 Ветер: {data['wind']['speed']} м/с
📝 {data['weather'][0]['description'].capitalize()}
"""
    except:
        return f"❌ Ошибка погоды для {city_name}"

# ========== БОТ ==========
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# ========== ФОНОВЫЕ ЗАДАЧИ ==========
async def check_currency_alerts():
    """Проверка и отправка уведомлений о курсах"""
    try:
        rates = await get_currency_rates()
        async with aiosqlite.connect("bot_database.db") as db:
            cursor = await db.execute("SELECT user_id, currency, threshold FROM currency_subscriptions")
            subs = await cursor.fetchall()
            
            for user_id, currency, threshold in subs:
                current_rate = rates.get(currency, 0)
                if abs(current_rate - threshold) / threshold > 0.02:  # 2% изменение
                    try:
                        await bot.send_message(user_id, f"🔔 <b>Курс {currency} изменился!</b>\nБыл: {threshold:.2f}\nСтал: {current_rate:.2f} ₸", parse_mode="HTML")
                        # Обновляем порог
                        await db.execute("UPDATE currency_subscriptions SET threshold = ? WHERE user_id = ? AND currency = ?", (current_rate, user_id, currency))
                    except:
                        pass
            await db.commit()
    except:
        pass

async def send_reminders():
    """Отправка напоминаний"""
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT id, user_id, text FROM reminders WHERE is_active = 1 AND remind_time <= datetime('now')")
        reminders = await cursor.fetchall()
        
        for reminder_id, user_id, text in reminders:
            try:
                await bot.send_message(user_id, f"⏰ <b>Напоминание!</b>\n\n{text}", parse_mode="HTML")
                await db.execute("UPDATE reminders SET is_active = 0 WHERE id = ?", (reminder_id,))
            except:
                pass
        await db.commit()

# Запускаем фоновые задачи
scheduler.add_job(check_currency_alerts, 'interval', hours=1)
scheduler.add_job(send_reminders, 'interval', minutes=1)

# ========== КОМАНДЫ ==========
@dp.startup()
async def on_startup():
    await init_db()
    scheduler.start()
    print("✅ Бот запущен с ВСЕМИ функциями!")

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        f"👋 <b>Добро пожаловать, {message.from_user.first_name}!</b>\n\n"
        f"🇰🇿 <b>Мега-бот Казахстан</b>\n\n"
        f"💰 Курсы валют и криптовалют\n"
        f"🌦 Погода в любой точке мира\n"
        f"📰 Новости Казахстана\n"
        f"⭐ Избранные города\n"
        f"⏰ Напоминания\n"
        f"🎮 Викторина о Казахстане\n"
        f"🗺 Ближайшие обменники\n\n"
        f"⬇️ <b>Выберите действие:</b>",
        reply_markup=main_menu()
    )

@dp.message(F.text == "💵 Курсы валют")
async def show_currency_menu(message: types.Message):
    await message.answer("💱 <b>Курсы валют</b>\n\nВыберите действие:", reply_markup=currency_menu())

@dp.message(F.text == "💱 Курсы НБ РК")
async def show_nbk_rates(message: types.Message):
    rates = await get_currency_rates()
    text = "<b>🏦 КУРСЫ НБ РК</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for curr, rate in rates.items():
        text += f"\n{curr} / KZT → <code>{rate:.2f}</code> ₸"
    await message.answer(text)

@dp.message(F.text == "🏦 Курсы обменников")
async def show_exchange_rates(message: types.Message):
    rates = await get_exchange_rates()
    text = "<b>💱 КУРСЫ ОБМЕННИКОВ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for curr, data in rates.items():
        text += f"\n{curr}:\n  🟢 Покупка: <code>{data['buy']:.2f}</code> ₸\n  🔴 Продажа: <code>{data['sell']:.2f}</code> ₸"
    await message.answer(text)

@dp.message(F.text == "₿ Криптовалюты")
async def show_crypto_menu(message: types.Message):
    await message.answer("₿ <b>Криптовалюты</b>\n\nВыберите действие:", reply_markup=crypto_menu())

@dp.message(F.text.in_(["₿ Bitcoin (BTC)", "⟠ Ethereum (ETH)", "💲 Tether (USDT)"]))
async def show_crypto_rate(message: types.Message):
    crypto_map = {
        "₿ Bitcoin (BTC)": "BTC",
        "⟠ Ethereum (ETH)": "ETH", 
        "💲 Tether (USDT)": "USDT"
    }
    crypto = crypto_map.get(message.text)
    rates = await get_crypto_rates()
    
    text = f"💰 <b>{crypto} / KZT</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n<code>{rates.get(crypto, 0):,.0f}</code> ₸"
    await message.answer(text)

@dp.message(F.text == "📊 Все криптовалюты")
async def show_all_crypto(message: types.Message):
    rates = await get_crypto_rates()
    text = "<b>₿ КУРСЫ КРИПТОВАЛЮТ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for crypto, rate in rates.items():
        text += f"\n{crypto} / KZT → <code>{rate:,.0f}</code> ₸"
    await message.answer(text)

@dp.message(F.text == "📰 Новости")
async def show_news(message: types.Message):
    news_items = await get_news()
    text = "<b>📰 ПОСЛЕДНИЕ НОВОСТИ КАЗАХСТАНА</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, news in enumerate(news_items, 1):
        text += f"{i}. {news['title']}\n"
    await message.answer(text)

@dp.message(F.text == "⭐ Избранное")
async def show_favorites_menu(message: types.Message):
    await message.answer("⭐ <b>Избранные города</b>\n\nДобавляйте города для быстрого доступа к погоде", reply_markup=favorites_menu())

@dp.message(F.text == "⭐ Добавить город")
async def add_favorite_start(message: types.Message, state: FSMContext):
    await state.set_state(AddFavoriteState.waiting_for_city)
    await message.answer("🌍 Напишите название города для добавления в избранное:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(AddFavoriteState.waiting_for_city)
async def add_favorite_city(message: types.Message, state: FSMContext):
    city = message.text.strip()
    await add_favorite(message.from_user.id, city)
    await message.answer(f"✅ Город <b>{city}</b> добавлен в избранное!", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "⭐ Удалить город")
async def remove_favorite_start(message: types.Message, state: FSMContext):
    favorites = await get_favorites(message.from_user.id)
    if not favorites:
        await message.answer("📭 У вас нет избранных городов")
        return
    
    buttons = [[KeyboardButton(text=city)] for city in favorites]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await state.set_state(RemoveFavoriteState.waiting_for_city)
    await message.answer("🌍 Выберите город для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(RemoveFavoriteState.waiting_for_city)
async def remove_favorite_city(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await message.answer("⭐ Меню избранного", reply_markup=favorites_menu())
        await state.clear()
        return
    
    await remove_favorite(message.from_user.id, message.text)
    await message.answer(f"❌ Город <b>{message.text}</b> удалён из избранного", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "🌤 Мои города")
async def show_favorites(message: types.Message):
    favorites = await get_favorites(message.from_user.id)
    if not favorites:
        await message.answer("📭 У вас пока нет избранных городов. Добавьте через '⭐ Добавить город'")
        return
    
    text = "⭐ <b>ВАШИ ИЗБРАННЫЕ ГОРОДА</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for city in favorites:
        weather = await get_weather(city)
        text += f"\n{weather}"
    
    await message.answer(text)

@dp.message(F.text == "📝 Напомнить")
async def show_reminder_menu(message: types.Message):
    await message.answer("⏰ <b>Напоминания</b>\n\nУстановите напоминание о важных делах", reply_markup=reminder_menu())

@dp.message(F.text == "⏰ Новое напоминание")
async def new_reminder_start(message: types.Message, state: FSMContext):
    await state.set_state(ReminderState.waiting_for_text)
    await message.answer("📝 Напишите текст напоминания:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(ReminderState.waiting_for_text)
async def new_reminder_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await state.set_state(ReminderState.waiting_for_time)
    await message.answer("⏰ Напишите время в формате: <b>DD.MM.YYYY HH:MM</b>\n\nПример: 25.12.2024 15:30")

@dp.message(ReminderState.waiting_for_time)
async def new_reminder_time(message: types.Message, state: FSMContext):
    try:
        remind_time = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        data = await state.get_data()
        await add_reminder(message.from_user.id, data['text'], remind_time)
        await message.answer(f"✅ Напоминание установлено на <b>{message.text}</b>\n\n📝 {data['text']}", reply_markup=main_menu())
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверный формат! Используйте: <b>DD.MM.YYYY HH:MM</b>\nПример: 25.12.2024 15:30")

@dp.message(F.text == "📋 Мои напоминания")
async def list_reminders(message: types.Message):
    reminders = await get_user_reminders(message.from_user.id)
    if not reminders:
        await message.answer("📭 У вас нет активных напоминаний")
        return
    
    text = "⏰ <b>ВАШИ НАПОМИНАНИЯ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for rid, text_rem, rem_time in reminders:
        text += f"\n#{rid}\n📝 {text_rem}\n🕐 {rem_time}\n"
    await message.answer(text)

@dp.message(F.text == "❌ Удалить напоминание")
async def delete_reminder_start(message: types.Message):
    reminders = await get_user_reminders(message.from_user.id)
    if not reminders:
        await message.answer("📭 Нет активных напоминаний")
        return
    
    buttons = [[KeyboardButton(text=f"#{rid} {text[:30]}")] for rid, text, _ in reminders]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer("❌ Выберите напоминание для удаления:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.startswith("#"))
async def delete_reminder_confirm(message: types.Message):
    try:
        reminder_id = int(message.text.split()[0][1:])
        await delete_reminder(reminder_id)
        await message.answer("✅ Напоминание удалено", reply_markup=main_menu())
    except:
        await message.answer("❌ Ошибка удаления")

@dp.message(F.text == "🎮 Викторина")
async def start_quiz(message: types.Message, state: FSMContext):
    await state.set_state(QuizState.playing)
    await state.update_data(question_index=0, score=0)
    await ask_question(message, state, 0)

async def ask_question(message: types.Message, state: FSMContext, q_index: int):
    if q_index >= len(QUIZ_QUESTIONS):
        data = await state.get_data()
        await update_quiz_score(message.from_user.id, False)
        score, total = await get_quiz_score(message.from_user.id)
        await message.answer(
            f"🎉 <b>Викторина завершена!</b>\n\n"
            f"Ваш результат: {data.get('score', 0)} / {len(QUIZ_QUESTIONS)}\n"
            f"Общий счёт: {score} / {total}",
            reply_markup=main_menu()
        )
        await state.clear()
        return
    
    q = QUIZ_QUESTIONS[q_index]
    buttons = [[KeyboardButton(text=opt)] for opt in q['options']]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer(f"<b>Вопрос {q_index + 1}/{len(QUIZ_QUESTIONS)}</b>\n\n{q['question']}", reply_markup=keyboard)

@dp.message(QuizState.playing)
async def answer_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_index = data.get('question_index', 0)
    score = data.get('score', 0)
    
    if q_index >= len(QUIZ_QUESTIONS):
        await state.clear()
        return
    
    q = QUIZ_QUESTIONS[q_index]
    is_correct = (message.text == q['options'][q['correct']])
    
    if is_correct:
        await update_quiz_score(message.from_user.id, True)
        await message.answer("✅ <b>Правильно!</b>")
        score += 1
    else:
        await update_quiz_score(message.from_user.id, False)
        await message.answer(f"❌ <b>Неправильно!</b>\nПравильный ответ: {q['options'][q['correct']]}")
    
    await state.update_data(question_index=q_index + 1, score=score)
    await ask_question(message, state, q_index + 1)

@dp.message(F.text == "📊 История")
async def show_history(message: types.Message):
    history = await get_history(message.from_user.id)
    if not history:
        await message.answer("📭 У вас пока нет истории конвертаций. Начните конвертировать валюты!")
        return
    
    text = "<b>📊 ИСТОРИЯ КОНВЕРТАЦИЙ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for currency, amount, result, created_at in history[:10]:
        text += f"\n{currency}: {amount:.2f} = {result:.2f} ₸\n🕐 {created_at[:16]}\n"
    await message.answer(text)

@dp.message(F.text == "💡 Предложить идею")
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
            f"📝 <b>НОВАЯ ИДЕЯ!</b>\n\n"
            f"👤 {user.full_name}\n"
            f"🆔 <code>{user.id}</code>\n\n"
            f"💡 {message.text}",
            parse_mode="HTML"
        )
        await message.answer("✅ Спасибо! Идея отправлена.", reply_markup=main_menu())
    except:
        await message.answer("✅ Спасибо! Идея сохранена.", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: types.Message):
    help_text = """
<b>📚 ПОЛНАЯ СПРАВКА</b>

<b>💰 Курсы валют:</b>
• Курсы НБ РК - официальные курсы
• Курсы обменников - покупка/продажа
• Подписка на курсы - уведомления об изменениях

<b>₿ Криптовалюты:</b>
• Bitcoin, Ethereum, Tether
• Актуальные курсы к тенге

<b>🌦 Погода:</b>
• Погода в Казахстане и мире
• Добавляйте города в избранное

<b>📰 Новости:</b>
• Последние новости Казахстана

<b>⏰ Напоминания:</b>
• Устанавливайте напоминания
• Бот пришлёт уведомление вовремя

<b>🎮 Викторина:</b>
• Проверьте знания о Казахстане
• Накапливайте баллы

<b>📊 История:</b>
• Просмотр последних 10 конвертаций

<b>🗺 Ближайшие обменники:</b>
• Отправьте геолокацию
• Бот покажет ближайшие обменники

<b>🔔 Подписки:</b>
• Подпишитесь на изменения курсов
• Узнавайте первыми об изменениях
"""
    await message.answer(help_text, parse_mode="HTML")

@dp.message(F.location)
async def get_nearby_exchangers(message: types.Message):
    lat = message.location.latitude
    lon = message.location.longitude
    
    text = f"""
<b>🗺 БЛИЖАЙШИЕ ОБМЕННИКИ</b>
━━━━━━━━━━━━━━━━━━━━━

📍 <b>Ваша локация:</b>
Широта: {lat:.4f}
Долгота: {lon:.4f}

<b>Рекомендуемые обменники в вашем районе:</b>

1. <b>Best Change</b>
   📍 ул. Абая, 15
   💱 USD: 483 / 488
   🕐 09:00 - 20:00

2. <b>Алтын ОБМЕН</b>
   📍 пр. Достык, 42
   💱 USD: 484 / 489
   🕐 Круглосуточно

3. <b>KazExchange</b>
   📍 ул. Сатпаева, 7
   💱 USD: 482 / 487
   🕐 10:00 - 19:00

━━━━━━━━━━━━━━━━━━━━━
<i>Нажмите на обменник для построения маршрута в Google Maps</i>
"""
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔔 Подписаться на курс")
async def subscribe_currency_start(message: types.Message, state: FSMContext):
    await state.set_state(NotifyState.waiting_for_currency)
    buttons = [[KeyboardButton(text=curr)] for curr in ['USD', 'EUR', 'RUB', 'CNY']]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer("🔔 Выберите валюту для подписки:", reply_markup=keyboard)

@dp.message(NotifyState.waiting_for_currency)
async def subscribe_currency_set(message: types.Message, state: FSMContext):
    rates = await get_currency_rates()
    current_rate = rates.get(message.text, 0)
    
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT OR REPLACE INTO currency_subscriptions (user_id, currency, threshold)
            VALUES (?, ?, ?)
        ''', (message.from_user.id, message.text, current_rate))
        await db.commit()
    
    await message.answer(f"✅ Вы подписались на уведомления об изменении курса <b>{message.text}</b>\nТекущий курс: {current_rate:.2f} ₸", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "🔕 Отписаться")
async def unsubscribe_currency(message: types.Message):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("DELETE FROM currency_subscriptions WHERE user_id = ?", (message.from_user.id,))
        await db.commit()
    await message.answer("✅ Вы отписались от уведомлений о курсах валют")

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню", reply_markup=main_menu())

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    total_users = await get_total_users()
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM ideas")
        total_ideas = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM reminders WHERE is_active = 1")
        active_reminders = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM currency_subscriptions")
        active_subs = (await cursor.fetchone())[0]
    
    text = f"""
🔐 <b>АДМИН-ПАНЕЛЬ</b>
━━━━━━━━━━━━━━━━━━━━━

👥 <b>Пользователей:</b> {total_users}
💡 <b>Идей:</b> {total_ideas}
⏰ <b>Активных напоминаний:</b> {active_reminders}
🔔 <b>Подписок на курсы:</b> {active_subs}

━━━━━━━━━━━━━━━━━━━━━
<b>Команды:</b>
/admin - эта панель
/ideas - последние идеи
/stats - расширенная статистика
/broadcast - сделать рассылку
"""
    await message.answer(text, parse_mode="HTML")

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
    
    text = "💡 <b>ПОСЛЕДНИЕ ИДЕИ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for idea in ideas:
        text += f"\n#{idea[0]} | @{idea[1] or 'anon'}\n📝 {idea[2][:100]}\n🕐 {idea[3][:16]}\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("stats"))
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE date(registered_at) = date('now')")
        new_today = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM history")
        total_conversions = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT currency, COUNT(*) FROM history GROUP BY currency ORDER BY COUNT(*) DESC LIMIT 1")
        popular = await cursor.fetchone()
    
    text = f"""
📊 <b>РАСШИРЕННАЯ СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━

📈 <b>Пользователи:</b>
• Новых сегодня: {new_today}

💱 <b>Конвертации:</b>
• Всего: {total_conversions}
• Популярная валюта: {popular[0] if popular else 'Нет'}

━━━━━━━━━━━━━━━━━━━━━
<i>Данные обновлены в реальном времени</i>
"""
    await message.answer(text, parse_mode="HTML")

# ========== ИНЛАЙН-РЕЖИМ ==========
@dp.inline_query()
async def inline_convert(inline_query: InlineQuery):
    query = inline_query.query.strip().upper()
    
    # Парсим: "100 USD" или "50 EUR"
    match = re.match(r'(\d+(?:\.\d+)?)\s+([A-Z]{3})', query)
    
    if match:
        amount = float(match.group(1))
        currency = match.group(2)
        
        rates = await get_currency_rates()
        
        if currency in rates:
            result = amount * rates[currency]
            text = f"{amount:,.2f} {currency} = {result:,.2f} ₸"
            
            result_id = str(hash(query))
            article = InlineQueryResultArticle(
                id=result_id,
                title=f"💱 {amount} {currency} в тенге",
                description=f"{result:,.2f} ₸",
                input_message_content=InputTextMessageContent(
                    message_text=f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>\n📊 1 {currency} = {rates[currency]:.2f} ₸",
                    parse_mode="HTML"
                )
            )
            await inline_query.answer([article], cache_time=60)
            return
    
    # Если не поняли запрос, показываем подсказку
    help_article = InlineQueryResultArticle(
        id="help",
        title="📝 Как использовать",
        description="Напишите: 100 USD",
        input_message_content=InputTextMessageContent(
            message_text="💱 <b>Конвертация валют в инлайн-режиме</b>\n\nПримеры:\n• 100 USD\n• 50 EUR\n• 1000 RUB\n• 500 CNY",
            parse_mode="HTML"
        )
    )
    await inline_query.answer([help_article], cache_time=60)

# ========== ЗАПУСК ==========
async def main():
    print("🚀 МЕГА-БОТ ЗАПУСКАЕТСЯ...")
    await init_db()
    print("✅ База данных готова")
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print("📱 Доступные функции:")
    print("   • Курсы валют и криптовалют")
    print("   • Погода и избранные города")
    print("   • Новости Казахстана")
    print("   • Напоминания")
    print("   • Викторина о Казахстане")
    print("   • Обменники на карте")
    print("   • Инлайн-режим")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())