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
                           InputLocationMessageContent, InputFile)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
import os
from dotenv import load_dotenv
import pytz
import matplotlib.pyplot as plt
from PIL import Image
import io
import yfinance as yf

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

# ========== КЛАВИАТУРЫ (РАСШИРЕННЫЕ) ==========

def main_menu():
    buttons = [
        [KeyboardButton(text="💵 Курсы валют"), KeyboardButton(text="₿ Криптовалюты")],
        [KeyboardButton(text="📈 Графики курсов"), KeyboardButton(text="💰 Бюджетный трекер")],
        [KeyboardButton(text="🌦 Погода"), KeyboardButton(text="📰 Новости")],
        [KeyboardButton(text="⭐ Избранное"), KeyboardButton(text="⏰ Напоминания")],
        [KeyboardButton(text="🎮 Игры"), KeyboardButton(text="🌟 Premium")],
        [KeyboardButton(text="💡 Идеи"), KeyboardButton(text="ℹ️ Помощь")],
        [KeyboardButton(text="🗺 Обменники", request_location=True)]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def games_menu():
    buttons = [
        [KeyboardButton(text="🎮 Экономическая игра"), KeyboardButton(text="❓ Ежедневная викторина")],
        [KeyboardButton(text="🔮 Гороскоп"), KeyboardButton(text="🏆 Топ игроков")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def premium_menu():
    buttons = [
        [KeyboardButton(text="💎 Купить Premium"), KeyboardButton(text="⭐ Мои бонусы")],
        [KeyboardButton(text="🔗 Реферальная ссылка"), KeyboardButton(text="👥 Приглашённые")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== СОСТОЯНИЯ ==========
class ConvertState(StatesGroup):
    waiting_for_amount = State()

class IdeaState(StatesGroup):
    waiting_for_idea = State()

class ReminderState(StatesGroup):
    waiting_for_text = State()
    waiting_for_time = State()

class AlertState(StatesGroup):
    waiting_for_currency = State()
    waiting_for_price = State()

class GameState(StatesGroup):
    trading = State()
    buying = State()
    selling = State()

class ExpenseState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_category = State()

class ForecastState(StatesGroup):
    waiting_for_currency = State()

# ========== БАЗА ДАННЫХ (РАСШИРЕННАЯ) ==========
async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        # Пользователи
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                premium BOOLEAN DEFAULT 0,
                premium_until TIMESTAMP,
                balance INTEGER DEFAULT 0,
                referrer_id INTEGER
            )
        ''')
        
        # Расходы
        await db.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                category TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Игровой портфель
        await db.execute('''
            CREATE TABLE IF NOT EXISTS game_portfolio (
                user_id INTEGER,
                currency TEXT,
                amount REAL,
                PRIMARY KEY (user_id, currency)
            )
        ''')
        
        # Умные уведомления
        await db.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                user_id INTEGER,
                currency TEXT,
                target_price REAL,
                is_above BOOLEAN,
                is_active BOOLEAN DEFAULT 1,
                PRIMARY KEY (user_id, currency)
            )
        ''')
        
        # Отзывы об обменниках
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city TEXT,
                exchanger_name TEXT,
                rating INTEGER,
                comment TEXT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.commit()

# ========== УМНЫЕ УВЕДОМЛЕНИЯ ==========
async def add_alert(user_id: int, currency: str, target_price: float, is_above: bool):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT OR REPLACE INTO alerts (user_id, currency, target_price, is_above, is_active)
            VALUES (?, ?, ?, ?, 1)
        ''', (user_id, currency, target_price, is_above))
        await db.commit()

async def check_alerts():
    rates = await get_currency_rates()
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT user_id, currency, target_price, is_above FROM alerts WHERE is_active = 1")
        alerts = await cursor.fetchall()
        
        for user_id, currency, target_price, is_above in alerts:
            current = rates.get(currency, 0)
            triggered = (current >= target_price if is_above else current <= target_price)
            
            if triggered:
                await bot.send_message(user_id, f"🔔 <b>Уведомление по {currency}!</b>\nЦель: {target_price:.2f}\nТекущий: {current:.2f} ₸", parse_mode="HTML")
                await db.execute("UPDATE alerts SET is_active = 0 WHERE user_id = ? AND currency = ?", (user_id, currency))
        await db.commit()

# ========== БЮДЖЕТНЫЙ ТРЕКЕР ==========
async def add_expense(user_id: int, amount: float, category: str, description: str = ""):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO expenses (user_id, amount, category, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, category, description))
        await db.commit()

async def get_monthly_stats(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT category, SUM(amount), COUNT(*)
            FROM expenses
            WHERE user_id = ? AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
            GROUP BY category
        ''', (user_id,))
        return await cursor.fetchall()

# ========== ЭКОНОМИЧЕСКАЯ ИГРА ==========
async def get_game_balance(user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 10000  # Стартовый баланс 10,000

async def update_game_balance(user_id: int, amount: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def buy_currency_game(user_id: int, currency: str, amount: float, price: float):
    total_cost = amount * price
    balance = await get_game_balance(user_id)
    
    if balance < total_cost:
        return False, "Недостаточно средств!"
    
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute('''
            INSERT INTO game_portfolio (user_id, currency, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, currency) DO UPDATE SET
            amount = amount + ?
        ''', (user_id, currency, amount, amount))
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total_cost, user_id))
        await db.commit()
    
    return True, f"✅ Куплено {amount} {currency} за {total_cost:,.0f} игровых тенге!"

async def sell_currency_game(user_id: int, currency: str, amount: float, price: float):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT amount FROM game_portfolio WHERE user_id = ? AND currency = ?", (user_id, currency))
        result = await cursor.fetchone()
        
        if not result or result[0] < amount:
            return False, "У вас нет столько валюты!"
        
        total_income = amount * price
        await db.execute("UPDATE game_portfolio SET amount = amount - ? WHERE user_id = ? AND currency = ?", (amount, user_id, currency))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_income, user_id))
        await db.commit()
    
    return True, f"✅ Продано {amount} {currency} за {total_income:,.0f} игровых тенге!"

