import asyncio
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import random
import os

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "tv_guide.db"

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === ГЛАВНАЯ КЛАВИАТУРА ===
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Сегодня")
    builder.button(text="Завтра")
    builder.button(text="По жанру")
    builder.button(text="По каналу")
    builder.button(text="Помощь")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# === СОЗДАНИЕ БАЗЫ ДАННЫХ ===
async def create_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY,
                name TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS programs (
                id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                title TEXT,
                genre TEXT,
                start_time TEXT,
                date TEXT
            )
        ''')

        # Очистка и заполнение
        await db.execute("DELETE FROM channels")
        await db.execute("DELETE FROM programs")

        channels = ["Первый канал", "Россия 1", "НТВ", "ТНТ", "СТС"]
        channel_ids = []
        for ch in channels:
            await db.execute("INSERT INTO channels (name) VALUES (?)", (ch,))
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            row = await cursor.fetchone()
            channel_ids.append(row[0])

        genres = ["Фильм", "Сериал", "Новости", "Шоу", "Детское", "Спорт"]
        today = datetime.now().date()
        for day_offset in range(8):
            current_date = (today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            for cid in channel_ids:
                for hour in [9, 12, 15, 18, 21]:
                    title = random.choice([
                        "Утреннее шоу", "Вести", "Комеди Клаб", "Дом-2",
                        "Спорт", "Мультфильмы", "Кино", "Новости 21:00"
                    ])
                    genre = random.choice(genres)
                    await db.execute(
                        "INSERT INTO programs (channel_id, title, genre, start_time, date) VALUES (?, ?, ?, ?, ?)",
                        (cid, title, genre, f"{hour:02d}:00", current_date)
                    )
        await db.commit()

# === СТАРТ ===
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я — ТВ Гид\n"
        "Выбери, что хочешь узнать:",
        reply_markup=get_main_keyboard()
    )

# === ПОМОЩЬ ===
@dp.message(F.text == "Помощь")
async def help_cmd(message: types.Message):
    text = (
        "*Инструкция:*\n\n"
        "• *Сегодня / Завтра* — программа на день\n"
        "• *По жанру* — выбери жанр\n"
        "• *По каналу* — выбери канал и день\n"
        "• Даты: до +7 дней"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

# === СЕГОДНЯ / ЗАВТРА ===
@dp.message(F.text.in_(["Сегодня", "Завтра"]))
async def show_day(message: types.Message):
    offset = 0 if message.text == "Сегодня" else 1
    target_date = (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")
    pretty_date = (datetime.now() + timedelta(days=offset)).strftime("%d.%m.%Y")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT c.name, p.title, p.start_time, p.genre
            FROM programs p
            JOIN channels c ON p.channel_id = c.id
            WHERE p.date = ?
            ORDER BY p.start_time
        """, (target_date,))
        rows = await cursor.fetchall()

    if not rows:
        await message.answer(f"На {pretty_date} передач нет.")
        return

    response = f"*Программа на {pretty_date}:*\n\n"
    current_channel = ""
    for channel, title, time, genre in rows:
        if channel != current_channel:
            response += f"\n*{channel}*\n"
            current_channel = channel
        response += f"  {time} | {title} ({genre})\n"

    await message.answer(response, parse_mode="Markdown")

# === ПО ЖАНРУ ===
@dp.message(F.text == "По жанру")
async def genre_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    genres = ["Фильм", "Сериал", "Новости", "Шоу", "Детское", "Спорт"]
    for g in genres:
        builder.button(text=g, callback_data=f"genre_{g}")
    builder.adjust(2)
    await message.answer("Выбери жанр:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("genre_"))
async def show_genre(callback: types.CallbackQuery):
    genre = callback.data.split("_", 1)[1]
    today = datetime.now().date().strftime("%Y-%m-%d")
    week_later = (datetime.now().date() + timedelta(days=7)).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT c.name, p.title, p.start_time, p.date
            FROM programs p
            JOIN channels c ON p.channel_id = c.id
            WHERE p.genre = ? AND p.date BETWEEN ? AND ?
            ORDER BY p.date, p.start_time
        """, (genre, today, week_later))
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text(f"Нет передач в жанре *{genre}* на этой неделе.", parse_mode="Markdown")
        return

    response = f"*{genre} на этой неделе:*\n\n"
    for channel, title, time, date in rows:
        pretty_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m")
        response += f"{pretty_date} | {channel} | {time} | {title}\n"

    await callback.message.edit_text(response, parse_mode="Markdown")

# === ПО КАНАЛУ ===
@dp.message(F.text == "По каналу")
async def channel_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT name FROM channels")
        rows = await cursor.fetchall()
        for (name,) in rows:
            builder.button(text=name, callback_data=f"chan_{name}")
    builder.adjust(2)
    await message.answer("Выбери канал:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("chan_"))
async def show_channel_days(callback: types.CallbackQuery):
    channel = callback.data.split("_", 1)[1]
    builder = InlineKeyboardBuilder()
    today = datetime.now().date()
    for i in range(8):
        day = today + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        display = "Сегодня" if i == 0 else "Завтра" if i == 1 else day.strftime("%d.%m")
        builder.button(text=display, callback_data=f"day_{channel}_{date_str}")
    builder.adjust(3)
    await callback.message.edit_text(
        f"Выбери день для *{channel}*:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("day_"))
async def show_day_program(callback: types.CallbackQuery):
    _, channel, date = callback.data.split("_", 2)
    pretty_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT p.title, p.start_time, p.genre
            FROM programs p
            JOIN channels c ON p.channel_id = c.id
            WHERE c.name = ? AND p.date = ?
            ORDER BY p.start_time
        """, (channel, date))
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text(f"На {pretty_date} на *{channel}* передач нет.", parse_mode="Markdown")
        return

    response = f"*{channel} — {pretty_date}:*\n\n"
    for title, time, genre in rows:
        response += f"{time} | {title} ({genre})\n"

    await callback.message.edit_text(response, parse_mode="Markdown")

# === ЗАПУСК ===
async def main():
    await create_db()
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
