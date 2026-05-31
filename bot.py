import asyncio
import aiosqlite
import aiohttp
import re
import random
from datetime import datetime, time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# Часовой пояс Казахстана
KZT_TZ = pytz.timezone('Asia/Almaty')

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class GameState(StatesGroup):
    buying = State()
    selling = State()

class SubscribeState(StatesGroup):
    waiting_for_currency = State()
    waiting_for_city = State()
    waiting_for_time = State()

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют")],
        [KeyboardButton(text="🌍 Погода"), KeyboardButton(text="🎮 Игра")],
        [KeyboardButton(text="🔔 Уведомления"), KeyboardButton(text="📊 Профиль")],
        [KeyboardButton(text="💡 Идея"), KeyboardButton(text="❓ Помощь")]
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
        [KeyboardButton(text="🌅 Утренние (9:00)"), KeyboardButton(text="🌙 Вечерние (19:00)")],
        [KeyboardButton(text="⏰ И то и другое"), KeyboardButton(text="🔕 Отключить всё")],
        [KeyboardButton(text="📋 Мои подписки"), KeyboardButton(text="🔙 Назад")]
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

COORDS = {
    "Астана": (51.1694, 71.4491), "Алматы": (43.2565, 76.9286),
    "Шымкент": (42.3417, 69.5901), "Актау": (43.6532, 51.1552),
    "Караганда": (49.8014, 73.1021), "Уральск": (51.2167, 51.3667),
    "Пекин": (39.9042, 116.4074), "Шанхай": (31.2304, 121.4737),
    "Гуанчжоу": (23.1291, 113.2644), "Сиань": (34.3416, 108.9402), "Чэнду": (30.5728, 104.0668),
    "Бишкек": (42.8746, 74.5698), "Ош": (40.5149, 72.8166),
    "Джалал-Абад": (40.9334, 73.0027), "Каракол": (42.4907, 78.3936), "Токмок": (42.8373, 75.2930),
    "Бангкок": (13.7367, 100.5231), "Пхукет": (7.8804, 98.3923),
    "Паттайя": (12.9236, 100.8825), "Чиангмай": (18.7883, 98.9853),
    "Краби": (8.0863, 98.9069), "Самуи": (9.5120, 100.0136),
    "Стамбул": (41.0082, 28.9784), "Анкара": (39.9334, 32.8597),
    "Анталья": (36.8969, 30.7133), "Измир": (38.4192, 27.1287),
    "Бодрум": (37.0344, 27.4305), "Каппадокия": (38.6435, 34.8289),
    "Дубай": (25.2048, 55.2708), "Абу-Даби": (24.4539, 54.3773),
    "Шарджа": (25.3463, 55.4209), "Рас-эль-Хайма": (25.7895, 55.9432),
    "Каир": (30.0444, 31.2357), "Хургада": (27.2574, 33.8128),
    "Шарм-эль-Шейх": (27.9158, 34.33), "Луксор": (25.6809, 32.6394),
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
        # Таблица для подписок на уведомления
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                user_id INTEGER PRIMARY KEY,
                morning BOOLEAN DEFAULT 0,
                evening BOOLEAN DEFAULT 0,
                currencies TEXT DEFAULT 'USD,EUR,RUB,CNY',
                cities TEXT DEFAULT ''
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
            INSERT OR IGNORE INTO notifications (user_id, morning, evening, currencies, cities)
            VALUES (?, 0, 0, 'USD,EUR,RUB,CNY', '')
        ''', (user_id,))
        await db.commit()

# ========== ФУНКЦИИ ДЛЯ УВЕДОМЛЕНИЙ ==========

async def get_user_notification_settings(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT morning, evening, currencies, cities FROM notifications WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        if result:
            return {"morning": result[0], "evening": result[1], "currencies": result[2].split(','), "cities": result[3].split(',') if result[3] else []}
        return {"morning": False, "evening": False, "currencies": ["USD", "EUR", "RUB", "CNY"], "cities": []}

async def update_notification_settings(user_id: int, morning: bool = None, evening: bool = None, currencies: list = None, cities: list = None):
    async with aiosqlite.connect("bot_database.db") as db:
        current = await get_user_notification_settings(user_id)
        new_morning = morning if morning is not None else current["morning"]
        new_evening = evening if evening is not None else current["evening"]
        new_currencies = ','.join(currencies) if currencies else current["currencies"]
        new_cities = ','.join(cities) if cities is not None else ','.join(current["cities"])
        await db.execute('''
            UPDATE notifications SET morning = ?, evening = ?, currencies = ?, cities = ?
            WHERE user_id = ?
        ''', (new_morning, new_evening, new_currencies, new_cities, user_id))
        await db.commit()

async def get_all_subscribed_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id, morning, evening, currencies, cities FROM notifications WHERE morning = 1 OR evening = 1")
        return await cursor.fetchall()

# ========== ФУНКЦИИ ДЛЯ ОТПРАВКИ УВЕДОМЛЕНИЙ ==========

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
                    return f"{emoji} {city_name}: {data['main']['temp']:.1f}°C, {data['weather'][0]['description']}"
    except:
        pass
    return None

async def send_morning_notifications():
    """Утренняя рассылка в 9:00"""
    now = datetime.now(KZT_TZ)
    print(f"🌅 Отправка утренних уведомлений в {now.strftime('%H:%M')}")
    
    users = await get_all_subscribed_users()
    rates = await get_currency_rates()
    
    for user_id, morning, evening, currencies_str, cities_str in users:
        if not morning:
            continue
        
        currencies = currencies_str.split(',') if currencies_str else ['USD', 'EUR', 'RUB', 'CNY']
        cities = cities_str.split(',') if cities_str else []
        
        text = f"🌅 <b>Доброе утро!</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        text += f"<b>📈 Курсы валют на сегодня:</b>\n"
        for curr in currencies:
            if curr in rates:
                text += f"{curr}: {rates[curr]:.2f} ₸\n"
        
        if cities:
            text += f"\n<b>🌍 Погода в ваших городах:</b>\n"
            for city in cities:
                weather = await get_weather(city)
                if weather:
                    text += f"{weather}\n"
        
        text += f"\n<i>Хорошего дня!</i>"
        
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            print(f"✅ Утреннее уведомление отправлено {user_id}")
        except Exception as e:
            print(f"❌ Ошибка отправки {user_id}: {e}")

async def send_evening_notifications():
    """Вечерняя рассылка в 19:00"""
    now = datetime.now(KZT_TZ)
    print(f"🌙 Отправка вечерних уведомлений в {now.strftime('%H:%M')}")
    
    users = await get_all_subscribed_users()
    rates = await get_currency_rates()
    
    for user_id, morning, evening, currencies_str, cities_str in users:
        if not evening:
            continue
        
        currencies = currencies_str.split(',') if currencies_str else ['USD', 'EUR', 'RUB', 'CNY']
        cities = cities_str.split(',') if cities_str else []
        
        text = f"🌙 <b>Вечерний дайджест</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        text += f"<b>📈 Итоговые курсы валют:</b>\n"
        for curr in currencies:
            if curr in rates:
                text += f"{curr}: {rates[curr]:.2f} ₸\n"
        
        if cities:
            text += f"\n<b>🌍 Погода сейчас:</b>\n"
            for city in cities:
                weather = await get_weather(city)
                if weather:
                    text += f"{weather}\n"
        
        text += f"\n<i>Спокойной ночи!</i>"
        
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
            print(f"✅ Вечернее уведомление отправлено {user_id}")
        except Exception as e:
            print(f"❌ Ошибка отправки {user_id}: {e}")

# ========== НАСТРОЙКА УВЕДОМЛЕНИЙ ==========

@dp.message(F.text == "🔔 Уведомления")
async def notifications_menu_handler(message: types.Message):
    settings = await get_user_notification_settings(message.from_user.id)
    
    morning_status = "✅ Вкл" if settings["morning"] else "❌ Выкл"
    evening_status = "✅ Вкл" if settings["evening"] else "❌ Выкл"
    
    text = f"""
🔔 <b>НАСТРОЙКИ УВЕДОМЛЕНИЙ</b>
━━━━━━━━━━━━━━━━━━━━━

🌅 Утренние (9:00): {morning_status}
🌙 Вечерние (19:00): {evening_status}

<b>📊 Вы получаете:</b>
• Курсы валют: USD, EUR, RUB, CNY
• Погода в выбранных городах

Выберите режим уведомлений:
"""
    await message.answer(text, reply_markup=notifications_menu())

@dp.message(F.text == "🌅 Утренние (9:00)")
async def subscribe_morning(message: types.Message):
    await update_notification_settings(message.from_user.id, morning=True)
    await message.answer("✅ Вы подписались на <b>утренние</b> уведомления в 9:00!\n\nТеперь каждое утро вы будете получать курсы валют и погоду.", parse_mode="HTML")

@dp.message(F.text == "🌙 Вечерние (19:00)")
async def subscribe_evening(message: types.Message):
    await update_notification_settings(message.from_user.id, evening=True)
    await message.answer("✅ Вы подписались на <b>вечерние</b> уведомления в 19:00!\n\nКаждый вечер вы будете получать итоговые курсы валют и погоду.", parse_mode="HTML")

@dp.message(F.text == "⏰ И то и другое")
async def subscribe_both(message: types.Message):
    await update_notification_settings(message.from_user.id, morning=True, evening=True)
    await message.answer("✅ Вы подписались на <b>утренние и вечерние</b> уведомления!\n\nВы будете получать курсы валют и погоду в 9:00 и 19:00.", parse_mode="HTML")

@dp.message(F.text == "🔕 Отключить всё")
async def unsubscribe_all(message: types.Message):
    await update_notification_settings(message.from_user.id, morning=False, evening=False)
    await message.answer("✅ Все уведомления отключены!\n\nВы больше не будете получать утренние и вечерние рассылки. Включить можно в любое время в меню 'Уведомления'.", parse_mode="HTML")

@dp.message(F.text == "📋 Мои подписки")
async def show_subscriptions(message: types.Message):
    settings = await get_user_notification_settings(message.from_user.id)
    
    morning_status = "✅ Да" if settings["morning"] else "❌ Нет"
    evening_status = "✅ Да" if settings["evening"] else "❌ Нет"
    
    text = f"""
<b>📋 МОИ ПОДПИСКИ</b>
━━━━━━━━━━━━━━━━━━━━━

🌅 Утренние (9:00): {morning_status}
🌙 Вечерние (19:00): {evening_status}

<b>📊 Курсы валют:</b>
{', '.join(settings['currencies'])}

<b>🌍 Города для погоды:</b>
{', '.join(settings['cities']) if settings['cities'] else 'Не выбраны'}

━━━━━━━━━━━━━━━━━━━━━
<i>Для настройки используйте меню выше</i>
"""
    await message.answer(text, parse_mode="HTML")

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ ==========

async def get_game_balance(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT game_balance FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 10000

async def update_game_balance(user_id: int, amount: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET game_balance = game_balance + ? WHERE user_id = ?", (amount, user_id))
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
            return False, f"❌ У вас нет столько {currency}!"
        total_income = int(amount * price)
        await db.execute("UPDATE portfolio SET amount = amount - ? WHERE user_id = ? AND currency = ?", (amount, user_id, currency))
        await db.execute("UPDATE users SET game_balance = game_balance + ? WHERE user_id = ?", (total_income, user_id))
        await db.commit()
    return True, f"✅ Продано {amount} {currency} за {total_income} ₸"

async def get_portfolio(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT currency, amount FROM portfolio WHERE user_id = ? AND amount > 0", (user_id,))
        return await cursor.fetchall()

# ========== БОТ ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=KZT_TZ)

# ========== ЗАПУСК ПЛАНИРОВЩИКА ==========

def schedule_notifications():
    # Утренняя рассылка в 9:00
    scheduler.add_job(send_morning_notifications, 'cron', hour=9, minute=0, id='morning_notifications')
    # Вечерняя рассылка в 19:00
    scheduler.add_job(send_evening_notifications, 'cron', hour=19, minute=0, id='evening_notifications')
    scheduler.start()
    print("✅ Планировщик уведомлений запущен (9:00 и 19:00)")

# ========== КОМАНДЫ ==========

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
        f"• Настроить уведомления о курсах и погоде 🔔\n"
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
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число! Например: 100", reply_markup=currency_menu())
        await state.clear()

# ========== ПОГОДА ==========

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
    if weather:
        await message.answer(weather)
    else:
        await message.answer(f"❌ Ошибка погоды для {city}")

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
    text += f"🇨🇳 CNY: {rates['CNY']:.2f} ₸\n"
    await message.answer(text)

@dp.message(F.text == "🛒 Купить")
async def game_buy_start(message: types.Message, state: FSMContext):
    await state.set_state(GameState.buying)
    await message.answer("🛒 Введите: <code>USD 100</code>\n\nДоступны: USD, EUR, RUB, CNY")

@dp.message(GameState.buying)
async def game_buy(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=game_menu())
        return
    parts = message.text.upper().split()
    if len(parts) != 2:
        await message.answer("❌ Формат: USD 100")
        return
    currency = parts[0]
    try:
        amount = float(parts[1])
    except:
        await message.answer("❌ Введите число!")
        return
    rates = await get_currency_rates()
    if currency not in rates:
        await message.answer("❌ Доступны: USD, EUR, RUB, CNY")
        return
    result, msg = await buy_currency_game(message.from_user.id, currency, amount, rates[currency])
    await message.answer(msg)
    await state.clear()

@dp.message(F.text == "💸 Продать")
async def game_sell_start(message: types.Message, state: FSMContext):
    await state.set_state(GameState.selling)
    await message.answer("💸 Введите: <code>USD 100</code>\n\nДоступны: USD, EUR, RUB, CNY")

@dp.message(GameState.selling)
async def game_sell(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=game_menu())
        return
    parts = message.text.upper().split()
    if len(parts) != 2:
        await message.answer("❌ Формат: USD 100")
        return
    currency = parts[0]
    try:
        amount = float(parts[1])
    except:
        await message.answer("❌ Введите число!")
        return
    rates = await get_currency_rates()
    if currency not in rates:
        await message.answer("❌ Доступны: USD, EUR, RUB, CNY")
        return
    result, msg = await sell_currency_game(message.from_user.id, currency, amount, rates[currency])
    await message.answer(msg)
    await state.clear()

@dp.message(F.text == "📊 Портфель")
async def game_portfolio(message: types.Message):
    portfolio = await get_portfolio(message.from_user.id)
    balance = await get_game_balance(message.from_user.id)
    if not portfolio:
        await message.answer(f"📊 Портфель пуст\n💰 Баланс: {balance} ₸")
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
        text += "📭 Нет истории"
    await message.answer(text)

# ========== ПОМОЩЬ ==========

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    text = """
<b>📚 ПОМОЩЬ</b>
━━━━━━━━━━━━━━━━━━━━━

<b>💵 Курсы валют:</b>
• Выберите валюту → напишите сумму

<b>🌍 Погода:</b>
• Выберите страну → город

<b>🎮 Экономическая игра:</b>
• Покупайте и продавайте валюту

<b>🔔 Уведомления:</b>
• Включите утренние (9:00) и/или вечерние (19:00)
• Получайте курсы валют и погоду автоматически

<b>💡 Идея:</b>
• Напишите предложение

━━━━━━━━━━━━━━━━━━━━━
<i>Также можно написать: 100 USD</i>
"""
    await message.answer(text)

# ========== НАЗАД ==========

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

# ========== КОНВЕРТАЦИЯ ==========

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
    await message.answer(f"🔐 Админ-панель\n\n👥 Пользователей: {total}\n\n/ideas - идеи")

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

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота с уведомлениями...")
    await init_db()
    print("✅ База данных готова")
    schedule_notifications()
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print("📱 Уведомления будут отправляться в 9:00 и 19:00")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())