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
    "1": "Математика",
    "2": "Физика",
    "3": "Информатика",
    "4": "Русский язык"
}
ADMIN_IDS = [973231400, 1180878673]
USER_COMMANDS = [
    types.BotCommand(command="book", description="📅 Забронировать время"),
    types.BotCommand(command="my_bookings", description="📋 Мои бронирования"),
    types.BotCommand(command="my_role", description="👤 Моя роль"),
    types.BotCommand(command="help", description="❓ Помощь")
]

ADMIN_COMMANDS = USER_COMMANDS + [
    types.BotCommand(command="schedule", description="📊 Составить расписание")
]


class BookingStates(StatesGroup):
    SELECT_ROLE = State()
    INPUT_NAME = State()
    TEACHER_SUBJECTS = State()
    SELECT_SUBJECT = State()
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


def has_booking_conflict(user_id, date, time_start, time_end, subject=None, exclude_id=None):
    """Проверяет конфликты бронирований с учетом предмета для учеников"""
    bookings = load_bookings()
    for booking in bookings:
        if (booking.get('user_id') == user_id and
            booking.get('date') == date):
            
            # Для учеников проверяем еще и совпадение предмета
            if booking.get('user_role') == 'student' and subject:
                if booking.get('subject') != subject:
                    continue
                    
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
    """Генерирует календарь с корректной обработкой переключения месяцев"""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    # Определяем минимальную дату (1 сентября текущего года)
    min_date = datetime(year=now.year, month=9, day=1).date()
    if now.date() > min_date:
        min_date = now.date()

    builder = InlineKeyboardBuilder()

    # Заголовок с месяцем и годом
    month_name = datetime(year, month, 1).strftime("%B %Y")
    builder.row(types.InlineKeyboardButton(
        text=month_name, 
        callback_data="ignore_month_header"
    ))

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[
        types.InlineKeyboardButton(text=day, callback_data="ignore_weekday") 
        for day in week_days
    ])

    # Генерация дней месяца
    first_day = datetime(year, month, 1)
    start_weekday = first_day.weekday()  # 0-6 (пн-вс)
    days_in_month = (datetime(year, month + 1, 1) - first_day).days if month < 12 else 31

    buttons = []
    # Пустые кнопки для дней предыдущего месяца
    for _ in range(start_weekday):
        buttons.append(types.InlineKeyboardButton(
            text=" ", 
            callback_data="ignore_empty_day"
        ))

    # Кнопки дней текущего месяца
    for day in range(1, days_in_month + 1):
        current_date = datetime(year, month, day).date()
        if current_date < min_date:
            buttons.append(types.InlineKeyboardButton(
                text=" ", 
                callback_data="ignore_past_day"
            ))
        else:
            buttons.append(types.InlineKeyboardButton(
                text=str(day),
                callback_data=f"calendar_day_{year}-{month}-{day}"
            ))

        # Перенос строки после каждого воскресенья
        if (day + start_weekday) % 7 == 0 or day == days_in_month:
            builder.row(*buttons)
            buttons = []

    # Кнопки навигации
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    # Проверяем, можно ли перейти на предыдущий месяц
    show_prev = datetime(prev_year, prev_month, 1).date() >= min_date

    nav_buttons = []
    if show_prev:
        nav_buttons.append(types.InlineKeyboardButton(
            text="⬅️", 
            callback_data=f"calendar_change_{prev_year}-{prev_month}"
        ))
    else:
        nav_buttons.append(types.InlineKeyboardButton(
            text=" ", 
            callback_data="ignore_prev_disabled"
        ))

    # Всегда показываем кнопку "вперед"
    nav_buttons.append(types.InlineKeyboardButton(
        text="➡️", 
        callback_data=f"calendar_change_{next_year}-{next_month}"
    ))

    builder.row(*nav_buttons)

    return builder.as_markup()

