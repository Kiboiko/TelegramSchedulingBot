# menu_handlers.py - УПРОЩЕННАЯ ВЕРСИЯ
from aiogram import types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardBuilder
import logging
from config import is_admin, ADMIN_IDS, SUBJECTS
from states import BookingStates
from datetime import datetime
from database import db

logger = logging.getLogger(__name__)

# Меню для пользователей без ролей
no_roles_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="❓ Обратиться к администратору")],
        [KeyboardButton(text="🔄 Проверить наличие ролей")],
    ],
    resize_keyboard=True
)


async def notify_admins_about_registration(bot, user_id: int, user_name: str):
    """Отправляет уведомление администраторам о новой заявке"""
    try:
        # Создаем клавиатуру для быстрого ответа
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="👨‍🎓 Назначить учеником",
                    callback_data=f"admin_quick_approve_student_{user_id}"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="👨‍🏫 Назначить преподавателем",
                    callback_data=f"admin_quick_approve_teacher_{user_id}"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="👨‍👩‍👧‍👦 Назначить родителем",
                    callback_data=f"admin_quick_approve_parent_{user_id}"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"admin_quick_reject_{user_id}"
                )
            ]
        ])

        message_text = (
            "🆕 *Новая заявка на регистрацию*\n\n"
            f"👤 Пользователь: {user_name}\n"
            f"🆔 ID: {user_id}\n"
            f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

        # Отправляем всем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    message_text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                logger.info(f"✅ Notification sent to admin {admin_id}")
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id}: {e}")

    except Exception as e:
        logger.error(f"Error in notify_admins_about_registration: {e}")


async def generate_main_menu(user_id: int, storage) -> ReplyKeyboardMarkup:
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

    # ДОБАВЬТЕ эту кнопку - возможность пополнения баланса
    if 'student' in roles or 'parent' in roles:
        keyboard_buttons.append([KeyboardButton(text="💰 Финансы")])
        keyboard_buttons.append([KeyboardButton(text="💳 Пополнить баланс")])

    keyboard_buttons.append([KeyboardButton(text="📋 Мои бронирования")])
    keyboard_buttons.append([KeyboardButton(text="📚 Прошедшие бронирования")])
    keyboard_buttons.append([KeyboardButton(text="👤 Моя роль")])
    keyboard_buttons.append([KeyboardButton(text="ℹ️ Помощь")])

    # Добавляем кнопки для администраторов
    if is_admin(user_id):
        keyboard_buttons.append([KeyboardButton(text="📊 Составить расписание")])
        keyboard_buttons.append([KeyboardButton(text="📚 Сгенерировать материалы")])

    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)


async def cmd_start(message: types.Message, state: FSMContext, storage):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    user_name = message.from_user.full_name

    logger.info(f"User {user_id} ({user_name}) started the bot")

    # Проверяем статус регистрации через БД
    try:
        # Используем синхронную обертку для совместимости
        reg_status = storage.get_user_registration_status_sync(user_id)
    except Exception as e:
        logger.error(f"Error getting registration status: {e}")
        reg_status = {'has_request': False, 'status': 'no_request'}

    logger.info(f"Registration status for {user_id}: {reg_status}")

    if reg_status.get('status') == 'approved':
        # Пользователь одобрен
        menu = await generate_main_menu(user_id, storage)

        # Получаем сохраненное имя пользователя из storage
        saved_name = storage.get_user_name(user_id)
        display_name = saved_name if saved_name else user_name

        await message.answer(
            f"👋 Добро пожаловать, {display_name}!\n\n"
            "Ваш аккаунт подтвержден администратором.\n"
            "Вы можете пользоваться всеми функциями бота.",
            reply_markup=menu
        )

        # Сохраняем имя пользователя, если еще не сохранено
        if not saved_name:
            storage.save_user_name(user_id, display_name)

    elif reg_status.get('status') == 'pending':
        # Заявка на рассмотрении
        await message.answer(
            f"⏳ Ваша заявка находится на рассмотрении.\n\n"
            f"Имя: {user_name}\n"
            f"ID: {user_id}\n\n"
            "Ожидайте решения администратора. Вы получите уведомление.",
            reply_markup=ReplyKeyboardRemove()
        )

    elif reg_status.get('status') == 'rejected':
        # Заявка отклонена
        notes = reg_status.get('notes', '')
        await message.answer(
            f"❌ Ваша заявка отклонена.\n\n"
            f"📝 Причина: {notes if notes else 'Не указана'}\n\n"
            "Свяжитесь с администратором:\n"
            f"📞 +79001372727",
            reply_markup=ReplyKeyboardRemove()
        )

    else:
        # Нет заявки, создаем новую
        await message.answer(
            f"👋 Привет, {user_name}!\n\n"
            "Добро пожаловать в систему записи на занятия!\n\n"
            "Для использования бота требуется регистрация.\n\n"
            "Введите ваше полное ФИО (как в паспорте):"
        )
        await state.set_state(BookingStates.INPUT_NAME)


