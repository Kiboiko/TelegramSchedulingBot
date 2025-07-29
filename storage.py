import json
import threading
from pathlib import Path

class JSONStorage:
    def __init__(self, file_path="data.json"):
        self.file_path = Path(file_path)
        self.lock = threading.Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Создает файл data.json, если его нет"""
        with self.lock:
            if not self.file_path.exists():
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump({"users": {}, "slots": {}}, f)

    def load(self):
        """Загружает данные из data.json"""
        with self.lock:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)

    def save(self, data):
        """Сохраняет данные в data.json"""
        with self.lock:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def add_slot(self, date: str, time: str):
        """Добавляет новый слот для записи"""
        data = self.load()
        slot_id = f"slot_{len(data['slots']) + 1}"
        data["slots"][slot_id] = {
            "date": date,
            "time": time,
            "booked": False
        }
        self.save(data)
        return slot_id

    def get_available_slots(self):
        """Возвращает свободные слоты"""
        data = self.load()
        return {
            slot_id: info
            for slot_id, info in data["slots"].items()
            if not info["booked"]
        }

    def get_all_slots(self):
        """Возвращает все слоты (для администрирования)"""
        return self.load().get("slots", {})

    def book_slot(self, user_id: int, slot_id: str):
        """Бронирует слот для пользователя"""
        data = self.load()
        if slot_id not in data["slots"] or data["slots"][slot_id]["booked"]:
            return False

        data["slots"][slot_id]["booked"] = True
        if str(user_id) not in data["users"]:
            data["users"][str(user_id)] = {"bookings": []}
        data["users"][str(user_id)]["bookings"].append(slot_id)
        self.save(data)
        return True

    def cancel_booking(self, user_id: int, slot_id: str):
        """Отменяет бронь"""
        data = self.load()
        if (str(user_id) not in data["users"] or
            slot_id not in data["users"][str(user_id)]["bookings"]):
            return False

        data["slots"][slot_id]["booked"] = False
        data["users"][str(user_id)]["bookings"].remove(slot_id)
        self.save(data)
        return True