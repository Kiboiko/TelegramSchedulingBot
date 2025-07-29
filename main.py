import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

bot = Bot(token="7807559906:AAFA0bsnb_Y6m3JHKIeWk2hZ3_ytMvnC-as")
dp = Dispatcher()

# Хранение данных
user_data = {}
bookings = []  # Все бронирования
booking_id_counter = 1  # Счетчик для ID бронирований

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Забронировать время")],
        [KeyboardButton(text="📋 Мои бронирования"), KeyboardButton(text="❌ Отменить бронь")]
    ],
    resize_keyboard=True
)

def generate_calendar(year=None, month=None):
    """Генерирует календарь"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    builder = InlineKeyboardBuilder()
    
    # Заголовок
    month_name = datetime(year, month, 1).strftime("%B %Y")
    builder.row(types.InlineKeyboardButton(text=month_name, callback_data="ignore"))

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[types.InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])

    # Даты
    first_day = datetime(year, month, 1)
    start_weekday = first_day.weekday()
    days_in_month = (datetime(year, month + 1, 1) - first_day).days

    buttons = []
    for _ in range(start_weekday):
        buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))

    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day)
        if date.date() < datetime.now().date():
            buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
        else:
            buttons.append(types.InlineKeyboardButton(
                text=str(day), 
                callback_data=f"calendar_day_{year}-{month}-{day}"
            ))
        if (day + start_weekday) % 7 == 0 or day == days_in_month:
            builder.row(*buttons)
            buttons = []

    # Навигация
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    builder.row(
        types.InlineKeyboardButton(text="⬅️", callback_data=f"calendar_change_{prev_year}-{prev_month}"),
        types.InlineKeyboardButton(text="➡️", callback_data=f"calendar_change_{next_year}-{next_month}"),
    )

    return builder.as_markup()

def generate_time_slots(selected_date):
    """Генерирует выбор времени"""
    builder = InlineKeyboardBuilder()
    
    start_time = datetime.strptime("09:00", "%H:%M")
    end_time = datetime.strptime("20:00", "%H:%M")
    current_time = start_time
    
    while current_time <= end_time:
        time_str = current_time.strftime("%H:%M")
        builder.add(types.InlineKeyboardButton(
            text=time_str,
            callback_data=f"time_slot_{time_str}"
        ))
        current_time += timedelta(minutes=30)
    
    builder.adjust(4)
    return builder.as_markup()

def generate_confirmation():
    """Клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking_confirm"),
        types.InlineKeyboardButton(text="❌ Отменить", callback_data="booking_cancel"),
    )
    return builder.as_markup()

def generate_booking_list(user_id):
    """Генерирует список бронирований пользователя"""
    user_bookings = [b for b in bookings if b["user_id"] == user_id]
    if not user_bookings:
        return None
    
    builder = InlineKeyboardBuilder()
    for booking in user_bookings:
        builder.row(types.InlineKeyboardButton(
            text=f"{booking['date'].strftime('%d.%m.%Y')} {booking['time_start']}-{booking['time_end']} (ID: {booking['id']})",
            callback_data=f"booking_info_{booking['id']}"
        ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_menu"
    ))
    return builder.as_markup()

