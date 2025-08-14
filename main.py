import asyncio
import json
import os
import logging
from datetime import datetime, timedelta, date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import threading
from gsheets_manager import GoogleSheetsManager
from storage import JSONStorage
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOKINGS_FILE = "bookings.json"

BOOKING_TYPES = ["Тип1"]
SUBJECTS = {
    "math": "Математика",
    "inf": "Информатика",
    "rus": "Русский язык",
    "phys": "Физика"
}

class BookingStates(StatesGroup):
    SELECT_ROLE = State()
    INPUT_NAME = State()
    TEACHER_SUBJECTS = State()
    SELECT_SUBJECT = State()
    SELECT_BOOKING_TYPE = State()
    SELECT_DATE = State()
    SELECT_TIME_RANGE = State()  # Объединенное состояние для выбора времени
    CONFIRMATION = State()

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
storage = JSONStorage(file_path=BOOKINGS_FILE)

# Настройка Google Sheets
try:
    gsheets = GoogleSheetsManager(
        credentials_file='credentials.json',
        spreadsheet_id='1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU'
    )
    gsheets.connect()
    storage.set_gsheets_manager(gsheets)
    logger.info("Google Sheets integration initialized successfully")
except Exception as e:
    logger.error(f"Google Sheets initialization error: {e}")
    gsheets = None

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

    sorted_bookings = sorted(bookings, key=lambda x: (
        x.get('booking_type', ''),
        x.get('date', ''),
        x.get('start_time', '')
    ))

    merged = []
    current = sorted_bookings[0]

    for next_booking in sorted_bookings[1:]:
        if (current.get('booking_type') == next_booking.get('booking_type') and
                current.get('date') == next_booking.get('date') and
                current.get('end_time') == next_booking.get('start_time')):

            current = {
                **current,
                'end_time': next_booking.get('end_time'),
                'id': min(current.get('id', 0), next_booking.get('id', 0)),
                'merged': True
            }
        else:
            merged.append(current)
            current = next_booking

    merged.append(current)
    return merged

def load_bookings():
    """Загружает бронирования из файла, объединяет смежные и удаляет прошедшие"""
    data = storage.load()
    valid_bookings = []
    current_time = datetime.now()

    for booking in data:
        if 'date' not in booking:
            continue

        try:
            if isinstance(booking['date'], str):
                booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
            else:
                continue

            time_end = datetime.strptime(booking.get('end_time', "00:00"), "%H:%M").time()
            booking_datetime = datetime.combine(booking_date, time_end)

            if booking_datetime < current_time:
                continue

            booking['date'] = booking_date
            valid_bookings.append(booking)

        except ValueError:
            continue

    valid_bookings = merge_adjacent_bookings(valid_bookings)
    return valid_bookings

def has_booking_conflict(user_id, booking_type, date, time_start, time_end, exclude_id=None):
    """Проверяет есть ли конфликтующие бронирования того же типа"""
    bookings = load_bookings()
    for booking in bookings:
        if (booking.get('user_id') == user_id and
                booking.get('booking_type') == booking_type and
                booking.get('date') == date):

            if exclude_id and booking.get('id') == exclude_id:
                continue

            def time_to_minutes(t):
                h, m = map(int, t.split(':'))
                return h * 60 + m

            new_start = time_to_minutes(time_start)
            new_end = time_to_minutes(time_end)
            existing_start = time_to_minutes(booking.get('start_time', '00:00'))
            existing_end = time_to_minutes(booking.get('end_time', '00:00'))

            if not (new_end <= existing_start or new_start >= existing_end):
                return True
    return False