async def process_name_registration(message: types.Message, state: FSMContext, storage, bot):
    """Обрабатывает ввод ФИО при регистрации"""
    try:
        user_id = message.from_user.id
        user_name = message.text.strip()

        if len(user_name.split()) < 2:
            await message.answer("❌ Введите полное ФИО (минимум имя и фамилия):")
            return

        # Сохраняем имя в storage
        storage.save_user_name(user_id, user_name)

        # Создаем заявку на регистрацию через БД
        try:
            request_id = await db.create_registration_request(user_id, user_name)
            logger.info(f"Registration request created: {request_id}")
        except Exception as e:
            logger.error(f"Error creating registration request: {e}")
            await message.answer("❌ Ошибка при создании заявки.")
            await state.clear()
            return

        # Уведомляем администраторов
        await notify_admins_about_registration(bot, user_id, user_name)

        await message.answer(
            f"✅ Спасибо, {user_name}!\n\n"
            "📨 Ваша заявка отправлена администратору.\n\n"
            "Что дальше:\n"
            "1. Администратор рассмотрит заявку\n"
            "2. Вам назначат роль и предметы\n"
            "3. Вы получите уведомление\n\n"
            "⏳ Обычно это занимает несколько часов.\n"
            "📞 Контакт: +79001372727",
            reply_markup=ReplyKeyboardRemove()
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Error in process_name_registration: {e}")
        await message.answer("❌ Ошибка. Попробуйте еще раз.")
        await state.clear()


async def process_name_booking(message: types.Message, state: FSMContext, storage):
    """Обрабатывает ввод ФИО при бронировании (когда уже есть роли)"""
    try:
        user_id = message.from_user.id
        user_name = message.text.strip()

        if len(user_name.split()) < 2:
            await message.answer("❌ Введите полное ФИО (минимум имя и фамилия):")
            return

        # Сохраняем имя в storage
        storage.save_user_name(user_id, user_name)
        await state.update_data(user_name=user_name)

        # Проверяем роли
        if storage.has_user_roles(user_id):
            user_roles = storage.get_user_roles(user_id)
            builder = InlineKeyboardBuilder()
            if 'teacher' in user_roles:
                builder.button(text="👨‍🏫 Как преподаватель", callback_data="role_teacher")
            if 'student' in user_roles:
                builder.button(text="👨‍🎓 Как ученик", callback_data="role_student")
            if 'parent' in user_roles:
                builder.button(text="👨‍👩‍👧‍👦 Как родитель", callback_data="role_parent")

            await message.answer(
                "Выберите роль для бронирования:",
                reply_markup=builder.as_markup()
            )
            await state.set_state(BookingStates.SELECT_ROLE)
        else:
            await message.answer(
                "✅ ФИО сохранено!\n"
                "⏳ Обратитесь к администратору для получения ролей.\n"
                f"📞 Телефон: +79001372727",
                reply_markup=await generate_main_menu(user_id, storage)
            )
            await state.clear()

    except Exception as e:
        logger.error(f"Error in process_name_booking: {e}")
        await message.answer("❌ Ошибка. Попробуйте еще раз.")
        await state.clear()


async def check_roles(message: types.Message, state: FSMContext, storage):
    """Обработчик кнопки проверки ролей - выполняет команду /start"""
    await cmd_start(message, state, storage)


async def show_my_role(message: types.Message, storage):
    """Показывает роли пользователя"""
    user_id = message.from_user.id

    # Проверяем статус регистрации через БД
    try:
        reg_status = await db.get_user_registration_status(user_id)
    except Exception as e:
        logger.error(f"Error getting registration status: {e}")
        reg_status = {'has_request': False, 'status': 'no_request'}

    if reg_status.get('status') == 'pending':
        await message.answer("⏳ Ваша заявка на регистрацию находится на рассмотрении.")
        return
    elif reg_status.get('status') == 'rejected':
        notes = reg_status.get('notes', '')
        await message.answer(f"❌ Ваша заявка отклонена. Причина: {notes}")
        return
    elif reg_status.get('status') != 'approved':
        await message.answer("⚠️ Вы не зарегистрированы. Нажмите /start для регистрации.")
        return

    # Получаем роли из storage
    roles = storage.get_user_roles(user_id)

    if roles:
        role_translations = {
            "teacher": "преподаватель",
            "student": "ученик",
            "parent": "родитель",
            "admin": "администратор"
        }
        role_text = ", ".join([role_translations.get(role, role) for role in roles])
        await message.answer(f"✅ Ваши роли: {role_text}")
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
        "/my_role - узнать свою роль\n"
        "/my_status - проверить статус регистрации"
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
                reply_markup=keyboard.as_markup()
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
                reply_markup=keyboard.as_markup()
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
def register_menu_handlers(dp, booking_manager, storage, bot):
    """Регистрирует все обработчики меню в диспетчере"""

    # Создаем обработчики с booking_manager
    show_bookings_handler = create_bookings_handler(booking_manager)
    show_past_bookings_handler = create_past_bookings_handler(booking_manager)
    back_to_bookings_handler = create_back_to_bookings_handler(booking_manager)
    back_to_past_bookings_handler = create_back_to_past_bookings_handler(booking_manager)

    # Создаем обертки для обработчиков, которым нужен storage
    async def wrapped_cmd_start(message: types.Message, state: FSMContext):
        return await cmd_start(message, state, storage)

    async def wrapped_process_name_registration(message: types.Message, state: FSMContext):
        return await process_name_registration(message, state, storage, bot)

    async def wrapped_process_name_booking(message: types.Message, state: FSMContext):
        return await process_name_booking(message, state, storage)

    async def wrapped_check_roles(message: types.Message, state: FSMContext):
        return await check_roles(message, state, storage)

    async def wrapped_show_my_role(message: types.Message):
        return await show_my_role(message, storage)

    async def wrapped_back_to_menu_handler(callback: types.CallbackQuery):
        return await back_to_menu_handler(callback, storage)

    async def wrapped_back_to_menu_from_past_handler(callback: types.CallbackQuery):
        return await back_to_menu_from_past_handler(callback, storage)

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

    # Обработчик ввода имени - ОБРАБАТЫВАЕТ ОБА СЛУЧАЯ
    dp.message.register(
        lambda message, state: (
            wrapped_process_name_registration(message, state)
            if not storage.has_user_roles(message.from_user.id)
            else wrapped_process_name_booking(message, state)
        ),
        BookingStates.INPUT_NAME
    )

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


async def cmd_pay(message: types.Message, state: FSMContext):
    """Обработчик команды оплаты"""
    from payment_handlers import PaymentHandlers
    await PaymentHandlers.handle_payment_start(message, state)