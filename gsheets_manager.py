import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from typing import List, Dict, Any


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
            print("Успешное подключение к Google Sheets")
            return self.spreadsheet
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            raise

    def format_date(self, date_str: str) -> str:
        """Форматирует дату из YYYY-MM-DD в DD.MM.YYYY"""
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except ValueError:
            return date_str

    def update_all_sheets(self, bookings: List[Dict[str, Any]]):
        """Основной метод обновления всех листов"""
        try:
            if not self.client:
                self.connect()

            print(f"Начато обновление Google Sheets. Всего броней: {len(bookings)}")

            # Разделяем данные
            teachers = [b for b in bookings if b.get('user_role') == 'teacher']
            students = [b for b in bookings if b.get('user_role') == 'student']

            print(f"Обновление: преподавателей={len(teachers)}, учеников={len(students)}")

            self._update_sheet('Преподаватели', teachers, is_teacher=True)
            self._update_sheet('Ученики', students, is_teacher=False)

            print("Google Sheets успешно обновлен!")
            return True
        except Exception as e:
            print(f"Критическая ошибка при обновлении: {e}")
            return False

    def _update_sheet(self, sheet_name: str, bookings: List[Dict[str, Any]], is_teacher: bool):
        """Обновляет конкретный лист"""
        try:
            # Получаем или создаем лист
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
                print(f"Лист '{sheet_name}' найден")
            except gspread.WorksheetNotFound:
                print(f"Создаем новый лист: '{sheet_name}'")
                worksheet = self.spreadsheet.add_worksheet(
                    title=sheet_name, rows=100, cols=20)

            # Собираем уникальные даты
            all_dates = sorted(
                {self.format_date(b['date']) for b in bookings},
                key=lambda x: datetime.strptime(x, '%d.%m.%Y')
            )

            # Формируем заголовки
            new_headers = ['Имя', 'Предмет'] + [
                date for date in all_dates for _ in (0, 1)
            ]  # Две колонки на дату

            # Полностью пересоздаем лист если структура изменилась
            current_headers = worksheet.row_values(1)
            if current_headers != new_headers:
                print(f"Обновляем структуру листа '{sheet_name}'")
                worksheet.clear()
                worksheet.append_row(new_headers)

            # Формируем данные
            records = {}
            for booking in bookings:
                name = booking['user_name']
                date = self.format_date(booking['date'])

                if is_teacher:
                    subjects = []
                    for subj in booking.get('subjects', []):
                        subjects.append({
                            'math': 'мат',
                            'inf': 'инф',
                            'rus': 'рус',
                            'phys': 'физ'
                        }.get(subj, subj))
                    subject_str = ', '.join(subjects)
                    key = name
                else:
                    subject_str = {
                        'math': 'мат',
                        'inf': 'инф',
                        'rus': 'рус',
                        'phys': 'физ'
                    }.get(booking.get('subject', ''), booking.get('subject', ''))
                    key = f"{name}_{subject_str}"

                if key not in records:
                    records[key] = {
                        'name': name,
                        'subject': subject_str,
                        'bookings': {}
                    }

                records[key]['bookings'][date] = {
                    'start': booking['start_time'],
                    'end': booking['end_time']
                }

            # Формируем строки для вставки
            rows = []
            for record in records.values():
                row = [record['name'], record['subject']]
                for date in all_dates:
                    if date in record['bookings']:
                        row.extend([
                            record['bookings'][date]['start'],
                            record['bookings'][date]['end']
                        ])
                    else:
                        row.extend(['', ''])
                rows.append(row)

            # Обновляем данные
            if rows:
                print(f"Вставляем {len(rows)} строк в '{sheet_name}'")
                worksheet.batch_clear(['A2:Z1000'])  # Очищаем старые данные
                worksheet.append_rows(rows)  # Вставляем новые

            return True
        except Exception as e:
            print(f"Ошибка при обновлении листа '{sheet_name}': {e}")
            return False