def generate_calendar(year=None, month=None):
    """Генерирует календарь, начиная с 1 сентября или текущей даты (если она позже)"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    # Определяем минимальную дату для отображения (1 сентября текущего года)
    min_date = datetime(year=now.year, month=9, day=1).date()
    
    # Если текущая дата позже 1 сентября, используем текущую дату как минимальную
    if now.date() > min_date:
        min_date = now.date()

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
        current_date = datetime(year, month, day).date()
        if current_date < min_date:
            buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
        else:
            buttons.append(types.InlineKeyboardButton(
                text=str(day),
                callback_data=f"calendar_day_{year}-{month}-{day}"
            ))
        if (day + start_weekday) % 7 == 0 or day == days_in_month:
            builder.row(*buttons)
            buttons = []

    # Добавляем кнопки навигации только если есть месяцы для навигации
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    
    # Проверяем, можно ли перейти на предыдущий месяц
    prev_month_min_date = datetime(prev_year, prev_month, 1).date()
    show_prev = prev_month_min_date >= min_date or (prev_year > now.year or (prev_year == now.year and prev_month >= 9))
    
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    show_next = True  # Всегда можно перейти вперед

    nav_buttons = []
    if show_prev:
        nav_buttons.append(types.InlineKeyboardButton(text="⬅️", callback_data=f"calendar_change_{prev_year}-{prev_month}"))
    else:
        nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
        
    if show_next:
        nav_buttons.append(types.InlineKeyboardButton(text="➡️", callback_data=f"calendar_change_{next_year}-{next_month}"))
    else:
        nav_buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))

    builder.row(*nav_buttons)

    return builder.as_markup()

def generate_time_range_keyboard(selected_date=None, start_time=None, end_time=None):
    """Генерирует клавиатуру выбора временного диапазона с раздельными кнопками выбора"""
    builder = InlineKeyboardBuilder()

    # Определяем рабочие часы (9:00 - 20:00)
    start = datetime.strptime("09:00", "%H:%M")
    end = datetime.strptime("20:00", "%H:%M")
    current = start

    while current <= end:
        time_str = current.strftime("%H:%M")
        time_obj = current.time()
        
        # Определяем стиль кнопки
        if start_time and time_str == start_time:
            button_text = "🟢 " + time_str  # Начало - зеленый
        elif end_time and time_str == end_time:
            button_text = "🔴 " + time_str  # Конец - красный
        elif (start_time and end_time and 
              datetime.strptime(start_time, "%H:%M").time() < time_obj < 
              datetime.strptime(end_time, "%H:%M").time()):
            button_text = "🔵 " + time_str  # Промежуток - синий
        else:
            button_text = time_str  # Обычный вид

        builder.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"time_point_{time_str}"
        ))
        current += timedelta(minutes=30)

    builder.adjust(4)
    
    # Добавляем кнопки управления
    control_buttons = [
        types.InlineKeyboardButton(
            text="Выбрать начало 🟢",
            callback_data="select_start_mode"
        ),
        types.InlineKeyboardButton(
            text="Выбрать конец 🔴",
            callback_data="select_end_mode"
        )
    ]
    
    builder.row(*control_buttons)
    
    if start_time and end_time:
        builder.row(
            types.InlineKeyboardButton(
                text="✅ Подтвердить время",
                callback_data="confirm_time_range"
            )
        )
    
    builder.row(
        types.InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_time_selection"
        )
    )
    
    return builder.as_markup()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "select_end_mode")
async def select_end_mode_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Проверка что уже выбрано время начала
    if not data.get('time_start'):
        await callback.answer(
            "Сначала выберите время начала!",
            show_alert=True
        )
        return
    
    await state.update_data(selecting_mode='end')
    
    await callback.message.edit_text(
        f"Текущее начало: {data['time_start']}\n"
        "Выберите время окончания (красный маркер):",
        reply_markup=generate_time_range_keyboard(
            selected_date=data.get('selected_date'),
            start_time=data['time_start'],
            end_time=data.get('time_end')
        )
    )
    await callback.answer()

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
    user_bookings = [b for b in bookings if b.get("user_id") == user_id]

    if not user_bookings:
        return None

    def get_sort_key(booking):
        booking_date = booking.get('date')
        if isinstance(booking_date, str):
            booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        time_obj = datetime.strptime(booking.get('start_time', '00:00'), "%H:%M").time()
        return (booking_date, time_obj)

    user_bookings.sort(key=get_sort_key)

    builder = InlineKeyboardBuilder()
    for booking in user_bookings:
        booking_date = booking.get('date')
        if isinstance(booking_date, str):
            booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()

        merged_note = " (объединено)" if booking.get('merged', False) else ""
        builder.row(types.InlineKeyboardButton(
            text=f"{booking.get('user_role', '')}{merged_note} {booking_date.strftime('%d.%m.%Y')} {booking.get('start_time', '')}-{booking.get('end_time', '')} (ID: {booking.get('id', '')})",
            callback_data=f"booking_info_{booking.get('id', '')}"
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

def generate_subjects_keyboard(selected_subjects=None, is_teacher=False):
    builder = InlineKeyboardBuilder()
    selected_subjects = selected_subjects or []

    for subject_id, subject_name in SUBJECTS.items():
        emoji = "✅" if subject_id in selected_subjects else "⬜️"
        builder.button(
            text=f"{emoji} {subject_name}",
            callback_data=f"subject_{subject_id}"
        )

    if is_teacher:
        builder.button(text="Готово", callback_data="subjects_done")
        builder.adjust(2, 2, 1)
    else:
        builder.adjust(2)

    return builder.as_markup()

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Забронировать время")],
        [KeyboardButton(text="📋 Мои бронирования"), KeyboardButton(text="❌ Отменить бронь")]
    ],
    resize_keyboard=True
)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Добро пожаловать в систему бронирования!\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=main_menu
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📋 Справка по боту:\n\n"
        "/book - начать процесс бронирования\n"
        " 1. Выбрать роль (ученик/преподаватель)\n"
        " 2. Ввести ваше ФИО\n"
        " 3. Выбрать предмет(ы)\n"
        " 4. Выбрать тип бронирования\n"
        " 5. Выбрать дату из календаря\n"
        " 6. Выбрать время начала и окончания\n"
        " 7. Подтвердить бронирование\n\n"
        "/my_bookings - показать ваши бронирования\n"
        "/my_role - показать вашу роль\n"
        "/help - показать эту справку"
    )

@dp.message(F.text == "📅 Забронировать время")
@dp.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🎓 Я ученик", callback_data="role_student")
    builder.button(text="👨‍🏫 Я преподаватель", callback_data="role_teacher")

    await message.answer(
        "Перед началом бронирования, пожалуйста, укажите вашу роль:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(BookingStates.SELECT_ROLE)

@dp.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    await state.update_data(user_role=role)

    await callback.message.edit_text("Введите ваше полное ФИО:")
    await state.set_state(BookingStates.INPUT_NAME)
    await callback.answer()

@dp.message(BookingStates.INPUT_NAME)
async def process_name(message: types.Message, state: FSMContext):
    if len(message.text.split()) < 2:
        await message.answer("Пожалуйста, введите полное ФИО (минимум имя и фамилию)")
        return

    await state.update_data(user_name=message.text)
    data = await state.get_data()

    if data['user_role'] == 'teacher':
        await message.answer(
            "Выберите предметы, которые вы преподаете:",
            reply_markup=generate_subjects_keyboard(is_teacher=True)
        )
        await state.set_state(BookingStates.TEACHER_SUBJECTS)
    else:
        await message.answer(
            "Выберите предмет для занятия:",
            reply_markup=generate_subjects_keyboard()
        )
        await state.set_state(BookingStates.SELECT_SUBJECT)

@dp.callback_query(BookingStates.TEACHER_SUBJECTS, F.data.startswith("subject_"))
async def process_teacher_subjects(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_subjects = data.get("subjects", [])

    subject_id = callback.data.split("_")[1]
    if subject_id in selected_subjects:
        selected_subjects.remove(subject_id)
    else:
        selected_subjects.append(subject_id)

    await state.update_data(subjects=selected_subjects)
    await callback.message.edit_reply_markup(
        reply_markup=generate_subjects_keyboard(selected_subjects, is_teacher=True)
    )
    await callback.answer()

@dp.callback_query(BookingStates.TEACHER_SUBJECTS, F.data == "subjects_done")
async def process_subjects_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("subjects"):
        await callback.answer("Выберите хотя бы один предмет!", show_alert=True)
        return

    storage.update_user_subjects(callback.from_user.id, data["subjects"])
    await state.update_data(booking_type="Тип1")  # Устанавливаем тип по умолчанию
    await callback.message.edit_text("Выберите дату:", reply_markup=generate_calendar())  # Пропускаем выбор типа
    await state.set_state(BookingStates.SELECT_DATE)
    await callback.answer()

@dp.callback_query(BookingStates.SELECT_SUBJECT, F.data.startswith("subject_"))
async def process_student_subject(callback: types.CallbackQuery, state: FSMContext):
    subject_id = callback.data.split("_")[1]
    await state.update_data(
        subject=subject_id,
        booking_type="Тип1"  # Устанавливаем тип по умолчанию
    )

    await callback.message.edit_text(f"Выбран предмет: {SUBJECTS[subject_id]}")
    await callback.message.answer("Выберите дату:", reply_markup=generate_calendar())  # Пропускаем выбор типа
    await state.set_state(BookingStates.SELECT_DATE)
    await callback.answer()

# @dp.callback_query(BookingStates.SELECT_BOOKING_TYPE, F.data.startswith("booking_type_"))
# async def process_booking_type(callback: types.CallbackQuery, state: FSMContext):
#     booking_type = callback.data.replace("booking_type_", "")
#     await state.update_data(booking_type=booking_type)
#     await callback.message.edit_text(
#         f"Выбран тип: {booking_type}\nТеперь выберите дату:",
#         reply_markup=generate_calendar()
#     )
#     await state.set_state(BookingStates.SELECT_DATE)
#     await callback.answer()

@dp.callback_query(BookingStates.SELECT_DATE, F.data.startswith("calendar_"))
async def process_calendar(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data

    if data.startswith("calendar_day_"):
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()
        
        # Проверяем, что выбранная дата не раньше минимальной
        now = datetime.now()
        min_date = datetime(year=now.year, month=9, day=1).date()
        if now.date() > min_date:
            min_date = now.date()
            
        if selected_date < min_date:
            await callback.answer("Нельзя выбрать дату раньше " + min_date.strftime('%d.%m.%Y'), show_alert=True)
            return

        await state.update_data(
            selected_date=selected_date,
            time_start=None,
            time_end=None,
            selecting_mode='start'
        )
        
        await callback.message.edit_text(
            f"Выбрана дата: {day}.{month}.{year}\n"
            "Нажмите 'Выбрать начало 🟢' и укажите время начала\n"
            "Затем нажмите 'Выбрать конец 🔴' и укажите время окончания",
            reply_markup=generate_time_range_keyboard(
                selected_date=selected_date
            )
        )
        await state.set_state(BookingStates.SELECT_TIME_RANGE)
        await callback.answer()

    elif data.startswith("calendar_change_"):
        date_str = data.replace("calendar_change_", "")
        year, month = map(int, date_str.split("-"))
        await callback.message.edit_reply_markup(reply_markup=generate_calendar(year, month))
        await callback.answer()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "cancel_time_selection")
async def cancel_time_selection_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Выбор времени отменен")
    await state.clear()
    
    # Возвращаем пользователя в главное меню
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=main_menu
    )
    await callback.answer()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data.startswith("time_point_"))
async def process_time_point(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.replace("time_point_", "")
    data = await state.get_data()
    selecting_mode = data.get('selecting_mode', 'start')  # По умолчанию выбираем начало
    
    if selecting_mode == 'start':
        # Выбираем начало
        await state.update_data(time_start=time_str)
        
        # Проверяем, если уже есть конец и он раньше начала
        if data.get('time_end') and datetime.strptime(time_str, "%H:%M") >= datetime.strptime(data['time_end'], "%H:%M"):
            await state.update_data(time_end=None)
            
        await callback.message.edit_text(
            f"Выбрано начало: {time_str}\n"
            "Нажмите 'Выбрать конец 🔴' и укажите время окончания\n"
            "Или выберите другое время начала:",
            reply_markup=generate_time_range_keyboard(
                selected_date=data.get('selected_date'),
                start_time=time_str,
                end_time=data.get('time_end')
            )
        )
    else:
        # Выбираем конец
        if not data.get('time_start'):
            await callback.answer("Сначала выберите время начала!", show_alert=True)
            return
            
        if datetime.strptime(time_str, "%H:%M") <= datetime.strptime(data['time_start'], "%H:%M"):
            await callback.answer("Время окончания должно быть после времени начала!", show_alert=True)
            return
            
        await state.update_data(time_end=time_str)
        
        await callback.message.edit_text(
            f"Текущий выбор:\n"
            f"Начало: {data['time_start']} (зеленый)\n"
            f"Конец: {time_str} (красный)\n\n"
            "Вы можете:\n"
            "1. Подтвердить выбор\n"
            "2. Изменить начало/конец\n"
            "3. Отменить",
            reply_markup=generate_time_range_keyboard(
                selected_date=data.get('selected_date'),
                start_time=data['time_start'],
                end_time=time_str
            )
        )
    
    await callback.answer()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data.in_(["select_start_mode", "select_end_mode"]))
async def switch_selection_mode(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if callback.data == "select_start_mode":
        await state.update_data(selecting_mode='start')
        message_text = "Режим выбора НАЧАЛА времени (зеленый маркер)\n"
    else:
        await state.update_data(selecting_mode='end')
        message_text = "Режим выбора ОКОНЧАНИЯ времени (красный маркер)\n"
    
    time_start = data.get('time_start')
    time_end = data.get('time_end')
    
    if time_start:
        message_text += f"Текущее начало: {time_start}\n"
    if time_end:
        message_text += f"Текущий конец: {time_end}\n"
    
    if callback.data == "select_start_mode":
        message_text += "Нажмите на время для установки начала:"
    else:
        message_text += "Нажмите на время для установки окончания:"
    
    await callback.message.edit_text(
        message_text,
        reply_markup=generate_time_range_keyboard(
            selected_date=data.get('selected_date'),
            start_time=time_start,
            end_time=time_end
        )
    )
    await callback.answer()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "confirm_time_range")
async def confirm_time_range(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Проверка что выбраны оба времени
    if not data.get('time_start') or not data.get('time_end'):
        await callback.answer(
            "❌ Необходимо выбрать и начало, и конец времени!",
            show_alert=True
        )
        return
    
    # Проверка на конфликты
    if has_booking_conflict(
            user_id=callback.from_user.id,
            booking_type=data['booking_type'],
            date=data['selected_date'],
            time_start=data['time_start'],
            time_end=data['time_end']
    ):
        await callback.answer(
            f"У вас уже есть бронь на это время!",
            show_alert=True
        )
        return

    role_text = "ученик" if data['user_role'] == 'student' else "преподаватель"

    if data['user_role'] == 'teacher':
        subjects_text = ", ".join(SUBJECTS[subj] for subj in data.get('subjects', []))
    else:
        subjects_text = SUBJECTS.get(data.get('subject', ''), "Не указан")

    # Переходим к финальному подтверждению
    await callback.message.edit_text(
        f"📋 Подтвердите бронирование:\n\n"
        f"Роль: {role_text}\n"
        f"Предмет(ы): {subjects_text}\n"
        f"Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
        f"Время: {data['time_start']} - {data['time_end']}",
        reply_markup=generate_confirmation()
    )
    await state.set_state(BookingStates.CONFIRMATION)
    await callback.answer()

@dp.callback_query(BookingStates.CONFIRMATION, F.data.in_(["booking_confirm", "booking_cancel"]))
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "booking_confirm":
        data = await state.get_data()

        # Проверка конфликтов
        if has_booking_conflict(
                user_id=callback.from_user.id,
                booking_type=data['booking_type'],
                date=data['selected_date'],
                time_start=data['time_start'],
                time_end=data['time_end']
        ):
            await callback.message.edit_text("❌ Время уже занято! Выберите другое.")
            await state.clear()
            return

        # Формируем данные брони
        booking_data = {
            "user_name": data['user_name'],
            "user_role": data['user_role'],
            "booking_type": data['booking_type'],
            "date": data['selected_date'].strftime("%Y-%m-%d"),
            "start_time": data['time_start'],
            "end_time": data['time_end'],
            "user_id": callback.from_user.id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if data['user_role'] == 'teacher':
            booking_data["subjects"] = data.get('subjects', [])
        else:
            booking_data["subject"] = data.get('subject', '')

        # Сохраняем бронь
        try:
            booking = storage.add_booking(booking_data)
            logger.info(f"Бронь сохранена в JSON. ID: {booking.get('id')}")

            # Принудительное обновление Google Sheets
            all_bookings = storage.load()
            if gsheets and gsheets.update_all_sheets(all_bookings):
                logger.info("Данные успешно отправлены в Google Sheets!")
            else:
                logger.warning("Не удалось обновить Google Sheets")

            await callback.message.edit_text(
                "✅ Бронирование подтверждено!\n"
                f"📅 Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
                f"⏰ Время: {data['time_start']}-{data['time_end']}\n"
                f"📌 Тип: {data['booking_type']}"
            )
        except Exception as e:
            await callback.message.edit_text("❌ Ошибка при сохранении брони!")
            logger.error(f"Ошибка: {e}")
    else:
        await callback.message.edit_text("❌ Бронирование отменено")

    await state.clear()
    await callback.answer()

@dp.message(F.text == "📋 Мои бронирования")
@dp.message(Command("my_bookings"))
async def show_bookings(message: types.Message):
    keyboard = generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований")
        return

    await message.answer("Ваши бронирования (отсортированы по дате и времени):", reply_markup=keyboard)

@dp.message(Command("my_role"))
async def show_role(message: types.Message):
    role = storage.get_user_role(message.from_user.id)
    if role:
        await message.answer(f"Ваша роль: {'ученик' if role == 'student' else 'преподаватель'}")
    else:
        await message.answer("Ваша роль еще не определена. Используйте /book чтобы установить роль.")

@dp.message(F.text == "❌ Отменить бронь")
async def start_cancel_booking(message: types.Message):
    keyboard = generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований для отмены")
        return

    await message.answer("Выберите бронирование для отмены:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("booking_info_"))
async def show_booking_info(callback: types.CallbackQuery):
    try:
        booking_id_str = callback.data.replace("booking_info_", "")
        if not booking_id_str:
            await callback.answer("❌ Не удалось определить ID бронирования", show_alert=True)
            return
            
        booking_id = int(booking_id_str)
        bookings = load_bookings()
        booking = next((b for b in bookings if b.get("id") == booking_id), None)

        if not booking:
            await callback.answer("Бронирование не найдено", show_alert=True)
            return

        # Остальной код обработчика...
    except ValueError:
        await callback.answer("❌ Неверный формат ID бронирования", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в show_booking_info: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

@dp.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    if storage.cancel_booking(booking_id):
        await callback.message.edit_text(f"✅ Бронирование ID {booking_id} успешно отменено")
    else:
        await callback.message.edit_text("❌ Не удалось отменить бронирование")
    await callback.answer()

@dp.callback_query(F.data.in_(["back_to_menu", "back_to_bookings"]))
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
        try:
            bookings = storage.load()
            storage.save(bookings)  # Это вызовет фильтрацию старых записей
            logger.info("Cleanup of old bookings completed")
            await asyncio.sleep(6 * 60 * 60)  # Каждые 6 часов
        except Exception as e:
            logger.error(f"Error in cleanup_old_bookings: {e}")
            await asyncio.sleep(60)  # Подождать минуту при ошибке

async def sync_with_gsheets():
    """Фоновая синхронизация с Google Sheets"""
    while True:
        try:
            if hasattr(storage, 'gsheets') and storage.gsheets:
                bookings = storage.load()
                success = storage.gsheets.update_all_sheets(bookings)
                if success:
                    logger.info("Фоновая синхронизация с Google Sheets выполнена")
                else:
                    logger.warning("Не удалось выполнить синхронизацию с Google Sheets")
            await asyncio.sleep(3600)  # Каждый час
        except Exception as e:
            logger.error(f"Ошибка в фоновой синхронизации: {e}")
            await asyncio.sleep(600)  # Ждем 10 минут при ошибке

async def on_startup():
    """Действия при запуске бота"""
    # Принудительная синхронизация при старте
    if gsheets:
        try:
            bookings = storage.load()
            gsheets.update_all_sheets(bookings)
            logger.info("Initial sync with Google Sheets completed")
        except Exception as e:
            logger.error(f"Initial sync failed: {e}")

async def sync_from_gsheets_background(storage):
    """Фоновая синхронизация из Google Sheets в JSON"""
    while True:
        try:
            if hasattr(storage, 'gsheets') and storage.gsheets:
                success = storage.gsheets.sync_from_gsheets_to_json(storage)
                if success:
                    logger.info("Фоновая синхронизация из Google Sheets в JSON выполнена")
                else:
                    logger.warning("Не удалось выполнить синхронизацию из Google Sheets")
            await asyncio.sleep(60)  # Синхронизация каждую минуту
        except Exception as e:
            logger.error(f"Ошибка в фоновой синхронизации из Google Sheets: {e}")
            await asyncio.sleep(300)

async def main():
    # Инициализация при старте
    await on_startup()
    
    # Запуск фоновых задач
    asyncio.create_task(cleanup_old_bookings())
    asyncio.create_task(sync_with_gsheets())
    asyncio.create_task(sync_from_gsheets_background(storage))  # Новая задача

    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    logger.info("Starting bot...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")