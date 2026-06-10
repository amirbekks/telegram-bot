import asyncio
import aiosqlite
import aiohttp
import re
from datetime import datetime, timedelta
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
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # Добавь в Railway Variables

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class AiChatState(StatesGroup):
    waiting_for_question = State()

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют")],
        [KeyboardButton(text="🌍 Погода"), KeyboardButton(text="🤖 ИИ помощник")],
        [KeyboardButton(text="🔔 Уведомления"), KeyboardButton(text="💡 Предложить идею")],
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
        [KeyboardButton(text="🌅 Утро 9:00"), KeyboardButton(text="🌙 Вечер 19:00")],
        [KeyboardButton(text="🔕 Отключить всё"), KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def weather_forecast_menu():
    buttons = [
        [KeyboardButton(text="🌡️ Сейчас"), KeyboardButton(text="📅 На сегодня (по часам)")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ВСЕ СТРАНЫ И ГОРОДА ==========

COUNTRIES = {
    "🇰🇿 Казахстан": ["Астана", "Алматы", "Шымкент", "Актау", "Караганда", "Уральск", "Атырау", "Павлодар"],
    "🇨🇳 Китай": ["Пекин", "Шанхай", "Гуанчжоу", "Сиань", "Чэнду", "Шэньчжэнь", "Гонконг"],
    "🇰🇬 Кыргызстан": ["Бишкек", "Ош", "Джалал-Абад", "Каракол", "Токмок", "Нарын"],
    "🇹🇭 Таиланд": ["Бангкок", "Пхукет", "Паттайя", "Чиангмай", "Краби", "Самуи", "Хуахин"],
    "🇹🇷 Турция": ["Стамбул", "Анкара", "Анталья", "Измир", "Бодрум", "Каппадокия", "Мармарис", "Кемер"],
    "🇦🇪 ОАЭ": ["Дубай", "Абу-Даби", "Шарджа", "Рас-эль-Хайма", "Фуджейра"],
    "🇪🇬 Египет": ["Каир", "Хургада", "Шарм-эль-Шейх", "Луксор", "Марса-Алам"],
    "🇮🇳 Индия": ["Дели", "Гоа", "Мумбаи", "Джайпур", "Агра", "Керала"]
}

def weather_countries_menu():
    buttons = [[KeyboardButton(text=country)] for country in COUNTRIES.keys()]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== КООРДИНАТЫ ВСЕХ ГОРОДОВ ==========

COORDS = {
    "Астана": (51.1694, 71.4491), "Алматы": (43.2565, 76.9286),
    "Шымкент": (42.3417, 69.5901), "Актау": (43.6532, 51.1552),
    "Караганда": (49.8014, 73.1021), "Уральск": (51.2167, 51.3667),
    "Атырау": (47.1167, 51.8833), "Павлодар": (52.2875, 76.9733),
    "Пекин": (39.9042, 116.4074), "Шанхай": (31.2304, 121.4737),
    "Гуанчжоу": (23.1291, 113.2644), "Сиань": (34.3416, 108.9402),
    "Чэнду": (30.5728, 104.0668), "Шэньчжэнь": (22.5431, 114.0579),
    "Гонконг": (22.3193, 114.1694), "Бишкек": (42.8746, 74.5698),
    "Ош": (40.5149, 72.8166), "Джалал-Абад": (40.9334, 73.0027),
    "Каракол": (42.4907, 78.3936), "Токмок": (42.8373, 75.2930),
    "Нарын": (41.4286, 75.9911), "Бангкок": (13.7367, 100.5231),
    "Пхукет": (7.8804, 98.3923), "Паттайя": (12.9236, 100.8825),
    "Чиангмай": (18.7883, 98.9853), "Краби": (8.0863, 98.9069),
    "Самуи": (9.5120, 100.0136), "Хуахин": (12.5683, 99.9578),
    "Стамбул": (41.0082, 28.9784), "Анкара": (39.9334, 32.8597),
    "Анталья": (36.8969, 30.7133), "Измир": (38.4192, 27.1287),
    "Бодрум": (37.0344, 27.4305), "Каппадокия": (38.6435, 34.8289),
    "Мармарис": (36.8554, 28.2765), "Кемер": (36.6001, 30.5606),
    "Дубай": (25.2048, 55.2708), "Абу-Даби": (24.4539, 54.3773),
    "Шарджа": (25.3463, 55.4209), "Рас-эль-Хайма": (25.7895, 55.9432),
    "Фуджейра": (25.1288, 56.3265), "Каир": (30.0444, 31.2357),
    "Хургада": (27.2574, 33.8128), "Шарм-эль-Шейх": (27.9158, 34.33),
    "Луксор": (25.6809, 32.6394), "Марса-Алам": (25.0663, 34.8961),
    "Дели": (28.6139, 77.2090), "Гоа": (15.2993, 74.1240),
    "Мумбаи": (19.0760, 72.8777), "Джайпур": (26.9124, 75.7873),
    "Агра": (27.1767, 78.0081), "Керала": (10.8505, 76.2711)
}

# ========== КЭШ ДЛЯ КУРСОВ ВАЛЮТ (ОБНОВЛЯЕТСЯ КАЖДЫЙ ЧАС) ==========
cached_rates = None
last_rate_update = None

async def get_currency_rates():
    global cached_rates, last_rate_update
    
    # Обновляем раз в час
    if cached_rates and last_rate_update and (datetime.now() - last_rate_update).seconds < 3600:
        return cached_rates
    
    try:
        async with aiohttp.ClientSession() as session:
            # Пробуем несколько источников для актуальных курсов
            sources = [
                'https://www.nationalbank.kz/ru/exchangerates/exportrates/?periodic=0&format=xml',
                'https://api.exchangerate-api.com/v4/latest/USD'
            ]
            
            for url in sources:
                async with session.get(url) as response:
                    if response.status == 200:
                        if 'nationalbank' in url:
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
                                cached_rates = rates
                                last_rate_update = datetime.now()
                                return rates
                        else:
                            data = await response.json()
                            usd_to_kzt = 485.50  # Базовый курс
                            cached_rates = {
                                'USD': usd_to_kzt,
                                'EUR': usd_to_kzt * data.get('rates', {}).get('EUR', 0.92),
                                'RUB': usd_to_kzt * data.get('rates', {}).get('RUB', 0.011) * 10,
                                'CNY': usd_to_kzt * data.get('rates', {}).get('CNY', 7.2)
                            }
                            last_rate_update = datetime.now()
                            return cached_rates
    except:
        pass
    
    # Если всё упало, возвращаем последние сохранённые курсы или тестовые
    if cached_rates:
        return cached_rates
    return {'USD': 485.50, 'EUR': 565.80, 'RUB': 6.85, 'CNY': 72.50}

# ========== ПОГОДА (КАЖДЫЙ ЧАС) ==========

async def get_current_weather(city_name: str):
    lat, lon = COORDS.get(city_name, (51.1694, 71.4491))
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    weather_id = data['weather'][0]['id']
                    if 200 <= weather_id < 300:
                        emoji = "⛈️"
                    elif 300 <= weather_id < 600:
                        emoji = "🌧️"
                    elif 600 <= weather_id < 700:
                        emoji = "❄️"
                    elif weather_id == 800:
                        emoji = "☀️"
                    elif weather_id == 801:
                        emoji = "🌤️"
                    elif 802 <= weather_id < 900:
                        emoji = "☁️"
                    else:
                        emoji = "🌡️"
                    
                    wind_kmh = data['wind']['speed'] * 3.6
                    
                    return f"""
{emoji} <b>{city_name}</b> — сейчас
━━━━━━━━━━━━━━━━━━━━━

🌡️ <b>Температура:</b> {data['main']['temp']:.1f}°C
🎯 <b>Ощущается как:</b> {data['main']['feels_like']:.1f}°C

💧 <b>Влажность:</b> {data['main']['humidity']}%
🌬️ <b>Ветер:</b> {wind_kmh:.1f} км/ч

📝 <b>Описание:</b> {data['weather'][0]['description'].capitalize()}

━━━━━━━━━━━━━━━━━━━━━
🕐 <i>Обновлено: {datetime.now().strftime('%H:%M:%S')}</i>
"""
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:50]}"

async def get_hourly_forecast(city_name: str):
    """Прогноз на 24 часа (каждый час)"""
    lat, lon = COORDS.get(city_name, (51.1694, 71.4491))
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru&cnt=24"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    result = f"""
🌤️ <b>{city_name}</b> — прогноз на сегодня (по часам)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
                    temps = []
                    rain_probs = []
                    
                    for item in data['list'][:24]:  # 24 часа (каждый час)
                        dt = datetime.fromtimestamp(item['dt'])
                        hour = dt.strftime('%H:%M')
                        temp = item['main']['temp']
                        rain_prob = item.get('pop', 0) * 100
                        weather_id = item['weather'][0]['id']
                        
                        if 200 <= weather_id < 300:
                            cond = "⛈️"
                        elif 300 <= weather_id < 600:
                            cond = "🌧️"
                        elif weather_id == 800:
                            cond = "☀️"
                        elif weather_id == 801:
                            cond = "🌤️"
                        else:
                            cond = "☁️"
                        
                        rain_icon = "💧" if rain_prob > 0 else "  "
                        result += f"<b>{hour}</b>  {temp:.1f}°C  {cond}  {rain_icon}{rain_prob:.0f}%\n"
                        
                        temps.append(temp)
                        rain_probs.append(rain_prob)
                    
                    avg_temp = sum(temps) / len(temps) if temps else 0
                    max_rain = max(rain_probs) if rain_probs else 0
                    max_temp = max(temps) if temps else 0
                    min_temp = min(temps) if temps else 0
                    
                    result += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>Сводка на день:</b>
🌡️ Средняя: {avg_temp:.1f}°C (макс {max_temp:.1f}°C / мин {min_temp:.1f}°C)
💧 Макс. вероятность осадков: {max_rain:.0f}%
"""
                    if max_rain > 50:
                        result += "☂️ <i>Не забудьте зонт!</i>"
                    elif max_rain > 20:
                        result += "🌂 <i>Возможен небольшой дождь</i>"
                    else:
                        result += "😎 <i>Отличная погода!</i>"
                    
                    return result
    except Exception as e:
        return f"❌ Ошибка прогноза: {str(e)[:50]}"

# ========== ИИ ПОМОЩНИК (CHATGPT) ==========

async def ask_ai(question: str):
    if not OPENAI_API_KEY:
        return "🤖 ИИ помощник временно недоступен. API ключ не настроен."
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": question}],
                "max_tokens": 500,
                "temperature": 0.7
            }
            
            async with session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content']
                else:
                    return "❌ Ошибка связи с ИИ. Попробуйте позже."
    except Exception as e:
        return f"❌ Ошибка: {str(e)[:100]}"

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

# ========== РАССЫЛКА ==========

async def send_morning():
    users = await get_all_subscribed()
    rates = await get_currency_rates()
    
    text = f"🌅 <b>Доброе утро!</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n<b>💰 Курсы валют:</b>\n"
    for curr, rate in rates.items():
        text += f"{curr}: {rate:.2f} ₸\n"
    text += f"\n<i>Хорошего дня!</i>"
    
    for user_id in users:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
        except:
            pass

async def send_evening():
    users = await get_all_subscribed()
    rates = await get_currency_rates()
    
    text = f"🌙 <b>Вечерний дайджест</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n<b>💰 Курсы валют:</b>\n"
    for curr, rate in rates.items():
        text += f"{curr}: {rate:.2f} ₸\n"
    text += f"\n<i>Спокойной ночи!</i>"
    
    for user_id in users:
        try:
            await bot.send_message(user_id, text, parse_mode="HTML")
        except:
            pass

# ========== ПЕРЕМЕННАЯ ДЛЯ ВЫБОРА ГОРОДА ==========

selected_city = {}

# ========== БОТ ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Обновление курсов каждый час
async def update_rates():
    await get_currency_rates()
    print(f"✅ Курсы валют обновлены в {datetime.now().strftime('%H:%M:%S')}")

# ========== КОМАНДЫ ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🇰🇿 <b>Мой бот поможет:</b>\n"
        f"• Узнать актуальные курсы валют 💵\n"
        f"• Посмотреть погоду сейчас или на сегодня (каждый час) 🌤️\n"
        f"• Спросить у ИИ помощника 🤖\n"
        f"• Настроить уведомления 🔔\n"
        f"• Предложить идею для улучшения бота 💡\n\n"
        f"⬇️ <b>Выберите действие:</b>",
        reply_markup=main_menu()
    )

@dp.message(F.text == "💵 Курсы валют")
async def show_currencies(message: types.Message):
    rates = await get_currency_rates()
    text = f"<b>💵 АКТУАЛЬНЫЕ КУРСЫ ВАЛЮТ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🇺🇸 USD / KZT → <code>{rates['USD']:.2f}</code> ₸\n"
    text += f"🇪🇺 EUR / KZT → <code>{rates['EUR']:.2f}</code> ₸\n"
    text += f"🇷🇺 RUB / KZT → <code>{rates['RUB']:.2f}</code> ₸\n"
    text += f"🇨🇳 CNY / KZT → <code>{rates['CNY']:.2f}</code> ₸\n\n"
    text += f"<i>Курсы обновляются каждый час</i>\n"
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
                f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>\n"
                f"📊 1 {currency} = {rates[currency]:.2f} ₸",
                reply_markup=currency_menu()
            )
        await state.clear()
    except:
        await message.answer("❌ Введите число!", reply_markup=currency_menu())
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
    await message.answer(f"🏙 <b>Города {country}:</b>\n\nВыберите город:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.in_(COORDS.keys()))
async def city_selected(message: types.Message):
    city = message.text
    selected_city[message.from_user.id] = city
    await message.answer(
        f"🏙️ <b>{city}</b>\n\nЧто хотите узнать?",
        reply_markup=weather_forecast_menu()
    )

@dp.message(F.text == "🌡️ Сейчас")
async def get_current(message: types.Message):
    city = selected_city.get(message.from_user.id)
    if not city:
        await message.answer("❌ Пожалуйста, выберите город сначала через кнопку '🌍 Погода'")
        return
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    weather = await get_current_weather(city)
    await message.answer(weather, parse_mode="HTML")

@dp.message(F.text == "📅 На сегодня (по часам)")
async def get_hourly(message: types.Message):
    city = selected_city.get(message.from_user.id)
    if not city:
        await message.answer("❌ Пожалуйста, выберите город сначала через кнопку '🌍 Погода'")
        return
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    forecast = await get_hourly_forecast(city)
    await message.answer(forecast, parse_mode="HTML")

# ========== ИИ ПОМОЩНИК ==========

@dp.message(F.text == "🤖 ИИ помощник")
async def ai_start(message: types.Message, state: FSMContext):
    await state.set_state(AiChatState.waiting_for_question)
    await message.answer(
        "🤖 <b>ИИ помощник</b>\n\n"
        "Задайте любой вопрос. Я помогу!\n"
        "Например:\n"
        "• Какой курс доллара был вчера?\n"
        "• Что такое тенге?\n"
        "• Какая погода будет завтра в Алматы?\n\n"
        "<i>/cancel - отмена</i>",
        parse_mode="HTML"
    )

@dp.message(AiChatState.waiting_for_question)
async def ai_ask(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())
        return
    
    await message.bot.send_chat_action(message.chat.id, "typing")
    response = await ask_ai(message.text)
    await message.answer(response, parse_mode="HTML")
    await state.clear()

# ========== ПРЕДЛОЖИТЬ ИДЕЮ ==========

@dp.message(F.text == "💡 Предложить идею")
async def idea_start(message: types.Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer(
        "💡 <b>Предложить идею для улучшения бота</b>\n\n"
        "Напишите вашу идею или предложение:\n"
        "• Что добавить?\n"
        "• Что улучшить?\n"
        "• Какие функции нужны?\n\n"
        "<i>/cancel - отмена</i>",
        parse_mode="HTML"
    )

@dp.message(IdeaState.waiting_for_idea)
async def idea_save(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())
        return
    
    user = message.from_user
    await save_idea(user.id, user.username or "no_username", message.text)
    
    # Отправляем админу с пометкой "ИДЕЯ ДЛЯ УЛУЧШЕНИЯ"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💡 <b>ИДЕЯ ДЛЯ УЛУЧШЕНИЯ БОТА!</b>\n\n"
            f"👤 От: {user.full_name}\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"📱 Username: @{user.username or 'нет'}\n\n"
            f"📝 <b>Идея:</b>\n{message.text}\n\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            parse_mode="HTML"
        )
        await message.answer(
            "💡 <b>Спасибо за вашу идею!</b>\n\n"
            "Она отправлена администратору и будет рассмотрена.\n"
            "Лучшие идеи будут реализованы в следующих обновлениях! 🚀",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    except:
        await message.answer("✅ Спасибо! Идея сохранена.", reply_markup=main_menu())
    
    await state.clear()

# ========== УВЕДОМЛЕНИЯ ==========

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

@dp.message(F.text == "🌅 Утро 9:00")
async def enable_morning(message: types.Message):
    await update_notifications(message.from_user.id, morning=True)
    await message.answer("✅ Утренние уведомления ВКЛЮЧЕНЫ! В 9:00 будет приходить курс валют.")

@dp.message(F.text == "🌙 Вечер 19:00")
async def enable_evening(message: types.Message):
    await update_notifications(message.from_user.id, evening=True)
    await message.answer("✅ Вечерние уведомления ВКЛЮЧЕНЫ! В 19:00 будет приходить курс валют.")

@dp.message(F.text == "🔕 Отключить всё")
async def disable_all(message: types.Message):
    await update_notifications(message.from_user.id, morning=False, evening=False)
    await message.answer("✅ Все уведомления ОТКЛЮЧЕНЫ!")

# ========== ПОМОЩЬ ==========

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    await message.answer(
        "<b>📚 ПОМОЩЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>💵 Курсы валют:</b>\n"
        "• Выберите валюту → напишите сумму\n"
        "• Курсы обновляются каждый час\n\n"
        "<b>🌤️ Погода:</b>\n"
        "• Выберите страну → город\n"
        "• Затем выберите: 'Сейчас' или 'На сегодня (по часам)'\n"
        "• Прогноз показывает температуру и вероятность осадков КАЖДЫЙ ЧАС\n\n"
        "<b>🤖 ИИ помощник:</b>\n"
        "• Задайте любой вопрос\n"
        "• ChatGPT ответит вам\n\n"
        "<b>🔔 Уведомления:</b>\n"
        "• Включите утренние (9:00) и/или вечерние (19:00)\n\n"
        "<b>💡 Предложить идею:</b>\n"
        "• Напишите предложение по улучшению бота\n\n"
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
    await message.answer(f"🔐 Админ-панель\n\n👥 Пользователей: {total}\n\n/ideas - просмотр идей")

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
    
    text = "💡 <b>ИДЕИ ДЛЯ УЛУЧШЕНИЯ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for idea in ideas:
        text += f"#{idea[0]} | @{idea[1] or 'anon'}\n📝 {idea[2][:150]}\n🕐 {idea[3][:16]}\n━━━━━━━━━━━━━━━━━━━━━\n"
    await message.answer(text, parse_mode="HTML")

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота...")
    await init_db()
    print("✅ База данных готова")
    
    # Запускаем обновление курсов каждый час
    scheduler.add_job(update_rates, 'interval', hours=1)
    scheduler.add_job(send_morning, 'cron', hour=9, minute=0, id='morning')
    scheduler.add_job(send_evening, 'cron', hour=19, minute=0, id='evening')
    scheduler.start()
    print("✅ Планировщик запущен")
    print("   • Курсы валют обновляются каждый час")
    print("   • Утренние уведомления в 9:00")
    print("   • Вечерние уведомления в 19:00")
    
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())