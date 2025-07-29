import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
from storage import JSONStorage

load_dotenv()
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()
storage = JSONStorage()

# Клавиатуры
user_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Свободные слоты"), KeyboardButton(text="🗓 Мои записи")],
        [KeyboardButton(text="🆘 Помощь")]
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Добавить слот")],
        [KeyboardButton(text="📊 Все записи")]
    ],
    resize_keyboard=True
)

# Команды для всех
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Я бот для записи на занятия.",
        reply_markup=user_keyboard
    )

@dp.message(Command("help"))
@dp.message(F.text == "🆘 Помощь")
async def help(message: types.Message):
    text = (
        "📌 Доступные команды:\n"
        "/start - Начать работу\n"
        "/help - Справка\n"
        "/slots - Свободные слоты\n"
        "/book <ID> - Бронировать\n"
        "/cancel <ID> - Отменить\n\n"
        "Или используйте кнопки ниже!"
    )
    await message.answer(text)

@dp.message(Command("slots"))
@dp.message(F.text == "📅 Свободные слоты")
async def show_slots(message: types.Message):
    slots = storage.get_available_slots()
    if not slots:
        await message.answer("❌ Нет свободных слотов")
        return
    text = "Свободные слоты:\n" + "\n".join(
        f"{slot_id}: {info['date']} {info['time']}"
        for slot_id, info in slots.items()
    )
    await message.answer(text)

# Команды для админа
@dp.message(Command("add_slot"))
async def add_slot_command(message: types.Message):
    if message.from_user.id != YOUR_ADMIN_ID:  # Замените на ваш ID
        return
    await message.answer(
        "Введите дату и время в формате: ДД.ММ.ГГГГ ЧЧ:ММ",
        reply_markup=admin_keyboard
    )

@dp.message(F.text == "➕ Добавить слот")
async def add_slot_button(message: types.Message):
    if message.from_user.id != YOUR_ADMIN_ID:
        return
    await message.answer("Введите дату и время в формате: ДД.ММ.ГГГГ ЧЧ:ММ")

# Обработчик текста для добавления слотов (админ)
@dp.message(F.text.regexp(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}"))
async def process_add_slot(message: types.Message):
    if message.from_user.id != YOUR_ADMIN_ID:
        return
    date, time = message.text.split()
    slot_id = storage.add_slot(date, time)
    await message.answer(f"✅ Слот добавлен (ID: {slot_id})")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())