# ========== ПРЕМИУМ И РЕФЕРАЛЫ ==========
async def give_premium(user_id: int, days: int):
    premium_until = datetime.now() + timedelta(days=days)
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET premium = 1, premium_until = ? WHERE user_id = ?", (premium_until, user_id))
        await db.commit()

async def add_referral(referrer_id: int, new_user_id: int):
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("UPDATE users SET referrer_id = ? WHERE user_id = ?", (referrer_id, new_user_id))
        await db.commit()
        # Бонус 1000 игровых тенге за реферала
        await db.execute("UPDATE users SET balance = balance + 1000 WHERE user_id = ?", (referrer_id,))
        await db.commit()

# ========== ГРАФИКИ КУРСОВ ==========
async def generate_chart(currency: str, days: int = 30):
    try:
        # Загружаем исторические данные из yfinance
        ticker = f"{currency}KZT=X" if currency != "USD" else "USDKZT=X"
        data = yf.download(ticker, period=f"{days}d", interval="1d")
        
        if data.empty:
            return None
        
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(data.index, data['Close'], 'b-', linewidth=2)
        ax.fill_between(data.index, data['Close'], alpha=0.3)
        ax.set_title(f'Курс {currency} к тенге за {days} дней', fontsize=14, fontweight='bold')
        ax.set_xlabel('Дата', fontsize=12)
        ax.set_ylabel('Курс (₸)', fontsize=12)
        ax.grid(True, alpha=0.3)
        
        # Сохраняем в буфер
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        plt.close()
        
        return buf
    except:
        return None

# ========== ГОРОСКОП ==========
HOROSCOPES = {
    "Овен": "Сегодня отличный день для финансовых операций!",
    "Телец": "Будьте осторожны с крупными тратами.",
    "Близнецы": "Удачный день для обмена валюты.",
    "Рак": "Ожидайте прибыльных предложений.",
    "Лев": "Ваша интуиция не подведёт.",
    "Дева": "Планируйте бюджет на месяц вперёд.",
    "Весы": "Хороший день для инвестиций.",
    "Скорпион": "Избегайте спонтанных покупок.",
    "Стрелец": "Время для крупных решений.",
    "Козерог": "Деньги будут поступать легко.",
    "Водолей": "Неожиданные доходы возможны.",
    "Рыбы": "Доверяйте своим финансовым решениям."
}

