import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
from typing import List, Dict, Any


class GoogleSheetsManager:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None
        self.last_update_time = 0
        self.update_interval = 60  # Обновлять не чаще чем раз в 60 секунд

    def connect(self):
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            self.credentials_file, scope)
        self.client = gspread.authorize(creds)
        self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        return self.spreadsheet

    def format_date(self, date_str: str) -> str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d.%m.%Y')
        except ValueError:
            return date_str

    def update_all_sheets(self, bookings: List[Dict[str, Any]]):
        current_time = time.time()
        if current_time - self.last_update_time < self.update_interval:
            return

        if not self.client:
            try:
                self.connect()
            except Exception as e:
                print(f"Connection error: {e}")
                return

        try:
            # Разделяем данные на преподавателей и учеников
            teachers = [b for b in bookings if b.get('user_role') == 'teacher']
            students = [b for b in bookings if b.get('user_role') == 'student']

            self._update_sheet('Преподаватели', teachers, is_teacher=True)
            self._update_sheet('Ученики', students, is_teacher=False)
            self.last_update_time = current_time
        except Exception as e:
            print(f"Update error: {e}")

    def _update_sheet(self, sheet_name: str, bookings: List[Dict[str, Any]], is_teacher: bool):
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title=sheet_name, rows=100, cols=20)

        # Получаем все существующие данные
        all_data = worksheet.get_all_values()
        headers = all_data[0] if all_data else []

        # Собираем все уникальные даты
        all_dates = set()
        for booking in bookings:
            all_dates.add(self.format_date(booking['date']))
        all_dates = sorted(all_dates, key=lambda x: datetime.strptime(x, '%d.%m.%Y'))

        # Обновляем заголовки
        new_headers = ['Имя', 'Предмет']
        for date in all_dates:
            new_headers.extend([date, date])  # Две колонки на дату

        if headers != new_headers:
            worksheet.clear()
            worksheet.append_row(new_headers)
            headers = new_headers

        # Собираем данные для обновления
        records = {}

        for booking in bookings:
            name = booking['user_name']
            date = self.format_date(booking['date'])

            if is_teacher:
                # Для преподавателей объединяем все предметы через запятую
                subjects = []
                for subj in booking.get('subjects', []):
                    if subj == 'math':
                        subjects.append('мат')
                    elif subj == 'inf':
                        subjects.append('инф')
                    elif subj == 'rus':
                        subjects.append('рус')
                    elif subj == 'phys':
                        subjects.append('физ')
                    else:
                        subjects.append(subj)
                subject_str = ', '.join(subjects)
                key = name
            else:
                # Для учеников отдельная строка для каждого предмета
                subject = booking.get('subject', '')
                if subject == 'math':
                    subject_str = 'мат'
                elif subject == 'inf':
                    subject_str = 'инф'
                elif subject == 'rus':
                    subject_str = 'рус'
                elif subject == 'phys':
                    subject_str = 'физ'
                else:
                    subject_str = subject
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

        # Формируем строки для обновления
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

        # Обновляем лист
        if rows:
            worksheet.batch_clear(['A2:Z1000'])
            worksheet.append_rows(rows)


def update_all_sheets(self, bookings: List[Dict[str, Any]]):
    try:
        if not self.client:
            print("Клиент не подключен, пытаюсь подключиться...")
            self.connect()

        if not self.spreadsheet:
            print("Таблица не загружена, пытаюсь получить доступ...")
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)

        print(f"Начало обновления Google Sheets. Записей: {len(bookings)}")

        # Разделяем данные на преподавателей и учеников
        teachers = [b for b in bookings if b.get('user_role') == 'teacher']
        students = [b for b in bookings if b.get('user_role') == 'student']

        print(f"Преподавателей: {len(teachers)}, учеников: {len(students)}")

        self._update_sheet('Преподаватели', teachers, is_teacher=True)
        self._update_sheet('Ученики', students, is_teacher=False)
        print("Обновление Google Sheets завершено успешно")
    except Exception as e:
        print(f"Ошибка при обновлении Google Sheets: {str(e)}")
        raise