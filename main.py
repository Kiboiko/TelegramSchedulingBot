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
from shedule_app.HelperMethods import School
from shedule_app.models import Person, Teacher, Student
from shedule_app.GoogleParser import GoogleSheetsDataLoader
# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOKINGS_FILE = "bookings.json"
CREDENTIALS_PATH = r"C:\Users\bestd\OneDrive\Документы\GitHub\TelegramSchedulingBot\credentials.json"

SPREADSHEET_ID = "1L4l6ONchMU5xk5v1y_50po_l0NwhssNCCCKTsy3aR_0"
ADMIN_IDS = [1180878673, 973231400, 1312414595]
BOOKING_TYPES = ["Тип1"]
SUBJECTS = {
    "1": "Математика",
    "2": "Физика",
    "3": "Информатика",
    "4": "Русский язык"
}

def _add_minutes_to_time(time_obj: time, minutes: int) -> time:
    """
    Добавляет минуты к объекту time
    """
    from datetime import datetime, timedelta
    dummy_date = datetime(2023, 1, 1)
    combined_datetime = datetime.combine(dummy_date, time_obj)
    new_datetime = combined_datetime + timedelta(minutes=minutes)
    return new_datetime.time()

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

def _create_empty_time_slots() -> Dict[time, Dict]:
    """Создает словарь со всеми временными интервалами с 9:00 до 20:00"""
    from datetime import time
    
    time_slots = {}
    current_time = time(9, 0)
    end_time = time(20, 0)
    
    while current_time <= end_time:
        time_slots[current_time] = {
            'distribution': {},
            'condition_result': True  # Для пустых интервалов условие всегда выполняется
        }
        # Добавляем 30 минут для следующего интервала
        next_time = (current_time.hour * 60 + current_time.minute + 30) // 60
        next_minute = (current_time.hour * 60 + current_time.minute + 30) % 60
        current_time = time(next_time, next_minute)
    
    return time_slots

class BookingStates(StatesGroup):
    SELECT_ROLE = State()
    INPUT_NAME = State()
    SELECT_SUBJECT = State()  # Только для учеников
    SELECT_DATE = State()
    SELECT_TIME_RANGE = State()
    CONFIRMATION = State()
    SELECT_CHILD = State()  # Новое состояние для выбора ребенка
    PARENT_SELECT_CHILD = State()
    SELECT_SCHEDULE_DATE = State()  # Новое состояние для выбора даты расписания
    CONFIRM_SCHEDULE = State()  # Подтверждение составления расписания


# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
storage = JSONStorage(file_path=BOOKINGS_FILE)

# Настройка Google Sheets
try:
    gsheets = GoogleSheetsManager(
        credentials_file='credentials.json',
        spreadsheet_id=SPREADSHEET_ID
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
                    "Обратитесь к администратору для получения доступа.\n Телефон администратора: +79001372727",
                    reply_markup=ReplyKeyboardRemove()
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "⏳ Обратитесь к администратору для получения доступа \n Телефон администратора: +79001372727",
                    show_alert=True
                )
            return
        
        return await handler(event, data)

# Добавление middleware
dp.update.middleware(RoleCheckMiddleware())

