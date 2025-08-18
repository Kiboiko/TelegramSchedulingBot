import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
logger = logging.getLogger(__name__)


class GoogleSheetsManager:
    SUBJECTS = {
        "1": "Математика",
        "2": "Физика",
        "3": "Информатика",
        "4": "Русский язык"
    }
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
            self._ensure_sheet_structure(worksheet, formatted_dates, is_teacher)
            records = self._prepare_records(bookings, formatted_dates, is_teacher)
            self._update_worksheet_data(worksheet, records, formatted_dates, is_teacher)
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

    def _ensure_sheet_structure(self, worksheet, formatted_dates: List[str], is_teacher: bool):
        """Создает структуру листа заново"""
        headers = ['ID', 'Имя', 'Предмет']
        if is_teacher:
            headers.append('Приоритет')  # Добавляем столбец Приоритет для преподавателей

        headers += [date for date in formatted_dates for _ in (0, 1)]
        worksheet.clear()
        worksheet.append_row(headers)

    def _prepare_records(self, bookings: List[Dict[str, Any]],
                     formatted_dates: List[str], is_teacher: bool) -> Dict[str, Any]:
        """Подготавливает данные для вставки с учетом предметов учеников"""
        records = {}
        
        for booking in bookings:
            if 'user_name' not in booking or 'date' not in booking:
                continue

            name = booking['user_name']
            user_id = str(booking.get('user_id', ''))
            date = self.format_date(booking['date'])

            if is_teacher:
                # Логика для преподавателей (оставляем как было)
                subjects = [self.SUBJECTS.get(subj, subj) for subj in booking.get('subjects', [])]
                subject_str = ', '.join(subjects)
                key = f"{user_id}_{name}"
            else:
                # Для учеников используем связку user_id + subject
                subject = booking.get('subject', '')
                subject_str = self.SUBJECTS.get(subject, subject)
                key = f"{user_id}_{subject_str}"  # Ключ теперь включает предмет

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
                               formatted_dates: List[str], is_teacher: bool):
        """Вставляет данные в лист"""
        if not records:
            worksheet.batch_clear(["A2:Z1000"])
            logger.info("Нет данных для вставки - лист очищен")
            return

        rows = []
        for record in records.values():
            row = [record['id'], record['name'], record['subject']]
            if is_teacher:
                row.append(record.get('priority', ''))

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
                priority = row[3] if is_teacher and len(row) > 3 else ""

                start_col = 4 if is_teacher else 3  # Для преподавателей начинаем с колонки E

                for i in range(start_col, len(row), 2):
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
                            booking["priority"] = priority
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
        
    def get_user_name(self, user_id: int) -> str:
        """Получает ФИО пользователя без создания дубликатов"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            # Используем формулу Google Sheets для поиска
            cell = worksheet.find(str(user_id), in_column=1)
            return worksheet.cell(cell.row, 2).value if cell else ""
        except Exception as e:
            logger.error(f"User lookup error: {e}")
            return ""

    def save_user_name(self, user_id: int, user_name: str) -> bool:
        """Обновляет или создает запись пользователя без дубликатов"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            cell = worksheet.find(str(user_id), in_column=1)
            
            if cell:  # Если пользователь существует - обновляем
                worksheet.update_cell(cell.row, 2, user_name)
            else:    # Если нет - добавляем новую запись
                worksheet.append_row([user_id, user_name])
            
            return True
        except Exception as e:
            logger.error(f"User save error: {e}")
            return False
    
    def _get_or_create_users_worksheet(self):
        """Создает лист пользователей с улучшенной структурой"""
        try:
            worksheet = self.spreadsheet.worksheet("Пользователи")
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title="Пользователи", 
                rows=100, 
                cols=3
            )
            worksheet.update("A1:C1", [["user_id", "user_name", "last_used_role"]])
        return worksheet
    
    def save_user_info(self, user_id: int, user_name: str, role: str = None) -> bool:
        """Сохраняет информацию о пользователе"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            cell = worksheet.find(str(user_id), in_column=1)
            
            if cell:  # Обновляем существующую запись
                updates = {}
                if user_name:
                    updates["B"] = user_name
                if role:
                    updates["C"] = role
                if updates:
                    worksheet.batch_update([{
                        'range': f"{k}{cell.row}",
                        'values': [[v]]
                    } for k, v in updates.items()])
            else:    # Создаем новую запись
                worksheet.append_row([user_id, user_name, role])
            
            return True
        except Exception as e:
            logger.error(f"Error saving user info: {e}")
            return False

    def get_user_data(self, user_id: int) -> dict:
        """Получает все данные пользователя по ID"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            records = worksheet.get_all_records()
            
            for record in records:
                if str(record.get("user_id")) == str(user_id):
                    return record
            return {}
        except Exception as e:
            logger.error(f"Ошибка при получении данных пользователя: {e}")
            return {}

    def save_user_data(self, user_data: dict) -> bool:
        """Сохраняет или обновляет данные пользователя"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            records = worksheet.get_all_records()
            user_id = str(user_data["user_id"])
            
            # Ищем существующую запись
            row_num = None
            for i, record in enumerate(records, start=2):
                if str(record.get("user_id")) == user_id:
                    row_num = i
                    break
            
            # Подготавливаем данные для записи
            data_to_save = [user_id, user_data.get("user_name", "")]
            
            if row_num:
                # Обновляем существующую запись
                worksheet.update(f"A{row_num}:B{row_num}", [data_to_save])
            else:
                # Добавляем новую запись
                worksheet.append_row(data_to_save)
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных пользователя: {e}")
            return False
        
    def save_user_subject(self, user_id: int, user_name: str, subject_id: str) -> bool:
        """Сохраняет связь пользователь-предмет для учеников"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики")
            records = worksheet.get_all_records()
            
            # Ищем существующую запись с таким user_id и subject_id
            row_num = None
            for i, record in enumerate(records, start=2):
                if (str(record.get('user_id')) == str(user_id) and 
                    record.get('subject') == subject_id):
                    row_num = i
                    break
            
            if row_num:
                # Обновляем существующую запись
                worksheet.update(f"A{row_num}:C{row_num}", [[user_id, user_name, subject_id]])
            else:
                # Добавляем новую запись
                worksheet.append_row([user_id, user_name, subject_id])
            
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения предмета ученика: {e}")
            return False