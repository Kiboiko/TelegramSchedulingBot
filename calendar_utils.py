# calendar_utils.py
from datetime import datetime, timedelta, time
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from calendar import monthrange
import logging

logger = logging.getLogger(__name__)


def generate_finance_calendar(year=None, month=None):
    """Генерирует календарь для финансов с возможностью выбора предыдущих дат"""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    # Исправление: корректируем некорректные значения месяца
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    # Определяем минимальную дату (1 сентября текущего года)
    min_date = datetime(year=now.year, month=9, day=1).date()

    builder = InlineKeyboardBuilder()

    # Заголовок с месяцем и годом
    try:
        month_name = datetime(year, month, 1).strftime("%B %Y")
    except ValueError as e:
        logger.error(f"Ошибка создания заголовка месяца: {e}, year={year}, month={month}")
        month_name = datetime.now().strftime("%B %Y")

    builder.row(types.InlineKeyboardButton(
        text=month_name,
        callback_data="ignore_month_header"
    ))

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[
        types.InlineKeyboardButton(text=day, callback_data="ignore_weekday")
        for day in week_days
    ])

    # Генерация дней месяца
    first_day = datetime(year, month, 1)
    start_weekday = first_day.weekday()  # 0-6 (пн-вс)

    # Используем monthrange для корректного определения дней в месяце
    days_in_month = monthrange(year, month)[1]

    buttons = []
    # Пустые кнопки для дней предыдущего месяца
    for _ in range(start_weekday):
        buttons.append(types.InlineKeyboardButton(
            text=" ",
            callback_data="ignore_empty_day"
        ))

    # Кнопки дней текущего месяца (все даты доступны для выбора)
    for day in range(1, days_in_month + 1):
        current_date = datetime(year, month, day).date()

        # Для финансов все даты доступны, включая прошедшие
        buttons.append(types.InlineKeyboardButton(
            text=str(day),
            callback_data=f"finance_day_{year}-{month}-{day}"
        ))

        # Перенос строки после каждого воскресенья
        if (day + start_weekday) % 7 == 0 or day == days_in_month:
            builder.row(*buttons)
            buttons = []

    # Кнопки навигации с корректной логикой
    prev_month = month - 1
    prev_year = year
    next_month = month + 1
    next_year = year

    if prev_month < 1:
        prev_month = 12
        prev_year = year - 1

    if next_month > 12:
        next_month = 1
        next_year = year + 1

    nav_buttons = []

    # Всегда показываем кнопку "назад" для навигации
    nav_buttons.append(types.InlineKeyboardButton(
        text="⬅️",
        callback_data=f"finance_change_{prev_year}-{prev_month}"
    ))

    # Всегда показываем кнопку "вперед"
    nav_buttons.append(types.InlineKeyboardButton(
        text="➡️",
        callback_data=f"finance_change_{next_year}-{next_month}"
    ))

    builder.row(*nav_buttons)

    return builder.as_markup()


def generate_calendar(year=None, month=None):
    """Генерирует календарь с корректной обработкой переключения месяцев"""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    # Исправление: корректируем некорректные значения месяца
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    builder = InlineKeyboardBuilder()

    # Заголовок с месяцем и годом
    try:
        month_name = datetime(year, month, 1).strftime("%B %Y")
    except ValueError as e:
        logger.error(f"Ошибка создания заголовка месяца: {e}, year={year}, month={month}")
        month_name = datetime.now().strftime("%B %Y")

    builder.row(types.InlineKeyboardButton(
        text=month_name,
        callback_data="ignore_month_header"
    ))

    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    builder.row(*[
        types.InlineKeyboardButton(text=day, callback_data="ignore_weekday")
        for day in week_days
    ])

    # Генерация дней месяца
    first_day = datetime(year, month, 1)
    start_weekday = first_day.weekday()  # 0-6 (пн-вс)

    # Используем monthrange для корректного определения дней в месяце
    days_in_month = monthrange(year, month)[1]

    buttons = []
    # Пустые кнопки для дней предыдущего месяца
    for _ in range(start_weekday):
        buttons.append(types.InlineKeyboardButton(
            text=" ",
            callback_data="ignore_empty_day"
        ))

    # УПРОЩЕННАЯ ЛОГИКА: показываем все даты, начиная с текущей даты
    for day in range(1, days_in_month + 1):
        current_date = datetime(year, month, day).date()

        # Проверяем, не раньше ли текущая дата
        if current_date < now.date():
            buttons.append(types.InlineKeyboardButton(
                text=" ",
                callback_data="ignore_past_day"
            ))
        else:
            buttons.append(types.InlineKeyboardButton(
                text=str(day),
                callback_data=f"calendar_day_{year}-{month}-{day}"
            ))

        # Перенос строки после каждого воскресенья
        if (day + start_weekday) % 7 == 0 or day == days_in_month:
            builder.row(*buttons)
            buttons = []

    # Кнопки навигации с корректной логикой
    prev_month = month - 1
    prev_year = year
    next_month = month + 1
    next_year = year

    if prev_month < 1:
        prev_month = 12
        prev_year = year - 1

    if next_month > 12:
        next_month = 1
        next_year = year + 1

    nav_buttons = []

    # Всегда показываем кнопку "назад" для навигации
    nav_buttons.append(types.InlineKeyboardButton(
        text="⬅️",
        callback_data=f"calendar_change_{prev_year}-{prev_month}"
    ))

    # Всегда показываем кнопку "вперед"
    nav_buttons.append(types.InlineKeyboardButton(
        text="➡️",
        callback_data=f"calendar_change_{next_year}-{next_month}"
    ))

    builder.row(*nav_buttons)

    return builder.as_markup()


def get_time_range_for_date(selected_date=None):
    """
    Возвращает временной диапазон и шаг в зависимости от дня недели
    """
    if selected_date:
        weekday = selected_date.weekday()
    else:
        weekday = datetime.now().weekday()

    if weekday <= 4:  # будни (пн-пт)
        start_time = time(14, 0)
        end_time = time(20, 0)
    else:  # выходные (сб-вс)
        start_time = time(9, 0)
        end_time = time(15, 0)

    return start_time, end_time, 15  # шаг 15 минут