import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class GoogleSheetsManager:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None

    def connect(self):
        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            logger.info("Successfully connected to Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Google Sheets connection error: {e}")
            return False

    def _get_or_create_worksheet(self, title: str):
        try:
            return self.spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return self.spreadsheet.add_worksheet(title=title, rows=100, cols=20)

    def update_all_sheets(self, bookings: List[Dict]) -> bool:
        try:
            # Обновление листа с бронированиями
            bookings_ws = self._get_or_create_worksheet("Бронирования")
            bookings_data = [["ID", "User ID", "User Name", "Role", "Type", "Date", "Start Time", "End Time", "Subject",
                              "Created At"]]

            for booking in bookings:
                bookings_data.append([
                    booking.get('id', ''),
                    booking.get('user_id', ''),
                    booking.get('user_name', ''),
                    booking.get('user_role', ''),
                    booking.get('booking_type', ''),
                    booking.get('date', ''),
                    booking.get('start_time', ''),
                    booking.get('end_time', ''),
                    booking.get('subject', '') if booking.get('user_role') == 'student' else ', '.join(
                        booking.get('subjects', [])),
                    booking.get('created_at', '')
                ])

            bookings_ws.clear()
            bookings_ws.update(bookings_data)

            return True
        except Exception as e:
            logger.error(f"Error updating Google Sheets: {e}")
            return False

    def sync_from_gsheets_to_json(self, storage) -> bool:
        try:
            users_ws = self._get_or_create_worksheet("Пользователи")
            records = users_ws.get_all_records()

            # Здесь можно добавить логику синхронизации пользователей
            # если необходимо

            return True
        except Exception as e:
            logger.error(f"Error syncing from Google Sheets: {e}")
            return False

    def get_user_name(self, user_id: int) -> Optional[str]:
        try:
            users_ws = self._get_or_create_worksheet("Пользователи")
            records = users_ws.get_all_records()

            for record in records:
                if str(record.get("user_id")) == str(user_id):
                    return record.get("user_name")
            return None
        except Exception as e:
            logger.error(f"Error getting user name: {e}")
            return None

    def save_user_name(self, user_id: int, user_name: str):
        try:
            users_ws = self._get_or_create_worksheet("Пользователи")
            records = users_ws.get_all_records()

            # Проверяем, есть ли уже пользователь
            for i, record in enumerate(records, start=2):
                if str(record.get("user_id")) == str(user_id):
                    users_ws.update_cell(i, 2, user_name)
                    return

            # Добавляем нового пользователя
            users_ws.append_row([user_id, user_name, "", ""])
        except Exception as e:
            logger.error(f"Error saving user name: {e}")

    def get_user_roles(self, user_id: int) -> List[str]:
        try:
            users_ws = self._get_or_create_worksheet("Пользователи")
            records = users_ws.get_all_records()

            for record in records:
                if str(record.get("user_id")) == str(user_id):
                    roles_str = record.get("roles", "")
                    return [role.strip() for role in roles_str.split(",") if role.strip()]
            return []
        except Exception as e:
            logger.error(f"Error getting user roles: {e}")
            return []

    def get_teacher_subjects(self, user_id: int) -> List[str]:
        try:
            teachers_ws = self._get_or_create_worksheet("Преподаватели")
            records = teachers_ws.get_all_records()

            for record in records:
                if str(record.get("user_id")) == str(user_id):
                    subjects_str = record.get("subjects", "")
                    return [subj.strip() for subj in subjects_str.split(",") if subj.strip()]
            return []
        except Exception as e:
            logger.error(f"Error getting teacher subjects: {e}")
            return []

    def get_parent_children(self, user_id: int) -> List[int]:
        try:
            parents_ws = self._get_or_create_worksheet("Родители")
            records = parents_ws.get_all_records()

            children_ids = []
            for record in records:
                if str(record.get("parent_id")) == str(user_id):
                    children_ids.append(int(record.get("child_id")))
            return children_ids
        except Exception as e:
            logger.error(f"Error getting parent children: {e}")
            return []

    def get_child_info(self, child_id: int) -> Dict:
        try:
            users_ws = self._get_or_create_worksheet("Пользователи")
            records = users_ws.get_all_records()

            for record in records:
                if str(record.get("user_id")) == str(child_id):
                    return {
                        'user_name': record.get("user_name", ""),
                        'roles': record.get("roles", "").split(",")
                    }
            return {}
        except Exception as e:
            logger.error(f"Error getting child info: {e}")
            return {}

    def get_available_subjects_for_student(self, user_id: int) -> List[str]:
        try:
            students_ws = self._get_or_create_worksheet("Ученики")
            records = students_ws.get_all_records()

            for record in records:
                if str(record.get("user_id")) == str(user_id):
                    subjects_str = record.get("available_subjects", "")
                    return [subj.strip() for subj in subjects_str.split(",") if subj.strip()]
            return []
        except Exception as e:
            logger.error(f"Error getting available subjects: {e}")
            return []

    def save_user_subject(self, user_id: int, user_name: str, subject_id: str):
        try:
            students_ws = self._get_or_create_worksheet("Ученики")
            records = students_ws.get_all_records()

            for i, record in enumerate(records, start=2):
                if str(record.get("user_id")) == str(user_id):
                    students_ws.update_cell(i, 3, subject_id)  # Колонка с предметом
                    return

            # Добавляем нового ученика
            students_ws.append_row([user_id, user_name, subject_id])
        except Exception as e:
            logger.error(f"Error saving user subject: {e}")