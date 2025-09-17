import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from .gsheets_service import GoogleSheetsManager

logger = logging.getLogger(__name__)


class JSONStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.gsheets = None

    def set_gsheets_manager(self, gsheets: GoogleSheetsManager):
        self.gsheets = gsheets

    def load(self) -> List[Dict]:
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save(self, data: List[Dict]):
        current_time = datetime.now()
        valid_bookings = []

        for booking in data:
            if 'date' not in booking:
                continue
            try:
                if isinstance(booking['date'], str):
                    booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                else:
                    continue

                time_end = datetime.strptime(booking.get('end_time', "00:00"), "%H:%M").time()
                booking_datetime = datetime.combine(booking_date, time_end)

                if booking_datetime >= current_time:
                    booking['date'] = booking_date
                    valid_bookings.append(booking)
            except ValueError:
                continue

        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(valid_bookings, f, ensure_ascii=False, indent=2, default=str)

        if self.gsheets:
            self.gsheets.update_all_sheets(valid_bookings)

    def add_booking(self, booking_data: Dict) -> Dict:
        bookings = self.load()
        booking_id = max([b.get('id', 0) for b in bookings], default=0) + 1
        booking_data['id'] = booking_id
        bookings.append(booking_data)
        self.save(bookings)
        return booking_data

    def cancel_booking(self, booking_id: int) -> bool:
        bookings = self.load()
        original_count = len(bookings)
        bookings = [b for b in bookings if b.get('id') != booking_id]

        if len(bookings) < original_count:
            self.save(bookings)
            return True
        return False

    def get_user_name(self, user_id: int) -> Optional[str]:
        if self.gsheets:
            return self.gsheets.get_user_name(user_id)
        return None

    def save_user_name(self, user_id: int, user_name: str):
        if self.gsheets:
            self.gsheets.save_user_name(user_id, user_name)

    def get_user_roles(self, user_id: int) -> List[str]:
        if self.gsheets:
            return self.gsheets.get_user_roles(user_id)
        return []

    def has_user_roles(self, user_id: int) -> bool:
        return bool(self.get_user_roles(user_id))

    def get_teacher_subjects(self, user_id: int) -> List[str]:
        if self.gsheets:
            return self.gsheets.get_teacher_subjects(user_id)
        return []

    def get_parent_children(self, user_id: int) -> List[int]:
        if self.gsheets:
            return self.gsheets.get_parent_children(user_id)
        return []

    def get_child_info(self, child_id: int) -> Dict:
        if self.gsheets:
            return self.gsheets.get_child_info(child_id)
        return {}

    def get_available_subjects_for_student(self, user_id: int) -> List[str]:
        if self.gsheets:
            return self.gsheets.get_available_subjects_for_student(user_id)
        return []

    def has_booking_on_date(self, user_id: int, date: str, role: str, subject: str = None) -> bool:
        bookings = self.load()
        for booking in bookings:
            if (booking.get('user_id') == user_id and
                    booking.get('date') == date and
                    booking.get('user_role') == role):
                if role == 'student' and subject and booking.get('subject') == subject:
                    return True
                elif role == 'teacher':
                    return True
        return False

    def has_time_conflict(self, user_id: int, date: str, time_start: str, time_end: str) -> bool:
        def time_to_minutes(t):
            h, m = map(int, t.split(':'))
            return h * 60 + m

        new_start = time_to_minutes(time_start)
        new_end = time_to_minutes(time_end)

        bookings = self.load()
        for booking in bookings:
            if (booking.get('user_id') == user_id and
                    booking.get('date') == date):

                existing_start = time_to_minutes(booking.get('start_time', '00:00'))
                existing_end = time_to_minutes(booking.get('end_time', '00:00'))

                if not (new_end <= existing_start or new_start >= existing_end):
                    return True
        return False


# Глобальный экземпляр storage
storage = JSONStorage(file_path="bookings.json")