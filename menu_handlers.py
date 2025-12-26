# menu_handlers.py
from aiogram import types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardMarkup, KeyboardButton
import logging
from config import is_admin
from states import BookingStates
import logging

logger = logging.getLogger(__name__)

# Меню для пользователей без ролей
no_roles_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Обратиться к администратору")],
        [KeyboardButton(text="🔄 Проверить наличие ролей")],
    ],
    resize_keyboard=True
)


async def generate_main_menu(user_id: int, storage) -> ReplyKeyboardMarkup:
    # ВАЖНО: Вызываем асинхронный метод напрямую, так как мы в async контексте
    if storage.db and storage.db.pool:
        roles = await storage.db.get_user_roles(user_id)
        logger.info(f"generate_main_menu: fetched roles from DB for {user_id}: {roles}")
    else:
        roles = storage.get_user_roles(user_id)
        logger.info(f"generate_main_menu: fetched roles from storage for {user_id}: {roles}")

    if not roles:
        # Если пользователь — администратор, показываем дополнительные кнопки
        if is_admin(user_id):
            keyboard_buttons = [
                [KeyboardButton(text="❓ Обратиться к администратору")],
                [KeyboardButton(text="🔄 Проверить наличие ролей")],
                [KeyboardButton(text="➕ Добавить роль пользователю")],
                [KeyboardButton(text="➖ Удалить роль пользователю")],
            ]
            logger.info(f"generate_main_menu: user {user_id} is admin and has no roles — returning admin menu")
            return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
        logger.info(f"generate_main_menu: no roles for {user_id}, returning no_roles_menu")
        return no_roles_menu

    keyboard_buttons = []

    # Проверяем, может ли пользователь бронировать
    can_book = any(role in roles for role in ['teacher', 'parent']) or (
            'student' in roles and 'parent' in roles
    )

    if can_book:
        keyboard_buttons.append([KeyboardButton(text="📅 Забронировать время")])

    # КНОПКА ДЛЯ РОДИТЕЛЕЙ - ДОБАВЛЯЕМ РЕБЕНКА
    if 'parent' in roles:
        keyboard_buttons.append([KeyboardButton(text="👶 Добавить ребенка")])
        keyboard_buttons.append([KeyboardButton(text="👨‍👩‍👧‍👦 Мои дети")])

    # Финансы и оплата
    if 'student' in roles or 'parent' in roles:
        keyboard_buttons.append([KeyboardButton(text="💰 Финансы")])
        keyboard_buttons.append([KeyboardButton(text="💳 Пополнить баланс")])

    # Общие кнопки
    keyboard_buttons.append([KeyboardButton(text="📋 Мои бронирования")])
    keyboard_buttons.append([KeyboardButton(text="📚 Прошедшие бронирования")])
    keyboard_buttons.append([KeyboardButton(text="👤 Моя роль")])
    keyboard_buttons.append([KeyboardButton(text="ℹ️ Помощь")])

    # Кнопки для админов
    if is_admin(user_id):
        keyboard_buttons.append([KeyboardButton(text="📊 Составить расписание")])
        keyboard_buttons.append([KeyboardButton(text="📚 Сгенерировать материалы")])
        keyboard_buttons.append([KeyboardButton(text="➕ Добавить роль пользователю")])
        keyboard_buttons.append([KeyboardButton(text="➖ Удалить роль пользователю")])
        keyboard_buttons.append([KeyboardButton(text="📝 Просмотреть отзывы")])

    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)


