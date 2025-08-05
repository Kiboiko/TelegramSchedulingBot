# import asyncio
# from datetime import datetime, timedelta
# from aiogram import Bot, Dispatcher, types, F
# from aiogram.filters import Command, CommandStart
# from aiogram.types import (
#     Message,
#     CallbackQuery,
#     InlineKeyboardButton,
#     InlineKeyboardMarkup,
#     ReplyKeyboardMarkup,
#     KeyboardButton
# )
# from aiogram.utils.keyboard import InlineKeyboardBuilder
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import State, StatesGroup
# import json
# import os
# from pathlib import Path
#
# BOT_TOKEN = "7807559906:AAFA0bsnb_Y6m3JHKIeWk2hZ3_ytMvnC-as"
# BOOKINGS_FILE = "bookings.json"
#
#
# class JSONStorage:
#     def __init__(self, file_path=BOOKINGS_FILE):
#         self.file_path = Path(file_path)
#         self._ensure_file_exists()
#
#     def _ensure_file_exists(self):
#         """Создает файл данных с пустым списком, если его нет или он пустой"""
#         if not self.file_path.exists() or os.path.getsize(self.file_path) == 0:
#             with open(self.file_path, 'w', encoding='utf-8') as f:
#                 json.dump([], f)
#
#     def load(self):
#         """Загружает данные из файла, гарантируя возврат списка"""
#         try:
#             with open(self.file_path, 'r', encoding='utf-8') as f:
#                 return json.load(f)
#         except (json.JSONDecodeError, FileNotFoundError):
#             return []
#
#     def save(self, data):
#         """Сохраняет данные в файл"""
#         with open(self.file_path, 'w', encoding='utf-8') as f:
#             json.dump(data, f, indent=2, ensure_ascii=False)
#
#     def add_booking(self, booking_data):
#         """Добавляет новое бронирование"""
#         data = self.load()
#         booking_data["id"] = len(data) + 1
#         booking_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         data.append(booking_data)
#         self.save(data)
#         return booking_data
#
#     def get_user_bookings(self, user_id: int):
#         """Возвращает бронирования пользователя"""
#         data = self.load()
#         return [b for b in data if b.get("user_id") == user_id]
#
#     def get_user_role(self, user_id: int):
#         """Возвращает роль пользователя"""
#         data = self.load()
#         user_bookings = [b for b in data if b.get("user_id") == user_id]
#         if user_bookings:
#             return user_bookings[0].get("user_role")
#         return None
#
#     def cancel_booking(self, booking_id: int):
#         """Отменяет бронирование по ID"""
#         data = self.load()
#         updated_data = [b for b in data if b.get("id") != booking_id]
#         if len(data) != len(updated_data):
#             self.save(updated_data)
#             return True
#         return False
#
#
# bot = Bot(token=BOT_TOKEN)
# dp = Dispatcher()
# storage = JSONStorage()
#
#
# class BookingStates(StatesGroup):
#     SELECT_ROLE = State()
#     INPUT_NAME = State()
#     SELECT_DATE = State()
#     SELECT_START_TIME = State()
#     SELECT_END_TIME = State()
#     CONFIRMATION = State()
#
#
# main_menu = ReplyKeyboardMarkup(
#     keyboard=[
#         [KeyboardButton(text="📅 Забронировать время")],
#         [KeyboardButton(text="📋 Мои бронирования"), KeyboardButton(text="❌ Отменить бронь")]
#     ],
#     resize_keyboard=True
# )
#
#
# def generate_calendar(year=None, month=None):
#     now = datetime.now()
#     year = year or now.year
#     month = month or now.month
#
#     builder = InlineKeyboardBuilder()
#
#     month_name = datetime(year, month, 1).strftime("%B %Y")
#     builder.row(types.InlineKeyboardButton(text=month_name, callback_data="ignore"))
#
#     week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
#     builder.row(*[types.InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])
#
#     first_day = datetime(year, month, 1)
#     start_weekday = first_day.weekday()
#     days_in_month = (datetime(year, month + 1, 1) - first_day).days
#
#     buttons = []
#     for _ in range(start_weekday):
#         buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
#
#     for day in range(1, days_in_month + 1):
#         date = datetime(year, month, day)
#         if date.date() < datetime.now().date():
#             buttons.append(types.InlineKeyboardButton(text=" ", callback_data="ignore"))
#         else:
#             buttons.append(types.InlineKeyboardButton(
#                 text=str(day),
#                 callback_data=f"calendar_day_{year}-{month}-{day}"
#             ))
#         if (day + start_weekday) % 7 == 0 or day == days_in_month:
#             builder.row(*buttons)
#             buttons = []
#
#     prev_month = month - 1 if month > 1 else 12
#     prev_year = year if month > 1 else year - 1
#     next_month = month + 1 if month < 12 else 1
#     next_year = year if month < 12 else year + 1
#
#     builder.row(
#         types.InlineKeyboardButton(text="⬅️", callback_data=f"calendar_change_{prev_year}-{prev_month}"),
#         types.InlineKeyboardButton(text="➡️", callback_data=f"calendar_change_{next_year}-{next_month}"),
#     )
#
#     return builder.as_markup()
#
#
# def generate_time_slots():
#     builder = InlineKeyboardBuilder()
#     start_time = datetime.strptime("09:00", "%H:%M")
#     end_time = datetime.strptime("20:00", "%H:%M")
#     current_time = start_time
#
#     while current_time <= end_time:
#         time_str = current_time.strftime("%H:%M")
#         builder.add(types.InlineKeyboardButton(
#             text=time_str,
#             callback_data=f"time_slot_{time_str}"
#         ))
#         current_time += timedelta(minutes=30)
#
#     builder.adjust(4)
#     return builder.as_markup()
#
#
# def generate_confirmation():
#     builder = InlineKeyboardBuilder()
#     builder.row(
#         types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
#         types.InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no"),
#     )
#     return builder.as_markup()
#
#
# @dp.message(CommandStart())
# async def cmd_start(message: types.Message):
#     await message.answer(
#         "Добро пожаловать в систему бронирования!\n"
#         "Используйте кнопки ниже для навигации:",
#         reply_markup=main_menu
#     )
#
#
# @dp.message(Command("help"))
# async def cmd_help(message: types.Message):
#     await message.answer(
#         "📋 Справка по боту:\n\n"
#         "/book - начать процесс бронирования\n"
#         " 1. Выбрать роль (ученик/преподаватель)\n"
#         " 2. Ввести ваше ФИО\n"
#         " 3. Выбрать дату из календаря\n"
#         " 4. Выбрать время начала и окончания\n"
#         " 5. Подтвердить бронирование\n\n"
#         "/my_bookings - показать ваши бронирования\n"
#         "/my_role - показать вашу роль\n"
#         "/help - показать эту справку"
#     )
#
#
# @dp.message(F.text == "📅 Забронировать время")
# @dp.message(Command("book"))
# async def start_booking(message: types.Message, state: FSMContext):
#     builder = InlineKeyboardBuilder()
#     builder.button(text="👨‍🎓 Я ученик", callback_data="role_student")
#     builder.button(text="👨‍🏫 Я преподаватель", callback_data="role_teacher")
#
#     await message.answer(
#         "Перед началом бронирования, пожалуйста, укажите вашу роль:",
#         reply_markup=builder.as_markup()
#     )
#     await state.set_state(BookingStates.SELECT_ROLE)
#
#
# @dp.callback_query(F.data.startswith("role_"))
# async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
#     role = callback.data.split("_")[1]
#     await state.update_data(user_role=role)
#
#     await callback.message.edit_text("Введите ваше полное ФИО:")
#     await state.set_state(BookingStates.INPUT_NAME)
#     await callback.answer()
#
#
# @dp.message(BookingStates.INPUT_NAME)
# async def process_name(message: types.Message, state: FSMContext):
#     if len(message.text.split()) < 2:
#         await message.answer("Пожалуйста, введите полное ФИО (минимум имя и фамилию)")
#         return
#
#     await state.update_data(user_name=message.text)
#     await message.answer("Выберите дату:", reply_markup=generate_calendar())
#     await state.set_state(BookingStates.SELECT_DATE)
#
#
# @dp.callback_query(BookingStates.SELECT_DATE, F.data.startswith("calendar_"))
# async def process_calendar(callback: types.CallbackQuery, state: FSMContext):
#     data = callback.data
#
#     if data.startswith("calendar_day_"):
#         date_str = data.replace("calendar_day_", "")
#         year, month, day = map(int, date_str.split("-"))
#         selected_date = datetime(year, month, day).date()
#
#         await state.update_data(selected_date=selected_date)
#         await callback.message.edit_text(f"Выбрана дата: {day}.{month}.{year}")
#         await callback.message.answer("Выберите время начала:", reply_markup=generate_time_slots())
#         await state.set_state(BookingStates.SELECT_START_TIME)
#         await callback.answer()
#
#     elif data.startswith("calendar_change_"):
#         date_str = data.replace("calendar_change_", "")
#         year, month = map(int, date_str.split("-"))
#         await callback.message.edit_reply_markup(reply_markup=generate_calendar(year, month))
#         await callback.answer()
#
#
# @dp.callback_query(BookingStates.SELECT_START_TIME, F.data.startswith("time_slot_"))
# async def process_start_time(callback: types.CallbackQuery, state: FSMContext):
#     time_start = callback.data.replace("time_slot_", "")
#     await state.update_data(time_start=time_start)
#     await callback.message.edit_text(f"Выбрано время начала: {time_start}\nВыберите время окончания:")
#     await callback.message.edit_reply_markup(reply_markup=generate_time_slots())
#     await state.set_state(BookingStates.SELECT_END_TIME)
#     await callback.answer()
#
#
# @dp.callback_query(BookingStates.SELECT_END_TIME, F.data.startswith("time_slot_"))
# async def process_end_time(callback: types.CallbackQuery, state: FSMContext):
#     time_end = callback.data.replace("time_slot_", "")
#     data = await state.get_data()
#     time_start = data['time_start']
#
#     if datetime.strptime(time_end, "%H:%M") <= datetime.strptime(time_start, "%H:%M"):
#         await callback.answer("Время окончания должно быть после времени начала!", show_alert=True)
#         return
#
#     await state.update_data(time_end=time_end)
#
#     role_text = "ученик" if data['user_role'] == 'student' else "преподаватель"
#     await callback.message.edit_text(
#         f"📋 Подтвердите бронирование:\n\n"
#         f"👤 Ваше ФИО: {data['user_name']}\n"
#         f"👤 Ваша роль: {role_text}\n"
#         f"📅 Дата: {data['selected_date'].strftime('%d.%m.%Y')}\n"
#         f"⏰ Время: {time_start} - {time_end}",
#         reply_markup=generate_confirmation()
#     )
#     await state.set_state(BookingStates.CONFIRMATION)
#     await callback.answer()
#
#
# @dp.callback_query(BookingStates.CONFIRMATION, F.data.in_(["confirm_yes", "confirm_no"]))
# async def process_confirmation(callback: types.CallbackQuery, state: FSMContext):
#     if callback.data == "confirm_yes":
#         data = await state.get_data()
#         booking_data = {
#             "user_name": data['user_name'],
#             "user_role": data['user_role'],
#             "date": data['selected_date'].strftime("%Y-%m-%d"),
#             "start_time": data['time_start'],
#             "end_time": data['time_end'],
#             "user_id": callback.from_user.id
#         }
#         booking = storage.add_booking(booking_data)
#
#         role_text = "ученик" if booking['user_role'] == 'student' else "преподаватель"
#         await callback.message.edit_text(
#             "✅ Бронирование подтверждено!\n\n"
#             f"👤 Ваше ФИО: {booking['user_name']}\n"
#             f"👤 Ваша роль: {role_text}\n"
#             f"📅 Дата: {booking['date']}\n"
#             f"⏰ Время: {booking['start_time']} - {booking['end_time']}\n\n"
#             "Вы можете создать новое бронирование через меню"
#         )
#     else:
#         await callback.message.edit_text("❌ Бронирование отменено")
#
#     await state.clear()
#     await callback.answer()
#
#
# @dp.message(F.text == "📋 Мои бронирования")
# @dp.message(Command("my_bookings"))
# async def show_bookings(message: types.Message):
#     bookings = storage.get_user_bookings(message.from_user.id)
#     if not bookings:
#         await message.answer("У вас нет активных бронирований")
#         return
#
#     text = "Ваши бронирования:\n\n"
#     for booking in bookings:
#         role_text = "ученик" if booking.get('user_role') == 'student' else "преподаватель"
#         text += (
#             f"👤 Ваше ФИО: {booking['user_name']}\n"
#             f"👤 Ваша роль: {role_text}\n"
#             f"📅 Дата: {booking['date']}\n"
#             f"⏰ Время: {booking['start_time']} - {booking['end_time']}\n"
#             f"🆔 ID: {booking['id']}\n\n"
#         )
#
#     await message.answer(text)
#
#
# @dp.message(Command("my_role"))
# async def show_role(message: types.Message):
#     role = storage.get_user_role(message.from_user.id)
#     if role:
#         await message.answer(f"Ваша роль: {'ученик' if role == 'student' else 'преподаватель'}")
#     else:
#         await message.answer("Ваша роль еще не определена. Используйте /book чтобы установить роль.")
#
#
# @dp.message(F.text == "❌ Отменить бронь")
# async def start_cancel_booking(message: types.Message):
#     bookings = storage.get_user_bookings(message.from_user.id)
#     if not bookings:
#         await message.answer("У вас нет активных бронирований для отмены")
#         return
#
#     builder = InlineKeyboardBuilder()
#     for booking in bookings:
#         builder.row(types.InlineKeyboardButton(
#             text=f"{booking['date']} {booking['start_time']}-{booking['end_time']}",
#             callback_data=f"cancel_booking_{booking['id']}"
#         ))
#
#     await message.answer(
#         "Выберите бронирование для отмены:",
#         reply_markup=builder.as_markup()
#     )
#
#
# @dp.callback_query(F.data.startswith("cancel_booking_"))
# async def cancel_booking(callback: types.CallbackQuery):
#     booking_id = int(callback.data.replace("cancel_booking_", ""))
#     if storage.cancel_booking(booking_id):
#         await callback.message.edit_text(f"✅ Бронирование ID {booking_id} успешно отменено")
#     else:
#         await callback.message.edit_text("❌ Не удалось отменить бронирование")
#     await callback.answer()
#
#
# async def main():
#     await dp.start_polling(bot)
#
#
# if __name__ == "__main__":
#     asyncio.run(main())
from gsheets_manager import GoogleSheetsManager
from storage import JSONStorage
import threading
import asyncio
import threading
from datetime import datetime, timedelta
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
import json
import os
from pathlib import Path
from gsheets_manager import GoogleSheetsManager

