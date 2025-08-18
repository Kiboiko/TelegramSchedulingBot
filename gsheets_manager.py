import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class GoogleSheetsManager:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None
        self.qual_map = {}

    def connect(self):
        """Устанавливает соединение с Google Sheets API"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_file, scope)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            self._load_qualifications()
            logger.info("Успешное подключение к Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            return False

    def _load_qualifications(self):
        """Загружает соответствия предметов из листа Квалификации"""
        try:
            worksheet = self.spreadsheet.worksheet("Квалификации")
            data = worksheet.get_all_values()

            self.qual_map = {}
            for row in data:
                if len(row) >= 2 and row[0].strip().isdigit():
                    self.qual_map[row[1].strip().lower()] = row[0].strip()
        except Exception as e:
            logger.error(f"Ошибка загрузки квалификаций: {e}")

    def format_date(self, date_str: str) -> str:
        """Форматирует дату из YYYY-MM-DD в DD.MM.YYYY"""
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except ValueError:
            return date_str

    def clear_sheet(self, sheet_name: str):
        """Полностью очищает лист"""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            worksheet.clear()
            logger.info(f"Лист '{sheet_name}' полностью очищен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при очистке листа: {e}")
            return False

    def update_all_sheets(self, bookings: List[Dict[str, Any]]):
        """Полностью перезаписывает данные в таблицах"""
        if not self.client and not self.connect():
            return False

        try:
            logger.info(f"Начато обновление Google Sheets. Всего броней: {len(bookings)}")

            teachers = [b for b in bookings if b.get('user_role') == 'teacher']
            students = [b for b in bookings if b.get('user_role') == 'student']

            success = True
            if not self._update_sheet('Преподаватели', teachers, is_teacher=True):
                success = False
            if not self._update_sheet('Ученики', students, is_teacher=False):
                success = False

            if success:
                logger.info("Google Sheets успешно обновлен!")
            return success
        except Exception as e:
            logger.error(f"Критическая ошибка при обновлении: {e}")
            return False

    def _update_sheet(self, sheet_name: str, bookings: List[Dict[str, Any]], is_teacher: bool):
        """Полностью перезаписывает данные в листе"""
        try:
            worksheet = self._get_or_create_worksheet(sheet_name)
            if not worksheet:
                return False

            start_date = datetime(2025, 9, 1)
            end_date = datetime(2026, 1, 4)
            formatted_dates = self._generate_formatted_dates(start_date, end_date)
            self._ensure_sheet_structure(worksheet, formatted_dates)
            records = self._prepare_records(bookings, formatted_dates, is_teacher)
            self._update_worksheet_data(worksheet, records, formatted_dates)
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении листа '{sheet_name}': {e}")
            return False

    def _get_or_create_worksheet(self, sheet_name: str):
        """Получает или создает лист"""
        try:
            return self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            try:
                logger.info(f"Создаем новый лист: '{sheet_name}'")
                return self.spreadsheet.add_worksheet(
                    title=sheet_name, rows=100, cols=20)
            except Exception as e:
                logger.error(f"Ошибка при создании листа: {e}")
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении листа: {e}")
            return None

    def _generate_formatted_dates(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Генерирует список отформатированных дат"""
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(self.format_date(current_date.strftime('%Y-%m-%d')))
            current_date += timedelta(days=1)
        return dates

    def _ensure_sheet_structure(self, worksheet, formatted_dates: List[str]):
        """Создает структуру листа заново"""
        new_headers = ['ID', 'Имя', 'Предмет'] + [
            date for date in formatted_dates for _ in (0, 1)
        ]
        worksheet.clear()
        worksheet.append_row(new_headers)

    def _prepare_records(self, bookings: List[Dict[str, Any]],
                         formatted_dates: List[str], is_teacher: bool) -> Dict[str, Any]:
        """Подготавливает данные для вставки"""
        records = {}
        subject_mapping = {
            'math': 'математика',
            'inf': 'информатика',
            'rus': 'русский язык',
            'phys': 'физика'
        }

        for booking in bookings:
            if 'user_name' not in booking or 'date' not in booking:
                continue

            name = booking['user_name']
            user_id = str(booking.get('user_id', ''))
            date = self.format_date(booking['date'])

            if is_teacher:
                subjects = []
                for subj in booking.get('subjects', []):
                    full_name = subject_mapping.get(subj, subj)
                    subjects.append(self.qual_map.get(full_name.lower(), subj))
                subject_str = ', '.join(subjects)
                key = f"{user_id}_{name}"
            else:
                full_name = subject_mapping.get(booking.get('subject', ''), booking.get('subject', ''))
                subject_str = self.qual_map.get(full_name.lower(), booking.get('subject', ''))
                key = f"{user_id}_{name}_{subject_str}"

            if key not in records:
                records[key] = {
                    'id': user_id,
                    'name': name,
                    'subject': subject_str,
                    'bookings': {}
                }

            if date in formatted_dates:
                records[key]['bookings'][date] = {
                    'start': booking.get('start_time', ''),
                    'end': booking.get('end_time', '')
                }

        return records

    def _update_worksheet_data(self, worksheet, records: Dict[str, Any],
                               formatted_dates: List[str]):
        """Вставляет данные в лист"""
        if not records:
            worksheet.batch_clear(["A2:Z1000"])
            logger.info("Нет данных для вставки - лист очищен")
            return

        rows = []
        for record in records.values():
            row = [record['id'], record['name'], record['subject']]
            for date in formatted_dates:
                if date in record['bookings']:
                    row.extend([
                        record['bookings'][date]['start'],
                        record['bookings'][date]['end']
                    ])
                else:
                    row.extend(['', ''])
            rows.append(row)

        worksheet.batch_clear(["A2:Z1000"])
        if rows:
            worksheet.update(f"A2:{gspread.utils.rowcol_to_a1(len(rows) + 1, len(rows[0]))}", rows)

        logger.info(f"Обновлено {len(rows)} строк в листе '{worksheet.title}'")

    def get_bookings_from_sheet(self, sheet_name: str, is_teacher: bool) -> List[Dict[str, Any]]:
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            data = worksheet.get_all_values()

            if len(data) < 2:
                return []

            headers = data[0]
            bookings = []
            reverse_qual_map = {v: k for k, v in self.qual_map.items()}

            for row in data[1:]:
                if not row or not row[0]:
                    continue

                try:
                    user_id = int(row[0]) if row[0].strip() else None
                except ValueError:
                    user_id = None

                user_name = row[1] if len(row) > 1 else ""
                subject = row[2] if len(row) > 2 else ""

                for i in range(3, len(row), 2):
                    if i + 1 >= len(row):
                        break

                    date_header = headers[i].split()[0] if i < len(headers) else ""
                    start_time = row[i] if i < len(row) else ""
                    end_time = row[i + 1] if i + 1 < len(row) else ""

                    if not date_header or not start_time or not end_time:
                        continue

                    try:
                        date_obj = datetime.strptime(date_header, "%d.%m.%Y")
                        date_str = date_obj.strftime("%Y-%m-%d")

                        booking = {
                            "user_id": user_id if user_id is not None else -1,
                            "user_name": user_name,
                            "date": date_str,
                            "start_time": start_time,
                            "end_time": end_time,
                            "user_role": "teacher" if is_teacher else "student",
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }

                        if is_teacher:
                            subjects = []
                            for subj in subject.split(","):
                                subj = subj.strip()
                                if subj in reverse_qual_map:
                                    subjects.append(reverse_qual_map[subj])
                                else:
                                    subjects.append(subj)
                            booking["subjects"] = subjects
                            booking["booking_type"] = "Тип1"
                        else:
                            if subject in reverse_qual_map:
                                booking["subject"] = reverse_qual_map[subject]
                            else:
                                booking["subject"] = subject
                            booking["booking_type"] = "Тип1"

                        bookings.append(booking)
                    except ValueError as e:
                        logger.error(f"Ошибка обработки данных: {e}")
                        continue

            return bookings
        except Exception as e:
            logger.error(f"Ошибка чтения из листа '{sheet_name}': {e}")
            return []

    def sync_from_gsheets_to_json(self, storage):
        """Синхронизирует данные из Google Sheets в JSON хранилище"""
        try:
            teacher_bookings = self.get_bookings_from_sheet("Преподаватели", is_teacher=True)
            student_bookings = self.get_bookings_from_sheet("Ученики", is_teacher=False)

            all_bookings = teacher_bookings + student_bookings

            if hasattr(storage, 'replace_all_bookings'):
                storage.replace_all_bookings(all_bookings)
                logger.info(f"Успешно синхронизировано {len(all_bookings)} записей из Google Sheets в JSON")
                return True
            else:
                storage.save(all_bookings, sync_to_gsheets=False)
                logger.warning("Использован fallback метод save вместо replace_all_bookings")
                return True

        except Exception as e:
            logger.error(f"Ошибка синхронизации из Google Sheets: {e}")
            return False