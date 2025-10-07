# time_utils.py
from datetime import datetime, time, timedelta
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

def generate_time_range_keyboard_with_availability(
    selected_date=None,
    start_time=None,
    end_time=None,
    availability_map: Dict[time, bool] = None,
    suggested_start_time: str = None,
    suggested_end_time: str = None
):
    """Генерирует клавиатуру выбора времени с учетом доступности, дня недели и предложенного времени"""
    builder = InlineKeyboardBuilder()

    # Определяем рабочие часы в зависимости от дня недели
    start_time_range, end_time_range = _get_working_hours(selected_date)
    
    start = datetime.combine(selected_date, start_time_range) if selected_date else datetime.strptime("14:00", "%H:%M")
    end = datetime.combine(selected_date, end_time_range) if selected_date else datetime.strptime("20:00", "%H:%M")

    current = start

    # Показываем предложенное время, если оно есть
    if suggested_start_time and suggested_end_time and not start_time and not end_time:
        start_time = suggested_start_time
        end_time = suggested_end_time

    while current <= end:
        time_str = current.strftime("%H:%M")
        time_obj = current.time()

        # Если availability_map = None (для преподавателей), все слоты доступны
        is_available = True
        if availability_map is not None:  # Только если есть карта доступности
            is_available = availability_map.get(time_obj, True)

        # Определяем стиль кнопки на основе доступности и предложенного времени
        is_suggested = (suggested_start_time and time_str == suggested_start_time) or \
                      (suggested_end_time and time_str == suggested_end_time)
        
        if start_time and time_str == start_time:
            button_text = "🟢 " + time_str
        elif end_time and time_str == end_time:
            button_text = "🔴 " + time_str
        elif (start_time and end_time and
              datetime.strptime(start_time, "%H:%M").time() < time_obj <
              datetime.strptime(end_time, "%H:%M").time()):
            button_text = "🔵 " + time_str
        elif is_suggested and not start_time and not end_time:
            button_text = "⭐ " + time_str  # Звездочка для предложенного времени
        else:
            button_text = time_str

        # Для учеников показываем заблокированные слоты
        if availability_map is not None and not is_available:
            button_text = "🔒 " + time_str
            callback_data = "time_slot_unavailable"
        else:
            callback_data = f"time_point_{time_str}"

        builder.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        ))
        current += timedelta(minutes=15)  # Шаг 15 минут

    builder.adjust(4)

    # Добавляем информацию о предложенном времени
    info_buttons = []
    if suggested_start_time and suggested_end_time and not start_time and not end_time:
        info_buttons.append(types.InlineKeyboardButton(
            text=f"⭐ Предложено: {suggested_start_time}-{suggested_end_time}",
            callback_data="suggested_time_info"
        ))

    # Добавляем кнопку информации о доступности только для учеников
    if availability_map is not None:  # Статистика только для учеников
        available_count = sum(1 for available in availability_map.values() if available)
        total_count = len(availability_map)
        info_buttons.append(types.InlineKeyboardButton(
            text=f"📊 Доступно: {available_count}/{total_count}",
            callback_data="availability_info"
        ))

    if info_buttons:
        builder.row(*info_buttons)

    if start_time and end_time:
        # Для преподавателей всегда доступно подтверждение
        if availability_map is None:
            builder.row(
                types.InlineKeyboardButton(
                    text="✅ Подтвердить время",
                    callback_data="confirm_time_range"
                )
            )
        else:
            # Для учеников проверяем доступность всего интервала
            is_interval_available = True
            
            # Проверяем все временные слоты в выбранном интервале
            start_obj = datetime.strptime(start_time, "%H:%M").time()
            end_obj = datetime.strptime(end_time, "%H:%M").time()
            
            current_check = start_obj
            while current_check < end_obj:
                if current_check not in availability_map or not availability_map[current_check]:
                    is_interval_available = False
                    break
                # Переходим к следующему 15-минутному слоту
                total_minutes = current_check.hour * 60 + current_check.minute + 15
                next_hour = total_minutes // 60
                next_minute = total_minutes % 60
                current_check = time(next_hour, next_minute)
            
            if is_interval_available:
                builder.row(
                    types.InlineKeyboardButton(
                        text="✅ Подтвердить время",
                        callback_data="confirm_time_range"
                    )
                )
            else:
                builder.row(
                    types.InlineKeyboardButton(
                        text="❌ Интервал содержит недоступные слоты",
                        callback_data="interval_contains_unavailable"
                    )
                )

    # Кнопка использования предложенного времени
    if suggested_start_time and suggested_end_time and not start_time and not end_time:
        builder.row(
            types.InlineKeyboardButton(
                text="✅ Использовать предложенное время",
                callback_data=f"use_suggested_time_{suggested_start_time}_{suggested_end_time}"
            )
        )

    builder.row(
        types.InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_time_selection"
        )
    )

    return builder.as_markup()

def _get_working_hours(selected_date):
    """Возвращает рабочие часы для указанной даты"""
    if selected_date:
        weekday = selected_date.weekday()
        if weekday <= 4:  # будни
            start_time = time(14, 0)  # 14:00
            end_time = time(20, 0)   # 20:00
        else:  # выходные
            start_time = time(9, 0)  # 9:00
            end_time = time(15, 0)   # 15:00
    else:
        # По умолчанию используем будний день
        start_time = time(14, 0)
        end_time = time(20, 0)
    
    return start_time, end_time

def calculate_lesson_duration(student_class: int) -> int:
    """Рассчитывает длительность занятия в минутах в зависимости от класса"""
    if student_class <= 6:
        return 60  # 1 час для 6 класса и младше
    elif student_class <= 8:
        return 90  # 1.5 часа для 7-8 классов
    else:
        return 120  # 2 часа для 9 класса и старше

def get_time_range_for_date(selected_date):
    """Возвращает временной диапазон и шаг для указанной даты"""
    start_time, end_time = _get_working_hours(selected_date)
    time_step = 15  # 15 минут
    
    return start_time, end_time, time_step

def adjust_time_to_working_hours(time_str: str, selected_date, is_start: bool = True) -> str:
    """Корректирует время в соответствии с рабочими часами"""
    try:
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        start_time_range, end_time_range = _get_working_hours(selected_date)
        
        if is_start:
            # Для времени начала: если раньше начала рабочего дня - ставим начало рабочего дня
            if time_obj < start_time_range:
                return start_time_range.strftime("%H:%M")
            # Если позже конца рабочего дня - ставим конец рабочего дня
            elif time_obj > end_time_range:
                return end_time_range.strftime("%H:%M")
            else:
                return time_str
        else:
            # Для времени окончания: обрезаем если выходит за рабочие часы
            if time_obj > end_time_range:
                return end_time_range.strftime("%H:%M")
            else:
                return time_str
    except Exception as e:
        logger.error(f"Ошибка корректировки времени: {e}")
        return time_str