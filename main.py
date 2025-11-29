# main.py
import sys

sys.path.append(r"C:\Users\bestd\OneDrive\Документы\GitHub\TelegramSchedulingBot\shedule_app")
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.aiohttp import AiohttpSession
from payment_handlers import PaymentStates
import aiohttp
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from functools import wraps
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from dotenv import load_dotenv

import asyncio
import json
import os
import logging
from datetime import datetime, timedelta, date, time
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
import threading

# from gsheets_manager import GoogleSheetsManager
from excel_manager import ExcelManager

from storage import JSONStorage
from shedule_app.HelperMethods import School
from shedule_app.models import Person, Teacher, Student
from typing import List, Dict
from shedule_app.GoogleParser import GoogleSheetsDataLoader
from bookings_management.booking_management import BookingManager
from background_tasks import BackgroundTasks
from menu_handlers import register_menu_handlers
# Импорты из новых файлов
from config import *
from states import BookingStates
from feedback import FeedbackManager, FeedbackStates
from feedback_teachers import FeedbackTeacherManager, FeedbackTeacherStates
from config import FEEDBACK_CONFIG
from materials_manager import MaterialsManager
from database import db
from calendar_utils import generate_calendar,get_time_range_for_date
from time_utils import generate_time_range_keyboard_with_availability,calculate_lesson_duration
from datetime import datetime
from aiogram.fsm.state import State, StatesGroup
from states import BookingStates, FinanceStates
from teacher_reminder import TeacherReminderManager
from booking_history_manager import BookingHistoryManager
from menu_handlers import (
    generate_main_menu,
    cmd_start,
    show_my_role,
    cmd_help,
    contact_admin
)
from menu_handlers import register_menu_handlers
from finance_handlers import FinanceHandlers
from reminder_manager import StudentReminderManager
from payment_handlers import PaymentHandlers,PaymentStates
from aiogram.utils.keyboard import InlineKeyboardBuilder
# Настройка логирования


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
load_dotenv()

