import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart

# Импорты из новых модулей
from config import BOT_TOKEN, is_admin
from middlewares.role_check import RoleCheckMiddleware
from handlers.start import cmd_start
from handlers.common import show_my_role, contact_admin
from handlers.booking.role_selection import process_role_selection
from storage import JSONStorage
from gsheets_manager import GoogleSheetsManager

logger = logging.getLogger(__name__)

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
storage = JSONStorage(file_path="bookings.json")

# Настройка Google Sheets
try:
    gsheets = GoogleSheetsManager(credentials_file='credentials.json', spreadsheet_id=SPREADSHEET_ID)
    gsheets.connect()
    storage.set_gsheets_manager(gsheets)
except Exception as e:
    logger.error(f"Google Sheets initialization error: {e}")
    gsheets = None

# Middleware
dp.update.middleware(RoleCheckMiddleware())

# Регистрация обработчиков
dp.message.register(cmd_start, CommandStart())
dp.message.register(show_my_role, F.text == "👤 Моя роль")
dp.message.register(contact_admin, F.text == "❓ Обратиться к администратору")
dp.callback_query.register(process_role_selection, F.data.startswith("role_"))

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())