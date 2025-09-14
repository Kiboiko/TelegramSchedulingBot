from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def generate_main_menu_keyboard(user_roles: list, is_admin: bool = False):
    keyboard_buttons = []

    can_book = any(role in user_roles for role in ['teacher', 'parent']) or (
        'student' in user_roles and 'parent' in user_roles
    )

    if can_book:
        keyboard_buttons.append([KeyboardButton(text="📅 Забронировать время")])

    keyboard_buttons.append([KeyboardButton(text="📋 Мои бронирования")])
    keyboard_buttons.append([KeyboardButton(text="👤 Моя роль")])

    if is_admin:
        keyboard_buttons.append([KeyboardButton(text="📊 Составить расписание")])

    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)