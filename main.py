import sys

sys.path.append(r"C:\Users\bestd\OneDrive\Документы\GitHub\TelegramSchedulingBot\shedule_app")

import asyncio
import json
import os
import logging
from datetime import datetime, timedelta, date,time
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
from shedule_app.HelperMethods import School
from shedule_app.models import Person,Teacher,Student
from typing import List, Dict
from shedule_app.GoogleParser import GoogleSheetsDataLoader

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOKINGS_FILE = "bookings.json"
CREDENTIALS_PATH = r"C:\Users\bestd\OneDrive\Документы\GitHub\TelegramSchedulingBot\credentials.json"
SPREADSHEET_ID = "1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU"

BOOKING_TYPES = ["Тип1"]
SUBJECTS = {
    "1": "Математика",
    "2": "Физика",
    "3": "Информатика",
    "4": "Русский язык"
}


class BookingStates(StatesGroup):
    SELECT_ROLE = State()
    INPUT_NAME = State()
    SELECT_SUBJECT = State()  # Только для учеников
    SELECT_DATE = State()
    SELECT_TIME_RANGE = State()
    CONFIRMATION = State()
    SELECT_CHILD = State()  # Новое состояние для выбора ребенка
    PARENT_SELECT_CHILD = State()


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

def check_student_availability_for_slots(
    student: Student,
    all_students: List[Student],
    teachers: List[Teacher],
    target_date: date,
    start_time: time,
    end_time: time,
    interval_minutes: int = 30
) -> Dict[time, bool]:
    result = {}
    current_time = start_time
    
    logger.info(f"=== ДЕТАЛЬНАЯ ПРОВЕРКА ДОСТУПНОСТИ ===")
    logger.info(f"Студент: {student.name}, предмет: {student.subject_id}")
    logger.info(f"Всего преподавателей: {len(teachers)}")
    
    # Логируем всех преподавателей и их предметы
    for i, teacher in enumerate(teachers):
        logger.info(f"Преподаватель {i+1}: {teacher.name}, предметы: {teacher.subjects_id}, "
                   f"время: {teacher.start_of_study_time}-{teacher.end_of_study_time}")
    
    logger.info(f"Всего студентов: {len(all_students)}")
    
    # Преобразуем subject_id студента в число для сравнения
    try:
        student_subject_id = int(student.subject_id)
    except (ValueError, TypeError):
        logger.error(f"Неверный формат subject_id: {student.subject_id}")
        return {time_obj: False for time_obj in [start_time + timedelta(minutes=i*interval_minutes) 
                for i in range(int((end_time.hour*60+end_time.minute - start_time.hour*60+start_time.minute)/interval_minutes)+1)]}
    
    while current_time <= end_time:
        active_students = [
            s for s in all_students 
            if (s.start_of_studying_time <= current_time <= s.end_of_studying_time and
                s != student)
        ]
        
        students_with_target = active_students + [student]
        
        active_teachers = [
            t for t in teachers 
            if t.start_of_studying_time <= current_time <= t.end_of_studying_time
        ]
        
        # Детальная проверка
        can_allocate = True
        
        if not active_teachers:
            logger.info(f"Время {current_time}: нет активных преподавателей")
            can_allocate = False
        else:
            # ИСПРАВЛЕННАЯ ПРОВЕРКА: сравниваем числа с числами
            subject_available = any(student_subject_id in t.subjects_id for t in active_teachers)
            if not subject_available:
                logger.info(f"Время {current_time}: нет преподавателя для предмета {student_subject_id}")
                can_allocate = False
        
        result[current_time] = can_allocate
        current_time = School.add_minutes_to_time(current_time, interval_minutes)
    
    available_count = sum(1 for available in result.values() if available)
    total_count = len(result)
    logger.info(f"ИТОГ: доступно {available_count}/{total_count} слотов")
    
    return result

