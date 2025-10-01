# booking_keyboards.py
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def generate_booking_actions(booking_id: int) -> InlineKeyboardBuilder:
    """Клавиатура действий с активным бронированием"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"cancel_booking_{booking_id}"),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_bookings"),
    )
    return builder.as_markup()

def generate_past_booking_info(booking_id: int) -> InlineKeyboardBuilder:
    """Клавиатура для прошедшего бронирования (только просмотр)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_past_bookings"),
        types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu_from_past"),
    )
    return builder.as_markup()

def generate_booking_actions(booking_id):
    """Клавиатура действий с бронированием"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"cancel_booking_{booking_id}"),
        types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_bookings"),
    )
    return builder.as_markup()

def generate_past_booking_info(booking_id):
    """Клавиатура для прошедшего бронирования (только просмотр)"""
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_past_bookings"),
        types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu_from_past"),
    )
    return builder.as_markup()