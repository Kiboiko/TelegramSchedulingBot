# menu_handlers.py
from aiogram import types,F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardMarkup, KeyboardButton
import logging
from config import is_admin
from storage import JSONStorage
from states import BookingStates

logger = logging.getLogger(__name__)

# Создаем экземпляр storage - используем тот же путь, что в main.py
storage = JSONStorage(file_path="bookings.json")

# Меню для пользователей без ролей
no_roles_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Обратиться к администратору")],
        [KeyboardButton(text="🔄 Проверить наличие ролей")],
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
    keyboard_buttons.append([KeyboardButton(text="📚 Прошедшие бронирования")])
    keyboard_buttons.append([KeyboardButton(text="👤 Моя роль")])
    keyboard_buttons.append([KeyboardButton(text="ℹ️ Помощь")])

    # Добавляем кнопку составления расписания только для администраторов
    if is_admin(user_id):
        keyboard_buttons.append([KeyboardButton(text="📊 Составить расписание")])

    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)

async def cmd_start(message: types.Message, state: FSMContext):
    """Обработчик команды /start"""
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
            "Введите ваши имя и фамилию для регистрации:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(BookingStates.INPUT_NAME)

async def check_roles(message: types.Message, state: FSMContext):
    """Обработчик кнопки проверки ролей - выполняет команду /start"""
    await cmd_start(message, state)

async def show_my_role(message: types.Message):
    """Показывает роли пользователя"""
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
        await message.answer(
            "Ваши роли еще не назначены. Обратитесь к администратору. \n Телефон администратора: +79001372727")

async def show_help(message: types.Message):
    """Показывает справку"""
    await cmd_help(message)

async def cmd_help(message: types.Message):
    """Обработчик команды /help"""
    await message.answer(
        "📞 Для получения помощи обратитесь к администратору\n"
        "Телефон администратора: +79001372727.\n\n"
        "Доступные команды:\n"
        "/start - начать работу с ботом\n"
        "/help - показать эту справку\n"
        "/book - забронировать время\n"
        "/my_bookings - посмотреть свои бронирования\n"
        "/my_role - узнать свою роль"
    )

async def contact_admin(message: types.Message):
    """Обработчик обращения к администратору"""
    await message.answer(
        "📞 Для получения доступа к системе бронирования\n"
        "обратитесь к администратору \n Телефон администратора: +79001372727.\n\n"
        "После назначения ролей вы сможете пользоваться всеми функциями бота."
    )

# Создаем обертки для обработчиков, которые требуют booking_manager
def create_bookings_handler(booking_manager):
    async def show_bookings_handler(message: types.Message):
        """Показывает активные бронирования"""
        keyboard = booking_manager.generate_booking_list(message.from_user.id)
        if not keyboard:
            await message.answer("У вас нет активных бронирований")
            return

        await message.answer("Ваши бронирования (отсортированы по дате и времени):", 
                            reply_markup=keyboard.as_markup() if hasattr(keyboard, 'as_markup') else keyboard)
    return show_bookings_handler

def create_past_bookings_handler(booking_manager):
    async def show_past_bookings_handler(message: types.Message):
        """Показывает прошедшие бронирования"""
        keyboard = booking_manager.generate_past_bookings_list(message.from_user.id)
        if not keyboard:
            await message.answer("У вас нет прошедших бронирований")
            return

        await message.answer("📚 Ваши прошедшие бронирования:", 
                            reply_markup=keyboard.as_markup() if hasattr(keyboard, 'as_markup') else keyboard)
    return show_past_bookings_handler

async def back_to_menu_handler(callback: types.CallbackQuery):
    """Обработчик возврата в главное меню"""
    user_id = callback.from_user.id
    menu = await generate_main_menu(user_id)

    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=None
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=menu
    )
    await callback.answer()

# Создаем обертки для callback обработчиков, которые требуют booking_manager
def create_back_to_bookings_handler(booking_manager):
    async def back_to_bookings_handler(callback: types.CallbackQuery):
        """Обработчик возврата к списку бронирований"""
        user_id = callback.from_user.id
        keyboard = booking_manager.generate_booking_list(user_id)
        if keyboard:
            await callback.message.edit_text(
                "Ваши бронирования:",
                reply_markup=keyboard
            )
        else:
            await callback.message.edit_text("У вас нет активных бронирований")
        await callback.answer()
    return back_to_bookings_handler

def create_back_to_past_bookings_handler(booking_manager):
    async def back_to_past_bookings_handler(callback: types.CallbackQuery):
        """Обработчик возврата к списку прошедших бронирований"""
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
    return back_to_past_bookings_handler

async def back_to_menu_from_past_handler(callback: types.CallbackQuery):
    """Обработчик возврата в меню из раздела прошедших бронирований"""
    user_id = callback.from_user.id
    menu = await generate_main_menu(user_id)

    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=None
    )
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=menu
    )
    await callback.answer()

# Функция для регистрации обработчиков в диспетчере
def register_menu_handlers(dp, booking_manager):
    """Регистрирует все обработчики меню в диспетчере"""
    
    # Создаем обработчики с booking_manager
    show_bookings_handler = create_bookings_handler(booking_manager)
    show_past_bookings_handler = create_past_bookings_handler(booking_manager)
    back_to_bookings_handler = create_back_to_bookings_handler(booking_manager)
    back_to_past_bookings_handler = create_back_to_past_bookings_handler(booking_manager)
    
    # Команды
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(show_my_role, Command("my_role"))
    
    # Текстовые обработчики меню
    dp.message.register(check_roles, F.text == "🔄 Проверить наличие ролей")
    dp.message.register(show_my_role, F.text == "👤 Моя роль")
    dp.message.register(show_help, F.text == "ℹ️ Помощь")
    dp.message.register(contact_admin, F.text == "❓ Обратиться к администратору")
    dp.message.register(show_bookings_handler, F.text == "📋 Мои бронирования")
    dp.message.register(show_past_bookings_handler, F.text == "📚 Прошедшие бронирования")
    
    # Callback обработчики навигации
    dp.callback_query.register(
        back_to_menu_handler, 
        F.data == "back_to_menu"
    )
    dp.callback_query.register(
        back_to_bookings_handler,
        F.data == "back_to_bookings"
    )
    dp.callback_query.register(
        back_to_past_bookings_handler,
        F.data == "back_to_past_bookings"
    )
    dp.callback_query.register(
        back_to_menu_from_past_handler,
        F.data == "back_to_menu_from_past"
    )