import asyncio
import json
import os
import logging
from datetime import datetime, timedelta, date
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import threading
from gsheets_manager import GoogleSheetsManager
from storage import JSONStorage
from dotenv import load_dotenv
from aiogram.types import Update

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
    SELECT_SUBJECT = State()  # Только для учеников
    SELECT_DATE = State()
    SELECT_TIME_RANGE = State()
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


class RoleCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Пропускаем команду /start, /help и ввод имени
        if isinstance(event, Message) and event.text == '/start':
            return await handler(event, data)
            
        current_state = await data['state'].get_state() if data.get('state') else None
        if current_state == BookingStates.INPUT_NAME:
            return await handler(event, data)
        
        # Получаем user_id в зависимости от типа события
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            # Для других типов событий пропускаем проверку
            return await handler(event, data)
        
        # Проверяем роли для всех остальных сообщений
        if not storage.has_user_roles(user_id):
            if isinstance(event, Message):
                await event.answer(
                    "⏳ Ваш аккаунт находится на проверке.\n"
                    "Обратитесь к администратору для получения доступа.",
                    reply_markup=ReplyKeyboardRemove()
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "⏳ Обратитесь к администратору для получения доступа",
                    show_alert=True
                )
            return
        
        return await handler(event, data)

# Добавление middleware
dp.update.middleware(RoleCheckMiddleware())

def has_teacher_booking_conflict(user_id, date, time_start, time_end, exclude_id=None):
    """Проверяет конфликты бронирований только для преподавателей"""
    bookings = storage.load()
    
    def time_to_minutes(t):
        h, m = map(int, t.split(':'))
        return h * 60 + m

    new_start = time_to_minutes(time_start)
    new_end = time_to_minutes(time_end)

    for booking in bookings:
        if (booking.get('user_id') == user_id and
            booking.get('date') == date and
            booking.get('user_role') == 'teacher'):  # Проверяем только для преподавателей
            
            if exclude_id and booking.get('id') == exclude_id:
                continue

            existing_start = time_to_minutes(booking.get('start_time', '00:00'))
            existing_end = time_to_minutes(booking.get('end_time', '00:00'))

            # Проверяем пересечение временных интервалов
            if not (new_end <= existing_start or new_start >= existing_end):
                return True
                
    return False


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

async def set_user_commands(user_id: int):
    """Устанавливает меню команд для пользователя"""
    if user_id in ADMIN_IDS:
        await bot.set_my_commands(ADMIN_COMMANDS, scope=types.BotCommandScopeChat(chat_id=user_id))
    else:
        await bot.set_my_commands(USER_COMMANDS, scope=types.BotCommandScopeChat(chat_id=user_id))

