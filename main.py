import asyncio
import json
import os
from datetime import datetime, timedelta, date
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Конфигурация
BOT_TOKEN = "8413883420:AAGL9-27CcgEUsaCbP-PJ8ukuh1u1x3YPbQ"
BOOKINGS_FILE = "bookings.json"
BOOKING_TYPES = ["Тип1", "Тип2", "Тип3", "Тип4"]

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранение временных данных
user_data = {}
booking_id_counter = 1

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Забронировать время")],
        [KeyboardButton(text="📋 Мои бронирования"), KeyboardButton(text="❌ Отменить бронь")]
    ],
    resize_keyboard=True
)

def generate_booking_types():
    """Генерирует клавиатуру с типами бронирований"""
    builder = InlineKeyboardBuilder()
    for booking_type in BOOKING_TYPES:
        builder.add(types.InlineKeyboardButton(
            text=booking_type,
            callback_data=f"booking_type_{booking_type}"
        ))
    builder.adjust(2)
    return builder.as_markup()

def merge_adjacent_bookings(bookings):
    """Объединяет смежные бронирования одного типа"""
    if not bookings:
        return bookings
    
    # Сортируем бронирования по типу, дате и времени начала
    sorted_bookings = sorted(bookings, key=lambda x: (
        x['booking_type'],
        x['date'],
        x['time_start']
    ))
    
    merged = []
    current = sorted_bookings[0]
    
    for next_booking in sorted_bookings[1:]:
        # Проверяем условия для объединения:
        # 1. Один тип
        # 2. Одна дата
        # 3. Время конца текущего = времени начала следующего
        if (current['booking_type'] == next_booking['booking_type'] and
            current['date'] == next_booking['date'] and
            current['time_end'] == next_booking['time_start']):
            
            # Объединяем бронирования
            current = {
                **current,
                'time_end': next_booking['time_end'],
                'id': min(current['id'], next_booking['id']),  # Сохраняем минимальный ID
                'merged': True  # Помечаем как объединенное
            }
        else:
            merged.append(current)
            current = next_booking
    
    merged.append(current)
    return merged

