from datetime import datetime, time, timedelta
from typing import Dict


def _add_minutes_to_time(time_obj: time, minutes: int) -> time:
    """Добавляет минуты к объекту time"""
    dummy_date = datetime(2023, 1, 1)
    combined_datetime = datetime.combine(dummy_date, time_obj)
    new_datetime = combined_datetime + timedelta(minutes=minutes)
    return new_datetime.time()


def _create_empty_time_slots() -> Dict[time, Dict]:
    """Создает словарь со всеми временными интервалами с 9:00 до 20:00"""
    time_slots = {}
    current_time = time(9, 0)
    end_time = time(20, 0)

    while current_time <= end_time:
        time_slots[current_time] = {
            'distribution': {},
            'condition_result': True
        }
        next_time = (current_time.hour * 60 + current_time.minute + 30) // 60
        next_minute = (current_time.hour * 60 + current_time.minute + 30) % 60
        current_time = time(next_time, next_minute)

    return time_slots


def get_subject_short_name(subject_id: str) -> str:
    """Возвращает сокращенное название предмета"""
    subject_names = {
        "1": "📐 Мат",
        "2": "⚛️ Физ",
        "3": "💻 Инф",
        "4": "📖 Рус"
    }
    return subject_names.get(subject_id, subject_id[:3] if subject_id else "???")