async def generate_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Генерирует главное меню в зависимости от наличия ролей"""
    if not storage.has_user_roles(user_id):
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❓ Обратиться к администратору")]],
            resize_keyboard=True
        )
    
    # Меню для пользователей с ролями
    keyboard = [
        [KeyboardButton(text="📅 Забронировать время")],
        [KeyboardButton(text="📋 Мои бронирования")],
        [KeyboardButton(text="👤 Моя роль")]
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
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = storage.get_user_name(user_id)
    
    # Устанавливаем правильное меню команд
    await set_user_commands(user_id)
    
    menu = await generate_main_menu(user_id)
    
    if user_name:
        await message.answer(
            f"С возвращением, {user_name}!\n"
            "Используйте кнопки ниже для навигации:",
            reply_markup=menu
        )
    else:
        await message.answer(
            "Добро пожаловать в систему бронирования!\n"
            "Введите ваше полное ФИО для регистрации:",
            reply_markup=ReplyKeyboardRemove()
        )
        await state.set_state(BookingStates.INPUT_NAME)

@dp.message(F.text == "👤 Моя роль")
async def show_my_role(message: types.Message):
    roles = storage.get_user_roles(message.from_user.id)
    if roles:
        role_text = ", ".join(["преподаватель" if role == "teacher" else "ученик" for role in roles])
        await message.answer(f"Ваши роли: {role_text}")
    else:
        await message.answer("Ваши роли еще не назначены. Обратитесь к администратору.")

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
        reply_markup=await generate_main_menu(user_id)
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

@dp.message(F.text == "❓ Обратиться к администратору")
async def contact_admin(message: types.Message):
    await message.answer(
        "📞 Для получения доступа к системе бронирования\n"
        "обратитесь к администратору.\n\n"
        "После назначения ролей вы сможете пользоваться всеми функциями бота."
    )

@dp.message(F.text == "📅 Забронировать время")
@dp.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, есть ли ФИО
    user_name = storage.get_user_name(user_id)
    if not user_name:
        await message.answer("Введите ваше полное ФИО:")
        await state.set_state(BookingStates.INPUT_NAME)
        return
    
    # Получаем доступные роли пользователя
    user_roles = storage.get_user_roles(user_id)
    if not user_roles:
        await message.answer(
            "⏳ Обратитесь к администратору для получения ролей",
            reply_markup=await generate_main_menu(user_id)
        )
        return
    
    await state.update_data(user_name=user_name)
    
    # Показываем доступные роли
    builder = InlineKeyboardBuilder()
    if 'teacher' in user_roles:
        builder.button(text="👨‍🏫 Я преподаватель", callback_data="role_teacher")
    if 'student' in user_roles:
        builder.button(text="👨‍🎓 Я ученик", callback_data="role_student")
    
    if builder.buttons:
        await message.answer(
            "Выберите роль для бронирования:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.SELECT_ROLE)
    else:
        await message.answer(
            "❌ У вас нет доступных ролей. Обратитесь к администратору.",
            reply_markup=await generate_main_menu(user_id)
        )

@dp.message(BookingStates.INPUT_NAME)
async def process_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.text.strip()
    
    if len(user_name.split()) < 2:
        await message.answer("Пожалуйста, введите полное ФИО (минимум имя и фамилию)")
        return
    
    # Сохраняем имя
    storage.save_user_name(user_id, user_name)
    await state.update_data(user_name=user_name)
    
    # Проверяем, есть ли роли
    if storage.has_user_roles(user_id):
        user_roles = storage.get_user_roles(user_id)
        builder = InlineKeyboardBuilder()
        if 'teacher' in user_roles:
            builder.button(text="👨‍🏫 Как преподаватель", callback_data="role_teacher")
        if 'student' in user_roles:
            builder.button(text="👨‍🎓 Как ученик", callback_data="role_student")
        
        await message.answer(
            "Выберите роль для этого бронирования:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.SELECT_ROLE)
    else:
        await message.answer(
            "✅ Ваше ФИО сохранено!\n"
            "⏳ Обратитесь к администратору для получения ролей.",
            reply_markup=await generate_main_menu(user_id)
        )
        await state.clear()

# Остальной код остается без изменений...
# [Продолжение с обработчиками callback-запросов и другими функциями]

@dp.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    await state.update_data(user_role=role)
    
    if role == 'teacher':
        # Для преподавателя получаем предметы из Google Sheets
        teacher_subjects = storage.get_teacher_subjects(user_id)
        
        if not teacher_subjects:
            await callback.answer(
                "У вас нет назначенных предметов. Обратитесь к администратору.",
                show_alert=True
            )
            return
        
        await state.update_data(subjects=teacher_subjects)
        
        # Безопасное форматирование названий предметов
        subject_names = []
        for subj_id in teacher_subjects:
            subject_names.append(SUBJECTS.get(subj_id, f"Предмет {subj_id}"))
        
        await callback.message.edit_text(
            f"Вы выбрали роль преподавателя\n"
            f"Ваши предметы: {', '.join(subject_names)}\n"
            "Теперь выберите дату:",
            reply_markup=generate_calendar()
        )
        await state.set_state(BookingStates.SELECT_DATE)
    else:
        # Для ученика сразу запрашиваем предмет
        await callback.message.edit_text(
            "Вы выбрали роль ученика\n"
            "Выберите предмет для занятия:",
            reply_markup=generate_subjects_keyboard()
        )
        await state.set_state(BookingStates.SELECT_SUBJECT)
    await callback.answer()

# [Остальные обработчики остаются без изменений...]

async def main():
    # Инициализация при старте
    await on_startup()
    
    # Запуск фоновых задач
    asyncio.create_task(cleanup_old_bookings())
    asyncio.create_task(sync_with_gsheets())
    asyncio.create_task(sync_from_gsheets_background(storage))

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