def load_bookings():
    """Загружает бронирования из файла, объединяет смежные и удаляет прошедшие"""
    if not os.path.exists(BOOKINGS_FILE):
        return []
    
    with open(BOOKINGS_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            valid_bookings = []
            current_time = datetime.now()
            
            for booking in data:
                if 'date' not in booking:
                    continue
                try:
                    # Преобразуем дату и время бронирования
                    if isinstance(booking['date'], str):
                        booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                    else:
                        continue
                    
                    time_end = datetime.strptime(booking['time_end'], "%H:%M").time()
                    booking_datetime = datetime.combine(booking_date, time_end)
                    
                    # Проверяем, не прошло ли время бронирования
                    if booking_datetime < current_time:
                        continue
                        
                    booking['date'] = booking_date
                    valid_bookings.append(booking)
                    
                except ValueError:
                    continue
            
            # Объединяем смежные бронирования
            valid_bookings = merge_adjacent_bookings(valid_bookings)
            
            # Если были изменения, сохраняем обновленный список
            if len(valid_bookings) != len(data):
                save_bookings(valid_bookings)
                
            return valid_bookings
            
        except (json.JSONDecodeError, KeyError, ValueError):
            return []

def save_bookings(bookings_list):
    """Сохраняет бронирования в файл, фильтруя прошедшие"""
    current_time = datetime.now()
    bookings_to_save = []
    
    for booking in bookings_list:
        try:
            # Проверяем, не прошло ли время бронирования
            if isinstance(booking['date'], date):
                booking_date = booking['date']
            elif isinstance(booking['date'], str):
                booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
            else:
                continue
                
            time_end = datetime.strptime(booking['time_end'], "%H:%M").time()
            booking_datetime = datetime.combine(booking_date, time_end)
            
            if booking_datetime >= current_time:
                booking_copy = booking.copy()
                if isinstance(booking_copy['date'], date):
                    booking_copy['date'] = booking_copy['date'].strftime("%Y-%m-%d")
                bookings_to_save.append(booking_copy)
                
        except (ValueError, KeyError):
            continue
    
    with open(BOOKINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(bookings_to_save, f, ensure_ascii=False, indent=2)

def get_next_booking_id():
    """Генерирует следующий ID для бронирования"""
    global booking_id_counter
    bookings = load_bookings()
    if bookings:
        booking_id_counter = max(b["id"] for b in bookings) + 1
    else:
        booking_id_counter = 1
    return booking_id_counter

def has_booking_conflict(user_id, booking_type, date, time_start, time_end, exclude_id=None):
    """Проверяет есть ли конфликтующие бронирования того же типа"""
    bookings = load_bookings()
    for booking in bookings:
        if (booking['user_id'] == user_id and 
            booking['booking_type'] == booking_type and 
            booking['date'] == date):
            
            if exclude_id and booking['id'] == exclude_id:
                continue
            
            def time_to_minutes(t):
                h, m = map(int, t.split(':'))
                return h * 60 + m
            
            new_start = time_to_minutes(time_start)
            new_end = time_to_minutes(time_end)
            existing_start = time_to_minutes(booking['time_start'])
            existing_end = time_to_minutes(booking['time_end'])
            
            if not (new_end <= existing_start or new_start >= existing_end):
                return True
    return False

def generate_calendar(year=None, month=None):
    """Генерирует календарь"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    builder = InlineKeyboardBuilder()
    
    month_name = datetime(year, month, 1).strftime("%B %Y")
    builder.row(types.InlineKeyboardButton(text=month_name, callback_data="ignore"))

    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[types.InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])

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
    """Генерирует выбор времени с кнопкой отмены"""
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
    builder.row(types.InlineKeyboardButton(
        text="❌ Отменить выбор времени",
        callback_data="cancel_time_selection"
    ))
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
    """Генерирует список бронирований пользователя с сортировкой по дате и времени"""
    bookings = load_bookings()
    user_bookings = [b for b in bookings if b["user_id"] == user_id]
    
    if not user_bookings:
        return None
    
    def get_sort_key(booking):
        booking_date = booking['date']
        if isinstance(booking_date, str):
            booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        time_obj = datetime.strptime(booking['time_start'], "%H:%M").time()
        return (booking_date, time_obj)
    
    user_bookings.sort(key=get_sort_key)
    
    builder = InlineKeyboardBuilder()
    for booking in user_bookings:
        booking_date = booking['date']
        if isinstance(booking_date, str):
            booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        
        # Добавляем пометку, если бронь была объединена
        merged_note = " (объединено)" if booking.get('merged', False) else ""
        builder.row(types.InlineKeyboardButton(
            text=f"{booking['booking_type']}{merged_note} {booking_date.strftime('%d.%m.%Y')} {booking['time_start']}-{booking['time_end']} (ID: {booking['id']})",
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
    await message.answer("Выберите тип бронирования:", reply_markup=generate_booking_types())

@dp.message(lambda message: message.text == "📋 Мои бронирования")
async def show_bookings(message: types.Message):
    keyboard = generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований")
        return
    
    await message.answer("Ваши бронирования (отсортированы по дате и времени):", reply_markup=keyboard)

@dp.message(lambda message: message.text == "❌ Отменить бронь")
async def start_cancel_booking(message: types.Message):
    keyboard = generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований для отмены")
        return
    
    await message.answer("Выберите бронирование для отмены:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("booking_type_"))
async def process_booking_type(callback: types.CallbackQuery):
    booking_type = callback.data.replace("booking_type_", "")
    user_data[callback.from_user.id] = {
        "booking_type": booking_type,
        "state": "selecting_date"
    }
    await callback.message.edit_text(
        f"Выбран тип: {booking_type}\nТеперь выберите дату:",
        reply_markup=generate_calendar()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("calendar_"))
async def process_calendar(callback: types.CallbackQuery):
    data = callback.data
    
    if data.startswith("calendar_day_"):
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()
        
        user_data[callback.from_user.id].update({
            "selected_date": selected_date,
            "state": "selecting_start_time"
        })
        
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
        
        # Проверка на конфликты только для текущего типа бронирования
        if has_booking_conflict(
            user_id=user_id,
            booking_type=user_data[user_id]["booking_type"],
            date=user_data[user_id]["selected_date"],
            time_start=user_data[user_id]["time_start"],
            time_end=time_str
        ):
            await callback.answer(
                f"У вас уже есть бронь типа '{user_data[user_id]['booking_type']}' на это время!",
                show_alert=True
            )
            return
        
        user_data[user_id].update({
            "time_end": time_str,
            "state": "confirmation"
        })
        
        await callback.message.edit_text(
            f"📋 Подтвердите бронирование:\n\n"
            f"Тип: {user_data[user_id]['booking_type']}\n"
            f"Дата: {user_data[user_id]['selected_date'].strftime('%d.%m.%Y')}\n"
            f"Время: {user_data[user_id]['time_start']} - {time_str}",
            reply_markup=generate_confirmation()
        )
    
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel_time_selection")
async def cancel_time_selection(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    await callback.message.edit_text(
        "Выбор времени отменён. Можете начать заново.",
        reply_markup=None
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=main_menu
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data in ["booking_confirm", "booking_cancel"])
async def process_confirmation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if callback.data == "booking_confirm":
        # Дополнительная проверка на случай, если что-то изменилось
        if has_booking_conflict(
            user_id=user_id,
            booking_type=user_data[user_id]["booking_type"],
            date=user_data[user_id]["selected_date"],
            time_start=user_data[user_id]["time_start"],
            time_end=user_data[user_id]["time_end"]
        ):
            await callback.message.edit_text(
                "К сожалению, это время стало недоступно. Пожалуйста, начните бронирование заново."
            )
            user_data.pop(user_id, None)
            await callback.answer()
            return
        
        booking_id = get_next_booking_id()
        booking = {
            "id": booking_id,
            "booking_type": user_data[user_id]["booking_type"],
            "date": user_data[user_id]["selected_date"],
            "time_start": user_data[user_id]["time_start"],
            "time_end": user_data[user_id]["time_end"],
            "user_id": user_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Сохраняем бронирование
        bookings = load_bookings()
        bookings.append(booking)
        save_bookings(bookings)
        
        await callback.message.edit_text(
            "✅ Бронирование подтверждено!\n\n"
            f"Тип: {booking['booking_type']}\n"
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
    bookings = load_bookings()
    booking = next((b for b in bookings if b["id"] == booking_id), None)
    
    if not booking:
        await callback.answer("Бронирование не найдено", show_alert=True)
        return
    
    booking_date = booking['date']
    if isinstance(booking_date, str):
        booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
    
    await callback.message.edit_text(
        f"Информация о бронировании:\n\n"
        f"Тип: {booking['booking_type']}\n"
        f"ID: {booking['id']}\n"
        f"Дата: {booking_date.strftime('%d.%m.%Y')}\n"
        f"Время: {booking['time_start']} - {booking['time_end']}\n"
        f"Создано: {booking.get('created_at', 'неизвестно')}",
        reply_markup=generate_booking_actions(booking['id'])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    bookings = load_bookings()
    booking = next((b for b in bookings if b["id"] == booking_id), None)
    
    if not booking:
        await callback.answer("Бронирование не найдено", show_alert=True)
        return
    
    if booking["user_id"] != callback.from_user.id:
        await callback.answer("Вы не можете отменить чужое бронирование", show_alert=True)
        return
    
    # Удаляем бронирование
    updated_bookings = [b for b in bookings if b["id"] != booking_id]
    save_bookings(updated_bookings)
    
    booking_date = booking['date']
    if isinstance(booking_date, str):
        booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
    
    await callback.message.edit_text(
        f"❌ Бронирование отменено\n\n"
        f"Тип: {booking['booking_type']}\n"
        f"ID: {booking['id']}\n"
        f"Дата: {booking_date.strftime('%d.%m.%Y')}\n"
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

async def cleanup_old_bookings():
    """Периодически очищает старые бронирования"""
    while True:
        # Загружаем и сохраняем - это автоматически удалит старые записи
        bookings = load_bookings()
        save_bookings(bookings)
        # Проверяем каждые 6 часов
        await asyncio.sleep(6 * 60 * 60)

async def main():
    asyncio.create_task(cleanup_old_bookings())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())