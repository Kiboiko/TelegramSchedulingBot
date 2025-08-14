import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from typing import List, Dict, Any
from time import sleep
import random


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
        """Обновляет конкретный лист с защитой от 'съезжания' таблицы"""
        def with_retry(func, max_retries=3, delay=1):
            """Повторяет операцию при ошибках"""
            for attempt in range(max_retries):
                try:
                    return func()
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    sleep_time = delay * (1 + random.random())
                    print(f"Ошибка, повтор #{attempt + 1} через {sleep_time:.1f} сек...")
                    sleep(sleep_time)

        try:
            # Получаем или создаем лист с повторными попытками
            worksheet = with_retry(lambda: self._get_or_create_worksheet(sheet_name))
            
            # Фиксированные даты учебного года (2025-2026)
            start_date = datetime(2025, 9, 1)  # 1 сентября 2025
            end_date = datetime(2026, 1, 4)    # 4 января 2026
            
            # Генерируем и форматируем даты
            formatted_dates = self._generate_formatted_dates(start_date, end_date)
            
            # Обновляем структуру листа если нужно
            with_retry(lambda: self._ensure_sheet_structure(worksheet, formatted_dates))
            
            # Формируем данные для вставки
            records = self._prepare_records(bookings, formatted_dates, is_teacher)
            
            # Полностью обновляем данные листа
            with_retry(lambda: self._update_worksheet_data(worksheet, records, formatted_dates))
            
            return True
        except Exception as e:
            print(f"Ошибка при обновлении листа '{sheet_name}': {e}")
            return False

    def _get_or_create_worksheet(self, sheet_name: str):
        """Получает или создает лист"""
        try:
            return self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            print(f"Создаем новый лист: '{sheet_name}'")
            return self.spreadsheet.add_worksheet(
                title=sheet_name, rows=100, cols=20)

    def _generate_formatted_dates(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Генерирует список отформатированных дат"""
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(self.format_date(current_date.strftime('%Y-%m-%d')))
            current_date += timedelta(days=1)
        return dates

    def _ensure_sheet_structure(self, worksheet, formatted_dates: List[str]):
        """Проверяет и обновляет структуру листа"""
        new_headers = ['Имя', 'Предмет'] + [
            date for date in formatted_dates for _ in (0, 1)
        ]
        
        current_headers = worksheet.row_values(1)
        if current_headers != new_headers:
            print(f"Обновляем структуру листа '{worksheet.title}'")
            worksheet.clear()
            worksheet.append_row(new_headers)

    def _prepare_records(self, bookings: List[Dict[str, Any]], 
                        formatted_dates: List[str], is_teacher: bool) -> Dict[str, Any]:
        """Подготавливает данные для вставки в таблицу"""
        records = {}
        subject_mapping = {
            'math': 'мат',
            'inf': 'инф',
            'rus': 'рус',
            'phys': 'физ'
        }
        
        for booking in bookings:
            name = booking['user_name']
            date = self.format_date(booking['date'])
            
            if is_teacher:
                subjects = [subject_mapping.get(subj, subj) 
                          for subj in booking.get('subjects', [])]
                subject_str = ', '.join(subjects)
                key = name
            else:
                subject_str = subject_mapping.get(
                    booking.get('subject', ''), booking.get('subject', ''))
                key = f"{name}_{subject_str}"
            
            if key not in records:
                records[key] = {
                    'name': name,
                    'subject': subject_str,
                    'bookings': {}
                }
            
            if date in formatted_dates:
                records[key]['bookings'][date] = {
                    'start': booking['start_time'],
                    'end': booking['end_time']
                }
        
        return records

    def _update_worksheet_data(self, worksheet, records: Dict[str, Any], 
                             formatted_dates: List[str]):
        """Обновляет данные в листе"""
        if not records:
            print("Нет данных для вставки")
            return
        
        # Формируем строки для вставки
        rows = []
        for record in records.values():
            row = [record['name'], record['subject']]
            for date in formatted_dates:
                if date in record['bookings']:
                    row.extend([
                        record['bookings'][date]['start'],
                        record['bookings'][date]['end']
                    ])
                else:
                    row.extend(['', ''])
            rows.append(row)
        
        # Определяем диапазон для обновления
        num_rows = len(rows)
        num_cols = 2 + len(formatted_dates) * 2  # Имя + Предмет + (даты × 2 колонки)
        range_name = f"A2:{gspread.utils.rowcol_to_a1(num_rows + 1, num_cols)}"
        
        # Очищаем старые данные и вставляем новые
        worksheet.batch_clear([range_name])
        worksheet.update(range_name, rows)
        
        print(f"Обновлено {len(rows)} строк в листе '{worksheet.title}'")