def get_subject_distribution_by_time(loader, target_date: str, condition_check: bool = True) -> Dict[time, Dict]:
    """
    Получает распределение тем занятий по получасовым интервалам для указанной даты
    """
    from datetime import time
    from typing import Dict
    
    # Загружаем данные студентов
    student_sheet = loader._get_sheet_data("Ученики")
    if not student_sheet:
        logger.error("Лист 'Ученики' не найден")
        return _create_empty_time_slots()
    
    # Находим колонки для указанной даты
    date_columns = loader._find_date_columns(student_sheet, target_date)
    if date_columns == (-1, -1):
        logger.error(f"Дата {target_date} не найдена в листе учеников")
        return _create_empty_time_slots()
    
    start_col, end_col = date_columns
    
    # Загружаем план обучения
    loader._load_study_plan_cache()
    
    # Создаем все временные интервалы с 9:00 до 20:00 с шагом 30 минут
    time_slots = _create_empty_time_slots()
    
    # Обрабатываем каждого студента
    for row in student_sheet[1:]:  # Пропускаем заголовок
        if not row or len(row) <= max(start_col, end_col):
            continue
        
        name = str(row[1]).strip() if len(row) > 1 else ""
        if not name:
            continue
        
        # Проверяем, есть ли запись на указанную дату
        start_time_str = str(row[start_col]).strip() if len(row) > start_col and row[start_col] else ""
        end_time_str = str(row[end_col]).strip() if len(row) > end_col and row[end_col] else ""
        
        if not start_time_str or not end_time_str:
            continue  # Нет записи на эту дату
        
        # Получаем тему занятия для этого студента
        lesson_number = loader._calculate_lesson_number_for_student(row, start_col)
        topic = None
        
        if name in loader._study_plan_cache:
            student_plan = loader._study_plan_cache[name]
            topic = student_plan.get(lesson_number, "Неизвестная тема")
        else:
            # Пытаемся получить тему из предмета (колонка C)
            if len(row) > 2 and row[2]:
                subject_id = str(row[2]).strip()
                topic = f"P{subject_id}"
            else:
                topic = "Тема не определена"
        
        # Парсим время начала и окончания
        try:
            start_time_parts = start_time_str.split(':')
            end_time_parts = end_time_str.split(':')
            
            if len(start_time_parts) >= 2 and len(end_time_parts) >= 2:
                start_hour = int(start_time_parts[0])
                start_minute = int(start_time_parts[1])
                end_hour = int(end_time_parts[0])
                end_minute = int(end_time_parts[1])
                
                lesson_start = time(start_hour, start_minute)
                lesson_end = time(end_hour, end_minute)
                
                # Находим все получасовые интервалы, попадающие в занятие
                current_interval = time(9, 0)
                while current_interval <= time(20, 0):
                    interval_end = _add_minutes_to_time(current_interval, 30)
                    if (current_interval >= lesson_start and interval_end <= lesson_end):
                        # Этот интервал полностью внутри занятия
                        if topic not in time_slots[current_interval]['distribution']:
                            time_slots[current_interval]['distribution'][topic] = 0
                        time_slots[current_interval]['distribution'][topic] += 1
                    
                    current_interval = interval_end
                    
        except (ValueError, IndexError) as e:
            logger.warning(f"Ошибка парсинга времени для студента {name}: {e}")
            continue
    
    # Вычисляем результат условия для каждого слота
    for time_slot, data in time_slots.items():
        topics_dict = data['distribution']
        p1_count = topics_dict.get("1", 0)
        p2_count = topics_dict.get("2", 0)
        p3_count = topics_dict.get("3", 0)
        p4_count = topics_dict.get("4", 0)
        
        data['condition_result'] = (p3_count < 5 and 
                                  p1_count + p2_count + p3_count + p4_count < 25)
    
    return time_slots

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
    
    logger.info(f"=== ДЕТАЛЬНАЯ ПРОВЕРКА ДОСТУПНОСТИ С generate_teacher_student_allocation ===")
    logger.info(f"Студент: {student.name}, предмет: {student.subject_id}, внимание: {student.need_for_attention}")
    
    while current_time <= end_time:
        # Получаем активных студентов и преподавателей на текущее время
        active_students = [
            s for s in all_students 
            if (s.start_of_studying_time <= current_time <= s.end_of_studying_time)
        ]
        
        active_teachers = [
            t for t in teachers 
            if t.start_of_studying_time <= current_time <= t.end_of_studying_time
        ]
        
        # Детальная проверка доступности
        can_allocate = False
        
        if not active_teachers:
            logger.info(f"Время {current_time}: нет активных преподавателей")
        else:
            # ОТЛАДОЧНАЯ ИНФОРМАЦИЯ о активных преподавателях
            logger.info(f"Время {current_time}: активных преподавателей - {len(active_teachers)}")
            for i, teacher in enumerate(active_teachers):
                logger.info(f"  Преподаватель {i+1}: {teacher.name}, предметы: {teacher.subjects_id}")
            
            # Проверяем, есть ли преподаватель для предмета нового студента
            subject_available = False
            matching_teachers = []
            
            for teacher in active_teachers:
                # ВАЖНО: преобразуем subject_id к тому же типу, что и у преподавателя
                teacher_subjects = [str(subj) for subj in teacher.subjects_id]
                if str(student.subject_id) in teacher_subjects:
                    subject_available = True
                    matching_teachers.append(teacher)
            
            if not subject_available:
                logger.info(f"Время {current_time}: нет преподавателя для предмета {student.subject_id}")
                logger.info(f"  Доступные предметы у преподавателей: {[t.subjects_id for t in active_teachers]}")
            else:
                logger.info(f"Время {current_time}: найдены преподаватели для предмета {student.subject_id}")
                logger.info(f"  Подходящие преподаватели: {[t.name for t in matching_teachers]}")
                
                # ИСПОЛЬЗУЕМ generate_teacher_student_allocation для проверки комбинации
                try:
                    # Добавляем нового студента к активным студентам
                    students_to_check = active_students + [student]
                    
                    logger.info(f"  Всего студентов для распределения: {len(students_to_check)}")
                    
                    # Проверяем возможность распределения
                    success, allocation = School.generate_teacher_student_allocation(
                        active_teachers, students_to_check
                    )
                    
                    if success:
                        can_allocate = True
                        logger.info(f"  КОМБИНАЦИЯ УСПЕШНА")
                    else:
                        logger.info(f"  КОМБИНАЦИЯ НЕВОЗМОЖНА")
                        
                except Exception as e:
                    logger.error(f"Ошибка при проверке комбинации: {e}")
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

        # Если availability_map = None (для преподавателей), все слоты доступны
        is_available = True
        if availability_map is not None:  # Только если есть карта доступности
            is_available = availability_map.get(time_obj, True)

        # Определяем стиль кнопки на основе доступности
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

        # Для учеников показываем заблокированные слоты
        if availability_map is not None and not is_available:
            button_text = "🔒 " + time_str
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
    if availability_map is not None:  # Статистика только для учеников
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
        # Для преподавателей всегда доступно подтверждение
        if availability_map is None:
            builder.row(
                types.InlineKeyboardButton(
                    text="✅ Подтвердить время",
                    callback_data="confirm_time_range"
                )
            )
        else:
            # Для учеников проверяем доступность всего интервала
            is_interval_available = True
            
            # Проверяем все временные слоты в выбранном интервале
            start_obj = datetime.strptime(start_time, "%H:%M").time()
            end_obj = datetime.strptime(end_time, "%H:%M").time()
            
            current_check = start_obj
            while current_check < end_obj:
                if current_check not in availability_map or not availability_map[current_check]:
                    is_interval_available = False
                    break
                # Переходим к следующему получасовому слоту
                current_check = School.add_minutes_to_time(current_check, 30)
            
            if is_interval_available:
                builder.row(
                    types.InlineKeyboardButton(
                        text="✅ Подтвердить время",
                        callback_data="confirm_time_range"
                    )
                )
            else:
                builder.row(
                    types.InlineKeyboardButton(
                        text="❌ Интервал содержит недоступные слоты",
                        callback_data="interval_contains_unavailable"
                    )
                )

    builder.row(
        types.InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_time_selection"
        )
    )

    return builder.as_markup()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "interval_contains_unavailable")