async def cmd_start(message: types.Message, state: FSMContext, storage):
    """Обработчик команды /start"""
    user_id = message.from_user.id

    # ВАЖНО: Вызываем асинхронный метод напрямую, так как мы в async контексте
    if storage.db and storage.db.pool:
        user_name = await storage.db.get_user_name_sync(user_id)
    else:
        user_name = storage.get_user_name(user_id)

    menu = await generate_main_menu(user_id, storage)

    # Debug: log menu type and keyboard rows to help diagnose missing keyboard
    try:
        rows = len(menu.keyboard) if hasattr(menu, 'keyboard') else 'N/A'
    except Exception:
        rows = 'err'
    logger.info(f"cmd_start: generated menu for {user_id}, menu_type={type(menu)}, rows={rows}")

    if user_name:
        # Проверяем роли для показа дополнительной информации
        if storage.db and storage.db.pool:
            roles = await storage.db.get_user_roles(user_id)
        else:
            roles = storage.get_user_roles(user_id)

        welcome_text = f"С возвращением, {user_name}!\nИспользуйте кнопки ниже для навигации:"

        # Дополнительная информация для родителей
        if 'parent' in roles:
            welcome_text += "\n\n👶 <b>Вы родитель!</b>\n"
            welcome_text += "• Добавляйте детей через '👶 Добавить ребенка'\n"
            welcome_text += "• Смотрите список через '👨‍👩‍👧‍👦 Мои дети'"

        await message.answer(
            welcome_text,
            parse_mode="HTML",  # Используем HTML
            reply_markup=menu
        )
    else:
        await message.answer(
            "Добро пожаловать в систему бронирования!\n"
            "Введите ваши имя и фамилию для регистрации:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(BookingStates.INPUT_NAME)

async def check_roles(message: types.Message, state: FSMContext, storage):
    """Обработчик кнопки проверки ролей - выполняет команду /start"""
    await cmd_start(message, state, storage)

async def show_my_role(message: types.Message, storage):
    """Показывает роли пользователя"""
    user_id = message.from_user.id
    
    # ВАЖНО: Вызываем асинхронный метод напрямую, так как мы в async контексте
    if storage.db and storage.db.pool:
        roles = await storage.db.get_user_roles(user_id)
    else:
        roles = storage.get_user_roles(user_id)
    
    logger.info("Найденные роли: " + ",".join(role for role in roles))
    logger.info("ID для поиска: " + str(user_id))

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

async def back_to_menu_handler(callback: types.CallbackQuery, storage):
    """Обработчик возврата в главное меню"""
    user_id = callback.from_user.id
    menu = await generate_main_menu(user_id, storage)

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
                reply_markup=keyboard.as_markup()  # Add .as_markup() here
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
                reply_markup=keyboard.as_markup()  # Add .as_markup() here
            )
        else:
            await callback.message.edit_text("У вас нет прошедших бронирований")
            await callback.answer()
    return back_to_past_bookings_handler