def generate_time_range_keyboard_with_availability(
    selected_date=None,
    start_time=None,
    end_time=None,
    availability_map: Dict[time, bool] = None
):
    """Генерирует клавиатуру выбора времени с учетом доступности"""
    builder = InlineKeyboardBuilder()

    # Определяем рабочие часы (9:00 - 20:00)
    start = datetime.strptime("09:00", "%H:%M")
    end = datetime.strptime("20:00", "%H:%M")
    current = start

    while current <= end:
        time_str = current.strftime("%H:%M")
        time_obj = current.time()

        # Определяем стиль кнопки на основе доступности
        if availability_map and time_obj in availability_map:
            is_available = availability_map[time_obj]
            if start_time and time_str == start_time:
                button_text = "🟢 " + time_str if is_available else "🔴 " + time_str
            elif end_time and time_str == end_time:
                button_text = "🔴 " + time_str if is_available else "🔴🔒 " + time_str
            elif (start_time and end_time and
                  datetime.strptime(start_time, "%H:%M").time() < time_obj <
                  datetime.strptime(end_time, "%H:%M").time()):
                button_text = "🔵 " + time_str if is_available else "🔵🔒 " + time_str
            else:
                button_text = time_str if is_available else "🔒 " + time_str
        else:
            # Если данные о доступности отсутствуют, используем обычный вид
            if start_time and time_str == start_time:
                button_text = "🟢 " + time_str
            elif end_time and time_str == end_time:
                button_text = "🔴 " + time_str
            elif (start_time and end_time and
                  datetime.strptime(start_time, "%H:%M").time() < time_obj <
                  datetime.strptime(end_time, "%H:%M").time()):
                button_text = "🔵 " + time_str
            else:
                button_text = time_str

        # Делаем недоступные слоты неактивными
        if availability_map and time_obj in availability_map and not availability_map[time_obj]:
            callback_data = "time_slot_unavailable"
        else:
            callback_data = f"time_point_{time_str}"

        builder.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
        current += timedelta(minutes=30)

    builder.adjust(4)

    # Добавляем кнопки управления
    control_buttons = []
    if availability_map:
        # Показываем статистику доступности
        available_count = sum(1 for available in availability_map.values() if available)
        total_count = len(availability_map)
        control_buttons.append(types.InlineKeyboardButton(
            text=f"Доступно: {available_count}/{total_count}",
            callback_data="availability_info"
        ))

    control_buttons.extend([
        types.InlineKeyboardButton(
            text="Выбрать начало 🟢",
            callback_data="select_start_mode"
        ),
        types.InlineKeyboardButton(
            text="Выбирать конец 🔴",
            callback_data="select_end_mode"
        )
    ])

    builder.row(*control_buttons)

    if start_time and end_time:
        # Проверяем, доступен ли выбранный интервал
        start_available = availability_map and datetime.strptime(start_time, "%H:%M").time() in availability_map and availability_map[datetime.strptime(start_time, "%H:%M").time()]
        end_available = availability_map and datetime.strptime(end_time, "%H:%M").time() in availability_map and availability_map[datetime.strptime(end_time, "%H:%M").time()]
        
        if start_available and end_available:
            builder.row(
                types.InlineKeyboardButton(
                    text="✅ Подтвердить время",
                    callback_data="confirm_time_range"
                )
            )
        else:
            builder.row(
                types.InlineKeyboardButton(
                    text="❌ Интервал недоступен",
                    callback_data="interval_unavailable"
                )
            )

    builder.row(
        types.InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_time_selection"
        )
    )

    return builder.as_markup()

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


# def merge_adjacent_bookings(bookings):
#     """Объединяет смежные бронирования одного типа"""
#     if not bookings:
#         return bookings

#     sorted_bookings = sorted(bookings, key=lambda x: (
#         x.get('booking_type', ''),
#         x.get('date', ''),
#         x.get('start_time', '')
#     ))

#     merged = []
#     current = sorted_bookings[0]

#     for next_booking in sorted_bookings[1:]:
#         if (current.get('booking_type') == next_booking.get('booking_type') and
#                 current.get('date') == next_booking.get('date') and
#                 current.get('end_time') == next_booking.get('start_time')):

#             current = {
#                 **current,
#                 'end_time': next_booking.get('end_time'),
#                 'id': min(current.get('id', 0), next_booking.get('id', 0)),
#                 'merged': True
#             }
#         else:
#             merged.append(current)
#             current = next_booking

#     merged.append(current)
#     return merged


def load_bookings():
    """Загружает бронирования из файла и удаляет прошедшие"""
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

    return valid_bookings


# def has_booking_conflict(user_id, date, time_start, time_end, subject=None, exclude_id=None):
#     """Проверяет конфликты бронирований для учеников (любые предметы в одно время)"""
#     bookings = load_bookings()
    
#     def time_to_minutes(t):
#         h, m = map(int, t.split(':'))
#         return h * 60 + m

#     new_start = time_to_minutes(time_start)
#     new_end = time_to_minutes(time_end)

#     for booking in bookings:
#         if (booking.get('user_id') == user_id and
#             booking.get('date') == date and
#             booking.get('user_role') == 'student'):  # Проверяем только для учеников
            
#             if exclude_id and booking.get('id') == exclude_id:
#                 continue

#             existing_start = time_to_minutes(booking.get('start_time', '00:00'))
#             existing_end = time_to_minutes(booking.get('end_time', '00:00'))

#             # Проверяем пересечение временных интервалов
#             if not (new_end <= existing_start or new_start >= existing_end):
#                 return True
                