async def handle_interval_contains_unavailable(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает попытку подтверждения интервала с недоступными слотами"""
    data = await state.get_data()
    start_time = data.get('time_start')
    end_time = data.get('time_end')
    
    await callback.answer(
        f"❌ Выбранный интервал {start_time}-{end_time} содержит недоступные временные слоты\n"
        "Выберите другой интервал, который не содержит значков 🔒",
        show_alert=True
    )


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

    # ИСПРАВЛЕНИЕ: Всегда показываем кнопку "назад", если есть предыдущий месяц
    # независимо от того, есть ли в нем доступные даты
    nav_buttons = []

    # Всегда показываем кнопку "назад" для навигации
    nav_buttons.append(types.InlineKeyboardButton(
        text="⬅️",
        callback_data=f"calendar_change_{prev_year}-{prev_month}"
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


def generate_schedule_for_date(target_date: str) -> str:
    """
    Функция для составления расписания на указанную дату
    Использует функционал из Program.py
    """
    try:
        # Импортируем необходимые модули
        from shedule_app.GoogleParser import GoogleSheetsDataLoader
        from shedule_app.HelperMethods import School
        from shedule_app.ScheduleGenerator import ScheduleGenerator
        from shedule_app.models import Teacher, Student

        # Настройки
        current_dir = os.path.dirname(os.path.abspath(__file__))
        credentials_path = os.path.join(current_dir, "credentials.json")
        spreadsheet_id = SPREADSHEET_ID

        # Загружаем данные
        loader = GoogleSheetsDataLoader(credentials_path, spreadsheet_id, target_date)
        teachers, students = loader.load_data()

        if not teachers or not students:
            return "Нет данных преподавателей или студентов"

        # Проверяем возможность распределения
        can_allocate = School.check_teacher_student_allocation(teachers, students)

        if not can_allocate:
            return "Невозможно распределить студентов по преподавателям"

        # Генерируем распределение
        success, allocation = School.generate_teacher_student_allocation(teachers, students)

        if not success:
            return "Не удалось распределить всех студентов"

        # Получаем работающих преподавателей
        working_teachers = School.get_working_teachers(teachers, students)

        # Генерируем матрицу расписания
        schedule_matrix = ScheduleGenerator.generate_teacher_schedule_matrix(students, working_teachers)

        # Экспортируем в Google Sheets
        loader.export_schedule_to_google_sheets(schedule_matrix, [])

        # Формируем отчет
        total_students = len(students)
        working_teacher_count = len(working_teachers)
        total_teachers = len(teachers)

        return (f"Успешно! Студентов: {total_students}, "
                f"Работающих преподавателей: {working_teacher_count}/{total_teachers}")

    except Exception as e:
        logger.error(f"Ошибка в generate_schedule_for_date: {e}")
        return f"Ошибка: {str(e)}"

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
    """Генерирует главное меню в зависимости от ролей и прав"""
    roles = storage.get_user_roles(user_id)

    if not roles:
        return no_roles_menu

    keyboard_buttons = []

    # Проверяем, может ли пользователь бронировать
    can_book = any(role in roles for role in ['teacher', 'parent']) or (
            'student' in roles and 'parent' in roles
    )

    if can_book:
        keyboard_buttons.append([KeyboardButton(text="📅 Забронировать время")])

    keyboard_buttons.append([KeyboardButton(text="📋 Мои бронирования")])
    keyboard_buttons.append([KeyboardButton(text="👤 Моя роль")])

    # Добавляем кнопку составления расписания только для администраторов
    if is_admin(user_id):
        keyboard_buttons.append([KeyboardButton(text="📊 Составить расписание")])

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
        await message.answer("Ваши роли еще не назначены. Обратитесь к администратору. \n Телефон администратора: +79001372727")

@dp.message(F.text == "ℹ️ Помощь")
async def show_help(message: types.Message):
    await cmd_help(message)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "обратитесь к администратору\nТелефон администратора: +79001372727.\n\n"
        "/help - показать эту справку"
    )


@dp.message(F.text == "❓ Обратиться к администратору")
async def contact_admin(message: types.Message):
    await message.answer(
        "📞 Для получения доступа к системе бронирования\n"
        "обратитесь к администратору \n Телефон администратора: +79001372727.\n\n"
        "После назначения ролей вы сможете пользоваться всеми функциями бота."
    )


@dp.message(F.text == "📊 Составить расписание")
async def start_schedule_generation(message: types.Message, state: FSMContext):
    """Начало процесса составления расписания"""
    user_id = message.from_user.id

    # Проверяем права доступа через список ADMIN_IDS
    if not is_admin(user_id):
        await message.answer(
            "❌ У вас нет прав для составления расписания. Обратитесь к администратору. \n Телефон администратора: +79001372727",
            reply_markup=await generate_main_menu(user_id)
        )
        return

    await message.answer(
        "📅 Выберите дату для составления расписания:",
        reply_markup=generate_calendar()
    )
    await state.set_state(BookingStates.SELECT_SCHEDULE_DATE)


@dp.message(Command("admin"))
async def admin_command(message: types.Message):
    """Команда для администраторов"""
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("❌ Эта команда только для администраторов")
        return

    # Показываем доступные команды администратора
    admin_commands = [
        "📊 Составить расписание - через кнопку в меню",
        "/force_sync - принудительная синхронизация с Google Sheets",
        "/stats - статистика системы"
    ]

    await message.answer(
        "👨‍💻 Команды администратора:\n" + "\n".join(admin_commands)
    )


@dp.message(Command("force_sync"))
async def force_sync_command(message: types.Message):
    """Принудительная синхронизация с Google Sheets"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Эта команда только для администраторов")
        return

    await message.answer("⏳ Синхронизирую с Google Sheets...")

    try:
        if hasattr(storage, 'gsheets') and storage.gsheets:
            success = storage.gsheets.sync_from_gsheets_to_json(storage)
            if success:
                await message.answer("✅ Синхронизация завершена успешно!")
            else:
                await message.answer("❌ Ошибка синхронизации")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
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
            "⏳ Обратитесь к администратору для получения ролей \n Телефон администратора: +79001372727",
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
            "❌ У вас нет ролей для бронирования. Обратитесь к администратору. \n Телефон администратора: +79001372727",
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
                    "У вас нет назначенных предметов. Обратитесь к администратору. \n Телефон администратора: +79001372727",
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
                    "У вас нет привязанных детей. Обратитесь к администратору.\n Телефон администратора: +79001372727",
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
            "⏳ Обратитесь к администратору для получения ролей. \n Телефон администратора: +79001372727",
            reply_markup=await generate_main_menu(user_id)
        )
        await state.clear()