async def back_to_menu_from_past_handler(callback: types.CallbackQuery, storage):
    """Обработчик возврата в меню из раздела прошедших бронирований"""
    user_id = callback.from_user.id
    menu = await generate_main_menu(user_id, storage)

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
def register_menu_handlers(dp, booking_manager, storage):
    """Регистрирует все обработчики меню в диспетчере"""

    # Создаем обработчики с booking_manager
    show_bookings_handler = create_bookings_handler(booking_manager)
    show_past_bookings_handler = create_past_bookings_handler(booking_manager)
    back_to_bookings_handler = create_back_to_bookings_handler(booking_manager)
    back_to_past_bookings_handler = create_back_to_past_bookings_handler(booking_manager)

    # Создаем обертки для обработчиков, которым нужен storage
    async def wrapped_cmd_start(message: types.Message, state: FSMContext):
        return await cmd_start(message, state, storage)

    async def wrapped_check_roles(message: types.Message, state: FSMContext):
        return await check_roles(message, state, storage)

    async def wrapped_show_my_role(message: types.Message):
        return await show_my_role(message, storage)

    async def wrapped_back_to_menu_handler(callback: types.CallbackQuery):
        return await back_to_menu_handler(callback, storage)

    async def wrapped_back_to_menu_from_past_handler(callback: types.CallbackQuery):
        return await back_to_menu_from_past_handler(callback, storage)

    # Создаем обработчик для кнопки "Мои дети"
    async def show_my_children_handler(message: types.Message):
        """Показывает список детей родителя"""
        user_id = message.from_user.id

        if storage.db and storage.db.pool:
            user_roles = await storage.db.get_user_roles(user_id)
        else:
            user_roles = storage.get_user_roles(user_id)

        if 'parent' not in user_roles:
            await message.answer("❌ У вас нет роли родителя")
            return

        if storage.db and storage.db.pool:
            children_ids = await storage.db.get_parent_children_sync(user_id)
        else:
            children_ids = storage.get_parent_children(user_id)

        if not children_ids:
            await message.answer(
                "👶 У вас еще нет привязанных детей.\n\n"
                "Используйте кнопку '👶 Добавить ребенка' чтобы добавить ребенка."
            )
            return

        children_info = []
        for child_id in children_ids:
            if storage.db and storage.db.pool:
                child_data = await storage.db.get_user(child_id)
                child_name = child_data.get('user_name', f'Ребенок {child_id}') if child_data else f'Ребенок {child_id}'

                # Получаем предметы ребенка
                subjects = await storage.db.get_available_subjects_for_student_sync(child_id)
                subject_names = [subjects.get(s, s) for s in subjects]

                children_info.append(
                    f"👶 <b>{child_name}</b>\n"
                    f"🆔 <b>ID:</b> {child_id}\n"
                    f"🎯 <b>Предметы:</b> {', '.join(subject_names) if subject_names else 'не назначены'}\n"
                    f"────────────────────"
                )

        await message.answer(
            f"👨‍👩‍👧‍👦 <b>Ваши дети:</b>\n\n" + "\n\n".join(children_info),
            parse_mode="HTML"
        )

    # Команды
    dp.message.register(wrapped_cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(wrapped_show_my_role, Command("my_role"))
    dp.message.register(cmd_pay, Command("pay"))

    # Текстовые обработчики меню
    dp.message.register(wrapped_check_roles, F.text == "🔄 Проверить наличие ролей")
    dp.message.register(wrapped_show_my_role, F.text == "👤 Моя роль")
    dp.message.register(show_help, F.text == "ℹ️ Помощь")
    dp.message.register(contact_admin, F.text == "❓ Обратиться к администратору")
    dp.message.register(show_bookings_handler, F.text == "📋 Мои бронирования")
    dp.message.register(show_past_bookings_handler, F.text == "📚 Прошедшие бронирования")

    # Обработчик для кнопки "Мои дети" (ОН ОСТАЕТСЯ)
    dp.message.register(show_my_children_handler, F.text == "👨‍👩‍👧‍👦 Мои дети")

    # Обработчик для кнопки "👶 Добавить ребенка" УДАЛЕН отсюда!
    # Он должен быть только в main.py

    # Callback обработчики навигации
    dp.callback_query.register(
        wrapped_back_to_menu_handler,
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
        wrapped_back_to_menu_from_past_handler,
        F.data == "back_to_menu_from_past"
    )


async def show_my_role(message: types.Message, storage):
    """Показывает роли пользователя"""
    user_id = message.from_user.id

    # ВАЖНО: Вызываем асинхронный метод напрямую, так как мы в async контексте
    if storage.db and storage.db.pool:
        roles = await storage.db.get_user_roles(user_id)
    else:
        roles = storage.get_user_roles(user_id)

    logger.info("Найденные роли: " + ",".join(role for role in roles))
    logger.info("ID для поиска: " + str(user_id))

    if roles:
        role_translations = {
            "teacher": "👨‍🏫 преподаватель",
            "student": "👨‍🎓 ученик",
            "parent": "👨‍👩‍👧‍👦 родитель"
        }
        role_text = ", ".join([role_translations.get(role, role) for role in roles])

        # Дополнительные инструкции для родителей
        message_text = f"🎯 Ваши роли: {role_text}"

        if 'parent' in roles:
            message_text += "\n\n👶 *Вы родитель!*\n"
            message_text += "Используйте кнопки:\n"
            message_text += "• '👶 Добавить ребенка' - добавить детей\n"
            message_text += "• '👨‍👩‍👧‍👦 Мои дети' - посмотреть список детей"

        await message.answer(
            message_text,
            parse_mode="Markdown" if 'parent' in roles else None,
            reply_markup=await generate_main_menu(user_id, storage)  # ПОКАЗЫВАЕМ ОБНОВЛЕННОЕ МЕНЮ!
        )
    else:
        await message.answer(
            "Ваши роли еще не назначены. Обратитесь к администратору. \n Телефон администратора: +79001372727",
            reply_markup=await generate_main_menu(user_id, storage)
        )

async def cmd_pay(message: types.Message, state: FSMContext):
    """Обработчик команды оплаты"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_payment_start(message, state)

