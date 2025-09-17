from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, time
from typing import Dict, List, Optional
from config import SUBJECTS
from services.availability_service import School


def generate_calendar(year=None, month=None):
    """Генерирует календарь"""
    from datetime import datetime
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    min_date = datetime(year=now.year, month=9, day=1).date()
    if now.date() > min_date:
        min_date = now.date()

    builder = InlineKeyboardBuilder()
    month_name = datetime(year, month, 1).strftime("%B %Y")
    builder.row(InlineKeyboardButton(text=month_name, callback_data="ignore_month_header"))

    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[InlineKeyboardButton(text=day, callback_data="ignore_weekday") for day in week_days])

    first_day = datetime(year, month, 1)
    start_weekday = first_day.weekday()
    days_in_month = (datetime(year, month + 1, 1) - first_day).days if month < 12 else 31

    buttons = []
    for _ in range(start_weekday):
        buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore_empty_day"))

    for day in range(1, days_in_month + 1):
        current_date = datetime(year, month, day).date()
        if current_date < min_date:
            buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore_past_day"))
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

    nav_buttons = [
        InlineKeyboardButton(text="⬅️", callback_data=f"calendar_change_{prev_year}-{prev_month}"),
        InlineKeyboardButton(text="➡️", callback_data=f"calendar_change_{next_year}-{next_month}")
    ]

    builder.row(*nav_buttons)
    return builder.as_markup()


def generate_time_range_keyboard_with_availability(
        selected_date=None, start_time=None, end_time=None, availability_map: Optional[Dict[time, bool]] = None
):
    """Генерирует клавиатуру выбора времени с учетом доступности"""
    builder = InlineKeyboardBuilder()
    start = datetime.strptime("09:00", "%H:%M")
    end = datetime.strptime("20:00", "%H:%M")
    current = start

    while current <= end:
        time_str = current.strftime("%H:%M")
        time_obj = current.time()

        is_available = True
        if availability_map is not None:
            is_available = availability_map.get(time_obj, True)

        if start_time and time_str == start_time:
            button_text = "🟢 " + time_str
        elif end_time and time_str == end_time:
            button_text = "🔴 " + time_str
        elif (start_time and end_time and
              datetime.strptime(start_time, "%H:%M").time() < time_obj <
              datetime.strptime(end_time, "%H:%M").time()):
            button_text = "🔵 " + time_str
        else:
            button_text = time_str

        if availability_map is not None and not is_available:
            button_text = "🔒 " + time_str
            callback_data = "time_slot_unavailable"
        else:
            callback_data = f"time_point_{time_str}"

        builder.add(InlineKeyboardButton(text=button_text, callback_data=callback_data))
        current += timedelta(minutes=30)

    builder.adjust(4)

    control_buttons = []
    if availability_map is not None:
        available_count = sum(1 for available in availability_map.values() if available)
        total_count = len(availability_map)
        control_buttons.append(InlineKeyboardButton(
            text=f"Доступно: {available_count}/{total_count}",
            callback_data="availability_info"
        ))

    control_buttons.extend([
        InlineKeyboardButton(text="Выбрать начало 🟢", callback_data="select_start_mode"),
        InlineKeyboardButton(text="Выбирать конец 🔴", callback_data="select_end_mode")
    ])

    builder.row(*control_buttons)

    if start_time and end_time:
        if availability_map is None:
            builder.row(InlineKeyboardButton(text="✅ Подтвердить время", callback_data="confirm_time_range"))
        else:
            is_interval_available = True
            start_obj = datetime.strptime(start_time, "%H:%M").time()
            end_obj = datetime.strptime(end_time, "%H:%M").time()

            current_check = start_obj
            while current_check < end_obj:
                if current_check not in availability_map or not availability_map[current_check]:
                    is_interval_available = False
                    break
                current_check = School.add_minutes_to_time(current_check, 30)

            if is_interval_available:
                builder.row(InlineKeyboardButton(text="✅ Подтвердить время", callback_data="confirm_time_range"))
            else:
                builder.row(InlineKeyboardButton(
                    text="❌ Интервал содержит недоступные слоты",
                    callback_data="interval_contains_unavailable"
                ))

    builder.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_time_selection"))
    return builder.as_markup()


def generate_subjects_keyboard(selected_subjects=None, is_teacher=False, available_subjects=None):
    builder = InlineKeyboardBuilder()
    selected_subjects = selected_subjects or []

    subjects_to_show = SUBJECTS
    if available_subjects is not None:
        subjects_to_show = {k: v for k, v in SUBJECTS.items() if k in available_subjects}

    for subject_id, subject_name in subjects_to_show.items():
        emoji = "✅" if subject_id in selected_subjects else "⬜️"
        builder.button(text=f"{emoji} {subject_name}", callback_data=f"subject_{subject_id}")

    if is_teacher:
        builder.button(text="Готово", callback_data="subjects_done")
        builder.adjust(2, 2, 1)
    else:
        builder.adjust(2)

    return builder.as_markup()


def generate_confirmation():
    """Клавиатура подтверждения"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking_confirm"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="booking_cancel"),
    )
    return builder.as_markup()


def generate_main_menu(user_roles: List[str], is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard_buttons = []

    can_book = any(role in user_roles for role in ['teacher', 'parent']) or (
                'student' in user_roles and 'parent' in user_roles)

    if can_book:
        keyboard_buttons.append([KeyboardButton(text="📅 Забронировать время")])

    keyboard_buttons.append([KeyboardButton(text="📋 Мои бронирования")])
    keyboard_buttons.append([KeyboardButton(text="👤 Моя роль")])

    if is_admin:
        keyboard_buttons.append([KeyboardButton(text="📊 Составить расписание")])

    return ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)


def generate_booking_actions(booking_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❌ Отменить бронь", callback_data=f"cancel_booking_{booking_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_bookings"),
    )
    return builder.as_markup()