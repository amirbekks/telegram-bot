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

# Загружаем секреты из файла .env
load_dotenv()

# Переменные окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# ========== КЛАВИАТУРЫ ==========

def main_menu():
    """Главное меню бота"""
    buttons = [
        [KeyboardButton(text="💵 Курсы валют")],
        [KeyboardButton(text="🌦 Погода")],
        [KeyboardButton(text="💡 Предложить идею")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def currency_menu():
    """Меню конвертации валют"""
    buttons = [
        [KeyboardButton(text="🇺🇸 USD → KZT"), KeyboardButton(text="🇪🇺 EUR → KZT")],
        [KeyboardButton(text="🇷🇺 RUB → KZT"), KeyboardButton(text="🇨🇳 CNY → KZT")],
        [KeyboardButton(text="🔄 Все курсы"), KeyboardButton(text="💱 Конвертировать вручную")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def weather_menu():
    """Меню выбора города для погоды"""
    buttons = [
        [KeyboardButton(text="🌆 Астана"), KeyboardButton(text="🌉 Алматы")],
        [KeyboardButton(text="🏞 Бурабай")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_menu():
    """Админ меню"""
    buttons = [
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="💡 Последние идеи")],
        [KeyboardButton(text="📢 Сделать рассылку")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== СОСТОЯНИЯ ДЛЯ FSM ==========

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class ConvertState(StatesGroup):
    waiting_for_currency = State()
    waiting_for_amount = State()

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
                    currencies = ['USD', 'EUR', 'RUB', 'CNY']
                    for currency in currencies:
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
    
    # Тестовые данные если API не работает
    return {'USD': 464.50, 'EUR': 505.80, 'RUB': 5.12, 'CNY': 64.80}

# ========== ПОГОДА ==========

async def get_weather(city_name: str):
    cities = {
        'Астана': {'lat': 51.1694, 'lon': 71.4491},
        'Алматы': {'lat': 43.2565, 'lon': 76.9286},
        'Бурабай': {'lat': 53.0853, 'lon': 70.3169}
    }
    
    if city_name not in cities:
        return None
    
    coords = cities[city_name]
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={coords['lat']}&lon={coords['lon']}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
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

# ========== ГЛАВНОЕ МЕНЮ ==========

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.username, user.full_name)
    
    welcome_text = f"""
👋 <b>Добро пожаловать, {user.first_name}!</b>

🇰🇿 <b>Многофункциональный бот для Казахстана</b>

<b>Мои возможности:</b>
💵 <i>Курсы валют и конвертация (USD, EUR, RUB, CNY)</i>
🌦 <i>Прогноз погоды по городам Казахстана</i>
💡 <i>Приём ваших идей и предложений</i>

<b>⬇️ Выберите действие в меню ниже</b>
    """
    await message.answer(welcome_text, reply_markup=main_menu())

@dp.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: types.Message):
    help_text = """
<b>📚 Справка по использованию бота</b>

<b>💵 Курсы валют:</b>
• Нажмите "Курсы валют" для перехода в меню конвертации
• Выберите нужную валюту для быстрой конвертации
• Или нажмите "Конвертировать вручную" для любого числа

<b>🌦 Погода:</b>
• Доступные города: Астана, Алматы, Бурабай

<b>💡 Предложить идею:</b>
• Поделитесь своими идеями по улучшению бота

<b>👨‍💻 Админ команда:</b>
• /admin - админ-панель (только для администратора)
    """
    await message.answer(help_text, parse_mode="HTML")

@dp.message(F.text == "🔙 Назад в меню")
async def cmd_back_to_menu(message: types.Message):
    await message.answer("🔙 Возвращаюсь в главное меню", reply_markup=main_menu())

# ========== КУРСЫ ВАЛЮТ И КОНВЕРТАЦИЯ ==========

@dp.message(F.text == "💵 Курсы валют")
async def cmd_currency_menu(message: types.Message):
    """Показать меню конвертации валют"""
    rates = await get_currency_rates()
    
    text = f"""
<b>💵 КУРСЫ ВАЛЮТ НБ РК</b>
━━━━━━━━━━━━━━━━━━━━━

🇺🇸 <b>USD / KZT</b>   →   <code>{rates.get('USD', 0):.2f}</code> ₸
🇪🇺 <b>EUR / KZT</b>   →   <code>{rates.get('EUR', 0):.2f}</code> ₸
🇷🇺 <b>RUB / KZT</b>   →   <code>{rates.get('RUB', 0):.2f}</code> ₸
🇨🇳 <b>CNY / KZT</b>   →   <code>{rates.get('CNY', 0):.2f}</code> ₸

━━━━━━━━━━━━━━━━━━━━━
<i>Выберите действие ниже:</i>
    """
    
    await message.answer(text, parse_mode="HTML", reply_markup=currency_menu())

@dp.message(F.text == "🔄 Все курсы")
async def cmd_all_rates(message: types.Message):
    """Показать все курсы"""
    rates = await get_currency_rates()
    
    text = f"""
<b>💵 ВСЕ КУРСЫ ВАЛЮТ</b>
━━━━━━━━━━━━━━━━━━━━━

🇺🇸 1 USD = <code>{rates.get('USD', 0):.2f}</code> ₸
🇪🇺 1 EUR = <code>{rates.get('EUR', 0):.2f}</code> ₸
🇷🇺 1 RUB = <code>{rates.get('RUB', 0):.2f}</code> ₸
🇨🇳 1 CNY = <code>{rates.get('CNY', 0):.2f}</code> ₸

━━━━━━━━━━━━━━━━━━━━━
🕐 <i>Курсы обновляются автоматически</i>
    """
    
    await message.answer(text, parse_mode="HTML")

# КОНВЕРТАЦИЯ ПО КНОПКАМ
@dp.message(F.text == "🇺🇸 USD → KZT")
async def convert_usd(message: types.Message):
    rates = await get_currency_rates()
    rate = rates.get('USD', 464.50)
    text = f"""
💱 <b>Конвертация USD → KZT</b>
━━━━━━━━━━━━━━━━━━━━━

🇺🇸 <b>1 USD = {rate:.2f} ₸</b>

<b>Примеры:</b>
• 10 USD = {rate * 10:.2f} ₸
• 50 USD = {rate * 50:.2f} ₸
• 100 USD = {rate * 100:.2f} ₸
• 500 USD = {rate * 500:.2f} ₸
• 1000 USD = {rate * 1000:.2f} ₸

━━━━━━━━━━━━━━━━━━━━━
<i>Для конвертации другой суммы нажмите "💱 Конвертировать вручную"</i>
    """
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🇪🇺 EUR → KZT")
async def convert_eur(message: types.Message):
    rates = await get_currency_rates()
    rate = rates.get('EUR', 505.80)
    text = f"""
💱 <b>Конвертация EUR → KZT</b>
━━━━━━━━━━━━━━━━━━━━━

🇪🇺 <b>1 EUR = {rate:.2f} ₸</b>

<b>Примеры:</b>
• 10 EUR = {rate * 10:.2f} ₸
• 50 EUR = {rate * 50:.2f} ₸
• 100 EUR = {rate * 100:.2f} ₸
• 500 EUR = {rate * 500:.2f} ₸
• 1000 EUR = {rate * 1000:.2f} ₸

━━━━━━━━━━━━━━━━━━━━━
<i>Для конвертации другой суммы нажмите "💱 Конвертировать вручную"</i>
    """
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🇷🇺 RUB → KZT")
async def convert_rub(message: types.Message):
    rates = await get_currency_rates()
    rate = rates.get('RUB', 5.12)
    text = f"""
💱 <b>Конвертация RUB → KZT</b>
━━━━━━━━━━━━━━━━━━━━━

🇷🇺 <b>1 RUB = {rate:.2f} ₸</b>

<b>Примеры:</b>
• 100 RUB = {rate * 100:.2f} ₸
• 500 RUB = {rate * 500:.2f} ₸
• 1000 RUB = {rate * 1000:.2f} ₸
• 5000 RUB = {rate * 5000:.2f} ₸
• 10000 RUB = {rate * 10000:.2f} ₸

━━━━━━━━━━━━━━━━━━━━━
<i>Для конвертации другой суммы нажмите "💱 Конвертировать вручную"</i>
    """
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🇨🇳 CNY → KZT")
async def convert_cny(message: types.Message):
    rates = await get_currency_rates()
    rate = rates.get('CNY', 64.80)
    text = f"""
💱 <b>Конвертация CNY → KZT</b>
━━━━━━━━━━━━━━━━━━━━━

🇨🇳 <b>1 CNY = {rate:.2f} ₸</b>

<b>Примеры:</b>
• 10 CNY = {rate * 10:.2f} ₸
• 50 CNY = {rate * 50:.2f} ₸
• 100 CNY = {rate * 100:.2f} ₸
• 500 CNY = {rate * 500:.2f} ₸
• 1000 CNY = {rate * 1000:.2f} ₸

━━━━━━━━━━━━━━━━━━━━━
<i>Для конвертации другой суммы нажмите "💱 Конвертировать вручную"</i>
    """
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "💱 Конвертировать вручную")
async def manual_convert_start(message: types.Message, state: FSMContext):
    """Ручная конвертация - выбор валюты"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 USD → KZT", callback_data="conv_USD")],
        [InlineKeyboardButton(text="🇪🇺 EUR → KZT", callback_data="conv_EUR")],
        [InlineKeyboardButton(text="🇷🇺 RUB → KZT", callback_data="conv_RUB")],
        [InlineKeyboardButton(text="🇨🇳 CNY → KZT", callback_data="conv_CNY")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="conv_cancel")]
    ])
    
    await state.set_state(ConvertState.waiting_for_currency)
    await message.answer(
        "💱 <b>Выберите валюту для конвертации:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query(ConvertState.waiting_for_currency)
async def manual_convert_currency(callback: types.CallbackQuery, state: FSMContext):
    """Выбрана валюта, запрашиваем сумму"""
    if callback.data == "conv_cancel":
        await state.clear()
        await callback.message.edit_text("❌ Конвертация отменена")
        await callback.answer()
        return
    
    currency = callback.data.split("_")[1]
    await state.update_data(currency=currency)
    await state.set_state(ConvertState.waiting_for_amount)
    
    await callback.message.edit_text(
        f"💱 <b>Введите сумму в {currency}:</b>\n\n"
        f"<i>Например: 100, 500.50, 1000</i>\n\n"
        f"Для отмены отправьте /cancel",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(ConvertState.waiting_for_amount)
async def manual_convert_amount(message: types.Message, state: FSMContext):
    """Получили сумму, конвертируем"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Конвертация отменена", reply_markup=currency_menu())
        return
    
    try:
        amount = float(message.text.replace(",", "."))
        if amount <= 0:
            raise ValueError
    except:
        await message.answer("❌ Пожалуйста, введите корректное число (например: 100 или 500.50)")
        return
    
    data = await state.get_data()
    currency = data.get('currency')
    rates = await get_currency_rates()
    
    currency_names = {
        'USD': ('🇺🇸 Доллар США', rates.get('USD', 464.50)),
        'EUR': ('🇪🇺 Евро', rates.get('EUR', 505.80)),
        'RUB': ('🇷🇺 Российский рубль', rates.get('RUB', 5.12)),
        'CNY': ('🇨🇳 Китайский юань', rates.get('CNY', 64.80))
    }
    
    name, rate = currency_names.get(currency, ('Unknown', 0))
    result = amount * rate
    
    text = f"""
💱 <b>РЕЗУЛЬТАТ КОНВЕРТАЦИИ</b>
━━━━━━━━━━━━━━━━━━━━━

<b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>

<b>Курс:</b> 1 {currency} = {rate:.2f} ₸

━━━━━━━━━━━━━━━━━━━━━
<i>Курс актуален на текущий момент</i>
    """
    
    await message.answer(text, parse_mode="HTML", reply_markup=currency_menu())
    await state.clear()

# ========== ПОГОДА ==========

@dp.message(F.text == "🌦 Погода")
async def cmd_weather_menu(message: types.Message):
    await message.answer("🌍 <b>Выберите город:</b>", parse_mode="HTML", reply_markup=weather_menu())

@dp.message(F.text.in_(["🌆 Астана", "🌉 Алматы", "🏞 Бурабай"]))
async def cmd_weather_city(message: types.Message):
    city_name = message.text.replace("🌆 ", "").replace("🌉 ", "").replace("🏞 ", "")
    await message.bot.send_chat_action(message.chat.id, "typing")
    weather = await get_weather(city_name)
    await message.answer(weather, parse_mode="HTML")

# ========== ИДЕИ ==========

@dp.message(F.text == "💡 Предложить идею")
async def cmd_idea_start(message: types.Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer(
        "💭 <b>Расскажите вашу идею или предложение</b>\n\n"
        "Напишите всё, что считаете нужным.\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode="HTML"
    )

@dp.message(IdeaState.waiting_for_idea)
async def cmd_idea_save(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=main_menu())
        return
    
    user = message.from_user
    await save_idea(user.id, user.username or "no_username", message.text)
    
    admin_notify = f"""
📝 <b>НОВАЯ ИДЕЯ!</b>
👤 <b>От:</b> {user.full_name}
🆔 <b>ID:</b> <code>{user.id}</code>
📱 <b>Username:</b> @{user.username if user.username else 'нет'}
<b>💡 Текст:</b>
<blockquote>{message.text}</blockquote>
    """
    
    try:
        await bot.send_message(ADMIN_ID, admin_notify, parse_mode="HTML")
    except:
        pass
    
    await message.answer(
        "❤️ <b>Спасибо за вашу идею!</b>\n\nОна отправлена администратору.",
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    await state.clear()

# ========== АДМИН КОМАНДЫ ==========

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен!")
        return
    await message.answer("🔐 <b>АДМИН-ПАНЕЛЬ</b>", parse_mode="HTML", reply_markup=admin_menu())

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    total_users = await get_total_users()
    await message.answer(f"📊 <b>Статистика</b>\n\n👥 Пользователей: {total_users}", parse_mode="HTML")

@dp.message(F.text == "💡 Последние идеи")
async def admin_ideas(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    ideas = await get_recent_ideas(10)
    if not ideas:
        await message.answer("📭 Нет предложений")
        return
    text = "💡 <b>Последние идеи:</b>\n\n"
    for idea in ideas:
        text += f"📝 {idea[3][:100]}\n👤 @{idea[2] or 'anon'}\n━━━━━━━━━\n"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📢 Сделать рассылку")
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("📢 Отправьте текст для рассылки:\n<i>/cancel - отмена</i>", parse_mode="HTML")

@dp.message(BroadcastState.waiting_for_message)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено")
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
    print(f"📱 Бот: @{(await bot.get_me()).username}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())