@dp.callback_query(BookingStates.SELECT_SCHEDULE_DATE, F.data.startswith("calendar_day_"))
async def process_schedule_date_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора даты для составления расписания"""
    try:
        data = callback.data
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()
        formatted_date = selected_date.strftime("%d.%m.%Y")

        await state.update_data(schedule_date=selected_date, formatted_date=formatted_date)

        # Создаем клавиатуру подтверждения
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ Да, составить", callback_data="confirm_schedule"),
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_schedule")
        )

        await callback.message.edit_text(
            f"📅 Вы выбрали дату: {formatted_date}\n"
            "Составить расписание на эту дату?",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.CONFIRM_SCHEDULE)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при выборе даты расписания: {e}")
        await callback.answer("Ошибка при выборе даты", show_alert=True)


@dp.callback_query(BookingStates.CONFIRM_SCHEDULE, F.data == "confirm_schedule")
async def process_schedule_confirmation(callback: types.CallbackQuery, state: FSMContext):
    """Запуск процесса составления расписания"""
    try:
        # Проверяем права еще раз на всякий случай
        if not is_admin(callback.from_user.id):
            await callback.answer("❌ Доступ запрещен", show_alert=True)
            await state.clear()
            return

        data = await state.get_data()
        selected_date = data.get('schedule_date')
        formatted_date = data.get('formatted_date')

        if not selected_date:
            await callback.answer("Ошибка: дата не выбрана", show_alert=True)
            return

        # Показываем сообщение о начале процесса
        await callback.message.edit_text(
            f"⏳ Составляю расписание на {formatted_date}...\n"
            "Это может занять несколько минут."
        )

        # Запускаем процесс составления расписания в отдельном потоке
        result = await asyncio.to_thread(
            generate_schedule_for_date,
            selected_date.strftime("%d.%m.%Y")
        )

        if "Успешно" in result:
            await callback.message.edit_text(
                f"✅ Расписание на {formatted_date} успешно составлено!\n"
                f"{result}\n\n"
                "Расписание экспортировано в Google Sheets."
            )
        else:
            await callback.message.edit_text(
                f"❌ Не удалось составить расписание на {formatted_date}\n"
                f"Ошибка: {result}"
            )

    except Exception as e:
        logger.error(f"Ошибка при составлении расписания: {e}")
        await callback.message.edit_text(
            f"❌ Произошла ошибка при составлении расписания:\n{str(e)}"
        )

    await state.clear()


@dp.callback_query(BookingStates.CONFIRM_SCHEDULE, F.data == "cancel_schedule")
async def cancel_schedule_generation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена составления расписания"""
    await callback.message.edit_text("❌ Составление расписания отменено")
    await state.clear()

    user_id = callback.from_user.id
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=await generate_main_menu(user_id)
    )
    await callback.answer()