#     return False


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
    user_roles = storage.get_user_roles(user_id)
    
    # Для родителя показываем бронирования всех его детей
    children_ids = []
    if 'parent' in user_roles:
        children_ids = storage.get_parent_children(user_id)
    
    # Разделяем бронирования по категориям
    teacher_bookings = []
    student_bookings = []
    children_bookings = []
    
    for booking in bookings:
        if booking.get('user_id') == user_id:
            if booking.get('user_role') == 'teacher':
                teacher_bookings.append(booking)
            else:
                student_bookings.append(booking)
        elif booking.get('user_id') in children_ids:
            children_bookings.append(booking)
    
    if not any([teacher_bookings, student_bookings, children_bookings]):
        return None
    
    builder = InlineKeyboardBuilder()
    
    # Бронирования преподавателя
    if teacher_bookings:
        builder.row(types.InlineKeyboardButton(
            text="👨‍🏫 МОИ БРОНИРОВАНИЯ (ПРЕПОДАВАТЕЛЬ)",
            callback_data="ignore"
        ))
        
        for booking in sorted(teacher_bookings, key=lambda x: (x.get("date"), x.get("start_time"))):
            date_str = booking.get('date', '')
            if isinstance(date_str, str) and len(date_str) == 10:  # YYYY-MM-DD format
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m")
                except ValueError:
                    formatted_date = date_str
            else:
                formatted_date = date_str
            
            button_text = (
                f"📅 {formatted_date} "
                f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')}"
            )
            
            builder.row(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"booking_info_{booking.get('id')}"
            ))
    
    # Бронирования ученика
    if student_bookings:
        builder.row(types.InlineKeyboardButton(
            text="👨‍🎓 МОИ БРОНИРОВАНИЯ (УЧЕНИК)",
            callback_data="ignore"
        ))
        
        for booking in sorted(student_bookings, key=lambda x: (x.get("date"), x.get("start_time"))):
            date_str = booking.get('date', '')
            if isinstance(date_str, str) and len(date_str) == 10:
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m")
                except ValueError:
                    formatted_date = date_str
            else:
                formatted_date = date_str
            
            subject = booking.get('subject', '')
            subject_short = get_subject_short_name(subject)
            
            button_text = (
                f"📅 {formatted_date} "
                f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')} "
                f"📚 {subject_short}"
            )
            
            builder.row(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"booking_info_{booking.get('id')}"
            ))
    
    # Бронирования детей (для родителей)
    if children_bookings:
        builder.row(types.InlineKeyboardButton(
            text="👶 БРОНИРОВАНИЯ МОИХ ДЕТЕЙ",
            callback_data="ignore"
        ))
        
        # Группируем по детям
        children_bookings_by_child = {}
        for booking in children_bookings:
            child_id = booking.get('user_id')
            if child_id not in children_bookings_by_child:
                children_bookings_by_child[child_id] = []
            children_bookings_by_child[child_id].append(booking)
        
        for child_id, child_bookings in children_bookings_by_child.items():
            child_info = storage.get_child_info(child_id)
            child_name = child_info.get('user_name', f'Ребенок {child_id}')
            
            builder.row(types.InlineKeyboardButton(
                text=f"👶 {child_name}",
                callback_data="ignore"
            ))
            
            for booking in sorted(child_bookings, key=lambda x: (x.get("date"), x.get("start_time"))):
                date_str = booking.get('date', '')
                if isinstance(date_str, str) and len(date_str) == 10:
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        formatted_date = date_obj.strftime("%d.%m")
                    except ValueError:
                        formatted_date = date_str
                else:
                    formatted_date = date_str
                
                subject = booking.get('subject', '')
                subject_short = get_subject_short_name(subject)
                
                button_text = (
                    f"   📅 {formatted_date} "
                    f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')} "
                    f"📚 {subject_short}"
                )
                
                builder.row(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"booking_info_{booking.get('id')}"
                ))
    
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад в меню",
        callback_data="back_to_menu"
    ))
    
    return builder.as_markup()


def get_subject_short_name(subject_id: str) -> str:
    """Возвращает сокращенное название предмета (первые 3 буквы)"""
    subject_names = {
        "1": "📐 Мат",
        "2": "⚛️ Физ",
        "3": "💻 Инф",
        "4": "📖 Рус"
    }
    return subject_names.get(subject_id, subject_id[:3] if subject_id else "???")


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

# Основное меню (всегда видимое)
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Забронировать время")],
        [KeyboardButton(text="📋 Мои бронирования")],
        [KeyboardButton(text="👤 Моя роль")]
    ],
    resize_keyboard=True
)

# Меню с дополнительными опциями (в развертываемом меню)
additional_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Обратиться к администратору")],
        [KeyboardButton(text="👤 Моя роль")]
    ],
    resize_keyboard=True
)

# Комбинированное меню для пользователей без ролей
no_roles_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Обратиться к администратору")]
    ],
    resize_keyboard=True
)


