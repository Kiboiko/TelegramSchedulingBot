# import logging
# from datetime import datetime, timedelta
# from typing import Optional, List
#
# from aiogram import Bot, Dispatcher, F, Router
# from aiogram.filters import Command, CommandStart
# from aiogram.types import (
#     Message,
#     CallbackQuery,
#     InlineKeyboardButton,
#     InlineKeyboardMarkup
# )
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import State, StatesGroup
# from aiogram.utils.keyboard import InlineKeyboardBuilder
#
# from storage import JSONStorage  # Импортируем хранилище
#
# # Настройка логгирования
# logging.basicConfig(
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     level=logging.INFO
# )
# logger = logging.getLogger(__name__)
#
# # Состояния FSM
# class BookingStates(StatesGroup):
#     selecting_date = State()
#     selecting_time = State()
#     confirming = State()
#
# class BookingBot:
#     def __init__(self, token: str, storage: JSONStorage):
#         self.bot = Bot(token=token)
#         self.storage = storage
#         self.dp = Dispatcher()
#         self.router = Router()
#         self.dp.include_router(self.router)
#
#         self._setup_handlers()
#
#     def _setup_handlers(self):
#         # Команды
#         self.router.message.register(self.start, CommandStart())
#         self.router.message.register(self.help, Command("help"))
#         self.router.message.register(self.my_bookings, Command("my_bookings"))
#         self.router.message.register(self.cancel_booking, Command("cancel_booking"))
#
#         # Обработка бронирования
#         self.router.message.register(self.book_start, Command("book"))
#         self.router.callback_query.register(
#             self.select_date,
#             F.data.startswith("date_"),
#             BookingStates.selecting_date
#         )
#         self.router.callback_query.register(
#             self.select_time,
#             F.data.startswith("time_"),
#             BookingStates.selecting_time
#         )
#         self.router.callback_query.register(
#             self.confirm_booking,
#             F.data.startswith("confirm_"),
#             BookingStates.confirming
#         )
#         self.router.callback_query.register(
#             self.cancel_booking_process,
#             F.data.startswith("cancel_")
#         )
#
#         # Любые другие сообщения
#         self.router.message.register(self.handle_message)
#
#     async def start(self, message: Message):
#         """Обработчик команды /start"""
#         await message.answer(
#             f"Привет, {message.from_user.first_name}!\n\n"
#             "Я бот для бронирования времени. Вот что ты можешь сделать:\n"
#             "/book - Забронировать время\n"
#             "/my_bookings - Посмотреть свои брони\n"
#             "/cancel_booking - Отменить бронь\n"
#             "/help - Помощь"
#         )
#
#     async def help(self, message: Message):
#         """Обработчик команды /help"""
#         await message.answer(
#             "Помощь по боту:\n\n"
#             "/book - Начать процесс бронирования\n"
#             "/my_bookings - Показать ваши текущие брони\n"
#             "/cancel_booking - Отменить существующую бронь\n\n"
#             "Выберите действие из меню или нажмите /start для возврата в главное меню."
#         )
#
#     async def book_start(self, message: Message, state: FSMContext):
#         """Начало процесса бронирования"""
#         available_dates = self._generate_available_dates()
#
#         builder = InlineKeyboardBuilder()
#         for date in available_dates:
#             builder.button(
#                 text=date.strftime("%d.%m.%Y"),
#                 callback_data=f"date_{date.strftime('%Y-%m-%d')}"
#             )
#         builder.adjust(2)
#
#         await message.answer(
#             "Выберите дату для бронирования:",
#             reply_markup=builder.as_markup()
#         )
#         await state.set_state(BookingStates.selecting_date)
#
#     async def select_date(self, callback: CallbackQuery, state: FSMContext):
#         """Обработка выбора даты"""
#         selected_date = callback.data.split("_")[1]
#         await state.update_data(selected_date=selected_date)
#
#         available_slots = self.storage.get_available_slots(selected_date)
#
#         if not available_slots:
#             await callback.message.edit_text(
#                 "На выбранную дату нет свободных слотов. Пожалуйста, выберите другую дату."
#             )
#             return
#
#         builder = InlineKeyboardBuilder()
#         for slot in available_slots:
#             builder.button(text=slot, callback_data=f"time_{slot}")
#         builder.adjust(2)
#
#         await callback.message.edit_text(
#             f"Выбрана дата: {selected_date}\nВыберите время:",
#             reply_markup=builder.as_markup()
#         )
#         await state.set_state(BookingStates.selecting_time)
#         await callback.answer()
#
#     async def select_time(self, callback: CallbackQuery, state: FSMContext):
#         """Обработка выбора времени"""
#         selected_time = callback.data.split("_")[1]
#         await state.update_data(selected_time=selected_time)
#
#         builder = InlineKeyboardBuilder()
#         builder.button(text="✅ Подтвердить", callback_data="confirm_1")
#         builder.button(text="❌ Отменить", callback_data="cancel_1")
#
#         data = await state.get_data()
#         await callback.message.edit_text(
#             f"Вы выбрали:\nДата: {data['selected_date']}\nВремя: {selected_time}\n\nПодтвердить бронирование?",
#             reply_markup=builder.as_markup()
#         )
#         await state.set_state(BookingStates.confirming)
#         await callback.answer()
#
#     async def confirm_booking(self, callback: CallbackQuery, state: FSMContext):
#         """Подтверждение бронирования"""
#         user_id = callback.from_user.id
#         data = await state.get_data()
#
#         success = self.storage.book_slot(
#             user_id,
#             f"{data['selected_date']} {data['selected_time']}"
#         )
#
#         if success:
#             await callback.message.edit_text(
#                 "✅ Бронирование успешно завершено!\n\n"
#                 f"Дата: {data['selected_date']}\n"
#                 f"Время: {data['selected_time']}\n\n"
#                 "Вы можете посмотреть свои брони с помощью команды /my_bookings"
#             )
#
#             # Уведомление о бронировании
#             await self.bot.send_message(
#                 chat_id=user_id,
#                 text=f"Вы успешно забронировали время на {data['selected_date']} в {data['selected_time']}!"
#             )
#         else:
#             await callback.message.edit_text(
#                 "❌ Не удалось завершить бронирование. Возможно, это время уже занято. Попробуйте выбрать другое время."
#             )
#
#         await state.clear()
#         await callback.answer()
#
#     async def cancel_booking_process(self, callback: CallbackQuery, state: FSMContext):
#         """Отмена процесса бронирования"""
#         await callback.message.edit_text("Бронирование отменено.")
#         await state.clear()
#         await callback.answer()
#
#     async def my_bookings(self, message: Message):
#         """Показывает текущие брони пользователя"""
#         bookings = self.storage.get_user_bookings(message.from_user.id)
#
#         if not bookings:
#             await message.answer("У вас нет активных бронирований.")
#             return
#
#         text = "Ваши бронирования:\n\n"
#         for idx, booking in enumerate(bookings, 1):
#             text += f"{idx}. {booking['date']} {booking['time']}\n"
#
#         await message.answer(text)
#
#     async def cancel_booking(self, message: Message):
#         """Отмена существующей брони"""
#         bookings = self.storage.get_user_bookings(message.from_user.id)
#
#         if not bookings:
#             await message.answer("У вас нет активных бронирований для отмены.")
#             return
#
#         builder = InlineKeyboardBuilder()
#         for booking in bookings:
#             builder.button(
#                 text=f"{booking['date']} {booking['time']}",
#                 callback_data=f"cancel_{booking['id']}"
#             )
#         builder.adjust(1)
#
#         await message.answer(
#             "Выберите бронирование для отмены:",
#             reply_markup=builder.as_markup()
#         )
#
#     async def handle_message(self, message: Message):
#         """Обработка любых других сообщений"""
#         await message.answer(
#             "Я не понимаю эту команду. Пожалуйста, используйте /help для списка доступных команд."
#         )
#
#     def _generate_available_dates(self) -> List[datetime.date]:
#         """Генерирует список доступных дат (на 2 недели вперёд)"""
#         today = datetime.now().date()
#         return [today + timedelta(days=i) for i in range(1, 15)]
#
#     async def run(self):
#         """Запуск бота"""
#         await self.dp.start_polling(self.bot)
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BookingStates(StatesGroup):
    SELECT_ROLE = State()
    INPUT_TEACHER_NAME = State()
    SELECT_DATE = State()
    SELECT_START_TIME = State()
    SELECT_END_TIME = State()
    CONFIRMATION = State()