@dp.callback_query(
    BookingStates.SELECT_SCHEDULE_DATE,
    F.data.startswith("calendar_change_")
)
async def process_schedule_calendar_change(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает переключение месяцев в календаре для выбора даты расписания"""
    try:
        date_str = callback.data.replace("calendar_change_", "")
        year, month = map(int, date_str.split("-"))

        await callback.message.edit_reply_markup(
            reply_markup=generate_calendar(year, month)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error changing calendar month for schedule: {e}")
        await callback.answer("Не удалось изменить месяц", show_alert=True)
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
                "У вас нет назначенных предметов. Обратитесь к администратору.\n Телефон администратора: +79001372727",
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
                "У вас нет привязанных детей. Обратитесь к администратору.\n Телефон администратора: +79001372727",
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

@dp.callback_query(
    BookingStates.SELECT_SCHEDULE_DATE,
    F.data.startswith("calendar_change_")
)
async def process_schedule_calendar_change(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает переключение месяцев в календаре для выбора даты расписания"""
    try:
        date_str = callback.data.replace("calendar_change_", "")
        year, month = map(int, date_str.split("-"))

        await callback.message.edit_reply_markup(
            reply_markup=generate_calendar(year, month)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error changing calendar month for schedule: {e}")
        await callback.answer("Не удалось изменить месяц", show_alert=True)
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
                loader = GoogleSheetsDataLoader(CREDENTIALS_PATH, SPREADSHEET_ID, formatted_date)
                topic = loader.get_student_topic_by_user_id(str(user_id), formatted_date)
                if not topic:
                    topic = str(subject)
                # Создаем временного студента для проверки
                temp_student = Student(
                    name="temp_check",
                    start_of_study_time="09:00",
                    end_of_study_time="20:00",
                    subject_id=topic,
                    need_for_attention=state_data.get('need_for_attention', 3)
                )
                
                # Получаем всех студентов и преподавателей из Google Sheets
                all_teachers, all_students = loader.load_data()
                distribution = get_subject_distribution_by_time(loader, formatted_date)
                
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
        
        # Добавляем проверку на None
        if availability_map is None:
            message = "Информация о доступности не загружена"
        else:
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
    if availability_map is not None:  # Только для учеников проверяем доступность
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

    if availability_map is not None:
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
    availability_map = data.get('availability_map')
    
    # Гарантируем, что booking_type = "Тип1"
    data['booking_type'] = "Тип1"
    await state.update_data(booking_type="Тип1")

    subject = data.get('subject') if data.get('user_role') == 'student' else None
    user_id = callback.from_user.id
    date_str = data['selected_date'].strftime("%Y-%m-%d")

    if availability_map is not None:
        start_time = data.get('time_start')
        end_time = data.get('time_end')
        
        if start_time and end_time:
            start_obj = datetime.strptime(start_time, "%H:%M").time()
            end_obj = datetime.strptime(end_time, "%H:%M").time()
            
            # Проверяем все слоты в интервале
            current_check = start_obj
            while current_check < end_obj:
                if current_check not in availability_map or not availability_map[current_check]:
                    await callback.answer(
                        "❌ Выбранный интервал содержит недоступные временные слоты!",
                        show_alert=True
                    )
                    return
                current_check = School.add_minutes_to_time(current_check, 30)
    
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
        role_text = ", ".join([
            "преподаватель" if role == "teacher" 
            else "родитель" if role == "parent" 
            else "ученик" 
            for role in roles
        ])
        await message.answer(f"Ваши роли: {role_text}")
    else:
        await message.answer("Ваши роли еще не назначены. Обратитесь к администратору.\n Телефон администратора: +79001372727")


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
            "У вас нет привязанных детей. Обратитесь к администратору.\n Телефон администратора: +79001372727",
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
            await asyncio.sleep(60)  # Каждый час
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
    # asyncio.create_task(sync_with_gsheets())
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