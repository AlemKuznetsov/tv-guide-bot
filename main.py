import asyncio
import aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
import random
import os
from aiogram import F
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен будет из Render
DB_NAME = "tv_guide.db"

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Клавиатура ===
from aiogram.utils.keyboard import ReplyKeyboardBuilder  # ← Добавь этот импорт в начало файла (после других импортов)

builder = ReplyKeyboardBuilder()
builder.button(text="Сегодня")
builder.button(text="Завтра")
builder.button(text="По жанру")
builder.button(text="По каналу")
builder.button(text="Помощь")
builder.adjust(2)  # ← 2 кнопки в ряд
main_keyboard = builder.as_markup(resize_keyboard=True)

# === Создание БД ===
async def create_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY, name TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS programs (
            id INTEGER PRIMARY KEY, channel_id INTEGER, title TEXT, genre TEXT, start_time TEXT, date TEXT
        )''')

        await db.execute("DELETE FROM channels")
        await db.execute("DELETE FROM programs")

        channels = ["Первый канал", "Россия 1", "НТВ", "ТНТ", "СТС"]
        channel_ids = []
        for ch in channels:
            await db.execute("INSERT INTO channels (name) VALUES (?)", (ch,))
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            cid = (await cursor.fetchone())[0]
            channel_ids.append(cid)

        genres = ["Фильм", "Сериал", "Новости", "Шоу", "Детское", "Спорт"]
        today = datetime.now().date()
        for day in range(8):
            date = (today + timedelta(days=day)).strftime("%Y-%m-%d")
            for cid in channel_ids:
                for hour in [9, 12, 15, 18, 21]:
                    title = random.choice(["Утро", "Вести", "Комеди Клаб", "Дом-2", "Спорт", "Мультики", "Кино"])
                    genre = random.choice(genres)
                    await db.execute("INSERT INTO programs (channel_id, title, genre, start_time, date) VALUES (?, ?, ?, ?, ?)",
                                   (cid, title, genre, f"{hour:02d}:00", date))
        await db.commit()

# === Команды ===
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Я — ТВ Гид\nВыбери действие:", reply_markup=main_keyboard)

@dp.message(F.text == "Помощь")
async def help_cmd(message: types.Message):
    await message.answer(
        "*Инструкция:*\n"
        "• *Сегодня / Завтра* — программа на день\n"
        "• *По жанру* — выбери жанр\n"
        "• *По каналу* — выбери канал и день\n"
        "• Даты: до +7 дней",
        parse_mode="Markdown", reply_markup=main_keyboard
    )

@dp.message(F.text.in_(["Сегодня", "Завтра"]))
async def show_day(message: types.Message):
    offset = 0 if message.text == "Сегодня" else 1
    target = (datetime.now().date() + timedelta(days=offset)).strftime("%Y-%m-%d")
    pretty = (datetime.now() + timedelta(days=offset)).strftime("%d.%m.%Y")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT c.name, p.title, p.start_time, p.genre FROM programs p
            JOIN channels c ON p.channel_id = c.id
            WHERE p.date = ? ORDER BY p.start_time
        """, (target,))
        rows = await cursor.fetchall()

    if not rows:
        await message.answer(f"На {pretty} передач нет.")
        return

    resp = f"*Программа на {pretty}:*\n\n"
    cur = ""
    for ch, title, time, genre in rows:
        if ch != cur:
            resp += f"\n*{ch}*\n"
            cur = ch
        resp += f"  {time} | {title} ({genre})\n"
    await message.answer(resp, parse_mode="Markdown")

@dp.message(F.text == "По жанру")
async def genre_start(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    for g in ["Фильм", "Сериал", "Новости", "Шоу", "Детское", "Спорт"]:
        kb.add(InlineKeyboardButton(g, callback_data=f"genre_{g}"))
    await message.answer("Выбери жанр:", reply_markup=kb)

@dp.message(F.text == "По каналу")
async def channel_start(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT name FROM channels")
        rows = await cursor.fetchall()
        for (name,) in rows:
            kb.add(InlineKeyboardButton(name, callback_data=f"chan_{name}"))
    await message.answer("Выбери канал:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("genre_"))
async def show_genre(callback: types.CallbackQuery):
    genre = callback.data.split("_", 1)[1]
    today = datetime.now().date().strftime("%Y-%m-%d")
    week = (datetime.now().date() + timedelta(days=7)).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT c.name, p.title, p.start_time, p.date FROM programs p
            JOIN channels c ON p.channel_id = c.id
            WHERE p.genre = ? AND p.date BETWEEN ? AND ?
            ORDER BY p.date, p.start_time
        """, (genre, today, week))
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text(f"Нет передач в жанре *{genre}*")
        return

    resp = f"*{genre} на неделе:*\n\n"
    for ch, title, time, date in rows:
        d = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m")
        resp += f"{d} | {ch} | {time} | {title}\n"
    await callback.message.edit_text(resp, parse_mode="Markdown")

@dp.callback_query(lambda c: c.data.startswith("chan_"))
async def show_channel_days(callback: types.CallbackQuery):
    channel = callback.data.split("_", 1)[1]
    kb = InlineKeyboardMarkup(row_width=3)
    today = datetime.now().date()
    for i in range(8):
        day = today + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        name = "Сегодня" if i == 0 else "Завтра" if i == 1 else day.strftime("%d.%m")
        kb.add(InlineKeyboardButton(name, callback_data=f"day_{channel}_{date_str}"))
    await callback.message.edit_text(f"День для *{channel}*:", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("day_"))
async def show_day_program(callback: types.CallbackQuery):
    _, channel, date = callback.data.split("_", 2)
    pretty = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT p.title, p.start_time, p.genre FROM programs p
            JOIN channels c ON p.channel_id = c.id
            WHERE c.name = ? AND p.date = ?
        """, (channel, date))
        rows = await cursor.fetchall()

    if not rows:
        await callback.message.edit_text(f"На {pretty} на *{channel}* ничего нет.")
        return

    resp = f"*{channel} — {pretty}:*\n\n"
    for title, time, genre in rows:
        resp += f"{time} | {title} ({genre})\n"
    await callback.message.edit_text(resp, parse_mode="Markdown")

# === Запуск ===
async def main():
    await create_db()
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