BOT_TOKEN = "7807559906:AAFA0bsnb_Y6m3JHKIeWk2hZ3_ytMvnC-as"
BOOKINGS_FILE = "bookings.json"

SUBJECTS = {
    "math": "Математика",
    "inf": "Информатика",
    "rus": "Русский язык",
    "phys": "Физика"
}


class JSONStorage:
    def __init__(self, file_path=BOOKINGS_FILE):
        self.file_path = Path(file_path)
        self.lock = threading.Lock()
        self._ensure_file_exists()
        self.gsheets_manager = None

    def set_gsheets_manager(self, gsheets_manager):
        self.gsheets_manager = gsheets_manager

    def _ensure_file_exists(self):
        if not self.file_path.exists() or os.path.getsize(self.file_path) == 0:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def load(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def save(self, data):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        if self.gsheets_manager:
            try:
                self.gsheets_manager.update_all_sheets(data)
            except Exception as e:
                print(f"Google Sheets update error: {e}")

    def add_booking(self, booking_data):
        data = self.load()
        booking_data["id"] = len(data) + 1
        booking_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data.append(booking_data)
        self.save(data)
        return booking_data

    def get_user_bookings(self, user_id: int):
        data = self.load()
        return [b for b in data if b.get("user_id") == user_id]

    def get_user_role(self, user_id: int):
        data = self.load()
        user_bookings = [b for b in data if b.get("user_id") == user_id]
        if user_bookings:
            return user_bookings[0].get("user_role")
        return None

    def cancel_booking(self, booking_id: int):
        data = self.load()
        updated_data = [b for b in data if b.get("id") != booking_id]
        if len(data) != len(updated_data):
            self.save(updated_data)
            return True
        return False

    def update_user_subjects(self, user_id: int, subjects: list):
        data = self.load()
        updated = False
        for booking in data:
            if booking.get("user_id") == user_id and booking.get("user_role") == "teacher":
                booking["subjects"] = subjects
                updated = True

        if updated:
            self.save(data)
        return updated


# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
storage = JSONStorage(file_path=BOOKINGS_FILE)

# Настройка Google Sheets
try:
    gsheets = GoogleSheetsManager(
        credentials_file='credentials.json',
        spreadsheet_id='1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU'  # Замените на реальный ID
    )
    storage.set_gsheets_manager(gsheets)
    print("Google Sheets integration initialized successfully")

    # Принудительное обновление при старте
    initial_data = storage.load()
    gsheets.update_all_sheets(initial_data)
except Exception as e:
    print(f"Google Sheets initialization error: {e}")


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


def generate_time_slots():
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
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
        types.InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no"),
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


@dp.callback_query(BookingStates.SELECT_DATE, F.data.startswith("calendar_"))
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

    await state.update_data(time_end=time_end)

    role_text = "ученик" if data['user_role'] == 'student' else "преподаватель"

    if data['user_role'] == 'teacher':
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


@dp.callback_query(BookingStates.CONFIRMATION, F.data.in_(["confirm_yes", "confirm_no"]))
async def process_confirmation(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_yes":
        data = await state.get_data()
        booking_data = {
            "user_name": data['user_name'],
            "user_role": data['user_role'],
            "date": data['selected_date'].strftime("%Y-%m-%d"),
            "start_time": data['time_start'],
            "end_time": data['time_end'],
            "user_id": callback.from_user.id
        }

        if data['user_role'] == 'teacher':
            booking_data["subjects"] = data.get('subjects', [])
        else:
            booking_data["subject"] = data.get('subject', '')

        booking = storage.add_booking(booking_data)

        role_text = "ученик" if booking['user_role'] == 'student' else "преподаватель"

        if booking['user_role'] == 'teacher':
            subjects_text = ", ".join(SUBJECTS[subj] for subj in booking.get('subjects', []))
        else:
            subjects_text = SUBJECTS.get(booking.get('subject', ''), "Не указан")

        await callback.message.edit_text(
            "✅ Бронирование подтверждено!\n\n"
            f"👤 Ваше ФИО: {booking['user_name']}\n"
            f"👤 Ваша роль: {role_text}\n"
            f"📚 Предмет(ы): {subjects_text}\n"
            f"📅 Дата: {booking['date']}\n"
            f"⏰ Время: {booking['start_time']} - {booking['end_time']}\n\n"
            "Вы можете создать новое бронирование через меню"
        )
    else:
        await callback.message.edit_text("❌ Бронирование отменено")

    await state.clear()
    await callback.answer()


@dp.message(F.text == "📋 Мои бронирования")
@dp.message(Command("my_bookings"))
async def show_bookings(message: types.Message):
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


@dp.message(Command("my_role"))
async def show_role(message: types.Message):
    role = storage.get_user_role(message.from_user.id)
    if role:
        await message.answer(f"Ваша роль: {'ученик' if role == 'student' else 'преподаватель'}")
    else:
        await message.answer("Ваша роль еще не определена. Используйте /book чтобы установить роль.")


@dp.message(F.text == "❌ Отменить бронь")
async def start_cancel_booking(message: types.Message):
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


@dp.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    booking_id = int(callback.data.replace("cancel_booking_", ""))
    if storage.cancel_booking(booking_id):
        await callback.message.edit_text(f"✅ Бронирование ID {booking_id} успешно отменено")
    else:
        await callback.message.edit_text("❌ Не удалось отменить бронирование")
    await callback.answer()


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())