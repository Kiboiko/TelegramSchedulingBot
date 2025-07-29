import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = "7807559906:AAFA0bsnb_Y6m3JHKIeWk2hZ3_ytMvnC-as"  # Замените на реальный токен

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Новый синтаксис обработчиков в aiogram 3.x
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Бот работает! ✅")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())