# config.py
import os
from datetime import time
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOKINGS_FILE = "bookings.json"
CREDENTIALS_PATH = r"C:\Users\bestd\OneDrive\Документы\GitHub\TelegramSchedulingBot\credentials.json"
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


def _create_empty_time_slots() -> dict:
    """Создает словарь со всеми временными интервалами с 9:00 до 20:00"""
    from datetime import time

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
    """Возвращает сокращенное название предмета (первые 3 буквы)"""
    subject_names = {
        "1": "📐 Мат",
        "2": "⚛️ Физ",
        "3": "💻 Инф",
        "4": "📖 Рус"
    }
    return subject_names.get(subject_id, subject_id[:3] if subject_id else "???")