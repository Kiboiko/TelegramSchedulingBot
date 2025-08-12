import asyncio
import json
import os
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
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOKINGS_FILE = "bookings.json"

BOOKING_TYPES = ["Тип1", "Тип2", "Тип3", "Тип4"]
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
    SELECT_START_TIME = State()
    SELECT_END_TIME = State()
    CONFIRMATION = State()


# main.py (часть инициализации)
# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
storage = JSONStorage(file_path=BOOKINGS_FILE)

# Настройка Google Sheets
try:
    gsheets = GoogleSheetsManager(
        credentials_file='credentials.json',
        spreadsheet_id='1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU'  # Убедитесь, что ID правильный
    )
    # Проверяем подключение
    gsheets.connect()  # Явно вызываем подключение
    storage.set_gsheets_manager(gsheets)
    print("Google Sheets integration initialized successfully")

    # Принудительное обновление при старте
    initial_data = storage.load()
    gsheets.update_all_sheets(initial_data)
except Exception as e:
    print(f"Google Sheets initialization error: {e}")
    # Даже если есть ошибка, бот продолжит работать, но без Google Sheets

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


def generate_time_slots(selected_date=None, selected_start=None, selected_end=None):
    """Генерирует клавиатуру выбора времени с визуальным выделением"""
    builder = InlineKeyboardBuilder()

    # Определяем рабочие часы (9:00 - 20:00)
    start_time = datetime.strptime("09:00", "%H:%M")
    end_time = datetime.strptime("20:00", "%H:%M")
    current_time = start_time

    # Преобразуем строки времени в объекты времени для сравнения
    start_obj = datetime.strptime(selected_start, "%H:%M").time() if selected_start else None
    end_obj = datetime.strptime(selected_end, "%H:%M").time() if selected_end else None

    while current_time <= end_time:
        time_str = current_time.strftime("%H:%M")
        current_obj = current_time.time()
        
        # Определяем стиль кнопки в зависимости от позиции в выбранном диапазоне
        if selected_start and selected_end:
            if current_obj == start_obj:
                # Начальная точка - зеленая
                button_text = f"🟢 {time_str}"
            elif current_obj == end_obj:
                # Конечная точка - красная
                button_text = f"🔴 {time_str}"
            elif start_obj < current_obj < end_obj:
                # Промежуточные точки - синие
                button_text = f"🔵 {time_str}"
            else:
                # Вне диапазона - обычный вид
                button_text = time_str
        elif selected_start and current_obj == start_obj:
            # Только начальное время выбрано - зеленая
            button_text = f"🟢 {time_str}"
        else:
            # Ничего не выбрано - обычный вид
            button_text = time_str

        builder.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"time_slot_{time_str}"
        ))
        current_time += timedelta(minutes=30)

    builder.adjust(4)
    
    # Добавляем кнопку отмены
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
            text=f"{booking.get('booking_type', '')}{merged_note} {booking_date.strftime('%d.%m.%Y')} {booking.get('start_time', '')}-{booking.get('end_time', '')} (ID: {booking.get('id', '')})",
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
    await callback.message.edit_text("Выберите тип бронирования:", reply_markup=generate_booking_types())
    await state.set_state(BookingStates.SELECT_BOOKING_TYPE)
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_SUBJECT, F.data.startswith("subject_"))
async def process_student_subject(callback: types.CallbackQuery, state: FSMContext):
    subject_id = callback.data.split("_")[1]
    await state.update_data(subject=subject_id)

    await callback.message.edit_text(f"Выбран предмет: {SUBJECTS[subject_id]}")
    await callback.message.answer("Выберите тип бронирования:", reply_markup=generate_booking_types())
    await state.set_state(BookingStates.SELECT_BOOKING_TYPE)
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_BOOKING_TYPE, F.data.startswith("booking_type_"))
async def process_booking_type(callback: types.CallbackQuery, state: FSMContext):
    booking_type = callback.data.replace("booking_type_", "")
    await state.update_data(booking_type=booking_type)
    await callback.message.edit_text(
        f"Выбран тип: {booking_type}\nТеперь выберите дату:",
        reply_markup=generate_calendar()
    )
    await state.set_state(BookingStates.SELECT_DATE)
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_DATE, F.data.startswith("calendar_"))
async def process_calendar(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data

    if data.startswith("calendar_day_"):
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()

        await state.update_data(selected_date=selected_date)
        await callback.message.edit_text(
            f"Выбрана дата: {day}.{month}.{year}\nВыберите время начала:",
            reply_markup=generate_time_slots(selected_date)
        )
        await state.set_state(BookingStates.SELECT_START_TIME)
        await callback.answer()

    elif data.startswith("calendar_change_"):
        date_str = data.replace("calendar_change_", "")
        year, month = map(int, date_str.split("-"))
        await callback.message.edit_reply_markup(reply_markup=generate_calendar(year, month))
        await callback.answer()


@dp.callback_query(BookingStates.SELECT_START_TIME, F.data.startswith("time_slot_"))
async def process_start_time(callback: types.CallbackQuery, state: FSMContext):
    try:
        # Получаем выбранное время начала
        time_start = callback.data.replace("time_slot_", "")
        
        # Проверяем корректность формата времени
        try:
            datetime.strptime(time_start, "%H:%M")
        except ValueError:
            await callback.answer("Некорректный формат времени!", show_alert=True)
            return

        # Обновляем состояние
        await state.update_data(time_start=time_start)
        data = await state.get_data()
        selected_date = data.get('selected_date')

        # Формируем текст сообщения
        booking_type = data.get('booking_type', 'не указан')
        message_text = (
            f"Тип бронирования: {booking_type}\n"
            f"Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"Выбрано время начала: {time_start}\n\n"
            "Выберите время окончания:"
        )

        # Отправляем обновленное сообщение с клавиатурой (выделяем только начало)
        await callback.message.edit_text(
            text=message_text,
            reply_markup=generate_time_slots(
                selected_date=selected_date,
                selected_start=time_start
            )
        )
        
        # Меняем состояние на выбор времени окончания
        await state.set_state(BookingStates.SELECT_END_TIME)
        await callback.answer()

    except Exception as e:
        logging.error(f"Error in process_start_time: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже", show_alert=True)
        await state.clear()


@dp.callback_query(BookingStates.SELECT_END_TIME, F.data.startswith("time_slot_"))
async def process_end_time(callback: types.CallbackQuery, state: FSMContext):
    try:
        time_end = callback.data.replace("time_slot_", "")
        data = await state.get_data()
        time_start = data['time_start']

        # Проверяем, что время окончания после времени начала
        if datetime.strptime(time_end, "%H:%M") <= datetime.strptime(time_start, "%H:%M"):
            await callback.answer("Время окончания должно быть после времени начала!", show_alert=True)
            return

        # Обновляем состояние
        await state.update_data(time_end=time_end)
        data = await state.get_data()

        role_text = "ученик" if data['user_role'] == 'student' else "преподаватель"

        if data['user_role'] == 'teacher':
            subjects_text = ", ".join(SUBJECTS[subj] for subj in data.get('subjects', []))
        else:
            subjects_text = SUBJECTS.get(data.get('subject', ''), "Не указан")

        # Создаем клавиатуру с кнопками действий
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(
                text="✅ Подтвердить время",
                callback_data="confirm_time_selection"
            ),
            types.InlineKeyboardButton(
                text="🔄 Изменить время окончания",
                callback_data="change_end_time"
            )
        )
        builder.row(
            types.InlineKeyboardButton(
                text="❌ Отменить бронирование",
                callback_data="cancel_time_selection"
            )
        )

        # Формируем сообщение с текущим выбором
        await callback.message.edit_text(
            f"📋 Текущий выбор времени:\n\n"
            f"Тип: {data['booking_type']}\n"
            f"Роль: {role_text}\n"
            f"Предмет(ы): {subjects_text}\n"
            f"Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
            f"Время: {data['time_start']} - {time_end}\n\n"
            "Вы можете подтвердить время или изменить окончание:",
            reply_markup=builder.as_markup()
        )
        
        # Остаемся в том же состоянии SELECT_END_TIME
        await callback.answer()

    except Exception as e:
        logging.error(f"Error in process_end_time: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже", show_alert=True)
        await state.clear()

