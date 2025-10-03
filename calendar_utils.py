# calendar_utils.py
from datetime import datetime, timedelta,time
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

def generate_calendar(year=None, month=None):
    """Генерирует календарь с корректной обработкой переключения месяцев"""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    # Определяем минимальную дату (1 сентября текущего года)
    min_date = datetime(year=now.year, month=9, day=1).date()
    if now.date() > min_date:
        min_date = now.date()

    builder = InlineKeyboardBuilder()

    # Заголовок с месяцем и годом
    month_name = datetime(year, month, 1).strftime("%B %Y")
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
    days_in_month = (datetime(year, month + 1, 1) - first_day).days if month < 12 else 31

    buttons = []
    # Пустые кнопки для дней предыдущего месяца
    for _ in range(start_weekday):
        buttons.append(types.InlineKeyboardButton(
            text=" ",
            callback_data="ignore_empty_day"
        ))

    # Кнопки дней текущего месяца
    for day in range(1, days_in_month + 1):
        current_date = datetime(year, month, day).date()
        if current_date < min_date:
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

    # Кнопки навигации
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    # ИСПРАВЛЕНИЕ: Всегда показываем кнопку "назад", если есть предыдущий месяц
    # независимо от того, есть ли в нем доступные даты
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