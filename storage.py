# import json
# import threading
# from pathlib import Path
# from datetime import datetime
# from typing import List, Dict, Any
#
#
# class JSONStorage:
#     def __init__(self, file_path: str = "bookings.json"):
#         self.file_path = Path(file_path)
#         self.lock = threading.Lock()
#         self._ensure_file_exists()
#         self.gsheets_manager = None
#
#     def set_gsheets_manager(self, gsheets_manager):
#         self.gsheets_manager = gsheets_manager
#
#     def _ensure_file_exists(self):
#         with self.lock:
#             if not self.file_path.exists() or self.file_path.stat().st_size == 0:
#                 with open(self.file_path, "w", encoding="utf-8") as f:
#                     json.dump([], f)
#
#     def load(self) -> List[Dict[str, Any]]:
#         with self.lock:
#             try:
#                 with open(self.file_path, "r", encoding="utf-8") as f:
#                     return json.load(f)
#             except (json.JSONDecodeError, FileNotFoundError):
#                 return []
#
#     def save(self, data: List[Dict[str, Any]]):
#         with self.lock:
#             with open(self.file_path, "w", encoding="utf-8") as f:
#                 json.dump(data, f, indent=2, ensure_ascii=False)
#
#             if self.gsheets_manager:
#                 try:
#                     self.gsheets_manager.update_all_sheets(data)
#                 except Exception as e:
#                     print(f"Google Sheets update error: {e}")
#
#     def add_booking(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
#         data = self.load()
#         booking_data["id"] = len(data) + 1
#         booking_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         data.append(booking_data)
#         self.save(data)
#         return booking_data
#
#     def get_user_bookings(self, user_id: int) -> List[Dict[str, Any]]:
#         data = self.load()
#         return [b for b in data if b.get("user_id") == user_id]
#
#     def get_user_role(self, user_id: int) -> str:
#         data = self.load()
#         user_bookings = [b for b in data if b.get("user_id") == user_id]
#         if user_bookings:
#             return user_bookings[0].get("user_role")
#         return None
#
#     def cancel_booking(self, booking_id: int) -> bool:
#         data = self.load()
#         updated_data = [b for b in data if b.get("id") != booking_id]
#         if len(data) != len(updated_data):
#             self.save(updated_data)
#             return True
#         return False
#
#     def update_user_subjects(self, user_id: int, subjects: List[str]) -> bool:
#         data = self.load()
#         updated = False
#         for booking in data:
#             if booking.get("user_id") == user_id and booking.get("user_role") == "teacher":
#                 booking["subjects"] = subjects
#                 updated = True
#
#         if updated:
#             self.save(data)
#         return updated

# storage.py
import json
import threading
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Any


class JSONStorage:
    def __init__(self, file_path: str = "bookings.json"):
        self.file_path = Path(file_path)
        self.lock = threading.Lock()
        self._ensure_file_exists()
        self.gsheets_manager = None

    def set_gsheets_manager(self, gsheets_manager):
        """Устанавливает менеджер Google Sheets"""
        self.gsheets_manager = gsheets_manager
        print("Google Sheets Manager установлен")

    def _ensure_file_exists(self):
        with self.lock:
            if not self.file_path.exists() or self.file_path.stat().st_size == 0:
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump([], f)

    def _convert_dates(self, data):
        """Конвертирует объекты date в строки для JSON сериализации"""
        if isinstance(data, dict):
            return {k: self._convert_dates(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._convert_dates(item) for item in data]
        elif isinstance(data, date):
            return data.strftime("%Y-%m-%d")
        return data

    def load(self) -> List[Dict[str, Any]]:
        with self.lock:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []

    def save(self, data: List[Dict[str, Any]]):
        with self.lock:
            try:
                # Конвертируем даты в строки перед сохранением
                data_to_save = self._convert_dates(data)

                # Сохраняем в файл
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(data_to_save, f, indent=2, ensure_ascii=False)
                    f.flush()

                print(f"Данные сохранены в JSON. Записей: {len(data)}")

                # Обновляем Google Sheets
                if self.gsheets_manager:
                    try:
                        print("Пытаюсь обновить Google Sheets...")
                        self.gsheets_manager.update_all_sheets(data_to_save)
                        print("Google Sheets успешно обновлен")
                    except Exception as e:
                        print(f"Ошибка при обновлении Google Sheets: {str(e)}")
            except Exception as e:
                print(f"Ошибка при сохранении данных: {str(e)}")
                raise

    def add_booking(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load()
        booking_data["id"] = len(data) + 1
        booking_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Убедимся, что дата в строковом формате
        if 'date' in booking_data and isinstance(booking_data['date'], date):
            booking_data['date'] = booking_data['date'].strftime("%Y-%m-%d")

        data.append(booking_data)
        self.save(data)
        return booking_data

    # Остальные методы остаются без изменений
    ...
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
            self.save(updated_data)  # Здесь будет автоматическое обновление Google Sheets
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
            self.save(data)  # Здесь будет автоматическое обновление Google Sheets
        return updated