async def generate_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    """Генерирует главное меню в зависимости от ролей"""
    roles = storage.get_user_roles(user_id)
    
    if not roles:
        return no_roles_menu
    
    keyboard_buttons = []
    
    # Проверяем, есть ли роли, которые могут бронировать
    can_book = any(role in roles for role in ['teacher', 'student', 'parent'])
    
    if can_book:
        keyboard_buttons.append([KeyboardButton(text="📅 Забронировать время")])
    
    keyboard_buttons.append([KeyboardButton(text="📋 Мои бронирования")])
    keyboard_buttons.append([KeyboardButton(text="👤 Моя роль")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = storage.get_user_name(user_id)
    
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
        role_translations = {
            "teacher": "преподаватель",
            "student": "ученик", 
            "parent": "родитель"
        }
        role_text = ", ".join([role_translations.get(role, role) for role in roles])
        await message.answer(f"Ваши роли: {role_text}")
    else:
        await message.answer("Ваши роли еще не назначены. Обратитесь к администратору.")

# @dp.message(F.text == "ℹ️ Помощь")
# async def show_help(message: types.Message):
#     await cmd_help(message)


# @dp.message(Command("help"))
# async def cmd_help(message: types.Message):
#     await message.answer(
#         "📋 Справка по боту:\n\n"
#         "/book - начать процесс бронирования\n"
#         " 1. Выбрать роль (ученик/преподаватель)\n"
#         " 2. Ввести ваше ФИО\n"
#         " 3. Выбрать предмет(ы)\n"
#         " 4. Выбрать тип бронирования\n"
#         " 5. Выбрать дату из календаря\n"
#         " 6. Выбрать время начала и окончания\n"
#         " 7. Подтвердить бронирование\n\n"
#         "/my_bookings - показать ваши бронирования\n"
#         "/my_role - показать вашу роль\n"
#         "/help - показать эту справку"
#     )


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
    
    # Показываем доступные роли для бронирования
    builder = InlineKeyboardBuilder()
    
    # Роли, которые можно использовать для бронирования
    available_booking_roles = []
    
    if 'teacher' in user_roles:
        available_booking_roles.append('teacher')
        builder.button(text="👨‍🏫 Я преподаватель", callback_data="role_teacher")
    
    if 'student' in user_roles:
        available_booking_roles.append('student') 
        builder.button(text="👨‍🎓 Я ученик", callback_data="role_student")
    
    if 'parent' in user_roles:
        available_booking_roles.append('parent')
        builder.button(text="👨‍👩‍👧‍👦 Я родитель", callback_data="role_parent")
    
    if not available_booking_roles:
        await message.answer(
            "❌ У вас нет ролей для бронирования. Обратитесь к администратору.",
            reply_markup=await generate_main_menu(user_id)
        )
        return
    
    await state.update_data(available_roles=available_booking_roles)
    
    if len(available_booking_roles) == 1:
        # Если только одна роль, автоматически выбираем ее
        role = available_booking_roles[0]

        await state.update_data(user_role=role)
        
        if role == 'teacher':
            # Для преподавателя получаем предметы
            teacher_subjects = storage.get_teacher_subjects(user_id)
            if not teacher_subjects:
                await message.answer(
                    "У вас нет назначенных предметов. Обратитесь к администратору.",
                    reply_markup=await generate_main_menu(user_id)
                )
                return
            
            await state.update_data(subjects=teacher_subjects)
            subject_names = [SUBJECTS.get(subj_id, f"Предмет {subj_id}") for subj_id in teacher_subjects]
            
            await message.answer(
                f"Вы преподаватель\n"
                f"Ваши предметы: {', '.join(subject_names)}\n"
                "Теперь выберите дату:",
                reply_markup=generate_calendar()
            )
            await state.set_state(BookingStates.SELECT_DATE)
            
        elif role == 'student':
            await message.answer(
                "Вы ученик\n"
                "Выберите предмет для занятия:",
                reply_markup=generate_subjects_keyboard()
            )
            await state.set_state(BookingStates.SELECT_SUBJECT)
            
        elif role == 'parent':
            # Обработка родителя
            children_ids = storage.get_parent_children(user_id)
            if not children_ids:
                await message.answer(
                    "У вас нет привязанных детей. Обратитесь к администратору.",
                    reply_markup=await generate_main_menu(user_id)
                )
                return
            
            builder = InlineKeyboardBuilder()
            for child_id in children_ids:
                child_info = storage.get_child_info(child_id)
                child_name = child_info.get('user_name', f'Ученик {child_id}')
                builder.button(
                    text=f"👶 {child_name}",
                    callback_data=f"select_child_{child_id}"
                )
            
            builder.button(text="❌ Отмена", callback_data="cancel_child_selection")
            builder.adjust(1)
            
            await message.answer(
                "Вы родитель\n"
                "Выберите ребенка для записи:",
                reply_markup=builder.as_markup()
            )
            await state.set_state(BookingStates.PARENT_SELECT_CHILD)
    
    else:
        # Если несколько ролей, показываем выбор
        await message.answer(
            "Выберите роль для бронирования:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.SELECT_ROLE)


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
        await state.set_state(BookingStates.SELECT_ROLE)  # Исправлено здесь
    else:
        await message.answer(
            "✅ Ваше ФИО сохранено!\n"
            "⏳ Обратитесь к администратору для получения ролей.",
            reply_markup=await generate_main_menu(user_id)
        )
        await state.clear()


@dp.callback_query(F.data.startswith("role_"))
async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    user_id = callback.from_user.id

    await state.update_data(user_role=role)

    if role == 'teacher':
        # Для преподавателя получаем предметы из Google Sheets
        teacher_subjects = storage.get_teacher_subjects(user_id)

        # ДЕБАГ: Логируем полученные предметы
        logger.info(f"Teacher {user_id} subjects: {teacher_subjects} (type: {type(teacher_subjects)})")

        # ВРЕМЕННОЕ ИСПРАВЛЕНИЕ: Если пришел список с одним элементом '1234'
        if (teacher_subjects and
                isinstance(teacher_subjects, list) and
                len(teacher_subjects) == 1 and
                teacher_subjects[0].isdigit() and
                len(teacher_subjects[0]) > 1):
            # Разбиваем '1234' на ['1', '2', '3', '4']
            combined_subject = teacher_subjects[0]
            teacher_subjects = [digit for digit in combined_subject]
            logger.info(f"Fixed combined subjects: {teacher_subjects}")

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

    elif role == 'student':
        # Для ученика сразу запрашиваем предмет
        await callback.message.edit_text(
            "Вы выбрали роль ученика\n"
            "Выберите предмет для занятия:",
            reply_markup=generate_subjects_keyboard()
        )
        await state.set_state(BookingStates.SELECT_SUBJECT)
        
    elif role == 'parent':
        # Для родителя получаем детей
        children_ids = storage.get_parent_children(user_id)
        
        if not children_ids:
            await callback.answer(
                "У вас нет привязанных детей. Обратитесь к администратору.",
                show_alert=True
            )
            return
        
        builder = InlineKeyboardBuilder()
        for child_id in children_ids:
            child_info = storage.get_child_info(child_id)
            child_name = child_info.get('user_name', f'Ученик {child_id}')
            builder.button(
                text=f"👶 {child_name}",
                callback_data=f"select_child_{child_id}"
            )
        
        builder.button(text="❌ Отмена", callback_data="cancel_child_selection")
        builder.adjust(1)
        
        await callback.message.edit_text(
            "Вы выбрали роль родителя\n"
            "Выберите ребенка для записи:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.PARENT_SELECT_CHILD)

    await callback.answer()

# @dp.callback_query(BookingStates.TEACHER_SUBJECTS, F.data.startswith("subject_"))
# async def process_teacher_subjects(callback: types.CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     selected_subjects = data.get("subjects", [])

#     subject_id = callback.data.split("_")[1]
#     if subject_id in selected_subjects:
#         selected_subjects.remove(subject_id)
#     else:
#         selected_subjects.append(subject_id)

#     await state.update_data(subjects=selected_subjects)
#     await callback.message.edit_reply_markup(
#         reply_markup=generate_subjects_keyboard(selected_subjects, is_teacher=True)
#     )
#     await callback.answer()


# @dp.callback_query(BookingStates.TEACHER_SUBJECTS, F.data == "subjects_done")
# async def process_subjects_done(callback: types.CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     if not data.get("subjects"):
#         await callback.answer("Выберите хотя бы один предмет!", show_alert=True)
#         return

#     storage.update_user_subjects(callback.from_user.id, data["subjects"])
#     await state.update_data(booking_type="Тип1")  # Устанавливаем тип по умолчанию
#     await callback.message.edit_text("Выберите дату:", reply_markup=generate_calendar())  # Пропускаем выбор типа
#     await state.set_state(BookingStates.SELECT_DATE)
#     await callback.answer()


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


@dp.callback_query(BookingStates.SELECT_DATE, F.data.startswith("calendar_day_"))
async def process_calendar(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data
    user_id = callback.from_user.id

    if data.startswith("calendar_day_"):
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()
        formatted_date = selected_date.strftime("%Y.%m.%d")

        # Получаем данные из состояния
        state_data = await state.get_data()
        role = state_data.get('user_role')
        subject = state_data.get('subject') if role == 'student' else None

        # Проверяем существующие брони
        

        # Для учеников: проверяем доступность временных слотов
        availability_map = None
        if role == 'student' and subject:
            try:
                # Создаем временного студента для проверки
                temp_student = Student(
                    name="temp_check",
                    start_of_study_time="09:00",
                    end_of_study_time="20:00",
                    subject_id=subject,
                    need_for_attention=state_data.get('need_for_attention', 1)
                )
                
                # Получаем всех студентов и преподавателей из Google Sheets
                loader = GoogleSheetsDataLoader(CREDENTIALS_PATH, SPREADSHEET_ID, formatted_date)
                all_teachers, all_students = loader.load_data()
                
                # # ВРЕМЕННО: если данные не загружаются, используем тестовые данные
                # if not all_teachers:
                #     logger.warning("Преподаватели не загружены из Google Sheets, используем тестовые данные")
                #
                #     # Тестовые преподаватели (активные с 9:00 до 18:00)
                #     all_teachers = [
                #         Teacher(
                #             name="Мария Ивановна",
                #             start_of_study_time="09:00",
                #             end_of_study_time="18:00",
                #             subjects_id=[1, 2],  # Математика и Физика
                #             priority=1,
                #             maximum_attention=20  # Увеличим емкость
                #         ),
                #         Teacher(
                #             name="Петр Сергеевич",
                #             start_of_study_time="10:00",
                #             end_of_study_time="19:00",
                #             subjects_id=[1, 3],  # Математика и Информатика
                #             priority=2,
                #             maximum_attention=15  # Увеличим емкость
                #         )
                #     ]
                #
                #     # Тестовые студенты с меньшей потребностью во внимании
                #     all_students = [
                #         Student(
                #             name="Иван Петров",
                #             start_of_study_time="10:00",
                #             end_of_study_time="12:00",
                #             subject_id=1,  # Математика
                #             need_for_attention=2  # Уменьшим потребность
                #         ),
                #         Student(
                #             name="Елена Сидорова",
                #             start_of_study_time="14:00",
                #             end_of_study_time="16:00",
                #             subject_id=2,  # Физика
                #             need_for_attention=2  # Уменьшим потребность
                #         )
                #     ]
                #
                # if not all_students:
                #     logger.warning("Студенты не загружены из Google Sheets, используем тестовые данные")
                #
                #     # Тестовые студенты с разным временем
                #     all_students = [
                #         Student(
                #             name="Иван Петров",
                #             start_of_study_time="10:00",
                #             end_of_study_time="12:00",
                #             subject_id=1,  # Математика
                #             need_for_attention=5
                #         ),
                #         Student(
                #             name="Елена Сидорова",
                #             start_of_study_time="14:00",
                #             end_of_study_time="16:00",
                #             subject_id=2,  # Физика
                #             need_for_attention=3
                #         ),
                #         Student(
                #             name="Алексей Козлов",
                #             start_of_study_time="11:00",
                #             end_of_study_time="13:00",
                #             subject_id=1,  # Математика
                #             need_for_attention=4
                #         )
                #     ]
                
                # Логируем загруженные данные
                logger.info(f"Используется: {len(all_teachers)} преподавателей, {len(all_students)} студентов")
                
                # Показываем сообщение о загрузке
                await callback.message.edit_text(
                    f"⏳ Проверяем доступность времени на {day}.{month}.{year}...\n"
                    "Это может занять несколько секунд"
                )
                
                # Асинхронно проверяем доступность
                availability_map = await asyncio.to_thread(
                    check_student_availability_for_slots,
                    student=temp_student,
                    all_students=all_students,
                    teachers=all_teachers,
                    target_date=selected_date,
                    start_time=time(9, 0),
                    end_time=time(20, 0),
                    interval_minutes=30
                )
                
            except Exception as e:
                logger.error(f"Ошибка при проверке доступности: {e}")
                await callback.answer(
                    "❌ Ошибка при проверке доступности времени",
                    show_alert=True
                )
                return

        await state.update_data(
            selected_date=selected_date,
            time_start=None,
            time_end=None,
            selecting_mode='start',
            availability_map=availability_map
        )

        message_text = f"📅 Выбрана дата: {day}.{month}.{year}\n"
        
        if role == 'student' and availability_map:
            available_count = sum(1 for available in availability_map.values() if available)
            total_count = len(availability_map)
            message_text += f"✅ Доступно слотов: {available_count}/{total_count}\n"
            message_text += "🔒 - время недоступно для бронирования\n"
            message_text += "🟢 - выберите начало занятия\n"
            message_text += "🔴 - выберите окончание занятия\n\n"

        message_text += "Как выбрать время:\n"
        message_text += "1. Нажмите 'Выбрать начало 🟢'\n"
        message_text += "2. Выберите доступное время начала\n"
        message_text += "3. Нажмите 'Выбрать конец 🔴'\n"
        message_text += "4. Выберите доступное время окончания\n"
        message_text += "5. Подтвердите выбор"

        await callback.message.edit_text(
            message_text,
            reply_markup=generate_time_range_keyboard_with_availability(
                selected_date=selected_date,
                availability_map=availability_map
            )
        )
        await state.set_state(BookingStates.SELECT_TIME_RANGE)
        await callback.answer()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "time_slot_unavailable")
async def handle_unavailable_slot(callback: types.CallbackQuery):
    """Обрабатывает нажатие на недоступный временной слот"""
    await callback.answer(
        "❌ Это время недоступно для бронирования\n"
        "Выберите другое время из доступных (без 🔒)",
        show_alert=True
    )

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "interval_unavailable")
async def handle_unavailable_interval(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает попытку подтверждения недоступного интервала"""
    data = await state.get_data()
    availability_map = data.get('availability_map', {})
    
    start_time = data.get('time_start')
    end_time = data.get('time_end')
    
    if start_time and end_time:
        start_obj = datetime.strptime(start_time, "%H:%M").time()
        end_obj = datetime.strptime(end_time, "%H:%M").time()
        
        start_available = start_obj in availability_map and availability_map[start_obj]
        end_available = end_obj in availability_map and availability_map[end_obj]
        
        if not start_available:
            message = f"Время начала {start_time} недоступно"
        elif not end_available:
            message = f"Время окончания {end_time} недоступно"
        else:
            message = "Выбранный интервал недоступен"
    else:
        message = "Выберите доступный временной интервал"
    
    await callback.answer(
        f"❌ {message}\nВыберите время из доступных слотов",
        show_alert=True
    )

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "availability_info")
async def show_availability_info(callback: types.CallbackQuery, state: FSMContext):
    """Показывает информацию о доступности"""
    data = await state.get_data()
    availability_map = data.get('availability_map', {})
    
    if availability_map:
        available_count = sum(1 for available in availability_map.values() if available)
        total_count = len(availability_map)
        percentage = (available_count / total_count * 100) if total_count > 0 else 0
        
        message = (
            f"📊 Статистика доступности:\n"
            f"• Доступно слотов: {available_count}/{total_count}\n"
            f"• Процент доступности: {percentage:.1f}%\n"
            f"• 🔒 - время недоступно\n"
            f"• Выбирайте только доступные слоты"
        )
    else:
        message = "Информация о доступности не загружена"
    
    await callback.answer(message, show_alert=True)


@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "cancel_time_selection")
async def cancel_time_selection_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Выбор времени отменен")
    await state.clear()

    # Возвращаем пользователя в главное меню
    user_id = callback.from_user.id
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=await generate_main_menu(user_id)
    )
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data.startswith("time_point_"))
async def process_time_point(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.replace("time_point_", "")
    data = await state.get_data()
    selecting_mode = data.get('selecting_mode', 'start')
    availability_map = data.get('availability_map')
    
    # Проверяем доступность слота
    if availability_map:
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        if time_obj in availability_map and not availability_map[time_obj]:
            await callback.answer(
                "❌ Это время недоступно для бронирования\n"
                "Выберите время из доступных слотов (без 🔒)",
                show_alert=True
            )
            return

    if selecting_mode == 'start':
        # Выбираем начало
        await state.update_data(time_start=time_str)

        # Сбрасываем конец, если он раньше нового начала
        if data.get('time_end'):
            end_obj = datetime.strptime(data['time_end'], "%H:%M")
            start_obj = datetime.strptime(time_str, "%H:%M")
            if end_obj <= start_obj:
                await state.update_data(time_end=None)

        await callback.message.edit_text(
            f"🟢 Выбрано начало: {time_str}\n"
            "Теперь нажмите 'Выбрать конец 🔴' и выберите время окончания\n"
            "Выбирайте только доступные времена (без 🔒)",
            reply_markup=generate_time_range_keyboard_with_availability(
                selected_date=data.get('selected_date'),
                start_time=time_str,
                end_time=data.get('time_end'),
                availability_map=availability_map
            )
        )
    else:
        # Выбираем конец
        if not data.get('time_start'):
            await callback.answer("Сначала выберите время начала!", show_alert=True)
            return

        start_obj = datetime.strptime(data['time_start'], "%H:%M")
        end_obj = datetime.strptime(time_str, "%H:%M")
        
        if end_obj <= start_obj:
            await callback.answer("Время окончания должно быть после времени начала!", show_alert=True)
            return

        await state.update_data(time_end=time_str)

        await callback.message.edit_text(
            f"📋 Текущий выбор:\n"
            f"🟢 Начало: {data['time_start']}\n"
            f"🔴 Конец: {time_str}\n\n"
            "Если выбор корректен, нажмите '✅ Подтвердить время'\n"
            "Или измените начало/конец с помощью кнопок выше",
            reply_markup=generate_time_range_keyboard_with_availability(
                selected_date=data.get('selected_date'),
                start_time=data['time_start'],
                end_time=time_str,
                availability_map=availability_map
            )
        )

    await callback.answer()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data.in_(["select_start_mode", "select_end_mode"]))
async def switch_selection_mode(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    availability_map = data.get('availability_map')

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

    if availability_map:
        available_count = sum(1 for available in availability_map.values() if available)
        total_count = len(availability_map)
        message_text += f"Доступно слотов: {available_count}/{total_count}\n"
        message_text += "🔒 - время недоступно для бронирования\n"

    if callback.data == "select_start_mode":
        message_text += "Нажмите на время для установки начала:"
    else:
        message_text += "Нажмите на время для установки окончания:"

    await callback.message.edit_text(
        message_text,
        reply_markup=generate_time_range_keyboard_with_availability(
            selected_date=data.get('selected_date'),
            start_time=time_start,
            end_time=time_end,
            availability_map=availability_map
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
    user_id = callback.from_user.id
    date_str = data['selected_date'].strftime("%Y-%m-%d")
    
    # Проверка для учеников - нет ли уже брони на этот предмет в этот день
    if data.get('user_role') == 'student' and subject:
        if storage.has_booking_on_date(user_id, date_str, 'student', subject):
            await callback.answer(
                f"У вас уже есть бронь на этот день по предмету {SUBJECTS.get(subject, subject)}!",
                show_alert=True
            )
            return
    
    # Проверка пересечений времени для учеников
    if data.get('user_role') == 'student':
        if storage.has_time_conflict(
            user_id=user_id,
            date=date_str,
            time_start=data['time_start'],
            time_end=data['time_end']
        ):
            await callback.answer(
                "У вас уже есть бронь на это время! Временные интервалы не должны пересекаться.",
                show_alert=True
            )
            return
    else:
        # Для преподавателей проверяем конфликты только для тех же предметов
        if has_teacher_booking_conflict(
            user_id=user_id,
            date=date_str,
            time_start=data['time_start'],
            time_end=data['time_end']
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
        # Безопасное получение названий предметов
        subject_names = []
        for subj in data.get('subjects', []):
            subject_names.append(SUBJECTS.get(subj, f"Предмет {subj}"))
        subjects_text = ", ".join(subject_names)
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
    
    # Определяем, кто делает бронирование
    is_parent = 'child_id' in data
    target_user_id = data['child_id'] if is_parent else callback.from_user.id
    target_user_name = data['child_name'] if is_parent else data['user_name']
    
    # Формируем данные брони
    booking_data = {
        "user_id": target_user_id,
        "user_name": target_user_name,
        "user_role": data['user_role'],
        "booking_type": "Тип1",
        "date": data['selected_date'].strftime("%Y-%m-%d"),
        "start_time": data['time_start'],
        "end_time": data['time_end'],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    if is_parent:
        booking_data["parent_id"] = callback.from_user.id
        booking_data["parent_name"] = storage.get_user_name(callback.from_user.id)
    
    if data['user_role'] == 'teacher':
        booking_data["subjects"] = data.get('subjects', [])
    else:
        booking_data["subject"] = data.get('subject', '')

    # Сохраняем бронь
    try:
        booking = storage.add_booking(booking_data)
        role_text = "преподавателя" if data['user_role'] == 'teacher' else "ученика"
        
        if is_parent:
            role_text = f"ребенка ({target_user_name})"
        
        # Безопасное формирование текста предметов для сообщения
        if data['user_role'] == 'teacher':
            subject_names = []
            for subj in data.get('subjects', []):
                subject_names.append(SUBJECTS.get(subj, f"Предмет {subj}"))
            subjects_text = f"Предметы: {', '.join(subject_names)}"
        else:
            subjects_text = f"Предмет: {SUBJECTS.get(data.get('subject', ''), 'Не указан')}"
        
        message_text = (
            f"✅ Бронирование {role_text} подтверждено!\n"
            f"📅 Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {data['time_start']}-{data['time_end']}\n"
            f"{subjects_text}\n"
        )
        
        if is_parent:
            message_text += f"👨‍👩‍👧‍👦 Записано родителем: {booking_data['parent_name']}"
        
        await callback.message.edit_text(message_text)
        
    except Exception as e:
        await callback.message.edit_text("❌ Ошибка при сохранении брони!")
        logger.error(f"Ошибка сохранения: {e}")
    
    await state.clear()


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
    roles = storage.get_user_roles(message.from_user.id)
    if roles:
        role_text = ", ".join(["преподаватель" if role == "teacher" else "ученик" for role in roles])
        await message.answer(f"Ваши роли: {role_text}")
    else:
        await message.answer("Ваши роли еще не назначены. Обратитесь к администратору.")


@dp.message(F.text == "❌ Отменить бронь")
async def start_cancel_booking(message: types.Message):
    keyboard = generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований для отмены")
        return

    await message.answer("Выберите бронирование для отмена:", reply_markup=keyboard)


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
        )
        
        # Добавляем информацию о ребенке, если это бронь ребенка
        if booking.get('parent_id'):
            parent_name = booking.get('parent_name', 'Родитель')
            message_text += f"👨‍👩‍👧‍👦 Записано родителем: {parent_name}\n"
        
        message_text += (
            f"👤 Имя: {booking.get('user_name', 'Неизвестно')}\n"
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

@dp.callback_query(BookingStates.SELECT_ROLE, F.data == "role_parent")
async def process_role_parent_selection(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    # Получаем детей родителя
    children_ids = storage.get_parent_children(user_id)
    
    if not children_ids:
        await callback.answer(
            "У вас нет привязанных детей. Обратитесь к администратору.",
            show_alert=True
        )
        return
    
    await state.update_data(user_role='parent')
    
    # Создаем клавиатуру для выбора ребенка
    builder = InlineKeyboardBuilder()
    for child_id in children_ids:
        child_info = storage.get_child_info(child_id)
        child_name = child_info.get('user_name', f'Ученик {child_id}')
        builder.button(
            text=f"👶 {child_name}",
            callback_data=f"select_child_{child_id}"
        )
    
    builder.button(text="❌ Отмена", callback_data="cancel_child_selection")
    builder.adjust(1)
    
    await callback.message.edit_text(
        "Вы выбрали роль родителя\n"
        "Выберите ребенка для записи:",
        reply_markup=builder.as_markup()
    )
    await state.set_state(BookingStates.PARENT_SELECT_CHILD)
    await callback.answer()

# Обработчик выбора ребенка
@dp.callback_query(BookingStates.PARENT_SELECT_CHILD, F.data.startswith("select_child_"))
async def process_child_selection(callback: types.CallbackQuery, state: FSMContext):
    child_id = int(callback.data.replace("select_child_", ""))
    child_info = storage.get_child_info(child_id)
    
    if not child_info:
        await callback.answer("Ошибка: информация о ребенке не найдена", show_alert=True)
        return
    
    await state.update_data(
        child_id=child_id,
        child_name=child_info.get('user_name', ''),
        user_role='student'  # Для бронирования используем роль ученика
    )
    
    await callback.message.edit_text(
        f"Выбран ребенок: {child_info.get('user_name', '')}\n"
        "Выберите предмет для занятия:",
        reply_markup=generate_subjects_keyboard()
    )
    await state.set_state(BookingStates.SELECT_SUBJECT)
    await callback.answer()

# Обработчик отмены выбора ребенка
@dp.callback_query(BookingStates.PARENT_SELECT_CHILD, F.data == "cancel_child_selection")
async def cancel_child_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Выбор ребенка отменен")
    await state.clear()
    
    user_id = callback.from_user.id
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=await generate_main_menu(user_id)
    )
    await callback.answer()


@dp.callback_query(F.data.in_(["back_to_menu", "back_to_bookings"]))
async def back_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    menu = await generate_main_menu(user_id)
    
    if callback.data == "back_to_menu":
        await callback.message.edit_text(
            "Главное меню:",
            reply_markup=None
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=menu
        )
    else:
        keyboard = generate_booking_list(user_id)
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