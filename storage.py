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

    def save(self, data: List[Dict[str, Any]]):
        """Сохраняет данные в JSON файл"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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

    def update_booking(self, booking_id: int, new_data: Dict[str, Any]) -> bool:
        """Обновляет существующее бронирование"""
        bookings = self.load()
        updated = False

        for booking in bookings:
            if booking.get('id') == booking_id:
                booking.update(new_data)
                updated = True
                break

        if updated:
            self.save(bookings)
        return updated

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

    def sync_from_gsheets(self, gsheets_data: List[Dict[str, Any]]):
        """Синхронизирует данные из Google Sheets в JSON"""
        current_data = self.load()
        updated = False

        # Создаем словарь текущих бронирований по ID для быстрого поиска
        current_bookings = {b['id']: b for b in current_data if 'id' in b}

        # Обрабатываем данные из Google Sheets
        for gs_booking in gsheets_data:
            if 'id' not in gs_booking:
                continue

            booking_id = gs_booking['id']

            if booking_id in current_bookings:
                # Проверяем, есть ли изменения
                current_booking = current_bookings[booking_id]
                needs_update = False

                for key, value in gs_booking.items():
                    if current_booking.get(key) != value:
                        needs_update = True
                        break

                if needs_update:
                    self.update_booking(booking_id, gs_booking)
                    updated = True
            else:
                # Добавляем новое бронирование
                self.add_booking(gs_booking)
                updated = True

        return updated