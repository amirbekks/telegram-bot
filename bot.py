import asyncio
import aiosqlite
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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
        [KeyboardButton(text="🔄 Другие валюты"), KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def other_currencies_menu():
    buttons = [
        [KeyboardButton(text="🇬🇧 GBP → KZT"), KeyboardButton(text="🇹🇷 TRY → KZT")],
        [KeyboardButton(text="🇰🇬 KGS → KZT"), KeyboardButton(text="🇯🇵 JPY → KZT")],
        [KeyboardButton(text="🇨🇦 CAD → KZT"), KeyboardButton(text="🇦🇺 AUD → KZT")],
        [KeyboardButton(text="🔙 Назад к валютам")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def countries_menu():
    buttons = [
        [KeyboardButton(text="🇰🇿 Казахстан"), KeyboardButton(text="🇨🇳 Китай")],
        [KeyboardButton(text="🇰🇬 Кыргызстан"), KeyboardButton(text="🇹🇭 Таиланд")],
        [KeyboardButton(text="🇹🇷 Турция"), KeyboardButton(text="🇦🇪 ОАЭ")],
        [KeyboardButton(text="🇪🇬 Египет"), KeyboardButton(text="🇮🇳 Индия")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# Города по странам
CITIES_BY_COUNTRY = {
    "🇰🇿 Казахстан": {
        "Астана": (51.1694, 71.4491),
        "Алматы": (43.2565, 76.9286),
        "Бурабай": (53.0853, 70.3169),
        "Шымкент": (42.3417, 69.5901),
        "Актау": (43.6532, 51.1552),
        "Атырау": (47.1167, 51.8833),
        "Караганда": (49.8014, 73.1021),
        "Уральск": (51.2167, 51.3667)
    },
    "🇨🇳 Китай": {
        "Пекин": (39.9042, 116.4074),
        "Шанхай": (31.2304, 121.4737),
        "Гуанчжоу": (23.1291, 113.2644),
        "Шэньчжэнь": (22.5431, 114.0579),
        "Сиань": (34.3416, 108.9402)
    },
    "🇰🇬 Кыргызстан": {
        "Бишкек": (42.8746, 74.5698),
        "Ош": (40.5149, 72.8166),
        "Иссык-Куль": (42.4414, 76.8286),
        "Джалал-Абад": (40.9334, 73.0027)
    },
    "🇹🇭 Таиланд": {
        "Бангкок": (13.7367, 100.5231),
        "Пхукет": (7.8804, 98.3923),
        "Паттайя": (12.9236, 100.8825),
        "Чиангмай": (18.7883, 98.9853),
        "Краби": (8.0863, 98.9069)
    },
    "🇹🇷 Турция": {
        "Стамбул": (41.0082, 28.9784),
        "Анкара": (39.9334, 32.8597),
        "Анталья": (36.8969, 30.7133),
        "Измир": (38.4192, 27.1287),
        "Бодрум": (37.0344, 27.4305),
        "Каппадокия": (38.6435, 34.8289)
    },
    "🇦🇪 ОАЭ": {
        "Дубай": (25.2048, 55.2708),
        "Абу-Даби": (24.4539, 54.3773),
        "Шарджа": (25.3463, 55.4209)
    },
    "🇪🇬 Египет": {
        "Каир": (30.0444, 31.2357),
        "Хургада": (27.2574, 33.8128),
        "Шарм-эль-Шейх": (27.9158, 34.33)
    },
    "🇮🇳 Индия": {
        "Дели": (28.6139, 77.2090),
        "Гоа": (15.2993, 74.1240),
        "Мумбаи": (19.0760, 72.8777)
    }
}

# Валюты для конвертации (код, название, эмодзи)
CURRENCIES = {
    "USD": {"name": "Доллар США", "emoji": "🇺🇸"},
    "EUR": {"name": "Евро", "emoji": "🇪🇺"},
    "RUB": {"name": "Российский рубль", "emoji": "🇷🇺"},
    "CNY": {"name": "Китайский юань", "emoji": "🇨🇳"},
    "GBP": {"name": "Фунт стерлингов", "emoji": "🇬🇧"},
    "TRY": {"name": "Турецкая лира", "emoji": "🇹🇷"},
    "KGS": {"name": "Кыргызский сом", "emoji": "🇰🇬"},
    "JPY": {"name": "Японская иена", "emoji": "🇯🇵"},
    "CAD": {"name": "Канадский доллар", "emoji": "🇨🇦"},
    "AUD": {"name": "Австралийский доллар", "emoji": "🇦🇺"}
}

# Состояния
class ConvertState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_currency = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

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

async def get_all_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id FROM users")
        return await cursor.fetchall()

async def get_total_users():
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        result = await cursor.fetchone()
        return result[0] if result else 0

async def save_idea(user_id: int, username: str, idea_text: str):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO ideas (user_id, username, idea_text)
            VALUES (?, ?, ?)
        ''', (user_id, username, idea_text))
        await db.commit()

async def get_recent_ideas(limit=10):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT id, user_id, username, idea_text, created_at 
            FROM ideas 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        return await cursor.fetchall()

# ========== КУРСЫ ВАЛЮТ ==========

async def get_currency_rates():
    """Получение курсов валют от НБ РК"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://www.nationalbank.kz/rss/get_rates.cfm') as response:
                if response.status == 200:
                    text = await response.text()
                    rates = {}
                    for currency in CURRENCIES.keys():
                        search_text = f'id="{currency}"'
                        if search_text in text:
                            start = text.find(search_text) + len(search_text) + 2
                            end = text.find('</rate>', start)
                            rate_text = text[start:end].strip()
                            try:
                                rates[currency] = float(rate_text)
                            except:
                                rates[currency] = 0
                    if rates:
                        return rates
    except Exception as e:
        print(f"Ошибка получения курсов: {e}")
    
    # Тестовые данные
    return {
        'USD': 464.50, 'EUR': 505.80, 'RUB': 5.12, 'CNY': 64.80,
        'GBP': 590.00, 'TRY': 14.50, 'KGS': 5.20, 'JPY': 3.10,
        'CAD': 340.00, 'AUD': 310.00
    }

# ========== ПОГОДА ==========

async def get_weather(city_name: str, lat: float, lon: float):
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
                    return f"❌ Не удалось получить погоду для {city_name}"
    except Exception as e:
        return f"❌ Ошибка при получении погоды для {city_name}"

# ========== СОЗДАЕМ БОТА ==========

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ========== КОНВЕРТАЦИЯ (БЕЗ КНОПКИ ОТПРАВКИ) ==========

@dp.message(F.text.startswith("💰 "))
async def convert_from_message(message: types.Message):
    """Автоматическая конвертация из сообщения пользователя"""
    try:
        parts = message.text.split()
        if len(parts) == 3:
            amount = float(parts[1])
            currency = parts[2].upper()
            
            rates = await get_currency_rates()
            
            if currency in rates and currency in CURRENCIES:
                result = amount * rates[currency]
                await message.answer(
                    f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>\n"
                    f"📊 Курс: 1 {currency} = {rates[currency]:.2f} ₸",
                    parse_mode="HTML"
                )
            else:
                await message.answer(f"❌ Валюта {currency} не поддерживается.\nДоступны: USD, EUR, RUB, CNY, GBP, TRY, KGS, JPY, CAD, AUD")
    except:
        pass

@dp.callback_query(F.data.startswith("conv_"))
async def convert_currency(callback: types.CallbackQuery, state: FSMContext):
    currency = callback.data.split("_")[1]
    await state.update_data(currency=currency)
    await state.set_state(ConvertState.waiting_for_amount)
    await callback.message.answer(
        f"💱 <b>Конвертация {CURRENCIES[currency]['emoji']} {currency} → KZT</b>\n\n"
        f"Просто <b>напишите сумму</b> цифрами (например: 100, 500.50)\n\n"
        f"<i>Сообщение будет автоматически переведено в тенге</i>",
        parse_mode="HTML"
    )
    await callback.answer()

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
                f"📊 Курс: 1 {currency} = {rates[currency]:.2f} ₸",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Курс временно недоступен, попробуйте позже")
        await state.clear()
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (например: 100 или 500.50)")

# ========== КУРСЫ ВАЛЮТ (КНОПКИ) ==========

@dp.message(F.text == "💵 Курсы валют")
async def cmd_currency(message: types.Message):
    rates = await get_currency_rates()
    text = "<b>💵 КУРСЫ ВАЛЮТ НБ РК</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for code, info in list(CURRENCIES.items())[:4]:
        rate = rates.get(code, 0)
        text += f"{info['emoji']} <b>{code} / KZT</b> → <code>{rate:.2f}</code> ₸\n"
    
    text += "\n<i>Выберите валюту для конвертации:</i>"
    await message.answer(text, parse_mode="HTML", reply_markup=currency_menu())

@dp.message(F.text == "🔄 Другие валюты")
async def other_currencies(message: types.Message):
    rates = await get_currency_rates()
    text = "<b>🔄 ДРУГИЕ ВАЛЮТЫ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for code, info in list(CURRENCIES.items())[4:]:
        rate = rates.get(code, 0)
        text += f"{info['emoji']} <b>{code} / KZT</b> → <code>{rate:.2f}</code> ₸\n"
    
    text += "\n<i>Выберите валюту для конвертации:</i>"
    await message.answer(text, parse_mode="HTML", reply_markup=other_currencies_menu())

# Кнопки конвертации
@dp.message(F.text.in_([
    "🇺🇸 USD → KZT", "🇪🇺 EUR → KZT", "🇷🇺 RUB → KZT", "🇨🇳 CNY → KZT",
    "🇬🇧 GBP → KZT", "🇹🇷 TRY → KZT", "🇰🇬 KGS → KZT", "🇯🇵 JPY → KZT",
    "🇨🇦 CAD → KZT", "🇦🇺 AUD → KZT"
]))
async def convert_button(message: types.Message, state: FSMContext):
    currency_map = {
        "🇺🇸 USD → KZT": "USD", "🇪🇺 EUR → KZT": "EUR",
        "🇷🇺 RUB → KZT": "RUB", "🇨🇳 CNY → KZT": "CNY",
        "🇬🇧 GBP → KZT": "GBP", "🇹🇷 TRY → KZT": "TRY",
        "🇰🇬 KGS → KZT": "KGS", "🇯🇵 JPY → KZT": "JPY",
        "🇨🇦 CAD → KZT": "CAD", "🇦🇺 AUD → KZT": "AUD"
    }
    currency = currency_map.get(message.text)
    if currency:
        await state.update_data(currency=currency)
        await state.set_state(ConvertState.waiting_for_amount)
        await message.answer(
            f"💱 <b>Конвертация {CURRENCIES[currency]['emoji']} {currency} → KZT</b>\n\n"
            f"Напишите сумму цифрами:",
            parse_mode="HTML"
        )

@dp.message(F.text == "🔙 Назад к валютам")
async def back_to_currency_menu(message: types.Message):
    await cmd_currency(message)

# ========== ПОГОДА (СТРАНЫ → ГОРОДА) ==========

@dp.message(F.text == "🌦 Погода")
async def weather_countries(message: types.Message):
    text = "<b>🌍 Выберите страну:</b>"
    await message.answer(text, parse_mode="HTML", reply_markup=countries_menu())

@dp.message(F.text.in_(CITIES_BY_COUNTRY.keys()))
async def weather_cities(message: types.Message):
    country = message.text
    cities = list(CITIES_BY_COUNTRY[country].keys())
    buttons = [[KeyboardButton(text=city)] for city in cities]
    buttons.append([KeyboardButton(text="🔙 Назад к странам")])
    
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer(f"🏙 <b>Выберите город в {country}:</b>", parse_mode="HTML", reply_markup=keyboard)

@dp.message(F.text == "🔙 Назад к странам")
async def back_to_countries(message: types.Message):
    await weather_countries(message)

@dp.message(F.text.in_(sum([list(cities.keys()) for cities in CITIES_BY_COUNTRY.values()], [])))
async def get_weather_for_city(message: types.Message):
    city_name = message.text
    
    # Находим координаты города
    for country, cities in CITIES_BY_COUNTRY.items():
        if city_name in cities:
            lat, lon = cities[city_name]
            await message.bot.send_chat_action(message.chat.id, "typing")
            weather = await get_weather(city_name, lat, lon)
            await message.answer(weather, parse_mode="HTML")
            return

# ========== ОСТАЛЬНЫЕ КОМАНДЫ ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    
    welcome_text = f"""
👋 <b>Добро пожаловать, {user.first_name}!</b>

🇰🇿 <b>Многофункциональный бот</b>

<b>Возможности:</b>
💵 <i>Конвертация валют (10 валют)</i>
🌦 <i>Погода в 40+ городах мира</i>
💡 <i>Отправка идей админу</i>

<b>Как пользоваться конвертацией:</b>
• Нажмите на любую валюту → напишите сумму
• Или напишите: 💰 100 USD

<b>⬇️ Выберите действие в меню</b>
"""
    await message.answer(welcome_text, reply_markup=main_menu())

@dp.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: types.Message):
    help_text = """
<b>📚 ПОМОЩЬ</b>

<b>💵 Конвертация валют:</b>
• Нажмите "Курсы валют"
• Выберите валюту
• Напишите ЛЮБУЮ сумму

<b>🌦 Погода:</b>
• Выберите страну → город
• Информация: температура, влажность, ветер

<b>💡 Идеи:</b>
• Напишите предложение
• Оно придёт администратору
"""
    await message.answer(help_text, parse_mode="HTML")

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
    
    # Отправляем админу
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📝 <b>НОВАЯ ИДЕЯ!</b>\n\n"
            f"👤 {user.full_name}\n"
            f"🆔 <code>{user.id}</code>\n"
            f"📱 @{user.username or 'нет'}\n\n"
            f"💡 {message.text}",
            parse_mode="HTML"
        )
    except:
        pass
    
    await message.answer("❤️ Спасибо! Идея отправлена администратору.", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "🔙 Назад в меню")
async def back_to_menu(message: types.Message):
    await message.answer("Главное меню", reply_markup=main_menu())

# ========== АДМИН КОМАНДЫ ==========

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    total_users = await get_total_users()
    await message.answer(
        f"🔐 <b>Админ-панель</b>\n\n👥 Пользователей: {total_users}\n\n"
        f"Команды:\n/stat - статистика\n/ideas - идеи\n/broadcast - рассылка",
        parse_mode="HTML"
    )

@dp.message(Command("stat"))
async def admin_stat(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    total = await get_total_users()
    await message.answer(f"📊 Пользователей: {total}")

@dp.message(Command("ideas"))
async def admin_ideas(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    ideas = await get_recent_ideas(5)
    if not ideas:
        await message.answer("📭 Нет идей")
        return
    text = "💡 Последние идеи:\n\n"
    for idea in ideas:
        text += f"👤 @{idea[2] or 'anon'}\n📝 {idea[3][:100]}\n🕐 {idea[4][:16]}\n━━━━━━━━━\n"
    await message.answer(text)

@dp.message(Command("broadcast"))
async def admin_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("📢 Напишите сообщение для рассылки:")

@dp.message(BroadcastState.waiting_for_message)
async def send_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    success = 0
    for user in users:
        try:
            await bot.send_message(user[0], message.text, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await message.answer(f"✅ Рассылка завершена! Отправлено: {success}")
    await state.clear()

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота...")
    await init_db()
    print("✅ База данных готова")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())