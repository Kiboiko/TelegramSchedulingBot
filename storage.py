# import json
# import threading
# from pathlib import Path
# from datetime import datetime
#
# class JSONStorage:
#     def __init__(self, file_path="bookings.json"):
#         self.file_path = file_path
#         self.lock = threading.Lock()
#         self._ensure_file_exists()
#
#     def _ensure_file_exists(self):
#         """Создает файл данных, если его нет"""
#         with self.lock:
#             if not Path(self.file_path).exists():
#                 with open(self.file_path, "w", encoding="utf-8") as f:
#                     json.dump([], f)
#
#     def load(self):
#         """Загружает данные из файла"""
#         with self.lock:
#             with open(self.file_path, "r", encoding="utf-8") as f:
#                 return json.load(f)
#
#     def save(self, data):
#         """Сохраняет данные в файл"""
#         with self.lock:
#             with open(self.file_path, "w", encoding="utf-8") as f:
#                 json.dump(data, f, indent=2, ensure_ascii=False)
#
#     def add_booking(self, booking_data):
#         """Добавляет новое бронирование"""
#         data = self.load()
#         booking = {
#             "id": len(data) + 1,
#             **booking_data,
#             "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         }
#         data.append(booking)
#         self.save(data)
#         return booking
#
#     def get_bookings_for_date(self, date: str):
#         """Возвращает бронирования на указанную дату"""
#         data = self.load()
#         return [b for b in data if b["date"] == date]
#
#     def get_user_bookings(self, user_id: int):
#         """Возвращает бронирования пользователя"""
#         data = self.load()
#         return [b for b in data if b["user_id"] == user_id]
#
#     def get_user_role(self, user_id: int):
#         """Возвращает роль пользователя"""
#         data = self.load()
#         user_bookings = [b for b in data if b["user_id"] == user_id]
#         if user_bookings:
#             return user_bookings[0].get("user_role")
#         return None
#
#     def cancel_booking(self, booking_id: int):
#         """Отменяет бронирование по ID"""
#         data = self.load()
#         updated_data = [b for b in data if b["id"] != booking_id]
#         self.save(updated_data)
#         return len(data) != len(updated_data)
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


class JSONStorage:
    def __init__(self, file_path: str = "bookings.json"):
        self.file_path = Path(file_path)
        self.lock = threading.Lock()
        self._ensure_file_exists()
        self.gsheets_manager = None

    def set_gsheets_manager(self, gsheets_manager):
        self.gsheets_manager = gsheets_manager

    def _ensure_file_exists(self):
        with self.lock:
            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump([], f)

    def load(self) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []

    def save(self, data: List[Dict[str, Any]]):
        with self.lock:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            if self.gsheets_manager:
                try:
                    self.gsheets_manager.update_all_sheets(data)
                except Exception as e:
                    print(f"Google Sheets update error: {e}")

    def add_booking(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load()
        booking_data["id"] = len(data) + 1
        booking_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data.append(booking_data)
        self.save(data)
        return booking_data

    def get_user_bookings(self, user_id: int) -> List[Dict[str, Any]]:
        data = self.load()
        return [b for b in data if b.get("user_id") == user_id]

    def get_user_role(self, user_id: int) -> str:
        data = self.load()
        user_bookings = [b for b in data if b.get("user_id") == user_id]
        if user_bookings:
            return user_bookings[0].get("user_role")
        return None

    def cancel_booking(self, booking_id: int) -> bool:
        data = self.load()
        updated_data = [b for b in data if b.get("id") != booking_id]
        if len(data) != len(updated_data):
            self.save(updated_data)
            return True
        return False

    def update_user_subjects(self, user_id: int, subjects: List[str]) -> bool:
        data = self.load()
        updated = False
        for booking in data:
            if booking.get("user_id") == user_id and booking.get("user_role") == "teacher":
                booking["subjects"] = subjects
                updated = True

        if updated:
            self.save(data)
        return updated