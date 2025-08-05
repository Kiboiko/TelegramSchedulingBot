import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Dict, Any

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

# Конфигурация
BOT_TOKEN = "8413883420:AAGL9-27CcgEUsaCbP-PJ8ukuh1u1x3YPbQ"
BOOKINGS_FILE = "bookings.json"
BOOKING_TYPES = ["Тип1", "Тип2", "Тип3", "Тип4"]

SUBJECTS = {
    "math": "Математика",
    "inf": "Информатика",
    "rus": "Русский язык",
    "phys": "Физика"
}

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранение временных данных
booking_id_counter = 1


class JSONStorage:
    def __init__(self, file_path: str = BOOKINGS_FILE):
        self.file_path = Path(file_path)
        self.lock = threading.Lock()
        self._ensure_file_exists()
        self.gsheets_manager = None

    def set_gsheets_manager(self, gsheets_manager):
        self.gsheets_manager = gsheets_manager

    def _ensure_file_exists(self):
        with self.lock:
            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump([], f)

    def load(self) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []

    def save(self, data: List[Dict[str, Any]]):
        with self.lock:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            if self.gsheets_manager:
                try:
                    self.gsheets_manager.update_all_sheets(data)
                except Exception as e:
                    print(f"Google Sheets update error: {e}")

    def add_booking(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load()
        booking_data["id"] = len(data) + 1
        booking_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data.append(booking_data)
        self.save(data)
        return booking_data

    def get_user_bookings(self, user_id: int) -> List[Dict[str, Any]]:
        data = self.load()
        return [b for b in data if b.get("user_id") == user_id]

    def get_user_role(self, user_id: int) -> str:
        data = self.load()
        user_bookings = [b for b in data if b.get("user_id") == user_id]
        if user_bookings:
            return user_bookings[0].get("user_role")
        return None

    def cancel_booking(self, booking_id: int) -> bool:
        data = self.load()
        updated_data = [b for b in data if b.get("id") != booking_id]
        if len(data) != len(updated_data):
            self.save(updated_data)
            return True
        return False

    def update_user_subjects(self, user_id: int, subjects: List[str]) -> bool:
        data = self.load()
        updated = False
        for booking in data:
            if booking.get("user_id") == user_id and booking.get("user_role") == "teacher":
                booking["subjects"] = subjects
                updated = True

        if updated:
            self.save(data)
        return updated


storage = JSONStorage(file_path=BOOKINGS_FILE)

# Настройка Google Sheets
try:
    from gsheets_manager import GoogleSheetsManager

    gsheets = GoogleSheetsManager(
        credentials_file='credentials.json',
        spreadsheet_id='1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU'
    )
    storage.set_gsheets_manager(gsheets)
    print("Google Sheets integration initialized successfully")

    # Первоначальная синхронизация данных
    try:
        initial_data = storage.load()
        gsheets.update_all_sheets(initial_data)
    except Exception as e:
        print(f"Initial Google Sheets sync error: {e}")

except ImportError as e:
    print(f"Google Sheets module not found: {e}. Continuing without Google Sheets integration.")
except Exception as e:
    print(f"Google Sheets initialization error: {e}. Continuing without Google Sheets integration.")


class BookingStates(StatesGroup):
    SELECT_ROLE = State()
    INPUT_NAME = State()
    TEACHER_SUBJECTS = State()
    SELECT_SUBJECT = State()
    SELECT_DATE = State()
    SELECT_START_TIME = State()
    SELECT_END_TIME = State()
    CONFIRMATION = State()


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Забронировать время")],
        [KeyboardButton(text="📋 Мои бронирования"), KeyboardButton(text="❌ Отменить бронь")]
    ],
    resize_keyboard=True
)


def generate_booking_types():
    builder = InlineKeyboardBuilder()
    for booking_type in BOOKING_TYPES:
        builder.add(types.InlineKeyboardButton(
            text=booking_type,
            callback_data=f"booking_type_{booking_type}"
        ))
    builder.adjust(2)
    return builder.as_markup()


def merge_adjacent_bookings(bookings):
    if not bookings:
        return bookings

    sorted_bookings = sorted(bookings, key=lambda x: (
        x['booking_type'],
        x['date'],
        x['time_start']
    ))

    merged = []
    current = sorted_bookings[0]

    for next_booking in sorted_bookings[1:]:
        if (current['booking_type'] == next_booking['booking_type'] and
                current['date'] == next_booking['date'] and
                current['time_end'] == next_booking['time_start']):

            current = {
                **current,
                'time_end': next_booking['time_end'],
                'id': min(current['id'], next_booking['id']),
                'merged': True
            }
        else:
            merged.append(current)
            current = next_booking

    merged.append(current)
    return merged


