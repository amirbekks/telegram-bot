import asyncio
import aiosqlite
import aiohttp
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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
        [KeyboardButton(text="👥 Список пользователей"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🚫 Забанить пользователя"), KeyboardButton(text="✅ Разбанить")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="💡 Идеи пользователей")],
        [KeyboardButton(text="🔙 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ВСЕ СТРАНЫ И ГОРОДА ==========

COUNTRIES = {
    "🇰🇿 Казахстан": ["Астана", "Алматы", "Шымкент", "Актау", "Караганда", "Уральск", "Атырау", "Павлодар", "Көкшетау"],
    "🇨🇳 Китай": ["Пекин", "Шанхай", "Гуанчжоу", "Сиань"],
    "🇰🇬 Кыргызстан": ["Бишкек", "Ош"],
    "🇹🇭 Таиланд": ["Бангкок", "Пхукет", "Паттайя"],
    "🇹🇷 Турция": ["Стамбул", "Анталья", "Анкара"],
    "🇦🇪 ОАЭ": ["Дубай", "Абу-Даби"],
    "🇪🇬 Египет": ["Каир", "Хургада"],
    "🇮🇳 Индия": ["Дели", "Гоа"]
}

def weather_countries_menu():
    buttons = [[KeyboardButton(text=country)] for country in COUNTRIES.keys()]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def weather_forecast_menu():
    buttons = [
        [KeyboardButton(text="🌡️ Сейчас"), KeyboardButton(text="📅 Почасовой прогноз")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

CITY_ENGLISH = {
    "Астана": "Astana", "Алматы": "Almaty", "Шымкент": "Shymkent",
    "Актау": "Aktau", "Караганда": "Karaganda", "Уральск": "Uralsk",
    "Атырау": "Atyrau", "Павлодар": "Pavlodar", "Көкшетау": "Kokshetau",
    "Пекин": "Beijing", "Шанхай": "Shanghai", "Гуанчжоу": "Guangzhou",
    "Сиань": "Xian", "Бишкек": "Bishkek", "Ош": "Osh",
    "Бангкок": "Bangkok", "Пхукет": "Phuket", "Паттайя": "Pattaya",
    "Стамбул": "Istanbul", "Анталья": "Antalya", "Анкара": "Ankara",
    "Дубай": "Dubai", "Абу-Даби": "Abu Dhabi", "Каир": "Cairo",
    "Хургада": "Hurghada", "Дели": "Delhi", "Гоа": "Goa"
}

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
                                rate = float(text[rate_start:rate_end])
                                if code == 'RUB' and rate > 100:
                                    rate = rate / 10
                                rates[code] = rate
                            except:
                                rates[code] = 0
                    if rates.get('USD') and rates['USD'] > 0:
                        return rates
    except:
        pass
    return {'USD': 485.50, 'EUR': 565.80, 'RUB': 6.85, 'CNY': 72.50}

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
                    condition = current['condition']['text'].lower()
                    if 'ясно' in condition or 'солнечно' in condition:
                        emoji = "☀️"
                    elif 'облачно' in condition:
                        emoji = "☁️"
                    elif 'дождь' in condition:
                        emoji = "🌧️"
                    elif 'снег' in condition:
                        emoji = "❄️"
                    else:
                        emoji = "🌡️"
                    return f"""
{emoji} <b>{city_name}</b> — сейчас
━━━━━━━━━━━━━━━━━━━━━

🌡️ <b>Температура:</b> {current['temp_c']:.1f}°C
🎯 <b>Ощущается как:</b> {current['feelslike_c']:.1f}°C

💧 <b>Влажность:</b> {current['humidity']}%
🌬️ <b>Ветер:</b> {current['wind_kph']:.1f} км/ч

📝 <b>Описание:</b> {current['condition']['text']}

━━━━━━━━━━━━━━━━━━━━━
🕐 <i>Обновлено: {current['last_updated'][-5:]}</i>
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
                    result = f"""
🌤️ <b>{city_name}</b> — почасовой прогноз на сегодня
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
                    temps = []
                    rain_chances = []
                    for hour_data in forecast[:24]:
                        hour = hour_data['time'].split()[-1][:5]
                        temp = hour_data['temp_c']
                        rain_chance = hour_data.get('chance_of_rain', 0)
                        condition = hour_data['condition']['text'].lower()
                        if 'ясно' in condition or 'солнечно' in condition:
                            cond_icon = "☀️"
                        elif 'облачно' in condition:
                            cond_icon = "☁️"
                        elif 'дождь' in condition:
                            cond_icon = "🌧️"
                        else:
                            cond_icon = "🌡️"
                        rain_icon = "💧" if rain_chance > 0 else "  "
                        result += f"<b>{hour}</b>  {temp:.1f}°C  {cond_icon}  {rain_icon}{rain_chance:.0f}%\n"
                        temps.append(temp)
                        rain_chances.append(rain_chance)
                    avg_temp = sum(temps) / len(temps) if temps else 0
                    max_rain = max(rain_chances) if rain_chances else 0
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
    except:
        return f"❌ Ошибка прогноза для {city_name}"

# ========== БАЗА ДАННЫХ ==========

async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        # Таблица пользователей (добавляем поле is_banned)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT
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

async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] == 1 if result else False

async def get_all_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id, username, full_name, registered_at, is_banned FROM users ORDER BY registered_at DESC")
        return await cursor.fetchall()

async def ban_user(user_id: int, reason: str = None):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?", (reason, user_id))
        await db.commit()

async def unban_user(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?", (user_id,))
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
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_banned_users_count():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        result = await cursor.fetchone()
        return result[0] if result else 0

async def get_all_ideas():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT id, user_id, username, idea_text, created_at FROM ideas ORDER BY id DESC")
        return await cursor.fetchall()

async def get_all_unbanned_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
        return [row[0] for row in await cursor.fetchall()]

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

async def send_morning():
    users = await get_all_subscribed()
    rates = await get_currency_rates()
    text = f"🌅 <b>Доброе утро!</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n<b>💰 Курсы валют:</b>\n"
    for curr, rate in rates.items():
        text += f"{curr}: {rate:.2f} ₸\n"
    for user_id in users:
        if not await is_user_banned(user_id):
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
    for user_id in users:
        if not await is_user_banned(user_id):
            try:
                await bot.send_message(user_id, text, parse_mode="HTML")
            except:
                pass

# Middleware для проверки бана
@dp.message()
async def check_ban(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("🚫 <b>Вы забанены!</b>\n\nВы не можете использовать этого бота.\nПричина: нарушение правил.", parse_mode="HTML")
        return
    await state.update_data()  # Просто пропускаем

# ========== БОТ ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

selected_city = {}

async def update_rates():
    await get_currency_rates()
    print(f"✅ Курсы обновлены в {datetime.now().strftime('%H:%M:%S')}")

# ========== АДМИН КОМАНДЫ ==========

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен. Вы не администратор!")
        return
    await message.answer(
        "🔐 <b>АДМИН-ПАНЕЛЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=admin_menu()
    )

@dp.message(F.text == "👥 Список пользователей")
async def list_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    total = await get_total_users()
    banned = await get_banned_users_count()
    
    text = f"👥 <b>ПОЛЬЗОВАТЕЛИ БОТА</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"📊 Всего: {len(users)} пользователей\n"
    text += f"✅ Активных: {total}\n"
    text += f"🚫 Забаненных: {banned}\n\n"
    text += "<b>📋 Список (последние 20):</b>\n"
    
    for user in users[:20]:
        user_id, username, full_name, reg_date, is_banned = user
        status = "🚫 ЗАБАНЕН" if is_banned else "✅ АКТИВЕН"
        text += f"\n🆔 <code>{user_id}</code> | {status}\n"
        text += f"👤 {full_name} | @{username or 'нет'}\n"
        text += f"📅 Зарегистрирован: {reg_date[:16]}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━\n"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    total_users = await get_total_users()
    banned_users = await get_banned_users_count()
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM ideas")
        total_ideas = (await cursor.fetchone())[0]
        
        cursor = await db.execute("SELECT COUNT(*) FROM history")
        total_conversions = (await cursor.fetchone())[0]
        
        # Зарегистрировались сегодня
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE DATE(registered_at) = DATE('now')")
        new_today = (await cursor.fetchone())[0]
    
    text = f"""
📊 <b>РАСШИРЕННАЯ СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👥 <b>ПОЛЬЗОВАТЕЛИ:</b>
├ ✅ Активных: {total_users}
├ 🚫 Забаненных: {banned_users}
├ 🆕 Новых сегодня: {new_today}
└ 📅 Всего регистраций: {total_users + banned_users}

💡 <b>АКТИВНОСТЬ:</b>
├ 💡 Идей получено: {total_ideas}
└ 💱 Конвертаций совершено: {total_conversions}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Данные обновлены в реальном времени</i>
"""
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🚫 Забанить пользователя")
async def ban_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BanState.waiting_for_user_id)
    await message.answer(
        "🚫 <b>ЗАБАНИТЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        "Введите ID пользователя (можно скопировать из списка):\n"
        "Пример: <code>123456789</code>\n\n"
        "<i>После этого введите причину бана</i>",
        parse_mode="HTML"
    )

@dp.message(BanState.waiting_for_user_id)
async def ban_user_id(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await message.answer("📝 Напишите причину бана (например: 'Спам'):")
        await state.set_state(BanState.waiting_for_reason)
    except:
        await message.answer("❌ Неверный ID! Введите число.")

@dp.message(BanState.waiting_for_reason)
async def ban_user_reason(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    user_id = data.get('user_id')
    reason = message.text
    
    await ban_user(user_id, reason)
    
    try:
        await bot.send_message(user_id, f"🚫 <b>Вас заблокировали в боте!</b>\n\nПричина: {reason}\n\nЕсли считаете это ошибкой, свяжитесь с администратором.", parse_mode="HTML")
    except:
        pass
    
    await message.answer(f"✅ Пользователь <code>{user_id}</code> ЗАБАНЕН!\nПричина: {reason}", parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "✅ Разбанить")
async def unban_user_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🚫 <b>РАЗБАНИТЬ ПОЛЬЗОВАТЕЛЯ</b>\n\nВведите ID пользователя для разбана:\nПример: <code>123456789</code>", parse_mode="HTML")
    
    @dp.message()
    async def unban_user_id(msg: types.Message):
        if msg.from_user.id != ADMIN_ID:
            return
        try:
            user_id = int(msg.text)
            await unban_user(user_id)
            try:
                await bot.send_message(user_id, "✅ <b>Вы разбанены в боте!</b>\n\nТеперь вы снова можете пользоваться всеми функциями.", parse_mode="HTML")
            except:
                pass
            await msg.answer(f"✅ Пользователь <code>{user_id}</code> РАЗБАНЕН!", parse_mode="HTML")
            dp.message.handlers.remove(unban_user_id)
        except:
            await msg.answer("❌ Неверный ID!")

@dp.message(F.text == "📢 Рассылка")
async def broadcast_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📢 <b>РАССЫЛКА</b>\n\nОтправьте сообщение для рассылки ВСЕМ пользователям бота (кроме забаненных):\n\n<i>/cancel - отмена</i>", parse_mode="HTML")
    
    @dp.message()
    async def broadcast_send(msg: types.Message):
        if msg.from_user.id != ADMIN_ID:
            return
        if msg.text == "/cancel":
            await msg.answer("❌ Рассылка отменена")
            dp.message.handlers.remove(broadcast_send)
            return
        
        users = await get_all_unbanned_users()
        success = 0
        fail = 0
        
        await msg.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")
        
        for user_id in users:
            try:
                await bot.send_message(user_id, f"📢 <b>РАССЫЛКА ОТ АДМИНИСТРАТОРА</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n{msg.text}", parse_mode="HTML")
                success += 1
                await asyncio.sleep(0.05)
            except:
                fail += 1
        
        await msg.answer(f"✅ <b>РАССЫЛКА ЗАВЕРШЕНА!</b>\n\n📨 Отправлено: {success}\n❌ Ошибок: {fail}", parse_mode="HTML")
        dp.message.handlers.remove(broadcast_send)

@dp.message(F.text == "💡 Идеи пользователей")
async def admin_ideas(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    ideas = await get_all_ideas()
    if not ideas:
        await message.answer("📭 Нет идей от пользователей")
        return
    
    text = "💡 <b>ИДЕИ ПОЛЬЗОВАТЕЛЕЙ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for idea in ideas[:20]:
        idea_id, user_id, username, idea_text, created_at = idea
        text += f"#{idea_id} | от @{username or user_id}\n"
        text += f"📝 {idea_text[:150]}\n"
        text += f"🕐 {created_at[:16]}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━\n"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

# ========== ОБЫЧНЫЕ КОМАНДЫ ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if await is_user_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены!")
        return
    
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🇰🇿 <b>Мой бот поможет:</b>\n"
        f"• Узнать актуальные курсы валют 💵\n"
        f"• Посмотреть погоду сейчас или почасовой прогноз 🌤️\n"
        f"• Настроить уведомления 🔔\n"
        f"• Предложить идею для улучшения бота 💡\n\n"
        f"⬇️ <b>Выберите действие:</b>",
        reply_markup=main_menu()
    )

@dp.message(F.text == "💵 Курсы валют")
async def show_currencies(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    rates = await get_currency_rates()
    text = f"<b>💵 АКТУАЛЬНЫЕ КУРСЫ ВАЛЮТ НБ РК</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += f"🇺🇸 <b>USD / KZT</b> → <code>{rates['USD']:.2f}</code> ₸\n"
    text += f"🇪🇺 <b>EUR / KZT</b> → <code>{rates['EUR']:.2f}</code> ₸\n"
    text += f"🇷🇺 <b>RUB / KZT</b> → <code>{rates['RUB']:.2f}</code> ₸\n"
    text += f"🇨🇳 <b>CNY / KZT</b> → <code>{rates['CNY']:.2f}</code> ₸\n\n"
    text += f"<i>Нажмите на валюту для конвертации</i>"
    await message.answer(text, reply_markup=currency_menu())

@dp.message(F.text.in_(["🇺🇸 USD → KZT", "🇪🇺 EUR → KZT", "🇷🇺 RUB → KZT", "🇨🇳 CNY → KZT"]))
async def convert_start(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    currency_map = {"🇺🇸 USD → KZT": "USD", "🇪🇺 EUR → KZT": "EUR", "🇷🇺 RUB → KZT": "RUB", "🇨🇳 CNY → KZT": "CNY"}
    currency = currency_map[message.text]
    await state.update_data(currency=currency)
    await state.set_state(ConvertState.waiting_for_amount)
    await message.answer(f"💱 <b>Конвертация {currency} → KZT</b>\n\nВведите сумму:")

@dp.message(ConvertState.waiting_for_amount)
async def convert_amount(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        currency = data.get('currency')
        rates = await get_currency_rates()
        if currency in rates:
            result = amount * rates[currency]
            await save_history(message.from_user.id, currency, amount, result)
            await message.answer(f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>", reply_markup=currency_menu())
        await state.clear()
    except:
        await message.answer("❌ Введите число!", reply_markup=currency_menu())
        await state.clear()

@dp.message(F.text == "🌍 Погода")
async def weather_countries(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    await message.answer("🌍 <b>Выберите страну:</b>", reply_markup=weather_countries_menu())

@dp.message(F.text.in_(COUNTRIES.keys()))
async def show_cities(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    country = message.text
    cities = COUNTRIES[country]
    buttons = [[KeyboardButton(text=city)] for city in cities]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer(f"🏙 <b>Города {country}:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.in_(CITY_ENGLISH.keys()))
async def city_selected(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    city = message.text
    selected_city[message.from_user.id] = city
    await message.answer(f"🏙️ <b>{city}</b>\n\nЧто хотите узнать?", reply_markup=weather_forecast_menu())

@dp.message(F.text == "🌡️ Сейчас")
async def get_current(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    city = selected_city.get(message.from_user.id)
    if not city:
        await message.answer("❌ Выберите город через '🌍 Погода'")
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    weather = await get_current_weather(city)
    await message.answer(weather, parse_mode="HTML")

@dp.message(F.text == "📅 Почасовой прогноз")
async def get_hourly(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    city = selected_city.get(message.from_user.id)
    if not city:
        await message.answer("❌ Выберите город через '🌍 Погода'")
        return    await message.bot.send_chat_action(message.chat.id, "typing")
    forecast = await get_hourly_forecast(city)
    await message.answer(forecast, parse_mode="HTML")

@dp.message(F.text == "💡 Предложить идею")
async def idea_start(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer("💭 Напишите вашу идею для улучшения бота:\n\n/cancel - отмена")

@dp.message(IdeaState.waiting_for_idea)
async def idea_save(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())
        return
    user = message.from_user
    await save_idea(user.id, user.username or "no_username", message.text)
    try:
        await bot.send_message(ADMIN_ID, f"💡 НОВАЯ ИДЕЯ!\n\nОт: {user.full_name}\nID: {user.id}\n\n{message.text}")
        await message.answer("✅ Спасибо! Идея отправлена администратору.", reply_markup=main_menu())
    except:
        await message.answer("✅ Спасибо! Идея сохранена.", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "🔔 Уведомления")
async def notifications_menu_handler(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    settings = await get_notification_settings(message.from_user.id)
    await message.answer(
        f"🔔 <b>Уведомления</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌅 Утро (9:00): {'✅ Вкл' if settings['morning'] else '❌ Выкл'}\n"
        f"🌙 Вечер (19:00): {'✅ Вкл' if settings['evening'] else '❌ Выкл'}\n\n"
        f"<i>Выберите действие:</i>",
        reply_markup=notifications_menu()
    )

@dp.message(F.text == "🌅 Утро 9:00")
async def enable_morning(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    await update_notifications(message.from_user.id, morning=True)
    await message.answer("✅ Утренние уведомления ВКЛЮЧЕНЫ!")

@dp.message(F.text == "🌙 Вечер 19:00")
async def enable_evening(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    await update_notifications(message.from_user.id, evening=True)
    await message.answer("✅ Вечерние уведомления ВКЛЮЧЕНЫ!")

@dp.message(F.text == "🔕 Отключить всё")
async def disable_all(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    await update_notifications(message.from_user.id, morning=False, evening=False)
    await message.answer("✅ Все уведомления ОТКЛЮЧЕНЫ!")

@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    await message.answer(
        "<b>📚 ПОМОЩЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>💵 Курсы валют:</b>\n• Выберите валюту → напишите сумму\n\n"
        "<b>🌤️ Погода:</b>\n• Выберите страну → город\n• 'Сейчас' - текущая погода\n• 'Почасовой прогноз' - на 24 часа\n\n"
        "<b>🔔 Уведомления:</b>\n• Включите утренние (9:00) и/или вечерние (19:00)\n\n"
        "<b>💡 Предложить идею:</b>\n• Напишите предложение по улучшению\n\n"
        "<i>Также можно написать: 100 USD</i>"
    )

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    await message.answer("🔙 Главное меню", reply_markup=main_menu())

@dp.message()
async def auto_convert(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    match = re.match(r'^(\d+(?:\.\d+)?)\s+([A-Z]{3})$', message.text.upper().strip())
    if match:
        amount = float(match.group(1))
        currency = match.group(2)
        rates = await get_currency_rates()
        if currency in rates:
            result = amount * rates[currency]
            await save_history(message.from_user.id, currency, amount, result)
            await message.answer(f"💱 {amount:,.2f} {currency} = {result:,.2f} ₸")

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота с админ-панелью...")
    await init_db()
    print("✅ База данных готова")
    
    scheduler.add_job(update_rates, 'interval', hours=1)
    scheduler.add_job(send_morning, 'cron', hour=9, minute=0)
    scheduler.add_job(send_evening, 'cron', hour=19, minute=0)
    scheduler.start()
    print("✅ Планировщик запущен")
    
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print("🔐 Админ-панель доступна по команде /admin")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())