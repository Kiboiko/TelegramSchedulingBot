# config.py
import os
from datetime import datetime, timedelta, date, time
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOKINGS_FILE = "bookings.json"
CREDENTIALS_PATH = r"C:\Users\user\Documents\GitHub\TelegramSchedulingBot\credentials.json"
SPREADSHEET_ID = "1gFtQ7UJstu-Uv_BpgCUp24unsVT9oajSyWxU0j0GMpg"
ADMIN_IDS = [1180878673, 973231400, 1312414595]
BOOKING_TYPES = ["Тип1"]

SUBJECTS = {
    "1": "Математика",
    "2": "Физика",
    "3": "Информатика",
    "4": "Русский язык"
}

WORKING_HOURS = {
    "start": time(9, 0),
    "end": time(20, 0)
}


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


def _add_minutes_to_time(time_obj: time, minutes: int) -> time:
    """Добавляет минуты к объекту time"""
    from datetime import datetime, timedelta
    dummy_date = datetime(2023, 1, 1)
    combined_datetime = datetime.combine(dummy_date, time_obj)
    new_datetime = combined_datetime + timedelta(minutes=minutes)
    return new_datetime.time()


def _create_empty_time_slots(selected_date=None) -> Dict[time, Dict]:
    """
    Создает словарь со временными интервалами в зависимости от дня недели
    Будни (пн-пт): 14:00-20:00 с шагом 15 минут
    Выходные (сб-вс): 10:00-15:00 с шагом 15 минут
    """
    from datetime import time
    
    time_slots = {}
    
    # Определяем день недели (0-пн, 6-вс)
    if selected_date:
        weekday = selected_date.weekday()  # 0-пн, 1-вт, ..., 5-сб, 6-вс
    else:
        weekday = datetime.now().weekday()
    
    # Настройки для будних дней (пн-пт)
    if weekday <= 4:  # 0-4 = понедельник-пятница
        start_hour, start_minute = 14, 0
        end_hour, end_minute = 20, 0
    else:  # 5-6 = суббота-воскресенье
        start_hour, start_minute = 10, 0
        end_hour, end_minute = 15, 0
    
    current_time = time(start_hour, start_minute)
    end_time = time(end_hour, end_minute)
    
    while current_time <= end_time:
        time_slots[current_time] = {
            'distribution': {},
            'condition_result': True
        }
        # Добавляем 15 минут для следующего интервала
        total_minutes = current_time.hour * 60 + current_time.minute + 15
        next_hour = total_minutes // 60
        next_minute = total_minutes % 60
        current_time = time(next_hour, next_minute)
    
    return time_slots



def get_subject_short_name(subject_id: str) -> str:
    """Возвращает сокращенное название предмета (первые 3 буквы)"""
    subject_names = {
        "1": "📐 Мат",
        "2": "⚛️ Физ",
        "3": "💻 Инф",
        "4": "📖 Рус"
    }
    return subject_names.get(subject_id, subject_id[:3] if subject_id else "???")