def load_bookings():
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
                    if isinstance(booking['date'], str):
                        booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                    else:
                        continue

                    time_end = datetime.strptime(booking['time_end'], "%H:%M").time()
                    booking_datetime = datetime.combine(booking_date, time_end)

                    if booking_datetime < current_time:
                        continue

                    booking['date'] = booking_date
                    valid_bookings.append(booking)

                except ValueError:
                    continue

            valid_bookings = merge_adjacent_bookings(valid_bookings)

            if len(valid_bookings) != len(data):
                save_bookings(valid_bookings)

            return valid_bookings

        except (json.JSONDecodeError, KeyError, ValueError):
            return []


def save_bookings(bookings_list):
    try:
        current_time = datetime.now()
        bookings_to_save = []

        for booking in bookings_list:
            try:
                if 'date' not in booking or 'time_end' not in booking:
                    continue

                if isinstance(booking['date'], date):
                    booking_date = booking['date']
                elif isinstance(booking['date'], str):
                    booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                else:
                    continue

                time_end = datetime.strptime(booking['time_end'], "%H:%M").time()
                booking_datetime = datetime.combine(booking_date, time_end)

                if booking_datetime >= current_time:
                    booking_copy = {
                        'id': booking.get('id'),
                        'booking_type': booking.get('booking_type'),
                        'date': booking_date.strftime("%Y-%m-%d"),
                        'time_start': booking.get('time_start'),
                        'time_end': booking.get('time_end'),
                        'user_id': booking.get('user_id'),
                        'created_at': booking.get('created_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    }
                    bookings_to_save.append(booking_copy)

            except Exception as e:
                print(f"Ошибка обработки бронирования {booking}: {e}")
                continue

        os.makedirs(os.path.dirname(BOOKINGS_FILE) or ".", exist_ok=True)

        with open(BOOKINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(bookings_to_save, f, ensure_ascii=False, indent=2)

        return True

    except Exception as e:
        print(f"Критическая ошибка при сохранении: {e}")
        return False


def get_next_booking_id():
    global booking_id_counter
    bookings = load_bookings()
    if bookings:
        booking_id_counter = max(b["id"] for b in bookings) + 1
    else:
        booking_id_counter = 1
    return booking_id_counter


def has_booking_conflict(user_id, booking_type, date, time_start, time_end, exclude_id=None):
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


def generate_time_slots(selected_date=None):
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

    if selected_date is not None:
        builder.row(types.InlineKeyboardButton(
            text="❌ Отменить выбор времени",
            callback_data="cancel_time_selection"
        ))

    return builder.as_markup()


def generate_confirmation():
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking_confirm"),
        types.InlineKeyboardButton(text="❌ Отменить", callback_data="booking_cancel"),
    )
    return builder.as_markup()


def generate_booking_list(user_id):
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
        emoji = "✅" if subject_id in selected_subjects else "⬜"
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


@dp.message(CommandStart())
@dp.message(Command("start"))
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
        " 4. Выбрать дату из календаря\n"
        " 5. Выбрать время начала и окончания\n"
        " 6. Подтвердить бронирование\n\n"
        "/my_bookings - показать ваши бронирования\n"
        "/my_role - показать вашу роль\n"
        "/help - показать эту справку"
    )


@dp.message(F.text == "📅 Забронировать время")
@dp.message(Command("book"))
async def start_booking(message: types.Message, state: FSMContext):
    user_role = storage.get_user_role(message.from_user.id)

    if user_role:
        await state.update_data(user_role=user_role)
        await message.answer("Выберите тип бронирования:", reply_markup=generate_booking_types())
    else:
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

    await callback.message.edit_text("Выберите дату:", reply_markup=generate_calendar())
    await state.set_state(BookingStates.SELECT_DATE)
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_SUBJECT, F.data.startswith("subject_"))
async def process_student_subject(callback: types.CallbackQuery, state: FSMContext):
    subject_id = callback.data.split("_")[1]
    await state.update_data(subject=subject_id)

    await callback.message.edit_text(f"Выбран предмет: {SUBJECTS[subject_id]}")
    await callback.message.answer("Выберите дату:", reply_markup=generate_calendar())
    await state.set_state(BookingStates.SELECT_DATE)
    await callback.answer()


