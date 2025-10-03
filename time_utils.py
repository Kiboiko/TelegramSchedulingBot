# time_utils.py
from datetime import datetime, time, timedelta
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict

def generate_time_range_keyboard_with_availability(
    selected_date=None,
    start_time=None,
    end_time=None,
    availability_map: Dict[time, bool] = None
):
    """Генерирует клавиатуру выбора времени с учетом доступности и дня недели"""
    builder = InlineKeyboardBuilder()

    # Определяем рабочие часы в зависимости от дня недели
    if selected_date:
        weekday = selected_date.weekday()
        if weekday <= 4:  # будни
            start = datetime.strptime("14:00", "%H:%M")
            end = datetime.strptime("20:00", "%H:%M")
        else:  # выходные
            start = datetime.strptime("9:00", "%H:%M")
            end = datetime.strptime("15:00", "%H:%M")
    else:
        # По умолчанию используем будний день
        start = datetime.strptime("14:00", "%H:%M")
        end = datetime.strptime("20:00", "%H:%M")

    current = start

    while current <= end:
        time_str = current.strftime("%H:%M")
        time_obj = current.time()

        # Если availability_map = None (для преподавателей), все слоты доступны
        is_available = True
        if availability_map is not None:  # Только если есть карта доступности
            is_available = availability_map.get(time_obj, True)

        # Определяем стиль кнопки на основе доступности
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

    # Добавляем кнопку информации о доступности только для учеников
    control_buttons = []
    if availability_map is not None:  # Статистика только для учеников
        available_count = sum(1 for available in availability_map.values() if available)
        total_count = len(availability_map)
        control_buttons.append(types.InlineKeyboardButton(
            text=f"Доступно: {available_count}/{total_count}",
            callback_data="availability_info"
        ))

    if control_buttons:
        builder.row(*control_buttons)

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

    builder.row(
        types.InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_time_selection"
        )
    )

    return builder.as_markup()

def calculate_lesson_duration(student_class: int) -> int:
    """Рассчитывает длительность занятия в минутах в зависимости от класса"""
    if student_class <= 6:
        return 60  # 1 час для 6 класса и младше
    elif student_class <= 8:
        return 90  # 1.5 часа для 7-8 классов
    else:
        return 120  # 2 часа для 9 класса и старше

# def get_student_class(user_id: int) -> int:
#     """Получает класс ученика из Google Sheets"""
#     try:
#         if not gsheets:
#             return 9  # По умолчанию старшие классы
        
#         worksheet = gsheets._get_or_create_worksheet("Ученики бот")
#         data = worksheet.get_all_values()
        
#         # Пропускаем заголовок
#         for row in data[1:]:
#             if row and len(row) > 0 and str(row[0]).strip() == str(user_id):
#                 # Класс находится в столбце K (индекс 10)
#                 if len(row) > 10 and row[10].strip():
#                     try:
#                         class_num = int(row[10].strip())
#                         return class_num
#                     except ValueError:
#                         pass
#         return 9  # По умолчанию старшие классы
#     except Exception as e:
#         logger.error(f"Ошибка получения класса ученика {user_id}: {e}")
#         return 9