@dp.callback_query(
    BookingStates.SELECT_DATE, 
    F.data.startswith("calendar_change_")
)
async def process_calendar_change(callback: types.CallbackQuery):
    try:
        date_str = callback.data.replace("calendar_change_", "")
        year, month = map(int, date_str.split("-"))
        
        await callback.message.edit_reply_markup(
            reply_markup=generate_calendar(year, month)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error changing calendar month: {e}")
        await callback.answer("Не удалось изменить месяц", show_alert=True)

@dp.callback_query(F.data.startswith("ignore_"))
async def ignore_callback(callback: types.CallbackQuery):
    """Обрабатывает все callback'и, которые должны игнорироваться"""
    await callback.answer()


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


def generate_booking_list(user_id: int):
    bookings = load_bookings()
    user_bookings = [b for b in bookings if b.get("user_id") == user_id]
    
    if not user_bookings:
        return None
    
    # Группируем по роли для удобства
    bookings_by_role = {}
    for booking in user_bookings:
        role = booking.get("user_role", "unknown")
        if role not in bookings_by_role:
            bookings_by_role[role] = []
        bookings_by_role[role].append(booking)
    
    builder = InlineKeyboardBuilder()
    
    for role, role_bookings in bookings_by_role.items():
        role_name = "Преподаватель" if role == "teacher" else "Ученик"
        builder.row(types.InlineKeyboardButton(
            text=f"--- {role_name} ---",
            callback_data="ignore"
        ))
        
        for booking in sorted(role_bookings, key=lambda x: (x.get("date"), x.get("start_time"))):
            builder.row(types.InlineKeyboardButton(
                text=f"{booking.get('date')} {booking.get('start_time')}-{booking.get('end_time')}",
                callback_data=f"booking_info_{booking.get('id')}"
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

# main_menu = ReplyKeyboardMarkup(
#     keyboard=[
#         [KeyboardButton(text="📅 Забронировать время")],
#         [KeyboardButton(text="📋 Мои бронирования"), KeyboardButton(text="❌ Отменить бронь")]
#     ],
#     resize_keyboard=True
# )


async def set_user_commands(user_id: int):
    """Устанавливает меню команд для пользователя"""
    if user_id in ADMIN_IDS:
        await bot.set_my_commands(ADMIN_COMMANDS, scope=types.BotCommandScopeChat(chat_id=user_id))
    else:
        await bot.set_my_commands(USER_COMMANDS, scope=types.BotCommandScopeChat(chat_id=user_id))


def generate_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Генерирует главное меню с учетом прав пользователя"""
    keyboard = [
        [KeyboardButton(text="📅 Забронировать время")],
        [KeyboardButton(text="📋 Мои бронирования"), KeyboardButton(text="❌ Отменить бронь")]
    ]

    # Добавляем кнопку админа только для указанных ID
    if user_id in ADMIN_IDS:
        keyboard.append([KeyboardButton(text="📊 Составить расписание")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


@dp.message.middleware()
async def update_menu_middleware(handler, event, data):
    user_id = event.from_user.id
    await set_user_commands(user_id)
    return await handler(event, data)


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_name = storage.get_user_name(user_id)

    # Устанавливаем правильное меню
    await set_user_commands(user_id)

    if user_name:
        await message.answer(
            f"С возвращением, {user_name}!\n"
            "Используйте кнопки ниже для навигации:",
            reply_markup=generate_main_menu(user_id)
        )
    else:
        await message.answer(
            "Добро пожаловать в систему бронирования!\n"
            "Используйте кнопки ниже для навигации:",
            reply_markup=generate_main_menu(user_id)
        )


@dp.message(Command("schedule"))
@dp.message(F.text == "📊 Составить расписание")
async def handle_schedule_button(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой функции")
        return

    # Заглушка - кнопка есть, но функционала пока нет
    await message.answer(
        "Функция составления расписания в разработке 🛠️\n"
        "Скоро здесь будет возможность автоматического распределения времени занятий.",
        reply_markup=generate_main_menu(user_id)
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


async def check_user_profile(user_id: int) -> bool:
    """Проверяет, полностью ли заполнен профиль"""
    name = storage.get_user_name(user_id)
    role = storage.get_user_role(user_id)
    return bool(name) and bool(role)

# Модифицированный обработчик команды /book
async def ensure_user_name(user_id: int) -> str:
    """Проверяет и возвращает сохраненное ФИО"""
    return storage.get_user_name(user_id)

@dp.message(F.text == "📅 Забронировать время")
@dp.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    # Устанавливаем тип бронирования по умолчанию
    await state.update_data(booking_type="Тип1")
    
    user_id = message.from_user.id
    user_name = storage.get_user_name(user_id)
    
    if user_name:
        await state.update_data(user_name=user_name)
        builder = InlineKeyboardBuilder()
        builder.button(text="👨‍🎓 Я ученик", callback_data="role_student")
        builder.button(text="👨‍🏫 Я преподаватель", callback_data="role_teacher")
        await message.answer(
            "Выберите роль для бронирования:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.SELECT_ROLE)
    else:
        await message.answer("Введите ваше полное ФИО:")
        await state.set_state(BookingStates.INPUT_NAME)


@dp.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    await state.update_data(user_role=role)
    
    if role == 'teacher':
        await callback.message.edit_text(
            "Вы выбрали роль преподавателя\n"
            "Выберите предметы, которые вы преподаете:",
            reply_markup=generate_subjects_keyboard(is_teacher=True)
        )
        await state.set_state(BookingStates.TEACHER_SUBJECTS)
    else:
        # Для ученика сразу запрашиваем предмет
        await callback.message.edit_text(
            "Вы выбрали роль ученика\n"
            "Выберите предмет для занятия:",
            reply_markup=generate_subjects_keyboard()
        )
        await state.set_state(BookingStates.SELECT_SUBJECT)
    await callback.answer()

async def ensure_user_data(message: types.Message, state: FSMContext):
    """Проверяет и запрашивает недостающие данные пользователя"""
    user_id = message.from_user.id
    user_data = storage.get_user_data(user_id)
    
    # Если ФИО уже есть, используем его
    if user_data.get("user_name"):
        await state.update_data(user_name=user_data["user_name"])
        return True
    
    # Если ФИО нет, запрашиваем его
    await message.answer("Введите ваше полное ФИО:")
    await state.set_state(BookingStates.INPUT_NAME)
    return False


@dp.message(BookingStates.INPUT_NAME)
async def process_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.text.strip()
    
    if len(user_name.split()) < 2:
        await message.answer("Пожалуйста, введите полное ФИО (минимум имя и фамилию)")
        return
    
    # Сохраняем имя без роли
    storage.save_user_info(user_id, user_name)
    await state.update_data(user_name=user_name)
    
    # Запрашиваем роль для текущего бронирования
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🎓 Как ученик", callback_data="role_student")
    builder.button(text="👨‍🏫 Как преподаватель", callback_data="role_teacher")
    await message.answer(
        "Выберите роль для этого бронирования:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(BookingStates.SELECT_ROLE)


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
    user_id = callback.from_user.id
    
    # Сохраняем предмет для текущего бронирования
    await state.update_data(subject=subject_id, booking_type="Тип1")
    
    # Получаем имя пользователя (оно уже должно быть в состоянии)
    data = await state.get_data()
    user_name = data.get('user_name', '')
    
    # Сохраняем связь пользователь-предмет в Google Sheets
    if gsheets:
        gsheets.save_user_subject(user_id, user_name, subject_id)
    
    await callback.message.edit_text(
        f"Выбран предмет: {SUBJECTS[subject_id]}\n"
        "Теперь выберите дату:",
        reply_markup=generate_calendar()
    )
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

@dp.callback_query(BookingStates.SELECT_DATE, F.data.startswith("calendar_day_"))
async def process_calendar(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    user_id = callback.from_user.id

    if data.startswith("calendar_day_"):
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()
        formatted_date = selected_date.strftime("%Y-%m-%d")

        # Получаем данные из состояния
        state_data = await state.get_data()
        role = state_data.get('user_role')

        # Проверяем существующие брони
        if storage.has_booking_on_date(user_id, formatted_date, role):
            await callback.answer(
                f"У вас уже есть бронь на {day}.{month}.{year} в роли {'преподавателя' if role == 'teacher' else 'ученика'}",
                show_alert=True
            )
            return

        # Продолжаем процесс бронирования
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


@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "cancel_time_selection")
async def cancel_time_selection_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Выбор времени отменен")
    await state.clear()

    # Возвращаем пользователя в главное меню
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=generate_main_menu(callback.from_user.id)
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
        if data.get('time_end') and datetime.strptime(time_str, "%H:%M") >= datetime.strptime(data['time_end'],
                                                                                              "%H:%M"):
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
    
    # Гарантируем, что booking_type = "Тип1"
    data['booking_type'] = "Тип1"
    await state.update_data(booking_type="Тип1")

    subject = data.get('subject') if data.get('user_role') == 'student' else None
    
    # Проверка конфликтов с учетом предмета
    if has_booking_conflict(
        user_id=callback.from_user.id,
        date=data['selected_date'].strftime("%Y-%m-%d"),
        time_start=data['time_start'],
        time_end=data['time_end'],
        subject=subject
    ):
        await callback.answer(
            "У вас уже есть бронь на это время!",
            show_alert=True
        )
        return
    
    # Проверка наличия всех необходимых данных
    required_fields = ['user_name', 'user_role', 'selected_date', 'time_start', 'time_end']
    for field in required_fields:
        if field not in data:
            await callback.answer(f"Ошибка: отсутствует {field}", show_alert=True)
            return

    role_text = "ученик" if data['user_role'] == 'student' else "преподаватель"
    
    if data['user_role'] == 'teacher':
        subjects_text = ", ".join(SUBJECTS[subj] for subj in data.get('subjects', []))
    else:
        subjects_text = SUBJECTS.get(data.get('subject', ''), "Не указан")

    await callback.message.edit_text(
        f"📋 Подтвердите бронирование:\n\n"
        f"Роль: {role_text}\n"
        f"Предмет(ы): {subjects_text}\n"
        f"Тип: ТИП1 (автоматически)\n"
        f"Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
        f"Время: {data['time_start']} - {data['time_end']}",
        reply_markup=generate_confirmation()
    )
    await state.set_state(BookingStates.CONFIRMATION)
    await callback.answer()


@dp.callback_query(BookingStates.CONFIRMATION, F.data == "booking_confirm")
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Гарантируем тип бронирования
    data['booking_type'] = "Тип1"
    
    # Формируем данные брони
    booking_data = {
        "user_id": callback.from_user.id,
        "user_name": data['user_name'],
        "user_role": data['user_role'],
        "booking_type": "Тип1",  # Всегда Тип1
        "date": data['selected_date'].strftime("%Y-%m-%d"),
        "start_time": data['time_start'],
        "end_time": data['time_end'],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    if data['user_role'] == 'teacher':
        booking_data["subjects"] = data.get('subjects', [])
    else:
        booking_data["subject"] = data.get('subject', '')

    # Сохраняем бронь
    try:
        booking = storage.add_booking(booking_data)
        await callback.message.edit_text(
            "✅ Бронирование подтверждено!\n"
            f"📅 Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {data['time_start']}-{data['time_end']}\n"
            f"📌 Тип: ТИП1"
        )
    except Exception as e:
        await callback.message.edit_text("❌ Ошибка при сохранении брони!")
        logger.error(f"Ошибка сохранения: {e}")
    
    await state.clear()
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=generate_main_menu(callback.from_user.id)
    )


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

        # Формируем текст сообщения
        role_text = "👨🎓 Ученик" if booking.get('user_role') == 'student' else "👨🏫 Преподаватель"
        
        # Обрабатываем дату
        booking_date = booking.get('date')
        if isinstance(booking_date, str):
            try:
                booking_date = datetime.strptime(booking_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            except ValueError:
                booking_date = "Неизвестно"

        message_text = (
            f"📋 Информация о бронировании:\n\n"
            f"🔹 {role_text}\n"
            f"📅 Дата: {booking_date}\n"
            f"⏰ Время: {booking.get('start_time', '?')} - {booking.get('end_time', '?')}\n"
        )

        # Добавляем информацию о предметах
        if booking.get('user_role') == 'teacher':
            subjects = booking.get('subjects', [])
            subjects_text = ", ".join([SUBJECTS.get(subj, subj) for subj in subjects])
            message_text += f"📚 Предметы: {subjects_text}\n"
        else:
            subject = booking.get('subject', 'Неизвестно')
            message_text += f"📚 Предмет: {SUBJECTS.get(subject, subject)}\n"

        # Добавляем тип бронирования
        message_text += f"🏷 Тип: {booking.get('booking_type', 'Тип1')}\n"

        # Отправляем сообщение с кнопками действий
        await callback.message.edit_text(
            message_text,
            reply_markup=generate_booking_actions(booking_id)
        )
        await callback.answer()

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
            reply_markup=generate_main_menu(callback.from_user.id)
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
            worksheet = gsheets._get_or_create_users_worksheet()
            records = worksheet.get_all_records()
            
            # Собираем уникальные user_id
            unique_users = {}
            duplicates = []
            
            for i, record in enumerate(records, start=2):
                user_id = str(record.get("user_id"))
                if user_id in unique_users:
                    duplicates.append(i)
                else:
                    unique_users[user_id] = record
            
            # Удаляем дубликаты (с конца, чтобы не сбивались номера строк)
            for row_num in sorted(duplicates, reverse=True):
                worksheet.delete_rows(row_num)
            
            logger.info(f"Удалено {len(duplicates)} дубликатов пользователей")
        except Exception as e:
            logger.error(f"Ошибка при очистке дубликатов: {e}")


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
    await bot.set_my_commands(USER_COMMANDS)
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