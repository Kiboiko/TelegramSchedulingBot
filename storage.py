import json
from typing import List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JSONStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.gsheets = None

    def set_gsheets_manager(self, gsheets_manager):
        self.gsheets = gsheets_manager

    def load(self) -> List[Dict[str, Any]]:
        """Загружает данные из JSON файла"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return self._filter_old_bookings(data)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных: {e}")
            return []

    def save(self, data: List[Dict[str, Any]], sync_to_gsheets: bool = True):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if sync_to_gsheets and self.gsheets:
                self._sync_with_gsheets()
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")

    def add_booking(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        """Добавляет новое бронирование"""
        bookings = self.load()
        booking_id = max([b.get('id', 0) for b in bookings] or [0]) + 1
        booking_data['id'] = booking_id
        bookings.append(booking_data)
        self.save(bookings)
        return booking_data

    def cancel_booking(self, booking_id: int) -> bool:
        """Отменяет бронирование"""
        bookings = self.load()
        initial_count = len(bookings)
        bookings = [b for b in bookings if b.get('id') != booking_id]

        if len(bookings) < initial_count:
            self.save(bookings)
            return True
        return False

    def _filter_old_bookings(self, bookings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Фильтрует старые бронирования"""
        current_time = datetime.now()
        valid_bookings = []

        for booking in bookings:
            try:
                if 'date' not in booking:
                    continue

                if isinstance(booking['date'], str):
                    booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                else:
                    continue

                time_end = datetime.strptime(booking.get('end_time', "00:00"), "%H:%M").time()
                booking_datetime = datetime.combine(booking_date, time_end)

                if booking_datetime >= current_time:
                    valid_bookings.append(booking)
            except Exception:
                continue

        return valid_bookings

    def _sync_with_gsheets(self):
        """Синхронизирует с Google Sheets"""
        if self.gsheets:
            try:
                bookings = self.load()
                self.gsheets.update_all_sheets(bookings)
            except Exception as e:
                logger.error(f"Ошибка синхронизации с Google Sheets: {e}")

    def get_user_role(self, user_id: int) -> str:
        """Возвращает роль пользователя"""
        bookings = self.load()
        for booking in bookings:
            if booking.get('user_id') == user_id:
                return booking.get('user_role')
        return None

    def update_user_subjects(self, user_id: int, subjects: List[str]):
        """Обновляет предметы преподавателя"""
        bookings = self.load()
        updated = False

        for booking in bookings:
            if booking.get('user_id') == user_id and booking.get('user_role') == 'teacher':
                booking['subjects'] = subjects
                updated = True

        if updated:
            self.save(bookings)

    def replace_all_bookings(self, new_bookings: List[Dict[str, Any]]):
        # Фильтруем старые бронирования перед сохранением
        valid_bookings = self._filter_old_bookings(new_bookings)

        # Убедимся, что все ID уникальны
        used_ids = set()
        for booking in valid_bookings:
            if 'id' not in booking or booking['id'] <= 0:
                # Генерируем новый ID, если его нет или он невалидный
                booking['id'] = max(used_ids or [0]) + 1
            while booking['id'] in used_ids:
                booking['id'] += 1
            used_ids.add(booking['id'])

        # Сохраняем без синхронизации с Google Sheets (чтобы избежать цикла)
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(valid_bookings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")