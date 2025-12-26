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

def generate_past_booking_info(booking_id: int, show_feedback: bool = False, subject: str = "", date_str: str = "", is_teacher: bool = False) -> InlineKeyboardBuilder:
    """Клавиатура для прошедшего бронирования (просмотр).
    Если show_feedback=True — добавляем кнопки отзывов.
    При is_teacher=True генерируем callbacks для отзывов преподавателя (без subject)."""
    builder = InlineKeyboardBuilder()

    # Если нужно — добавляем кнопки для отзывов (отлично/нормально/плохо)
    if show_feedback and date_str:
        try:
            if is_teacher:
                # Для преподавателя не указываем subject
                builder.row(
                    types.InlineKeyboardButton(text="Хорошо 👍", callback_data=f"feedback_teacher_good_{date_str}"),
                )
                builder.row(
                    types.InlineKeyboardButton(text="Могло быть лучше 🤔", callback_data=f"feedback_teacher_better_{date_str}"),
                )
                builder.row(
                    types.InlineKeyboardButton(text="Ужасно 👎", callback_data=f"feedback_teacher_bad_{date_str}"),
                )
            else:
                # Для ученика используем subject и date
                if subject:
                    builder.row(
                        types.InlineKeyboardButton(text="Отлично 👍", callback_data=f"feedback_good_{subject}_{date_str}"),
                    )
                    builder.row(
                        types.InlineKeyboardButton(text="Нормально 🤔", callback_data=f"feedback_better_{subject}_{date_str}"),
                    )
                    builder.row(
                        types.InlineKeyboardButton(text="Плохо 👎", callback_data=f"feedback_bad_{subject}_{date_str}"),
                    )
        except Exception as e:
            # Логируем, но не ломаем клавиатуру
            import logging
            logging.getLogger(__name__).error(f"Ошибка добавления feedback кнопок в generate_past_booking_info: {e}")

    builder.row(
        types.InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_past_bookings"),
        types.InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu_from_past"),
    )
    return builder.as_markup()

