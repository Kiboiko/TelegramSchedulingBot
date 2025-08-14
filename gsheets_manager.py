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
            logger.info("Успешное подключение к Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения: {e}")
            return False

    def format_date(self, date_str: str) -> str:
        """Форматирует дату из YYYY-MM-DD в DD.MM.YYYY"""
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except ValueError:
            return date_str

    def parse_date(self, date_str: str) -> str:
        """Парсит дату из DD.MM.YYYY в YYYY-MM-DD"""
        try:
            date_obj = datetime.strptime(date_str, '%d.%m.%Y')
            return date_obj.strftime('%Y-%m-%d')
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

    def read_all_sheets(self) -> List[Dict[str, Any]]:
        """Читает данные из всех листов и возвращает в формате JSON"""
        if not self.client and not self.connect():
            return []

        try:
            teachers_sheet = self._read_sheet('Преподаватели', is_teacher=True)
            students_sheet = self._read_sheet('Ученики', is_teacher=False)
            return teachers_sheet + students_sheet
        except Exception as e:
            logger.error(f"Ошибка при чтении данных: {e}")
            return []

    def _read_sheet(self, sheet_name: str, is_teacher: bool) -> List[Dict[str, Any]]:
        """Читает данные из конкретного листа"""
        try:
            worksheet = self._get_or_create_worksheet(sheet_name)
            if not worksheet:
                return []

            records = []
            data = worksheet.get_all_values()

            if not data or len(data) < 2:
                return records

            headers = data[0]
            date_columns = headers[3:]  # Пропускаем ID, Имя, Предмет

            for row in data[1:]:
                if not row or len(row) < 3:
                    continue

                user_id = row[0]
                user_name = row[1]
                subjects = row[2]

                # Для каждого дня проверяем наличие брони
                for i in range(0, len(date_columns), 2):
                    if i + 1 >= len(row):
                        break

                    date_str = date_columns[i]
                    start_time = row[3 + i]
                    end_time = row[3 + i + 1] if (3 + i + 1) < len(row) else ''

                    if start_time and end_time:
                        booking = {
                            'user_id': int(user_id) if user_id.isdigit() else 0,
                            'user_name': user_name,
                            'date': self.parse_date(date_str),
                            'start_time': start_time,
                            'end_time': end_time,
                            'user_role': 'teacher' if is_teacher else 'student',
                            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }

                        if is_teacher:
                            booking['subjects'] = [s.strip().lower() for s in subjects.split(',')]
                        else:
                            booking['subject'] = subjects.lower()

                        records.append(booking)

            return records
        except Exception as e:
            logger.error(f"Ошибка при чтении листа '{sheet_name}': {e}")
            return []

    def update_all_sheets(self, bookings: List[Dict[str, Any]]):
        """Полностью перезаписывает данные в таблицах"""
        if not self.client and not self.connect():
            return False

        try:
            logger.info(f"Начато обновление Google Sheets. Всего броней: {len(bookings)}")

            # Разделяем данные
            teachers = [b for b in bookings if b.get('user_role') == 'teacher']
            students = [b for b in bookings if b.get('user_role') == 'student']

            # Очищаем и обновляем каждый лист
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
            'math': 'мат',
            'inf': 'инф',
            'rus': 'рус',
            'phys': 'физ'
        }

        for booking in bookings:
            if 'user_name' not in booking or 'date' not in booking:
                continue

            name = booking['user_name']
            user_id = str(booking.get('user_id', ''))
            date = self.format_date(booking['date'])

            if is_teacher:
                subjects = [subject_mapping.get(subj, subj)
                            for subj in booking.get('subjects', [])]
                subject_str = ', '.join(subjects)
                key = f"{user_id}_{name}"
            else:
                subject_str = subject_mapping.get(
                    booking.get('subject', ''), booking.get('subject', ''))
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

        # Полностью очищаем старые данные
        worksheet.batch_clear(["A2:Z1000"])

        # Вставляем новые данные
        if rows:
            worksheet.update(f"A2:{gspread.utils.rowcol_to_a1(len(rows) + 1, len(rows[0]))}", rows)

        logger.info(f"Обновлено {len(rows)} строк в листе '{worksheet.title}'")

    def _update_sheet(self, sheet_name: str, bookings: List[Dict[str, Any]], is_teacher: bool):
        """Полностью перезаписывает данные в листе"""
        try:
            worksheet = self._get_or_create_worksheet(sheet_name)
            if not worksheet:
                return False

            # Фиксированные даты учебного года (2025-2026)
            start_date = datetime(2025, 9, 1)
            end_date = datetime(2026, 1, 4)

            # Генерируем и форматируем даты
            formatted_dates = self._generate_formatted_dates(start_date, end_date)

            # Полностью очищаем и пересоздаем структуру
            self._ensure_sheet_structure(worksheet, formatted_dates)

            # Формируем данные для вставки
            records = self._prepare_records(bookings, formatted_dates, is_teacher)

            # Вставляем данные
            self._update_worksheet_data(worksheet, records, formatted_dates)

            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении листа '{sheet_name}': {e}")
            return False