# ========== ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ ==========
async def get_currency_rates():
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
                    return rates
    except:
        pass
    return {'USD': 485.50, 'EUR': 565.80, 'RUB': 6.85, 'CNY': 72.50, 'GBP': 625, 'TRY': 16.5}

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

# ========== БОТ ==========
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Фоновые задачи
scheduler.add_job(check_alerts, 'interval', minutes=5)

@dp.startup()
async def on_startup():
    await init_db()
    scheduler.start()
    print("✅ МЕГА-БОТ ЗАПУЩЕН СО ВСЕМИ ФУНКЦИЯМИ!")

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        f"👋 <b>Добро пожаловать в МЕГА-БОТ!</b>\n\n"
        f"🌟 <b>ВСЕ ФУНКЦИИ В ОДНОМ БОТЕ:</b>\n\n"
        f"💵 Валюты и криптовалюты\n"
        f"📈 Графики курсов\n"
        f"💰 Бюджетный трекер\n"
        f"🎮 Экономическая игра\n"
        f"🔔 Умные уведомления\n"
        f"⭐ Premium подписка\n"
        f"👥 Реферальная программа\n"
        f"🔮 Гороскоп\n"
        f"🗺 Отзывы об обменниках\n\n"
        f"⬇️ <b>Выберите действие:</b>",
        reply_markup=main_menu()
    )