def handle_network_errors(max_retries=3):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Error after {max_retries} attempts in {func.__name__}: {e}")
                        # Не пробрасываем исключение, чтобы бот не падал
                        return None
                    wait_time = 2 ** attempt
                    logger.warning(f"Error (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
            return None
        return wrapper
    return decorator
# Инициализация бота
session = AiohttpSession(
    timeout=aiohttp.ClientTimeout(total=30)  # Универсальный таймаут
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
storage = JSONStorage(file_path=BOOKINGS_FILE)

# Настройка Google Sheets
# try:
#     gsheets = GoogleSheetsManager(
#         credentials_file='credentials.json',
#         spreadsheet_id=SPREADSHEET_ID
#     )
#     gsheets.connect()
#     storage.set_gsheets_manager(gsheets)
#     logger.info("Google Sheets integration initialized successfully")
# except Exception as e:
#     logger.error(f"Google Sheets initialization error: {e}")
#     gsheets = None

# Вместо Google Sheets используем Excel
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    excel_file_path = os.path.join(current_dir, "Ученики тест.xlsx")

    logger.info(f"🔍 Полный путь к файлу: {excel_file_path}")

    # Проверим существует ли файл
    if os.path.exists(excel_file_path):
        logger.info(f"✅ Файл найден! Размер: {os.path.getsize(excel_file_path)} байт")
    else:
        logger.error(f"❌ Файл не найден! Ищем в: {current_dir}")
        logger.error(f"📁 Файлы в папке: {[f for f in os.listdir(current_dir) if f.endswith('.xlsx')]}")
    gsheets = ExcelManager(excel_file_path=excel_file_path)
except Exception as e:
    logger.error(f"Excel initialization error: {e}")
    gsheets = None
    excel_manager = None

# После инициализации ExcelManager добавьте:
if gsheets:
    # Запускаем диагностику
    gsheets.debug_table_structure()

    # Ищем конкретного пользователя
    test_user_id = 1180878673  # ваш user_id
    gsheets.find_user_in_all_sheets(test_user_id)

    # Проверяем роли
    roles = gsheets.get_user_roles(test_user_id)
    logger.info(f"🎯 ФИНАЛЬНЫЙ ТЕСТ РОЛЕЙ: {roles}")

feedback_manager = FeedbackManager(storage, gsheets, bot)
feedback_teacher_manager = FeedbackTeacherManager(storage, gsheets, bot)
feedback_manager.good_feedback_delay = FEEDBACK_CONFIG["good_feedback_delay"]
feedback_teacher_manager.good_feedback_delay = FEEDBACK_CONFIG["good_feedback_delay"]
teacher_reminder_manager = TeacherReminderManager(storage, gsheets, bot)
student_reminder_manager = StudentReminderManager(storage, gsheets, bot)
materials_manager = MaterialsManager(gsheets, 'credentials.json', SPREADSHEET_ID)
# ДОБАВЬТЕ после инициализации других менеджеров:
try:
    from advanced_materials_manager import AdvancedMaterialsManager
    materials_manager = AdvancedMaterialsManager(gsheets, 'credentials.json', SPREADSHEET_ID)
    logger.info("Advanced materials manager initialized")
except Exception as e:
    logger.error(f"Failed to initialize advanced materials manager: {e}")
    materials_manager = None

    class DummyMaterialsManager:
        def create_combined_materials_document(self, target_date):
            return "Сервис генерации материалов временно недоступен"
    materials_manager = DummyMaterialsManager()
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
booking_manager = BookingManager(storage, gsheets)
background_tasks = BackgroundTasks(storage, gsheets, feedback_manager, feedback_teacher_manager, bot)
register_menu_handlers(dp, booking_manager, storage)
booking_history = BookingHistoryManager("booking_history.json")


def get_subject_distribution_by_time(loader, target_date: str, condition_check: bool = True) -> Dict[time, Dict]:
    """
    Получает распределение тем занятий по 15-минутным интервалам для указанной даты
    с учетом дня недели
    """
    from datetime import time,datetime
    from typing import Dict

    # Загружаем данные студентов
    student_sheet = loader._get_sheet_data("Ученики бот")
    if not student_sheet:
        logger.error("Лист 'Ученики' не найден")
        return _create_empty_time_slots()
    
    # Парсим дату для определения дня недели
    try:
        date_obj = datetime.strptime(target_date, "%d.%m.%Y").date()
    except ValueError:
        date_obj = datetime.now().date()
    
    # Находим колонки для указанной даты
    date_columns = loader._find_date_columns(student_sheet, target_date)
    if date_columns == (-1, -1):
        logger.error(f"Дата {target_date} не найдена в листе учеников")
        return _create_empty_time_slots(date_obj)
    
    start_col, end_col = date_columns

    # Загружаем план обучения
    loader._load_study_plan_cache()
    
    # Создаем временные интервалы в зависимости от дня недели
    time_slots = _create_empty_time_slots(date_obj)
    
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
                
                # Находим все 15-минутные интервалы, попадающие в занятие
                current_interval = min(time_slots.keys())  # Начинаем с первого доступного времени
                while current_interval <= max(time_slots.keys()):
                    # Вычисляем конец интервала (15 минут)
                    total_minutes = current_interval.hour * 60 + current_interval.minute + 15
                    interval_end_hour = total_minutes // 60
                    interval_end_minute = total_minutes % 60
                    interval_end = time(interval_end_hour, interval_end_minute)
                    
                    if (current_interval >= lesson_start and interval_end <= lesson_end):
                        # Этот интервал полностью внутри занятия
                        if topic not in time_slots[current_interval]['distribution']:
                            time_slots[current_interval]['distribution'][topic] = 0
                        time_slots[current_interval]['distribution'][topic] += 1
                    
                    # Переходим к следующему интервалу
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

dp.callback_query.register(
    PaymentHandlers.handle_teacher_payment_confirmation,
    F.data.startswith("teacher_confirm_")
)
dp.callback_query.register(
    PaymentHandlers.handle_teacher_payment_rejection,
    F.data.startswith("teacher_reject_")
)

def check_student_availability_for_slots(
    student: Student,
    all_students: List[Student],
    teachers: List[Teacher],
    target_date: date,
    start_time: time,
    end_time: time,
    interval_minutes: int = 15
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
                logger.info(f"  Преподаватель {i + 1}: {teacher.name}, предметы: {teacher.subjects_id}")

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
dp.callback_query.register(
    PaymentHandlers.handle_payment_confirmation,
    F.data == "confirm_direct_payment"
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


async def check_teacher_feedback_background():
    """Фоновая задача для проверки и отправки обратной связи преподавателям"""
    while True:
        try:
            await feedback_teacher_manager.send_feedback_questions()
            await asyncio.sleep(1800)  # Проверка каждые 30 минут
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче feedback преподавателей: {e}")
            await asyncio.sleep(300)

async def sync_pending_teacher_feedback_background():
    """Фоновая задача для синхронизации неотправленных отзывов преподавателей"""
    while True:
        try:
            pending_feedback = feedback_teacher_manager.get_pending_feedback_for_gsheets()

            if pending_feedback:
                logger.info(f"Найдено {len(pending_feedback)} несинхронизированных отзывов преподавателей")

                for feedback in pending_feedback:
                    try:
                        feedback_teacher_manager.sync_feedback_to_gsheets(feedback)
                        feedback_teacher_manager.mark_feedback_synced(
                            feedback['user_id'],
                            feedback['date']
                        )
                        logger.info(f"Синхронизирован отзыв преподавателя user_id {feedback['user_id']}")
                    except Exception as e:
                        logger.error(f"Ошибка синхронизации отзыва преподавателя: {e}")
                        continue

            await asyncio.sleep(300)  # Проверка каждые 5 минут

        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче синхронизации отзывов преподавателей: {e}")
            await asyncio.sleep(300)

# Добавьте обработчики callback'ов для преподавателей
@dp.callback_query(F.data.startswith("feedback_teacher_"))
async def handle_teacher_feedback_rating(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор оценки обратной связи преподавателя"""
    try:
        if callback.data == "feedback_teacher_submit_details":
            await handle_teacher_feedback_submit(callback, state)
            return

        data_parts = callback.data.split('_')
        if len(data_parts) < 4:
            logger.error(f"Неверный формат callback_data: {callback.data}")
            await callback.answer("Ошибка обработки запроса", show_alert=True)
            return

        rating_type = data_parts[2]  # good, better, bad
        date_str = '_'.join(data_parts[3:])

        user_id = callback.from_user.id

        await state.update_data(
            feedback_teacher_date=date_str,
            feedback_teacher_rating=rating_type
        )

        if rating_type == 'good':
            # Для "Хорошо" - сразу сохраняем и благодарим
            feedback_teacher_manager.save_feedback_response(
                user_id, date_str, 'good'
            )

            await callback.message.edit_text(
                "Спасибо за вашу обратную связь! 💫"
            )

        elif rating_type == 'better':
            # Для "Могло быть лучше" - запрашиваем детали
            await callback.message.edit_text(
                "Что можно улучшить в организации занятий?\n\n"
                "Напишите ваши предложения и нажмите кнопку ниже:"
            )

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="📨 Все написал, отправить",
                    callback_data="feedback_teacher_submit_details"
                )]
            ])

            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await state.set_state(FeedbackTeacherStates.WAITING_FEEDBACK_DETAILS)

        elif rating_type == 'bad':
            # Для "Ужасно" - предупреждаем и запрашиваем детали
            await callback.message.edit_text(
                "Сожалеем о негативном опыте! 😔\n"
                "Что случилось?\n\n"
                "Если ситуация требует немедленного решения, "
                "звоните по номеру: +79001372727\n\n"
                "Опишите проблему и нажмите кнопку отправки:"
            )

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="📨 Все написал, отправить",
                    callback_data="feedback_teacher_submit_details"
                )]
            ])

            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await state.set_state(FeedbackTeacherStates.WAITING_FEEDBACK_DETAILS)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка обработки feedback преподавателя: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@dp.callback_query(F.data == "feedback_teacher_submit_details")
async def handle_teacher_feedback_submit_button(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает нажатие кнопки отправки деталей обратной связи преподавателя"""
    await handle_teacher_feedback_submit(callback, state)

async def handle_teacher_feedback_submit(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает отправку деталей обратной связи преподавателя"""
    try:
        data = await state.get_data()
        user_id = callback.from_user.id

        # Получаем текст из состояния
        details = data.get('feedback_teacher_details', '')

        if not details:
            # Если текста нет в состоянии, пытаемся получить из сообщения
            message_text = callback.message.text
            system_texts = [
                "Что можно улучшить в организации занятий?",
                "Сожалеем о негативном опыте!",
                "Что случилось?",
                "Если ситуация требует немедленного решения"
            ]

            details = message_text
            for system_text in system_texts:
                details = details.replace(system_text, "").strip()

            details = details.replace("*Ваш ответ:*", "").strip()

        # Проверяем, что у нас есть все необходимые данные
        if not all(key in data for key in ['feedback_teacher_date', 'feedback_teacher_rating']):
            await callback.answer("Ошибка: недостаточно данных для сохранения", show_alert=True)
            return

        # Сохраняем обратную связь
        feedback_teacher_manager.save_feedback_response(
            user_id,
            data['feedback_teacher_date'],
            data['feedback_teacher_rating'],
            details
        )

        await callback.message.edit_text(
            "Спасибо за вашу обратную связь! 💫\n"
            "Ваш отзыв важен для совершенствования нашей работы!"
        )

        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отправки feedback преподавателя: {e}")
        await callback.answer("Ошибка отправки", show_alert=True)

@dp.message(FeedbackTeacherStates.WAITING_FEEDBACK_DETAILS)
async def handle_teacher_feedback_text_input(message: types.Message, state: FSMContext):
    """Обрабатывает текстовый ввод для обратной связи преподавателя"""
    try:
        data = await state.get_data()
        rating_type = data.get('feedback_teacher_rating', 'better')

        # Сохраняем текст от пользователя в состоянии
        await state.update_data(feedback_teacher_details=message.text)

        if rating_type == 'better':
            base_text = "Что можно улучшить в организации занятий?\n\n"
        else:  # bad
            base_text = "Сожалеем о негативном опыте! 😔\nЧто случилось?\n\n"
            base_text += "Если ситуация требует немедленного решения, звоните: +79001372727\n\n"

        new_text = base_text + f"*Ваш ответ:* {message.text}"

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="📨 Все написал, отправить",
                callback_data="feedback_teacher_submit_details"
            )]
        ])

        await message.answer(
            new_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка обработки текста feedback преподавателя: {e}")
        await message.answer("Произошла ошибка, попробуйте еще раз")

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

    # Получаем выбранную дату для правильного определения временного диапазона
    selected_date = data.get('selected_date')

    await callback.message.edit_text(
        f"Текущее начало: {data['time_start']}\n"
        "Выберите время окончания (красный маркер):",
        reply_markup=generate_time_range_keyboard_with_availability(
            selected_date=selected_date,  # Передаем дату для правильного диапазона
            start_time=data['time_start'],
            end_time=data.get('time_end'),
            availability_map=data.get('availability_map')
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


def generate_subjects_keyboard(selected_subjects=None, is_teacher=False, available_subjects=None):
    """Генерирует клавиатуру выбора предметов"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    selected_subjects = selected_subjects or []

    # Если указаны доступные предметы, показываем только их
    subjects_to_show = SUBJECTS
    if available_subjects is not None:
        subjects_to_show = {k: v for k, v in SUBJECTS.items() if k in available_subjects}

    for subject_id, subject_name in subjects_to_show.items():
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
        [KeyboardButton(text="👤 Моя роль")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ],
    resize_keyboard=True
)

# Меню с дополнительными опциями (в развертываемом меню)
additional_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Обратиться к администратору")],
        [KeyboardButton(text="👤 Моя роль")],
    ],
    resize_keyboard=True
)


@dp.message(F.text == "ℹ️ Помощь")
async def show_help(message: types.Message,state:FSMContext):
    await cmd_start(message, state, storage)



@dp.message(F.text == "📊 Составить расписание")
async def start_schedule_generation(message: types.Message, state: FSMContext):
    """Начало процесса составления расписания"""
    user_id = message.from_user.id

    # Проверяем права доступа через список ADMIN_IDS
    if not is_admin(user_id):
        await message.answer(
            "❌ У вас нет прав для составления расписания. Обратитесь к администратору. \n Телефон администратора: +79001372727",
            reply_markup=await generate_main_menu(user_id,storage)
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
            reply_markup=await generate_main_menu(user_id,storage)
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
            reply_markup=await generate_main_menu(user_id,storage)
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
                    reply_markup=await generate_main_menu(user_id,storage)
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
                    reply_markup=await generate_main_menu(user_id,storage)
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

def load_past_bookings():
    """Загружает прошедшие бронирования"""
    try:
        data = storage.load_all_bookings()  # Нужно создать эту функцию в storage.py
        past_bookings = []
        current_time = datetime.now()

        for booking in data:
            if 'date' not in booking or 'end_time' not in booking:
                continue

            try:
                if isinstance(booking['date'], str):
                    booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                else:
                    continue

                time_end = datetime.strptime(booking.get('end_time', "00:00"), "%H:%M").time()
                booking_datetime = datetime.combine(booking_date, time_end)

                # Добавляем только прошедшие бронирования
                if booking_datetime < current_time:
                    booking['date'] = booking_date
                    past_bookings.append(booking)

            except ValueError:
                continue

        return past_bookings
    except Exception as e:
        logger.error(f"Ошибка загрузки прошедших бронирований: {e}")
        return []


@dp.message(F.text == "📚 Прошедшие бронирования")
async def show_past_bookings(message: types.Message):
    """Показывает прошедшие бронирования"""
    keyboard = booking_manager.generate_past_bookings_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет прошедших бронирований")
        return

    await message.answer("📚 Ваши прошедшие бронирования:", 
                        reply_markup=keyboard.as_markup())  # Add .as_markup() here


@dp.callback_query(F.data.startswith("past_booking_info_"))
async def show_past_booking_info(callback: types.CallbackQuery):
    try:
        booking_id_str = callback.data.replace("past_booking_info_", "")
        if not booking_id_str:
            await callback.answer("❌ Не удалось определить ID бронирования", show_alert=True)
            return

        booking_id = int(booking_id_str)
        booking = booking_manager.find_past_booking_by_id(booking_id)

        if not booking:
            await callback.answer("Бронирование не найдено или еще не прошло", show_alert=True)
            return

        message_text = booking_manager.get_past_booking_info_text(booking)

        # Импортируем клавиатуру из отдельного файла
        from bookings_management.booking_keyboards import generate_past_booking_info
        await callback.message.edit_text(
            message_text,
            reply_markup=generate_past_booking_info(booking_id)
        )
        await callback.answer()

    except ValueError:
        await callback.answer("❌ Неверный формат ID бронирования", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка в show_past_booking_info: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@dp.callback_query(F.data == "back_to_past_bookings")
async def back_to_past_bookings(callback: types.CallbackQuery):
    """Возврат к списку прошедших бронирований"""
    user_id = callback.from_user.id
    keyboard = booking_manager.generate_past_bookings_list(user_id)
    
    if keyboard:
        await callback.message.edit_text(
            "📚 Ваши прошедшие бронирования:",
            reply_markup=keyboard
        )
    else:
        await callback.message.edit_text("У вас нет прошедших бронирований")
        await callback.answer()


@dp.callback_query(F.data == "back_to_menu_from_past")
async def back_to_menu_from_past(callback: types.CallbackQuery):
    """Возврат в меню из раздела прошедших бронирований"""
    user_id = callback.from_user.id
    menu = await generate_main_menu(user_id,storage)

    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=None
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=menu
    )
    await callback.answer()


@dp.message(PaymentStates.WAITING_RECEIPT, F.content_type.in_({'photo', 'document'}))
async def handle_payment_receipt(message: types.Message, state: FSMContext):
    """Обрабатывает загрузку чека для прямого перевода"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_receipt_upload(message, state)

@dp.message(PaymentStates.WAITING_RECEIPT)
async def handle_waiting_receipt_text(message: types.Message):
    """Обрабатывает текстовые сообщения в состоянии ожидания чека"""
    await message.answer(
        "📎 Пожалуйста, отправьте скриншот или фото чека перевода.\n\n"
        "📸 Как сделать скриншот:\n"
        "• В приложении банка найдите операцию перевода\n"
        "• Сделайте скриншот экрана с информацией о переводе\n"
        "• Отправьте его в этот чат"
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
            "⏳ Обратитесь к администратору для получения ролей. \n Телефон администратора: +79001372727",
            reply_markup=await generate_main_menu(user_id,storage)
        )
        await state.clear()


# Обработчик команды генерации материалов
@dp.message(F.text == "📚 Сгенерировать материалы")
async def generate_materials_command(message: types.Message, state: FSMContext):
    """Команда для генерации материалов"""
    try:
        user_id = message.from_user.id

        if not is_admin(user_id):
            await message.answer("❌ Эта команда только для администраторов")
            return

        await message.answer(
            "📅 Выберите дату для генерации материалов:",
            reply_markup=generate_calendar()
        )
        await state.set_state(BookingStates.SELECT_MATERIALS_DATE)
    except Exception as e:
        logger.error(f"Error in generate_materials_command: {e}")
        await message.answer("❌ Произошла ошибка")
#@dp.callback_query(BookingStates.SELECT_MATERIALS_DATE, F.data.startswith("calendar_day_"))
@dp.callback_query(BookingStates.SELECT_MATERIALS_DATE, F.data.startswith("calendar_day_"))
async def process_materials_date_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора даты для генерации материалов"""
    try:
        data = callback.data
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()
        formatted_date = selected_date.strftime("%d.%m.%Y")

        await state.update_data(materials_date=formatted_date)

        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ Сгенерировать", callback_data="generate_materials"),
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_materials")
        )

        await callback.message.edit_text(
            f"📅 Дата для генерации материалов: {formatted_date}\n"
            "Сгенерировать объединенный документ с материалами?",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.CONFIRM_MATERIALS_GENERATION)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при выборе даты материалов: {e}")
        await callback.answer("Ошибка при выборе даты", show_alert=True)


@dp.callback_query(BookingStates.CONFIRM_MATERIALS_GENERATION, F.data == "generate_materials")
async def process_materials_generation(callback: types.CallbackQuery, state: FSMContext):
    """Запуск процесса объединения документов"""
    try:
        data = await state.get_data()
        target_date = data.get('materials_date')

        if not target_date:
            await callback.answer("Ошибка: дата не выбрана", show_alert=True)
            return

        if not materials_manager:
            await callback.message.edit_text("❌ Сервис объединения документов недоступен")
            return

        await callback.message.edit_text(
            "⏳ Начинаю объединение документов...\n"
            "📚 Ищу занятия студентов на указанную дату\n"
            "🔗 Загружаю материалы по квалификациям\n"
            "📄 Объединяю документы...\n\n"
            "Это может занять несколько минут."
        )

        # Запускаем объединение - используем await для асинхронного метода
        result = await materials_manager.create_combined_materials_document(target_date)

        await callback.message.edit_text(result)

    except Exception as e:
        logger.error(f"Ошибка при объединении документов: {e}")
        await callback.message.edit_text(
            f"❌ Произошла ошибка при объединении документов:\n{str(e)}"
        )

    await state.clear()
@dp.callback_query(BookingStates.CONFIRM_MATERIALS_GENERATION, F.data == "cancel_materials")
async def cancel_materials_generation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена генерации материалов"""
    try:
        await callback.message.edit_text("❌ Генерация материалов отменена")
        await state.clear()

        user_id = callback.from_user.id
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=await generate_main_menu(user_id)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in cancel_materials_generation: {e}")
 
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


@dp.callback_query(F.data.startswith("feedback_"))
async def handle_feedback_rating(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор оценки обратной связи"""
    try:
        # Обрабатываем отдельно кнопку отправки деталей
        if callback.data == "feedback_submit_details":
            await handle_feedback_submit(callback, state)
            return

        data_parts = callback.data.split('_')
        if len(data_parts) < 4:
            logger.error(f"Неверный формат callback_data: {callback.data}")
            await callback.answer("Ошибка обработки запроса", show_alert=True)
            return

        rating_type = data_parts[1]  # good, better, bad
        subject_id = data_parts[2]
        date_str = '_'.join(data_parts[3:])  # Дата может содержать дефисы, поэтому объединяем остальные части

        user_id = callback.from_user.id

        # Получаем название предмета
        from config import SUBJECTS
        subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

        await state.update_data(
            feedback_subject=subject_id,
            feedback_date=date_str,
            feedback_rating=rating_type
        )

        if rating_type == 'good':
            # Для "Хорошо" - сразу сохраняем и благодарим
            feedback_manager.save_feedback_response(
                user_id, date_str, subject_id, 'good'
            )

            await callback.message.edit_text(
                "Спасибо за обратную связь! 💫"
            )

        elif rating_type == 'better':
            # Для "Могло быть лучше" - запрашиваем детали
            await callback.message.edit_text(
                "Чего не хватило для идеального занятия?\n\n"
                "Напишите ваши предложения и нажмите кнопку ниже:"
            )

            # Создаем клавиатуру с кнопкой отправки
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="📨 Все написал, отправить",
                    callback_data="feedback_submit_details"
                )]
            ])

            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await state.set_state(FeedbackStates.WAITING_FEEDBACK_DETAILS)

        elif rating_type == 'bad':
            # Для "Ужасно" - предупреждаем и запрашиваем детали
            await callback.message.edit_text(
                "Сожалеем о негативном опыте! 😔\n"
                "Что случилось?\n\n"
                "Если ситуация требует немедленного решения, "
                "звоните по номеру: +79001372727\n\n"
                "Опишите проблему и нажмите кнопку отправки:"
            )

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="📨 Все написал, отправить",
                    callback_data="feedback_submit_details"
                )]
            ])

            await callback.message.edit_reply_markup(reply_markup=keyboard)
            await state.set_state(FeedbackStates.WAITING_FEEDBACK_DETAILS)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка обработки feedback: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