@dp.callback_query(BookingStates.SELECT_END_TIME, F.data == "change_end_time")
async def change_end_time(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик кнопки изменения времени окончания"""
    data = await state.get_data()
    
    # Возвращаем пользователя к выбору времени окончания
    await callback.message.edit_text(
        f"Выберите новое время окончания (начало в {data['time_start']}):",
        reply_markup=generate_time_slots(
            selected_date=data.get('selected_date'),
            selected_start=data.get('time_start')
        )
    )
    await callback.answer()

@dp.callback_query(BookingStates.SELECT_END_TIME, F.data == "confirm_time_selection")
async def confirm_time_selection(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик подтверждения выбранного времени"""
    data = await state.get_data()
    
    # Проверка на конфликты
    if has_booking_conflict(
            user_id=callback.from_user.id,
            booking_type=data['booking_type'],
            date=data['selected_date'],
            time_start=data['time_start'],
            time_end=data['time_end']
    ):
        await callback.answer(
            f"У вас уже есть бронь типа '{data['booking_type']}' на это время!",
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
        f"Тип: {data['booking_type']}\n"
        f"Роль: {role_text}\n"
        f"Предмет(ы): {subjects_text}\n"
        f"Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
        f"Время: {data['time_start']} - {data['time_end']}",
        reply_markup=generate_confirmation()
    )
    await state.set_state(BookingStates.CONFIRMATION)
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_END_TIME, F.data == "cancel_time_selection")
async def cancel_end_time_selection(callback: types.CallbackQuery, state: FSMContext):
    try:
        # Получаем данные из состояния
        data = await state.get_data()
        booking_type = data.get('booking_type', 'неизвестный тип')
        selected_date = data.get('selected_date')

        # Формируем сообщение об отмене
        cancel_message = (
            f"❌ Выбор времени для бронирования '{booking_type}' "
            f"на {selected_date.strftime('%d.%m.%Y')} отменен.\n\n"
            "Вы можете начать процесс заново."
        )

        # Редактируем сообщение и очищаем клавиатуру
        await callback.message.edit_text(
            text=cancel_message,
            reply_markup=None
        )

        # Предлагаем вернуться в меню
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=main_menu
        )

        # Очищаем состояние
        await state.clear()
        await callback.answer()

    except Exception as e:
        logging.error(f"Error in cancel_end_time_selection: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
        await state.clear()


# В функции process_confirmation изменим сохранение бронирования:
@dp.callback_query(BookingStates.CONFIRMATION, F.data.in_(["booking_confirm", "booking_cancel"]))
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "booking_confirm":
        data = await state.get_data()

        if has_booking_conflict(
                user_id=callback.from_user.id,
                booking_type=data['booking_type'],
                date=data['selected_date'],
                time_start=data['time_start'],
                time_end=data['time_end']
        ):
            await callback.message.edit_text(
                "К сожалению, это время стало недоступно. Пожалуйста, начните бронирование заново."
            )
            await state.clear()
            await callback.answer()
            return

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

        # Добавляем бронирование (автоматически сохранится и в JSON и в Google Sheets)
        booking = storage.add_booking(booking_data)

        role_text = "ученик" if booking['user_role'] == 'student' else "преподаватель"

        if booking['user_role'] == 'teacher':
            subjects_text = ", ".join(SUBJECTS[subj] for subj in booking.get('subjects', []))
        else:
            subjects_text = SUBJECTS.get(booking.get('subject', ''), "Не указан")

        await callback.message.edit_text(
            "✅ Бронирование подтверждено!\n\n"
            f"Тип: {booking['booking_type']}\n"
            f"Роль: {role_text}\n"
            f"Предмет(ы): {subjects_text}\n"
            f"Дата: {booking['date']}\n"
            f"Время: {booking['start_time']} - {booking['end_time']}\n\n"
            "Вы можете просмотреть или отменить бронирование через меню",
        )
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
    booking_id = int(callback.data.replace("booking_info_", ""))
    bookings = load_bookings()
    booking = next((b for b in bookings if b.get("id") == booking_id), None)

    if not booking:
        await callback.answer("Бронирование не найдено", show_alert=True)
        return

    booking_date = booking.get('date')
    if isinstance(booking_date, str):
        booking_date = datetime.strptime(booking_date, "%Y-%m-%d").date()

    role_text = "ученик" if booking.get('user_role') == 'student' else "преподаватель"

    if booking.get('user_role') == 'teacher':
        subjects_text = ", ".join(SUBJECTS[subj] for subj in booking.get('subjects', []))
    else:
        subjects_text = SUBJECTS.get(booking.get('subject', ''), "Не указан")

    await callback.message.edit_text(
        f"Информация о бронировании:\n\n"
        f"Тип: {booking.get('booking_type', '')}\n"
        f"Роль: {role_text}\n"
        f"Предмет(ы): {subjects_text}\n"
        f"Дата: {booking_date.strftime('%d.%m.%Y')}\n"
        f"Время: {booking.get('start_time', '')} - {booking.get('end_time', '')}\n"
        f"ID: {booking.get('id', '')}",
        reply_markup=generate_booking_actions(booking.get('id'))
    )
    await callback.answer()


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
        # Загружаем и сохраняем - это автоматически удалит старые записи
        bookings = load_bookings()
        storage.save(bookings)
        # Проверяем каждые 6 часов
        await asyncio.sleep(6 * 60 * 60)


async def main():
    asyncio.create_task(cleanup_old_bookings())
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("Текущая директория:", os.getcwd())
    print("Полный путь к файлу:", os.path.abspath(BOOKINGS_FILE))
    asyncio.run(main())