@dp.callback_query(F.data.startswith("booking_type_"))
async def process_booking_type(callback: types.CallbackQuery, state: FSMContext):
    booking_type = callback.data.replace("booking_type_", "")
    await state.update_data(booking_type=booking_type)

    await callback.message.edit_text(
        f"Выбран тип: {booking_type}\nТеперь выберите дату:",
        reply_markup=generate_calendar()
    )
    await state.set_state(BookingStates.SELECT_DATE)
    await callback.answer()


@dp.callback_query(F.data.startswith("calendar_"))
async def process_calendar(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data

    if data.startswith("calendar_day_"):
        date_str = data.replace("calendar_day_", "")
        year, month, day = map(int, date_str.split("-"))
        selected_date = datetime(year, month, day).date()

        await state.update_data(selected_date=selected_date)
        await callback.message.edit_text(f"Выбрана дата: {day}.{month}.{year}")
        await callback.message.answer("Выберите время начала:", reply_markup=generate_time_slots())
        await state.set_state(BookingStates.SELECT_START_TIME)
        await callback.answer()

    elif data.startswith("calendar_change_"):
        date_str = data.replace("calendar_change_", "")
        year, month = map(int, date_str.split("-"))
        await callback.message.edit_reply_markup(reply_markup=generate_calendar(year, month))
        await callback.answer()


@dp.callback_query(BookingStates.SELECT_START_TIME, F.data.startswith("time_slot_"))
async def process_start_time(callback: types.CallbackQuery, state: FSMContext):
    time_start = callback.data.replace("time_slot_", "")
    await state.update_data(time_start=time_start)
    await callback.message.edit_text(f"Выбрано время начала: {time_start}\nВыберите время окончания:")
    await callback.message.edit_reply_markup(reply_markup=generate_time_slots())
    await state.set_state(BookingStates.SELECT_END_TIME)
    await callback.answer()


@dp.callback_query(BookingStates.SELECT_END_TIME, F.data.startswith("time_slot_"))
async def process_end_time(callback: types.CallbackQuery, state: FSMContext):
    time_end = callback.data.replace("time_slot_", "")
    data = await state.get_data()
    time_start = data['time_start']

    if datetime.strptime(time_end, "%H:%M") <= datetime.strptime(time_start, "%H:%M"):
        await callback.answer("Время окончания должно быть после времени начала!", show_alert=True)
        return

    if has_booking_conflict(
            user_id=callback.from_user.id,
            booking_type=data.get('booking_type', ''),
            date=data['selected_date'],
            time_start=time_start,
            time_end=time_end
    ):
        await callback.answer(
            f"У вас уже есть бронь на это время!",
            show_alert=True
        )
        return

    await state.update_data(time_end=time_end)

    role_text = "ученик" if data.get('user_role') == 'student' else "преподаватель"

    if data.get('user_role') == 'teacher':
        subjects_text = ", ".join(SUBJECTS[subj] for subj in data.get('subjects', []))
    else:
        subjects_text = SUBJECTS.get(data.get('subject', ''), "Не указан")

    await callback.message.edit_text(
        f"📋 Подтвердите бронирование:\n\n"
        f"👤 Ваше ФИО: {data['user_name']}\n"
        f"👤 Ваша роль: {role_text}\n"
        f"📚 Предмет(ы): {subjects_text}\n"
        f"📅 Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
        f"⏰ Время: {time_start} - {time_end}",
        reply_markup=generate_confirmation()
    )
    await state.set_state(BookingStates.CONFIRMATION)
    await callback.answer()


@dp.callback_query(F.data == "cancel_time_selection")
async def cancel_time_selection(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()

    await callback.message.edit_text(
        "Выбор времени отменён. Можете начать заново.",
        reply_markup=None
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=main_menu
    )
    await callback.answer()


@dp.callback_query(BookingStates.CONFIRMATION, F.data.in_(["booking_confirm", "booking_cancel"]))
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "booking_confirm":
        data = await state.get_data()

        # Проверка на конфликты
        if has_booking_conflict(
                user_id=callback.from_user.id,
                booking_type=data.get('booking_type', ''),
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

        # Создаем бронирование
        booking_id = get_next_booking_id()
        booking = {
            "id": booking_id,
            "booking_type": data.get('booking_type', ''),
            "date": data['selected_date'].strftime("%Y-%m-%d"),
            "time_start": data['time_start'],
            "time_end": data['time_end'],
            "user_id": callback.from_user.id,
            "user_name": data['user_name'],
            "user_role": data['user_role'],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        if data.get('user_role') == 'teacher':
            booking["subjects"] = data.get('subjects', [])
        else:
            booking["subject"] = data.get('subject', '')

        # Сохраняем бронирование
        storage.add_booking(booking)

        # Формируем сообщение об успешном бронировании
        role_text = "ученик" if booking.get('user_role') == 'student' else "преподаватель"

        if booking.get('user_role') == 'teacher':
            subjects_text = ", ".join(SUBJECTS[subj] for subj in booking.get('subjects', []))
        else:
            subjects_text = SUBJECTS.get(booking.get('subject', ''), "Не указан")

        message_text = (
            "✅ Бронирование подтверждено!\n\n"
            f"👤 Ваше ФИО: {booking['user_name']}\n"
            f"👤 Ваша роль: {role_text}\n"
            f"📚 Предмет(ы): {subjects_text}\n"
            f"📅 Дата: {booking['date']}\n"
            f"⏰ Время: {booking['time_start']} - {booking['time_end']}\n\n"
            "Вы можете просмотреть или отменить бронирование через меню"
        )

        await callback.message.edit_text(message_text)
    else:
        await callback.message.edit_text("❌ Бронирование отменено")

    # Очищаем состояние
    await state.clear()
    await callback.answer()


@dp.message(F.text == "📋 Мои бронирования")
@dp.message(Command("my_bookings"))
async def show_bookings(message: types.Message):
    user_role = storage.get_user_role(message.from_user.id)

    if user_role:
        bookings = storage.get_user_bookings(message.from_user.id)
        if not bookings:
            await message.answer("У вас нет активных бронирований")
            return

        text = "Ваши бронирования:\n\n"
        for booking in bookings:
            role_text = "ученик" if booking.get('user_role') == 'student' else "преподаватель"

            if booking.get('user_role') == 'teacher':
                subjects_text = ", ".join(SUBJECTS[subj] for subj in booking.get('subjects', []))
            else:
                subjects_text = SUBJECTS.get(booking.get('subject', ''), "Не указан")

            text += (
                f"👤 Ваше ФИО: {booking['user_name']}\n"
                f"👤 Ваша роль: {role_text}\n"
                f"📚 Предмет(ы): {subjects_text}\n"
                f"📅 Дата: {booking['date']}\n"
                f"⏰ Время: {booking['start_time']} - {booking['end_time']}\n"
                f"🆔 ID: {booking['id']}\n\n"
            )

        await message.answer(text)
    else:
        keyboard = generate_booking_list(message.from_user.id)
        if not keyboard:
            await message.answer("У вас нет активных бронирований")
            return

        await message.answer("Ваши бронирования (отсортированы по дате и времени):", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("booking_info_"))
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


@dp.message(Command("my_role"))
async def show_role(message: types.Message):
    role = storage.get_user_role(message.from_user.id)
    if role:
        await message.answer(f"Ваша роль: {'ученик' if role == 'student' else 'преподаватель'}")
    else:
        await message.answer("Ваша роль еще не определена. Используйте /book чтобы установить роль.")


@dp.message(F.text == "❌ Отменить бронь")
async def start_cancel_booking(message: types.Message):
    user_role = storage.get_user_role(message.from_user.id)

    if user_role:
        bookings = storage.get_user_bookings(message.from_user.id)
        if not bookings:
            await message.answer("У вас нет активных бронирований для отмены")
            return

        builder = InlineKeyboardBuilder()
        for booking in bookings:
            builder.row(types.InlineKeyboardButton(
                text=f"{booking['date']} {booking['start_time']}-{booking['end_time']}",
                callback_data=f"cancel_booking_{booking['id']}"
            ))

        await message.answer(
            "Выберите бронирование для отмены:",
            reply_markup=builder.as_markup()
        )
    else:
        keyboard = generate_booking_list(message.from_user.id)
        if not keyboard:
            await message.answer("У вас нет активных бронирований для отмены")
            return

        await message.answer("Выберите бронирование для отмены:", reply_markup=keyboard)


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
    while True:
        bookings = load_bookings()
        save_bookings(bookings)
        await asyncio.sleep(6 * 60 * 60)


async def main():
    asyncio.create_task(cleanup_old_bookings())
    await dp.start_polling(bot)


if __name__ == "__main__":
    print("Текущая директория:", os.getcwd())
    print("Полный путь к файлу:", os.path.abspath(BOOKINGS_FILE))
    asyncio.run(main())