@dp.callback_query(F.data == "feedback_submit_details")
async def handle_feedback_submit_button(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает нажатие кнопки отправки деталей обратной связи"""
    await handle_feedback_submit(callback, state)
async def handle_feedback_submit(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает отправку деталей обратной связи"""
    try:
        data = await state.get_data()
        user_id = callback.from_user.id

        # Получаем текст из состояния
        details = data.get('feedback_details', '')

        if not details:
            # Если текста нет в состоянии, пытаемся получить из сообщения
            message_text = callback.message.text
            system_texts = [
                "Чего не хватило для идеального занятия?",
                "Сожалеем о негативном опыте!",
                "Что случилось?",
                "Если ситуация требует немедленного решения"
            ]

            details = message_text
            for system_text in system_texts:
                details = details.replace(system_text, "").strip()

            # Убираем маркдаун разметку если есть
            details = details.replace("*Ваш ответ:*", "").strip()

        # Проверяем, что у нас есть все необходимые данные
        if not all(key in data for key in ['feedback_date', 'feedback_subject', 'feedback_rating']):
            await callback.answer("Ошибка: недостаточно данных для сохранения", show_alert=True)
            return

        # Сохраняем обратную связь
        feedback_manager.save_feedback_response(
            user_id,
            data['feedback_date'],
            data['feedback_subject'],
            data['feedback_rating'],
            details
        )

        await callback.message.edit_text(
            "Спасибо за обратную связь! 💫\n"
            "Ваше мнение очень важно для нас!"
        )

        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка отправки feedback: {e}")
        await callback.answer("Ошибка отправки", show_alert=True)


@dp.message(FeedbackStates.WAITING_FEEDBACK_DETAILS)
async def handle_feedback_text_input(message: types.Message, state: FSMContext):
    """Обрабатывает текстовый ввод для обратной связи"""
    try:
        data = await state.get_data()
        rating_type = data.get('feedback_rating', 'better')

        # Сохраняем текст от пользователя в состоянии
        await state.update_data(feedback_details=message.text)

        if rating_type == 'better':
            base_text = "Чего не хватило для идеального занятия?\n\n"
        else:  # bad
            base_text = "Сожалеем о негативном опыте! 😔\nЧто случилось?\n\n"
            base_text += "Если ситуация требует немедленного решения, звоните: +79001372727\n\n"

        new_text = base_text + f"*Ваш ответ:* {message.text}"

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="📨 Все написал, отправить",
                callback_data="feedback_submit_details"
            )]
        ])

        await message.answer(
            new_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка обработки текста feedback: {e}")
        await message.answer("Произошла ошибка, попробуйте еще раз")
@dp.callback_query(BookingStates.CONFIRM_SCHEDULE, F.data == "cancel_schedule")
async def cancel_schedule_generation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена составления расписания"""
    await callback.message.edit_text("❌ Составление расписания отменено")
    await state.clear()

    user_id = callback.from_user.id
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=await generate_main_menu(user_id,storage)
    )
    await callback.answer()


@dp.callback_query(BookingStates.CONFIRMATION, F.data == "booking_cancel")
async def process_cancellation(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает отмену бронирования"""
    await callback.message.edit_text("❌ Бронирование отменено")
    await state.clear()

    user_id = callback.from_user.id
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=await generate_main_menu(user_id,storage)
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
        available_subjects = storage.get_available_subjects_for_student(user_id)

        if not available_subjects:
            await callback.answer(
                "У вас нет доступных предметов. Обратитесь к администратору.\n Телефон администратора: +79001372727",
                show_alert=True
            )
            return

        await callback.message.edit_text(
            "Вы выбрали роль ученика\n"
            "Выберите предмет для занятия:",
            reply_markup=generate_subjects_keyboard(available_subjects=available_subjects)
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
    
# Обработчик для оплаты через ЮKassa
@dp.callback_query(F.data == "confirm_yookassa_payment")
async def handle_yookassa_payment(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает подтверждение оплаты через ЮKassa"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_yookassa_payment(callback, state)

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
        child_id = state_data.get('child_id')

        suggested_start_time = None
        suggested_end_time = None

        if role == 'student':
            # Для ученика или ребенка родителя
            target_user_id = child_id if child_id else user_id
            is_child = bool(child_id)
            
            suggested_time = booking_history.get_suggested_time(
                target_user_id, subject, selected_date, is_child
            )
            suggested_start_time = suggested_time.get("start_time")
            suggested_end_time = suggested_time.get("end_time")

        # Для учеников: проверяем доступность временных слотов
        availability_map = None
        if role == 'student' and subject:
            try:
                loader = GoogleSheetsDataLoader(CREDENTIALS_PATH, SPREADSHEET_ID, formatted_date)
                topic = loader.get_student_topic_by_user_id(str(user_id), formatted_date, str(subject))
            
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
                
                # Получаем временной диапазон для выбранной даты
                start_time_range, end_time_range, time_step = get_time_range_for_date(selected_date)
                
                # Логируем загруженные данные
                logger.info(f"Используется: {len(all_teachers)} преподавателей, {len(all_students)} студентов")
                logger.info(f"Временной диапазон: {start_time_range}-{end_time_range} (шаг: {time_step} мин)")
                
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
                    start_time=start_time_range,
                    end_time=end_time_range,
                    interval_minutes=time_step
                )

            except Exception as e:
                logger.error(f"Ошибка при проверке доступности: {e}")
                await callback.answer(
                    "❌ Ошибка при проверке доступности времени",
                    show_alert=True
                )
                return

        # Сбрасываем состояние выбора времени
        await state.update_data(
            selected_date=selected_date,
            time_start=None,
            time_end=None,
            availability_map=availability_map,
            click_count=0,  # Сбрасываем счетчик нажатий
            suggested_start_time=suggested_start_time,
            suggested_end_time=suggested_end_time
        )

        # Формируем текст сообщения с информацией о дне недели
        weekday_names = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
        weekday_name = weekday_names[selected_date.weekday()]
        start_time_range, end_time_range, time_step = get_time_range_for_date(selected_date)
        
        message_text = f"📅 Выбрана дата: {day}.{month}.{year} ({weekday_name})\n"
        message_text += f"⏰ Доступное время: {start_time_range.strftime('%H:%M')}-{end_time_range.strftime('%H:%M')}\n"
        message_text += f"📊 Шаг времени: {time_step} минут\n"

        if suggested_start_time and suggested_end_time:
            message_text += f"⭐ Предложенное время: {suggested_start_time}-{suggested_end_time}\n"
        
        if role == 'student' and availability_map:
            available_count = sum(1 for available in availability_map.values() if available)
            total_count = len(availability_map)
            message_text += f"✅ Доступно слотов: {available_count}/{total_count}\n"
            message_text += "🔒 - время недоступно для бронирования\n\n"

        message_text += "Как выбрать время:\n"
        message_text += "1. Нажмите на время начала (первое нажатие)\n"
        message_text += "2. Нажмите на время окончания (второе нажатие)\n"
        message_text += "3. Подтвердите выбор\n\n"
        message_text += "🟢 - начало, 🔴 - конец, 🔵 - промежуток"

        await callback.message.edit_text(
            message_text,
            reply_markup=generate_time_range_keyboard_with_availability(
                selected_date=selected_date,
                availability_map=availability_map,
                suggested_start_time=suggested_start_time,
                suggested_end_time=suggested_end_time
            )
        )
        await state.set_state(BookingStates.SELECT_TIME_RANGE)
        await callback.answer()

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data.startswith("use_suggested_time_"))
async def use_suggested_time(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает использование предложенного времени"""
    try:
        data_parts = callback.data.split('_')
        if len(data_parts) >= 6:
            start_time = data_parts[3]
            end_time = data_parts[4] + '_' + data_parts[5] if len(data_parts) > 5 else data_parts[4]
            
            # Корректируем время окончания если нужно
            state_data = await state.get_data()
            selected_date = state_data.get('selected_date')
            
            end_time = booking_history.adjust_time_to_working_hours(end_time, selected_date, is_start=False)
            
            await state.update_data(
                time_start=start_time,
                time_end=end_time,
                click_count=2  # Устанавливаем что оба времени выбраны
            )
            
            # Переходим к подтверждению
            await confirm_time_range(callback, state)
            
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка использования предложенного времени: {e}")
        await callback.answer("Ошибка использования предложенного времени", show_alert=True)

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data == "time_slot_unavailable")
async def handle_unavailable_slot(callback: types.CallbackQuery):
    """Обрабатывает нажатие на недоступный временной слот"""
    await callback.answer(
        "❌ Это время недоступно для бронирования\n"
        "Выберите другое время из доступных (без 🔒)",
        show_alert=True
    )

def get_student_class(user_id: int) -> int:
    """Получает класс ученика из Google Sheets"""
    try:
        if not gsheets:
            return 9  # По умолчанию старшие классы
        
        worksheet = gsheets._get_or_create_worksheet("Ученики бот")
        data = worksheet.get_all_values()
        
        # Пропускаем заголовок
        for row in data[1:]:
            if row and len(row) > 0 and str(row[0]).strip() == str(user_id):
                # Класс находится в столбце K (индекс 10)
                if len(row) > 10 and row[10].strip():
                    try:
                        class_num = int(row[10].strip())
                        return class_num
                    except ValueError:
                        pass
        return 9  # По умолчанию старшие классы
    except Exception as e:
        logger.error(f"Ошибка получения класса ученика {user_id}: {e}")
        return 9
    


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
        reply_markup=await generate_main_menu(user_id,storage)
    )
    await callback.answer()


@dp.callback_query(F.data == "direct_transfer")
async def handle_direct_transfer_direct(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает прямой перевод (временный обработчик)"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_direct_transfer(callback, state)

@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data.startswith("time_point_"))
async def process_time_point(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.replace("time_point_", "")
    data = await state.get_data()
    availability_map = data.get('availability_map')
    selected_date = data.get('selected_date')
    
    # Получаем текущее состояние выбора
    time_start = data.get('time_start')
    time_end = data.get('time_end')
    click_count = data.get('click_count', 0)
    user_role = data.get('user_role')
    
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

    # Определяем, что выбираем: начало или конец
    if click_count % 2 == 0:  # Нечетное нажатие - выбор начала
        # Устанавливаем время начала
        await state.update_data(time_start=time_str)
        new_click_count = click_count + 1
        
        # АВТОМАТИЧЕСКИ ВЫСТАВЛЯЕМ ВРЕМЯ ОКОНЧАНИЯ ДЛЯ УЧЕНИКОВ
        if user_role == 'student':
            user_id = callback.from_user.id
            student_class = get_student_class(user_id)
            duration_minutes = calculate_lesson_duration(student_class)
            
            # Рассчитываем время окончания
            start_time = datetime.strptime(time_str, "%H:%M")
            end_time = start_time + timedelta(minutes=duration_minutes)
            auto_end_time = end_time.strftime("%H:%M")
            
            # Проверяем, что автоматическое время окончания не выходит за границы рабочего дня
            start_time_range, end_time_range, _ = get_time_range_for_date(selected_date)
            end_time_obj = end_time.time()
            
            if end_time_obj > end_time_range:
                # Если выходит за границы, ставим максимальное время
                auto_end_time = end_time_range.strftime("%H:%M")
            
            await state.update_data(time_end=auto_end_time)
            
            # Показываем сообщение с автоматически установленным временем
            await callback.message.edit_text(
                f"🟢 Выбрано начало: {time_str}\n"
                f"🔴 Автоматически установлен конец: {auto_end_time}\n"
                f"📚 Класс: {student_class} ({duration_minutes} минут)\n\n"
                "Если время окончания устраивает, нажмите '✅ Подтвердить время'\n"
                "Или выберите другое время окончания вручную",
                reply_markup=generate_time_range_keyboard_with_availability(
                    selected_date=selected_date,
                    start_time=time_str,
                    end_time=auto_end_time,
                    availability_map=availability_map
                )
            )
        else:
            # Для преподавателей просто показываем выбор начала
            await callback.message.edit_text(
                f"🟢 Выбрано начало: {time_str}\n"
                "Теперь выберите время окончания\n"
                "Выбирайте только доступные времена (без 🔒)",
                reply_markup=generate_time_range_keyboard_with_availability(
                    selected_date=selected_date,
                    start_time=time_str,
                    end_time=None,
                    availability_map=availability_map
                )
            )
        
    else:  # Четное нажатие - выбор конца (ручная корректировка)
        if not time_start:
            await callback.answer("Сначала выберите время начала!", show_alert=True)
            return

        start_obj = datetime.strptime(time_start, "%H:%M")
        end_obj = datetime.strptime(time_str, "%H:%M")

        if end_obj <= start_obj:
            await callback.answer("Время окончания должно быть после времени начала!", show_alert=True)
            return

        await state.update_data(time_end=time_str)
        new_click_count = click_count + 1

        # Показываем информацию о классе для учеников
        info_text = ""
        if user_role == 'student':
            user_id = callback.from_user.id
            student_class = get_student_class(user_id)
            duration_minutes = calculate_lesson_duration(student_class)
            info_text = f"📚 Класс: {student_class} (рекомендуется {duration_minutes} минут)\n\n"

        await callback.message.edit_text(
            f"📋 Текущий выбор:\n"
            f"🟢 Начало: {time_start}\n"
            f"🔴 Конец: {time_str}\n"
            f"{info_text}"
            "Если выбор корректен, нажмите '✅ Подтвердить время'\n"
            "Или выберите другое время для изменения начала/конца",
            reply_markup=generate_time_range_keyboard_with_availability(
                selected_date=selected_date,
                start_time=time_start,
                end_time=time_str,
                availability_map=availability_map
            )
        )
    
    await state.update_data(click_count=new_click_count)
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_TIME_RANGE, F.data.in_(["select_start_mode", "select_end_mode"]))
async def switch_selection_mode(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    availability_map = data.get('availability_map')
    selected_date = data.get('selected_date')  # Получаем дату

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
            selected_date=selected_date,  # Передаем дату
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

    # Показываем информацию о классе для учеников
    class_info = ""
    if data.get('user_role') == 'student':
        student_class = get_student_class(user_id)
        duration_minutes = calculate_lesson_duration(student_class)
        class_info = f"📚 Класс: {student_class} (длительность: {duration_minutes} минут)\n"

    # ... остальная логика проверки доступности и конфликтов ...

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
        f"{class_info}"
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
    subject_id = data.get('subject', '')

    if subject_id and data.get('time_start') and data.get('time_end'):
        booking_history.save_booking_time(
            user_id=target_user_id,
            subject_id=subject_id,
            start_time=data['time_start'],
            end_time=data['time_end'],
            is_child=is_parent,
            date=data['selected_date'].strftime("%Y-%m-%d")
        )

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
    keyboard = booking_manager.generate_booking_list(message.from_user.id)
    if not keyboard:
        await message.answer("У вас нет активных бронирований")
        return

    await message.answer("Ваши бронирования (отсортированы по дате и времени):", 
                        reply_markup=keyboard.as_markup())  # Add .as_markup() here


@dp.message(F.text == "❌ Отменить бронь")
async def start_cancel_booking(message: types.Message):
    keyboard = booking_manager.generate_booking_list(message.from_user.id)
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
        booking = booking_manager.find_booking_by_id(booking_id)

        if not booking:
            await callback.answer("Бронирование не найдено", show_alert=True)
            return

        message_text = booking_manager.get_booking_info_text(booking)
        
        # Импортируем клавиатуру из отдельного файла
        from bookings_management.booking_keyboards import generate_booking_actions
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
    if booking_manager.cancel_booking_by_id(booking_id):
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

    available_subjects = storage.get_available_subjects_for_student(child_id)

    if not available_subjects:
        await callback.answer(
            "У ребенка нет доступных предметов. Обратитесь к администратору.\n Телефон администратора: +79001372727",
            show_alert=True
        )
        return

    await state.update_data(
        child_id=child_id,
        child_name=child_info.get('user_name', ''),
        user_role='student'  # Для бронирования используем роль ученика
    )

    await callback.message.edit_text(
        f"Выбран ребенок: {child_info.get('user_name', '')}\n"
        "Выберите предмет для занятия:",
        reply_markup=generate_subjects_keyboard(available_subjects=available_subjects)
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
        reply_markup=await generate_main_menu(user_id,storage)
    )
    await callback.answer()


@dp.callback_query(F.data.in_(["back_to_menu", "back_to_bookings"]))
async def back_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    menu = await generate_main_menu(user_id,storage)

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
        keyboard = booking_manager.generate_booking_list(user_id)
        await callback.message.edit_text(
            "Ваши бронирования:",
            reply_markup=keyboard
        )
    await callback.answer()

# Инициализация обработчиков финансов
finance_handlers = FinanceHandlers(
    storage=storage,
    gsheets=gsheets,
    subjects_config=SUBJECTS,
    generate_subjects_keyboard_func=generate_subjects_keyboard
)
finance_handlers.register_handlers(dp)

# Команда для тестирования оплаты
@dp.message(F.text == "💳 Тест оплаты")
@dp.message(Command("pay"))
async def cmd_pay(message: types.Message, state: FSMContext):
    await PaymentHandlers.handle_payment_start(message, state)

# Обработчики callback'ов для платежей
@dp.callback_query(F.data == 'pay_1')
async def create_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Начать новый платеж' - ПЕРЕЗАПУСКАЕМ ПРОЦЕСС"""
    try:
        # Очищаем состояние и начинаем с начала
        await state.clear()
        await PaymentHandlers.handle_payment_start(callback, state)
    except Exception as e:
        logger.error(f"Ошибка в create_payment_handler: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

@dp.callback_query(F.data.startswith('check_'))
async def check_payment_handler(callback: types.CallbackQuery):
    await PaymentHandlers.handle_check_payment(callback)

@dp.message(PaymentStates.WAITING_AMOUNT)
async def handle_payment_amount(message: types.Message, state: FSMContext):
    """Обрабатывает ввод суммы для пополнения баланса"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_amount_input(message, state)

@dp.callback_query(F.data == 'confirm_payment')
async def confirm_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    await PaymentHandlers.handle_confirm_payment(callback, state)

@dp.callback_query(F.data == 'cancel_payment')
async def cancel_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    await PaymentHandlers.handle_cancel_payment(callback, state)

@dp.callback_query(F.data == 'new_payment')
async def new_payment_handler(callback: types.CallbackQuery, state: FSMContext):
    await PaymentHandlers.handle_new_payment(callback, state)

@dp.callback_query(F.data.startswith('check_'))
async def check_payment_handler(callback: types.CallbackQuery):
    await PaymentHandlers.handle_check_payment(callback)

@dp.message(F.text == "💳 Пополнить баланс")
async def start_payment(message: types.Message, state: FSMContext):
    """Начало процесса пополнения баланса - ОЧИЩАЕМ СОСТОЯНИЕ ПЕРЕД НАЧАЛОМ"""
    try:
        # Очищаем состояние перед началом нового процесса
        await state.clear()
        from payment_handlers import PaymentHandlers
        await PaymentHandlers.handle_payment_start(message, state)
    except Exception as e:
        logger.error(f"Ошибка в start_payment: {e}")
        await message.answer("❌ Произошла ошибка при запуске оплаты")

@dp.callback_query(F.data == "payment_self")
async def handle_payment_self(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор себя для оплаты"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_self_selection(callback, state)

@dp.callback_query(F.data.startswith("payment_child_"))
async def handle_payment_child(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор ребенка для оплаты"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_child_selection(callback, state)

@dp.callback_query(F.data.startswith("payment_subject_"))
async def handle_payment_subject(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор предмета для оплаты"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_subject_selection(callback, state)

@dp.callback_query(F.data == "cancel_payment")
async def handle_cancel_payment(callback: types.CallbackQuery, state: FSMContext):
    """Отмена процесса оплаты"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_cancel_payment(callback, state)

@dp.message(PaymentStates.WAITING_AMOUNT)
async def handle_payment_amount(message: types.Message, state: FSMContext):
    """Обрабатывает ввод суммы для пополнения баланса"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_amount_input(message, state)

@dp.callback_query(F.data == "reminder_book_now")
async def handle_reminder_book_now(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает нажатие кнопки 'Давайте запишемся!' из напоминания"""
    try:
        user_id = callback.from_user.id

        # ПРОПУСКАЕМ ПРОВЕРКУ ФИО - пользователь уже зарегистрирован!
        # Вместо вызова start_booking, делаем то же самое, но без проверки ФИО

        # Получаем доступные роли пользователя
        user_roles = storage.get_user_roles(user_id)
        if not user_roles:
            await callback.answer(
                "⏳ Обратитесь к администратору для получения ролей \n Телефон администратора: +79001372727",
                show_alert=True
            )
            return

        # Получаем ФИО пользователя (оно точно есть)
        user_name = storage.get_user_name(user_id)
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
            await callback.answer(
                "❌ У вас нет ролей для бронирования. Обратитесь к администратору. \n Телефон администратора: +79001372727",
                show_alert=True
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
                    await callback.answer(
                        "У вас нет назначенных предметов. Обратитесь к администратору. \n Телефон администратора: +79001372727",
                        show_alert=True
                    )
                    return

                await state.update_data(subjects=teacher_subjects)
                subject_names = [SUBJECTS.get(subj_id, f"Предмет {subj_id}") for subj_id in teacher_subjects]

                await callback.message.edit_text(
                    f"Вы преподаватель\n"
                    f"Ваши предметы: {', '.join(subject_names)}\n"
                    "Теперь выберите дату:",
                    reply_markup=generate_calendar()
                )
                await state.set_state(BookingStates.SELECT_DATE)

            elif role == 'student':
                await callback.message.edit_text(
                    "Вы ученик\n"
                    "Выберите предмет для занятия:",
                    reply_markup=generate_subjects_keyboard()
                )
                await state.set_state(BookingStates.SELECT_SUBJECT)

            elif role == 'parent':
                # Обработка родителя
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
                    "Вы родитель\n"
                    "Выберите ребенка для записи:",
                    reply_markup=builder.as_markup()
                )
                await state.set_state(BookingStates.PARENT_SELECT_CHILD)

        else:
            # Если несколько ролей, показываем выбор
            await callback.message.edit_text(
                "Выберите роль для бронирования:",
                reply_markup=builder.as_markup()
            )
            await state.set_state(BookingStates.SELECT_ROLE)

        await callback.answer()

    except Exception as e:
        logger.error(f"Error handling reminder book now: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже", show_alert=True)



async def main():
    try:
        await db.connect()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return

    await background_tasks.startup_tasks()

    # Запуск фоновых задач
    tasks = background_tasks.start_all_tasks()
    for task in tasks:
        asyncio.create_task(task)

    # Простой запуск бота
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Fatal error in polling: {e}")
        raise

if __name__ == "__main__":
    logger.info("Starting bot...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