class BookingHandlers:
    def __init__(self, storage):
        self.router = Router()
        self.storage = storage
        self._setup_handlers()

    def _setup_handlers(self):
        self.router.message.register(self.start_handler, CommandStart())
        self.router.message.register(self.help_handler, Command("help"))
        self.router.message.register(self.book_handler, Command("book"))
        self.router.message.register(self.my_bookings_handler, Command("my_bookings"))
        self.router.message.register(self.my_role_handler, Command("my_role"))

        self.router.callback_query.register(self.process_role_selection, F.data.startswith("role_"))
        self.router.message.register(self.process_teacher_name, BookingStates.INPUT_TEACHER_NAME)
        self.router.callback_query.register(self.process_calendar, F.data.startswith("calendar_"),
                                            BookingStates.SELECT_DATE)
        self.router.callback_query.register(self.process_start_time, BookingStates.SELECT_START_TIME)
        self.router.callback_query.register(self.process_end_time, BookingStates.SELECT_END_TIME)
        self.router.callback_query.register(self.process_confirmation, BookingStates.CONFIRMATION)
        self.router.callback_query.register(self.cancel_booking_handler, F.data.startswith("cancel_"))

    async def start_handler(self, message: Message):
        await message.answer(
            "Добро пожаловать в систему бронирования преподавателей!\n\n"
            "Используйте команды:\n"
            "/book - начать новое бронирование\n"
            "/my_bookings - посмотреть свои бронирования\n"
            "/my_role - узнать свою роль\n"
            "/help - показать справку"
        )

    async def help_handler(self, message: Message):
        await message.answer(
            "📋 Справка по боту:\n\n"
            "/book - начать процесс бронирования\n"
            " 1. Выбрать роль (ученик/преподаватель)\n"
            " 2. Ввести ФИО преподавателя (для учеников)\n"
            " 3. Выбрать дату из календаря\n"
            " 4. Выбрать время начала и окончания\n"
            " 5. Подтвердить бронирование\n\n"
            "/my_bookings - показать ваши бронирования\n"
            "/my_role - показать вашу роль\n"
            "/help - показать эту справку"
        )

    async def book_handler(self, message: Message, state: FSMContext):
        builder = InlineKeyboardBuilder()
        builder.button(text="👨‍🎓 Я ученик", callback_data="role_student")
        builder.button(text="👨‍🏫 Я преподаватель", callback_data="role_teacher")
        await message.answer(
            "Перед началом бронирования, пожалуйста, укажите вашу роль:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.SELECT_ROLE)

    async def process_role_selection(self, callback: CallbackQuery, state: FSMContext):
        role = callback.data.split("_")[1]
        await state.update_data(user_role=role)

        if role == "student":
            await callback.message.edit_text("Введите полное ФИО преподавателя:")
            await state.set_state(BookingStates.INPUT_TEACHER_NAME)
        else:
            await state.update_data(teacher_name="Я преподаватель")
            await self.show_calendar(callback.message, state)
            await state.set_state(BookingStates.SELECT_DATE)

        await callback.answer()

    async def process_teacher_name(self, message: Message, state: FSMContext):
        teacher_name = message.text.strip()
        if len(teacher_name.split()) < 2:
            await message.answer("Пожалуйста, введите полное ФИО (минимум имя и фамилию)")
            return

        await state.update_data(teacher_name=teacher_name)
        await self.show_calendar(message, state)
        await state.set_state(BookingStates.SELECT_DATE)

    async def show_calendar(self, message: Message, state: FSMContext, year: int = None, month: int = None):
        now = datetime.now()
        year = year or now.year
        month = month or now.month

        builder = InlineKeyboardBuilder()
        month_name = datetime(year, month, 1).strftime("%B %Y")
        builder.row(InlineKeyboardButton(text=month_name, callback_data="ignore"))

        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        builder.row(*[InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])

        first_day = datetime(year, month, 1)
        start_weekday = first_day.weekday()
        days_in_month = (datetime(year, month + 1, 1) - first_day).days if month < 12 else 31

        buttons = []
        for _ in range(start_weekday):
            buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

        for day in range(1, days_in_month + 1):
            date = datetime(year, month, day)
            if date.date() < datetime.now().date():
                buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                buttons.append(InlineKeyboardButton(
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
            InlineKeyboardButton(text="⬅️", callback_data=f"calendar_change_{prev_year}-{prev_month}"),
            InlineKeyboardButton(text="➡️", callback_data=f"calendar_change_{next_year}-{next_month}"),
        )

        await message.answer("Выберите дату занятия:", reply_markup=builder.as_markup())

    async def process_calendar(self, callback: CallbackQuery, state: FSMContext):
        data = callback.data

        if data.startswith("calendar_day_"):
            date_str = data.replace("calendar_day_", "")
            year, month, day = map(int, date_str.split("-"))
            selected_date = datetime(year, month, day).date()

            await state.update_data(date=selected_date.strftime("%Y-%m-%d"))
            await callback.message.edit_text(f"Выбрана дата: {day}.{month}.{year}")
            await callback.message.answer(
                "Выберите время начала занятия:",
                reply_markup=self._generate_time_keyboard()
            )
            await state.set_state(BookingStates.SELECT_START_TIME)
            await callback.answer()

        elif data.startswith("calendar_change_"):
            date_str = data.replace("calendar_change_", "")
            year, month = map(int, date_str.split("-"))
            await callback.message.edit_reply_markup(
                reply_markup=(await self._generate_calendar_keyboard(year, month))
            )
            await callback.answer()

    def _generate_time_keyboard(self):
        builder = InlineKeyboardBuilder()
        start_time = datetime.strptime("09:00", "%H:%M")
        end_time = datetime.strptime("20:00", "%H:%M")
        current_time = start_time

        while current_time <= end_time:
            time_str = current_time.strftime("%H:%M")
            builder.button(text=time_str, callback_data=f"time_{time_str}")
            current_time += timedelta(minutes=30)

        builder.adjust(4)
        return builder.as_markup()

    async def process_start_time(self, callback: CallbackQuery, state: FSMContext):
        start_time = callback.data.split("_")[1]
        await state.update_data(start_time=start_time)
        await callback.message.edit_text(f"Выбрано время начала: {start_time}\nВыберите время окончания:")
        await callback.message.edit_reply_markup(reply_markup=self._generate_time_keyboard())
        await state.set_state(BookingStates.SELECT_END_TIME)
        await callback.answer()

    async def process_end_time(self, callback: CallbackQuery, state: FSMContext):
        end_time = callback.data.split("_")[1]
        data = await state.get_data()
        start_time = data['start_time']

        if datetime.strptime(end_time, "%H:%M") <= datetime.strptime(start_time, "%H:%M"):
            await callback.answer("Время окончания должно быть позже времени начала!", show_alert=True)
            return

        await state.update_data(end_time=end_time)

        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no")
        ]])

        await callback.message.edit_text(
            f"📋 Подтвердите бронирование:\n\n"
            f"👨‍🏫 Преподаватель: {data['teacher_name']}\n"
            f"📅 Дата: {data['date']}\n"
            f"⏰ Время: {start_time} - {end_time}\n"
            f"👤 Ваша роль: {'ученик' if data['user_role'] == 'student' else 'преподаватель'}",
            reply_markup=confirm_kb
        )
        await state.set_state(BookingStates.CONFIRMATION)
        await callback.answer()

    async def process_confirmation(self, callback: CallbackQuery, state: FSMContext):
        if callback.data == "confirm_yes":
            data = await state.get_data()
            booking = {
                "teacher_name": data['teacher_name'],
                "date": data['date'],
                "start_time": data['start_time'],
                "end_time": data['end_time'],
                "user_id": callback.from_user.id,
                "user_role": data['user_role'],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.storage.add_booking(booking)

            await callback.message.edit_text(
                "✅ Бронирование успешно сохранено!\n\n"
                f"👨‍🏫 Преподаватель: {data['teacher_name']}\n"
                f"📅 Дата: {data['date']}\n"
                f"⏰ Время: {data['start_time']} - {data['end_time']}\n"
                f"👤 Ваша роль: {'ученик' if data['user_role'] == 'student' else 'преподаватель'}\n\n"
                "Для нового бронирования используйте /book"
            )
        else:
            await callback.message.edit_text("❌ Бронирование отменено")

        await state.clear()
        await callback.answer()

    async def my_bookings_handler(self, message: Message):
        bookings = self.storage.get_user_bookings(message.from_user.id)
        if not bookings:
            await message.answer("У вас нет активных бронирований.")
            return

        text = "Ваши бронирования:\n\n"
        for booking in bookings:
            text += (
                f"👨‍🏫 Преподаватель: {booking['teacher_name']}\n"
                f"📅 Дата: {booking['date']}\n"
                f"⏰ Время: {booking['start_time']} - {booking['end_time']}\n"
                f"👤 Ваша роль: {'ученик' if booking.get('user_role') == 'student' else 'преподаватель'}\n"
                f"🆔 ID: {booking['id']}\n\n"
            )

        await message.answer(text)

    async def my_role_handler(self, message: Message):
        role = self.storage.get_user_role(message.from_user.id)
        if role:
            await message.answer(f"Ваша роль: {'ученик' if role == 'student' else 'преподаватель'}")
        else:
            await message.answer("Ваша роль еще не определена. Используйте /book чтобы установить роль.")

    async def cancel_booking_handler(self, callback: CallbackQuery):
        booking_id = int(callback.data.replace("cancel_", ""))
        if self.storage.cancel_booking(booking_id):
            await callback.message.edit_text(f"✅ Бронирование ID {booking_id} успешно отменено")
        else:
            await callback.message.edit_text("❌ Не удалось отменить бронирование")
        await callback.answer()