def generate_booking_actions(booking_id):
    """Клавиатура действий с бронированием"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"cancel_booking_{booking_id}"),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_bookings"),
    )
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Добро пожаловать в систему бронирования!\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=main_menu
    )

@dp.message(lambda message: message.text == "📅 Забронировать время")
async def start_booking(message: types.Message):
    await message.answer("Выберите дату:", reply_markup=generate_calendar())

@dp.message(lambda message: message.text == "📋 Мои бронирования")
async def show_bookings(message: types.Message):
    keyboard = generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований")
        return
    
    await message.answer("Ваши бронирования:", reply_markup=keyboard)

@dp.message(lambda message: message.text == "❌ Отменить бронь")
async def start_cancel_booking(message: types.Message):
    keyboard = generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований для отмены")
        return
    
    await message.answer("Выберите бронирование для отмены:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("calendar_"))
async def process_calendar(callback: types.CallbackQuery):
    data = callback.data
    
    if data.startswith("calendar_day_"):
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()
        
        user_data[callback.from_user.id] = {
            "selected_date": selected_date,
            "state": "selecting_start_time"
        }
        
        await callback.message.edit_text(
            f"Выбрана дата: {day}.{month}.{year}\nВыберите время начала:",
            reply_markup=generate_time_slots(selected_date)
        )
        await callback.answer()
        
    elif data.startswith("calendar_change_"):
        date_str = data.replace("calendar_change_", "")
        year, month = map(int, date_str.split("-"))
        await callback.message.edit_reply_markup(reply_markup=generate_calendar(year, month))
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("time_slot_"))
async def process_time_slot(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    time_str = callback.data.replace("time_slot_", "")
    
    if user_data.get(user_id, {}).get("state") == "selecting_start_time":
        user_data[user_id].update({
            "time_start": time_str,
            "state": "selecting_end_time"
        })
        await callback.message.edit_text(
            f"Начальное время: {time_str}\nВыберите конечное время:",
            reply_markup=generate_time_slots(user_data[user_id]["selected_date"])
        )
    else:
        time_start = datetime.strptime(user_data[user_id]["time_start"], "%H:%M")
        time_end = datetime.strptime(time_str, "%H:%M")
        
        if time_end <= time_start:
            await callback.answer("Конечное время должно быть после начального!", show_alert=True)
            return
        
        user_data[user_id].update({
            "time_end": time_str,
            "state": "confirmation"
        })
        
        await callback.message.edit_text(
            f"📋 Подтвердите бронирование:\n\n"
            f"Дата: {user_data[user_id]['selected_date'].strftime('%d.%m.%Y')}\n"
            f"Время: {user_data[user_id]['time_start']} - {time_str}",
            reply_markup=generate_confirmation()
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["booking_confirm", "booking_cancel"])
async def process_confirmation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "booking_confirm":
        global booking_id_counter
        booking = {
            "id": booking_id_counter,
            "date": user_data[user_id]["selected_date"],
            "time_start": user_data[user_id]["time_start"],
            "time_end": user_data[user_id]["time_end"],
            "user_id": user_id
        }
        bookings.append(booking)
        booking_id_counter += 1
        
        await callback.message.edit_text(
            "✅ Бронирование подтверждено!\n\n"
            f"ID: {booking['id']}\n"
            f"Дата: {booking['date'].strftime('%d.%m.%Y')}\n"
            f"Время: {booking['time_start']} - {booking['time_end']}\n\n"
            "Вы можете просмотреть или отменить бронирование через меню",
        )
    else:
        await callback.message.edit_text("❌ Бронирование отменено")
    
    user_data.pop(user_id, None)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("booking_info_"))
async def show_booking_info(callback: types.CallbackQuery):
    booking_id = int(callback.data.replace("booking_info_", ""))
    booking = next((b for b in bookings if b["id"] == booking_id), None)
    
    if not booking:
        await callback.answer("Бронирование не найдено", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"Информация о бронировании:\n\n"
        f"ID: {booking['id']}\n"
        f"Дата: {booking['date'].strftime('%d.%m.%Y')}\n"
        f"Время: {booking['time_start']} - {booking['time_end']}",
        reply_markup=generate_booking_actions(booking['id'])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    booking = next((b for b in bookings if b["id"] == booking_id), None)
    
    if not booking:
        await callback.answer("Бронирование не найдено", show_alert=True)
        return
    
    if booking["user_id"] != callback.from_user.id:
        await callback.answer("Вы не можете отменить чужое бронирование", show_alert=True)
        return
    
    bookings.remove(booking)
    await callback.message.edit_text(
        f"❌ Бронирование ID {booking_id} отменено\n\n"
        f"Дата: {booking['date'].strftime('%d.%m.%Y')}\n"
        f"Время: {booking['time_start']} - {booking['time_end']}"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["back_to_menu", "back_to_bookings"])
async def back_handler(callback: types.CallbackQuery):
    if callback.data == "back_to_menu":
        await callback.message.edit_text(
            "Главное меню:",
            reply_markup=None
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=main_menu
        )
    else:
        keyboard = generate_booking_list(callback.from_user.id)
        await callback.message.edit_text(
            "Ваши бронирования:",
            reply_markup=keyboard
        )
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


# import os
# from aiogram import Bot, Dispatcher, types, F
# from aiogram.filters import Command
# from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
# from dotenv import load_dotenv
# from storage import JSONStorage
#
# load_dotenv()
# bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
# dp = Dispatcher()
# storage = JSONStorage()
#
# # Клавиатуры
# user_keyboard = ReplyKeyboardMarkup(
#     keyboard=[
#         [KeyboardButton(text="📅 Свободные слоты"), KeyboardButton(text="🗓 Мои записи")],
#         [KeyboardButton(text="🆘 Помощь")]
#     ],
#     resize_keyboard=True
# )
#
# admin_keyboard = ReplyKeyboardMarkup(
#     keyboard=[
#         [KeyboardButton(text="➕ Добавить слот")],
#         [KeyboardButton(text="📊 Все записи")]
#     ],
#     resize_keyboard=True
# )
#
# # Команды для всех
# @dp.message(Command("start"))
# async def start(message: types.Message):
#     await message.answer(
#         "Привет! Я бот для записи на занятия.",
#         reply_markup=user_keyboard
#     )
#
# @dp.message(Command("help"))
# @dp.message(F.text == "🆘 Помощь")
# async def help(message: types.Message):
#     text = (
#         "📌 Доступные команды:\n"
#         "/start - Начать работу\n"
#         "/help - Справка\n"
#         "/slots - Свободные слоты\n"
#         "/book <ID> - Бронировать\n"
#         "/cancel <ID> - Отменить\n\n"
#         "Или используйте кнопки ниже!"
#     )
#     await message.answer(text)
#
# @dp.message(Command("slots"))
# @dp.message(F.text == "📅 Свободные слоты")
# async def show_slots(message: types.Message):
#     slots = storage.get_available_slots()
#     if not slots:
#         await message.answer("❌ Нет свободных слотов")
#         return
#     text = "Свободные слоты:\n" + "\n".join(
#         f"{slot_id}: {info['date']} {info['time']}"
#         for slot_id, info in slots.items()
#     )
#     await message.answer(text)
#
# # Команды для админа
# @dp.message(Command("add_slot"))
# async def add_slot_command(message: types.Message):
#     if message.from_user.id != YOUR_ADMIN_ID:  # Замените на ваш ID
#         return
#     await message.answer(
#         "Введите дату и время в формате: ДД.ММ.ГГГГ ЧЧ:ММ",
#         reply_markup=admin_keyboard
#     )
#
# @dp.message(F.text == "➕ Добавить слот")
# async def add_slot_button(message: types.Message):
#     if message.from_user.id != YOUR_ADMIN_ID:
#         return
#     await message.answer("Введите дату и время в формате: ДД.ММ.ГГГГ ЧЧ:ММ")
#
# # Обработчик текста для добавления слотов (админ)
# @dp.message(F.text.regexp(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}"))
# async def process_add_slot(message: types.Message):
#     if message.from_user.id != YOUR_ADMIN_ID:
#         return
#     date, time = message.text.split()
#     slot_id = storage.add_slot(date, time)
#     await message.answer(f"✅ Слот добавлен (ID: {slot_id})")
#
# # Запуск бота
# async def main():
#     await dp.start_polling(bot)
#
# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())

