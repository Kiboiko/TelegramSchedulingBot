import logging
from datetime import datetime, timedelta
from typing import Optional, List

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, 
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from storage import JSONStorage  # Импортируем хранилище

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния FSM
class BookingStates(StatesGroup):
    selecting_date = State()
    selecting_time = State()
    confirming = State()

class BookingBot:
    def __init__(self, token: str, storage: JSONStorage):
        self.bot = Bot(token=token)
        self.storage = storage
        self.dp = Dispatcher()
        self.router = Router()
        self.dp.include_router(self.router)
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        # Команды
        self.router.message.register(self.start, CommandStart())
        self.router.message.register(self.help, Command("help"))
        self.router.message.register(self.my_bookings, Command("my_bookings"))
        self.router.message.register(self.cancel_booking, Command("cancel_booking"))
        
        # Обработка бронирования
        self.router.message.register(self.book_start, Command("book"))
        self.router.callback_query.register(
            self.select_date, 
            F.data.startswith("date_"), 
            BookingStates.selecting_date
        )
        self.router.callback_query.register(
            self.select_time, 
            F.data.startswith("time_"), 
            BookingStates.selecting_time
        )
        self.router.callback_query.register(
            self.confirm_booking, 
            F.data.startswith("confirm_"), 
            BookingStates.confirming
        )
        self.router.callback_query.register(
            self.cancel_booking_process, 
            F.data.startswith("cancel_")
        )
        
        # Любые другие сообщения
        self.router.message.register(self.handle_message)
    
    async def start(self, message: Message):
        """Обработчик команды /start"""
        await message.answer(
            f"Привет, {message.from_user.first_name}!\n\n"
            "Я бот для бронирования времени. Вот что ты можешь сделать:\n"
            "/book - Забронировать время\n"
            "/my_bookings - Посмотреть свои брони\n"
            "/cancel_booking - Отменить бронь\n"
            "/help - Помощь"
        )
    
    async def help(self, message: Message):
        """Обработчик команды /help"""
        await message.answer(
            "Помощь по боту:\n\n"
            "/book - Начать процесс бронирования\n"
            "/my_bookings - Показать ваши текущие брони\n"
            "/cancel_booking - Отменить существующую бронь\n\n"
            "Выберите действие из меню или нажмите /start для возврата в главное меню."
        )
    
    async def book_start(self, message: Message, state: FSMContext):
        """Начало процесса бронирования"""
        available_dates = self._generate_available_dates()
        
        builder = InlineKeyboardBuilder()
        for date in available_dates:
            builder.button(
                text=date.strftime("%d.%m.%Y"), 
                callback_data=f"date_{date.strftime('%Y-%m-%d')}"
            )
        builder.adjust(2)
        
        await message.answer(
            "Выберите дату для бронирования:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.selecting_date)
    
    async def select_date(self, callback: CallbackQuery, state: FSMContext):
        """Обработка выбора даты"""
        selected_date = callback.data.split("_")[1]
        await state.update_data(selected_date=selected_date)
        
        available_slots = self.storage.get_available_slots(selected_date)
        
        if not available_slots:
            await callback.message.edit_text(
                "На выбранную дату нет свободных слотов. Пожалуйста, выберите другую дату."
            )
            return
        
        builder = InlineKeyboardBuilder()
        for slot in available_slots:
            builder.button(text=slot, callback_data=f"time_{slot}")
        builder.adjust(2)
        
        await callback.message.edit_text(
            f"Выбрана дата: {selected_date}\nВыберите время:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.selecting_time)
        await callback.answer()
    
    async def select_time(self, callback: CallbackQuery, state: FSMContext):
        """Обработка выбора времени"""
        selected_time = callback.data.split("_")[1]
        await state.update_data(selected_time=selected_time)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Подтвердить", callback_data="confirm_1")
        builder.button(text="❌ Отменить", callback_data="cancel_1")
        
        data = await state.get_data()
        await callback.message.edit_text(
            f"Вы выбрали:\nДата: {data['selected_date']}\nВремя: {selected_time}\n\nПодтвердить бронирование?",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.confirming)
        await callback.answer()
    
    async def confirm_booking(self, callback: CallbackQuery, state: FSMContext):
        """Подтверждение бронирования"""
        user_id = callback.from_user.id
        data = await state.get_data()
        
        success = self.storage.book_slot(
            user_id, 
            f"{data['selected_date']} {data['selected_time']}"
        )
        
        if success:
            await callback.message.edit_text(
                "✅ Бронирование успешно завершено!\n\n"
                f"Дата: {data['selected_date']}\n"
                f"Время: {data['selected_time']}\n\n"
                "Вы можете посмотреть свои брони с помощью команды /my_bookings"
            )
            
            # Уведомление о бронировании
            await self.bot.send_message(
                chat_id=user_id,
                text=f"Вы успешно забронировали время на {data['selected_date']} в {data['selected_time']}!"
            )
        else:
            await callback.message.edit_text(
                "❌ Не удалось завершить бронирование. Возможно, это время уже занято. Попробуйте выбрать другое время."
            )
        
        await state.clear()
        await callback.answer()
    
    async def cancel_booking_process(self, callback: CallbackQuery, state: FSMContext):
        """Отмена процесса бронирования"""
        await callback.message.edit_text("Бронирование отменено.")
        await state.clear()
        await callback.answer()
    
    async def my_bookings(self, message: Message):
        """Показывает текущие брони пользователя"""
        bookings = self.storage.get_user_bookings(message.from_user.id)
        
        if not bookings:
            await message.answer("У вас нет активных бронирований.")
            return
        
        text = "Ваши бронирования:\n\n"
        for idx, booking in enumerate(bookings, 1):
            text += f"{idx}. {booking['date']} {booking['time']}\n"
        
        await message.answer(text)
    
    async def cancel_booking(self, message: Message):
        """Отмена существующей брони"""
        bookings = self.storage.get_user_bookings(message.from_user.id)
        
        if not bookings:
            await message.answer("У вас нет активных бронирований для отмены.")
            return
        
        builder = InlineKeyboardBuilder()
        for booking in bookings:
            builder.button(
                text=f"{booking['date']} {booking['time']}", 
                callback_data=f"cancel_{booking['id']}"
            )
        builder.adjust(1)
        
        await message.answer(
            "Выберите бронирование для отмены:",
            reply_markup=builder.as_markup()
        )
    
    async def handle_message(self, message: Message):
        """Обработка любых других сообщений"""
        await message.answer(
            "Я не понимаю эту команду. Пожалуйста, используйте /help для списка доступных команд."
        )
    
    def _generate_available_dates(self) -> List[datetime.date]:
        """Генерирует список доступных дат (на 2 недели вперёд)"""
        today = datetime.now().date()
        return [today + timedelta(days=i) for i in range(1, 15)]
    
    async def run(self):
        """Запуск бота"""
        await self.dp.start_polling(self.bot)