@dp.message(F.text == "📈 Графики курсов")
async def chart_menu(message: types.Message):
    buttons = [[KeyboardButton(text=f"📊 {curr}/KZT")] for curr in ['USD', 'EUR', 'RUB', 'CNY']]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer("📈 <b>Выберите валюту для графика:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.startswith("📊 "))
async def show_chart(message: types.Message):
    currency = message.text.split()[1].split('/')[0]
    await message.bot.send_chat_action(message.chat.id, "upload_photo")
    
    chart = await generate_chart(currency, 30)
    if chart:
        await message.answer_photo(photo=types.BufferedInputFile(chart.getvalue(), filename="chart.png"), caption=f"📈 График курса {currency}/KZT за 30 дней")
    else:
        await message.answer("❌ Не удалось загрузить график")

@dp.message(F.text == "💰 Бюджетный трекер")
async def budget_menu(message: types.Message):
    buttons = [
        [KeyboardButton(text="➕ Добавить расход"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📋 Категории"), KeyboardButton(text="🔙 Назад")]
    ]
    await message.answer("💰 <b>Бюджетный трекер</b>\n\nВыберите действие:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text == "➕ Добавить расход")
async def add_expense_start(message: types.Message, state: FSMContext):
    await state.set_state(ExpenseState.waiting_for_amount)
    await message.answer("💰 Введите сумму расхода (в тенге):", reply_markup=types.ReplyKeyboardRemove())

@dp.message(ExpenseState.waiting_for_amount)
async def add_expense_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        await state.update_data(amount=amount)
        await state.set_state(ExpenseState.waiting_for_category)
        
        categories = ["🍔 Еда", "🚕 Транспорт", "🏠 Жильё", "🛍 Покупки", "🎮 Развлечения", "💊 Здоровье", "📚 Образование", "💡 Другое"]
        buttons = [[KeyboardButton(text=cat)] for cat in categories]
        await message.answer("📂 Выберите категорию:", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))
    except:
        await message.answer("❌ Введите число!")

@dp.message(ExpenseState.waiting_for_category)
async def add_expense_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await add_expense(message.from_user.id, data['amount'], message.text)
    await message.answer(f"✅ Добавлен расход: {data['amount']} ₸ на {message.text}", reply_markup=main_menu())
    await state.clear()

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    stats = await get_monthly_stats(message.from_user.id)
    if not stats:
        await message.answer("📭 Нет расходов за этот месяц")
        return
    
    text = f"<b>📊 СТАТИСТИКА ЗА МЕСЯЦ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    total = 0
    for cat, amount, count in stats:
        text += f"\n{cat}: <code>{amount:,.0f}</code> ₸ ({count} раз)"
        total += amount
    text += f"\n\n<b>💰 Всего: {total:,.0f} ₸</b>"
    await message.answer(text)

@dp.message(F.text == "🎮 Игры")
async def games_menu_handler(message: types.Message):
    await message.answer("🎮 <b>ИГРЫ И РАЗВЛЕЧЕНИЯ</b>\n\nВыберите игру:", reply_markup=games_menu())

@dp.message(F.text == "🎮 Экономическая игра")
async def economic_game(message: types.Message, state: FSMContext):
    balance = await get_game_balance(message.from_user.id)
    rates = await get_currency_rates()
    
    text = f"<b>🎮 ЭКОНОМИЧЕСКАЯ ИГРА</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 <b>Ваш баланс:</b> {balance:,.0f} игровых тенге\n\n"
    text += f"<b>📈 Текущие курсы:</b>\n"
    text += f"🇺🇸 USD: {rates['USD']:.2f} ₸\n"
    text += f"🇪🇺 EUR: {rates['EUR']:.2f} ₸\n"
    text += f"🇷🇺 RUB: {rates['RUB']:.2f} ₸\n\n"
    text += f"<b>Действия:</b>\n"
    text += f"• Купить валюту: /buy USD 100\n"
    text += f"• Продать валюту: /sell USD 100\n"
    text += f"• Мой портфель: /portfolio"
    
    await message.answer(text)

@dp.message(Command("buy"))
async def buy_game(message: types.Message):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Используйте: /buy USD 100")
        return
    
    currency = parts[1].upper()
    amount = float(parts[2])
    rates = await get_currency_rates()
    
    if currency not in rates:
        await message.answer("❌ Неизвестная валюта")
        return
    
    result, msg = await buy_currency_game(message.from_user.id, currency, amount, rates[currency])
    await message.answer(msg)

@dp.message(Command("sell"))
async def sell_game(message: types.Message):
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("❌ Используйте: /sell USD 100")
        return
    
    currency = parts[1].upper()
    amount = float(parts[2])
    rates = await get_currency_rates()
    
    result, msg = await sell_currency_game(message.from_user.id, currency, amount, rates[currency])
    await message.answer(msg)

@dp.message(Command("portfolio"))
async def portfolio_game(message: types.Message):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT currency, amount FROM game_portfolio WHERE user_id = ? AND amount > 0", (message.from_user.id,))
        portfolio = await cursor.fetchall()
    
    if not portfolio:
        await message.answer("📭 Ваш портфель пуст")
        return
    
    text = "<b>💼 МОЙ ПОРТФЕЛЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for currency, amount in portfolio:
        text += f"\n{currency}: {amount:,.2f}"
    await message.answer(text)

@dp.message(F.text == "❓ Ежедневная викторина")
async def daily_quiz(message: types.Message):
    questions = [
        {"q": "Курс USD к тенге выше 500?", "a": "Нет"},
        {"q": "Евро дороже доллара?", "a": "Да"},
        {"q": "Bitcoin цифровая валюта?", "a": "Да"}
    ]
    
    import random
    q = random.choice(questions)
    
    buttons = [[KeyboardButton(text="✅ Да"), KeyboardButton(text="❌ Нет")]]
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)
    
    await message.answer(f"❓ <b>Ежедневная викторина</b>\n\n{q['q']}", reply_markup=keyboard)
    
    # Сохраняем правильный ответ
    async def check_answer(m):
        if m.text == "✅ Да":
            answer = "Да"
        else:
            answer = "Нет"
        
        if answer == q['a']:
            await m.answer("✅ Правильно! +100 игровых тенге!", reply_markup=main_menu())
            await update_game_balance(m.from_user.id, 100)
        else:
            await m.answer(f"❌ Неправильно! Правильный ответ: {q['a']}", reply_markup=main_menu())
        
        dp.message.handlers.remove(check_answer)
    
    dp.message.register(check_answer)

@dp.message(F.text == "🔮 Гороскоп")
async def horoscope(message: types.Message):
    buttons = [[KeyboardButton(text=sign)] for sign in HOROSCOPES.keys()]
    buttons.append([KeyboardButton(text="🔙 Назад")])
    await message.answer("🔮 <b>Выберите знак зодиака:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text.in_(HOROSCOPES.keys()))
async def show_horoscope(message: types.Message):
    horoscope_text = HOROSCOPES[message.text]
    await message.answer(f"🔮 <b>{message.text}</b>\n\n{horoscope_text}")

@dp.message(F.text == "🌟 Premium")
async def premium_menu_handler(message: types.Message):
    await message.answer(
        "🌟 <b>PREMIUM ПОДПИСКА</b>\n\n"
        "💎 <b>Преимущества Premium:</b>\n"
        "• Неограниченная история конвертаций\n"
        "• Умные уведомления (до 10 валют)\n"
        "• Приоритетная поддержка\n"
        "• Эксклюзивные графики\n\n"
        "💰 <b>Цена:</b> 1000 игровых тенге / месяц\n\n"
        "💎 <b>Приведи друга и получи Premium бесплатно!</b>\n"
        "За каждого приглашённого друга - 1000 тенге и 7 дней Premium",
        reply_markup=premium_menu()
    )

@dp.message(F.text == "💎 Купить Premium")
async def buy_premium(message: types.Message):
    balance = await get_game_balance(message.from_user.id)
    if balance >= 1000:
        await update_game_balance(message.from_user.id, -1000)
        await give_premium(message.from_user.id, 30)
        await message.answer("✅ Поздравляем! Вы стали Premium пользователем на 30 дней!")
    else:
        await message.answer(f"❌ Недостаточно средств! Нужно 1000 тенге, у вас {balance}")

@dp.message(F.text == "🔗 Реферальная ссылка")
async def referral_link(message: types.Message):
    link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{message.from_user.id}"
    await message.answer(
        f"🔗 <b>Ваша реферальная ссылка:</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"За каждого приглашённого друга вы получите 1000 игровых тенге!"
    )

@dp.message(F.text == "🔔 Умные уведомления")
async def alert_menu(message: types.Message):
    await message.answer(
        "🔔 <b>УМНЫЕ УВЕДОМЛЕНИЯ</b>\n\n"
        "Получайте уведомления когда курс достигнет нужного уровня!\n\n"
        "Примеры:\n"
        "• /alert USD 490 - уведомить когда USD станет 490 ₸\n"
        "• /alert EUR 560 ниже - уведомить когда упадет ниже 560 ₸"
    )

@dp.message(Command("alert"))
async def set_alert(message: types.Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Используйте: /alert USD 490 или /alert USD 490 ниже")
        return
    
    currency = parts[1].upper()
    target_price = float(parts[2])
    is_above = "выше" not in message.text.lower()
    
    await add_alert(message.from_user.id, currency, target_price, is_above)
    await message.answer(f"✅ Уведомление установлено!\nКогда {currency} будет {'выше' if is_above else 'ниже'} {target_price:.2f} ₸, я пришлю сообщение!")

@dp.message(F.text == "🗺 Отзывы об обменниках")
async def reviews_menu(message: types.Message):
    buttons = [
        [KeyboardButton(text="✍️ Оставить отзыв"), KeyboardButton(text="⭐ Топ обменников")],
        [KeyboardButton(text="🔙 Назад")]
    ]
    await message.answer("🗺 <b>ОБМЕННИКИ И ОТЗЫВЫ</b>", reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True))

@dp.message(F.text == "✍️ Оставить отзыв")
async def add_review_start(message: types.Message):
    await message.answer(
        "✍️ <b>Оставить отзыв об обменнике</b>\n\n"
        "Напишите в формате:\n"
        "<code>Город | Название | Оценка(1-5) | Комментарий</code>\n\n"
        "Пример:\n"
        "<code>Алматы | Best Change | 5 | Отличный курс!</code>"
    )

@dp.message(F.text.contains("|"))
async def save_review(message: types.Message):
    try:
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) >= 3:
            city, name, rating = parts[0], parts[1], int(parts[2])
            comment = parts[3] if len(parts) > 3 else ""
            
            async with aiosqlite.connect("bot_database.db") as db:
                await db.execute('''
                    INSERT INTO reviews (city, exchanger_name, rating, comment, user_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (city, name, rating, comment, message.from_user.id))
                await db.commit()
            
            await message.answer(f"✅ Отзыв добавлен!\n{city} | {name} | {'⭐' * rating}")
        else:
            await message.answer("❌ Неверный формат!")
    except:
        await message.answer("❌ Ошибка! Используйте формат: Город | Название | Оценка | Комментарий")

@dp.message(F.text == "⭐ Топ обменников")
async def top_exchangers(message: types.Message):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT exchanger_name, AVG(rating) as avg_rating, COUNT(*) as reviews
            FROM reviews
            GROUP BY exchanger_name
            ORDER BY avg_rating DESC
            LIMIT 10
        ''')
        top = await cursor.fetchall()
    
    if not top:
        await message.answer("📭 Пока нет отзывов. Будьте первым!")
        return
    
    text = "⭐ <b>ТОП ОБМЕННИКОВ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for i, (name, rating, reviews) in enumerate(top, 1):
        text += f"\n{i}. <b>{name}</b>\n   ⭐ {rating:.1f} ({reviews} отзывов)"
    await message.answer(text)

@dp.message(F.text == "📊 История")
async def show_history(message: types.Message):
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute('''
            SELECT currency, amount, result, created_at 
            FROM history 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 20
        ''', (message.from_user.id,))
        history = await cursor.fetchall()
    
    if not history:
        await message.answer("📭 Нет истории конвертаций")
        return
    
    text = "<b>📊 ИСТОРИЯ КОНВЕРТАЦИЙ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for curr, amt, res, dt in history[:10]:
        text += f"\n{curr}: {amt:.2f} = {res:.2f} ₸\n🕐 {dt[:16]}\n"
    await message.answer(text)

@dp.message(F.text == "💵 Курсы валют")
async def show_currencies(message: types.Message):
    rates = await get_currency_rates()
    text = "<b>💵 КУРСЫ ВАЛЮТ НБ РК</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for curr, rate in rates.items():
        text += f"\n{curr} / KZT → <code>{rate:.2f}</code> ₸"
    await message.answer(text)

@dp.message(F.text == "₿ Криптовалюты")
async def show_crypto(message: types.Message):
    rates = await get_crypto_rates()
    text = "<b>₿ КРИПТОВАЛЮТЫ</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    for crypto, rate in rates.items():
        text += f"\n{crypto} / KZT → <code>{rate:,.0f}</code> ₸"
    await message.answer(text)

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню", reply_markup=main_menu())

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    async with aiosqlite.connect("bot_database.db") as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        users = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE premium = 1")
        premium = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT SUM(balance) FROM users")
        total_balance = (await cursor.fetchone())[0] or 0
    
    await message.answer(
        f"🔐 <b>АДМИН-ПАНЕЛЬ</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Пользователей: {users}\n"
        f"💎 Premium: {premium}\n"
        f"💰 Игровая экономика: {total_balance:,.0f}\n\n"
        f"📊 /stats - подробная статистика\n"
        f"💡 /ideas - идеи\n"
        f"📢 /broadcast - рассылка",
        parse_mode="HTML"
    )

@dp.message()
async def convert_any(message: types.Message):
    # Конвертация в любом сообщении: "100 USD"
    match = re.match(r'^(\d+(?:\.\d+)?)\s+([A-Z]{3})$', message.text.upper().strip())
    if match:
        amount = float(match.group(1))
        currency = match.group(2)
        rates = await get_currency_rates()
        
        if currency in rates:
            result = amount * rates[currency]
            await save_history(message.from_user.id, currency, amount, result)
            await message.answer(f"💱 <b>{amount:,.2f} {currency}</b> = <b>{result:,.2f} ₸</b>\n📊 1 {currency} = {rates[currency]:.2f} ₸")

async def main():
    print("🚀 ЗАПУСК МЕГА-БОТА СО ВСЕМИ ФУНКЦИЯМИ...")
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print(f"✅ Бот @{me.username} запущен!")
    print("📱 ДОСТУПНЫЕ ФУНКЦИИ:")
    print("   • Графики курсов")
    print("   • Бюджетный трекер")
    print("   • Экономическая игра")
    print("   • Умные уведомления")
    print("   • Premium подписка")
    print("   • Реферальная программа")
    print("   • Отзывы об обменниках")
    print("   • Гороскоп")
    print("   • Ежедневная викторина")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())