import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import traceback

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
            worksheet = self.spreadsheet.worksheet("Предметы бот")
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

            # Добавляем пользователей с ролями, но без записей
            teachers = self._add_users_without_bookings(teachers, 'teacher')
            students = self._add_users_without_bookings(students, 'student')

            success = True
            if not self._update_sheet('Преподаватели бот', teachers, is_teacher=True):
                success = False
            if not self._update_sheet('Ученики бот', students, is_teacher=False):
                success = False

            if success:
                logger.info("Google Sheets успешно обновлен!")
            return success
        except Exception as e:
            logger.error(f"Критическая ошибка при обновлении: {e}")
            return False
        
    def _add_users_without_bookings(self, bookings: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
        """Добавляет пользователей с ролями, но без записей"""
        try:
            # Получаем всех пользователей с соответствующей ролью
            users_worksheet = self._get_or_create_users_worksheet()
            users_data = users_worksheet.get_all_records()
            
            users_with_role = []
            for user in users_data:
                user_roles = user.get('roles', '').lower().split(',')
                if role in user_roles:
                    users_with_role.append({
                        'user_id': user.get('user_id'),
                        'user_name': user.get('user_name', ''),
                        'user_role': role
                    })
            
            # Находим пользователей с ролью, но без записей
            existing_user_ids = {str(booking.get('user_id')) for booking in bookings}
            
            for user in users_with_role:
                user_id_str = str(user.get('user_id'))
                if user_id_str not in existing_user_ids:
                    # Создаем пустую запись для пользователя
                    empty_booking = {
                        'user_id': user.get('user_id'),
                        'user_name': user.get('user_name'),
                        'user_role': role,
                        'date': None,
                        'start_time': '',
                        'end_time': '',
                        'subjects': [] if role == 'teacher' else None,
                        'subject': '' if role == 'student' else None,
                        'priority': '' if role == 'teacher' else None,
                        'attention_need': '' if role == 'student' else None
                    }
                    bookings.append(empty_booking)
                    logger.info(f"Добавлен {role} без записей: {user.get('user_name')} (ID: {user.get('user_id')})")
            
            return bookings
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении пользователей без записей: {e}")
            return bookings

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
        headers = ['ID', 'Имя', 'Предмет ID']

        # Добавляем новые столбцы только для учеников
        if not is_teacher:
            headers.extend(['Предмет', 'Класс'])

        if is_teacher:
            headers.append('Приоритет')
        else:
            headers.append('Потребность во внимании (мин)')

        headers += [date for date in formatted_dates for _ in (0, 1)]
        worksheet.clear()
        worksheet.append_row(headers)

    def _prepare_records(self, bookings: List[Dict[str, Any]],
                         formatted_dates: List[str], is_teacher: bool) -> Dict[str, Any]:
        """Подготавливает данные для вставки с учетом предметов учеников"""
        records = {}

        for booking in bookings:
            if 'user_name' not in booking:
                continue

            name = booking['user_name']
            user_id = str(booking.get('user_id', ''))
            date = self.format_date(booking['date']) if booking.get('date') else ''

            if is_teacher:
                # Для преподавателей используем ID предметов
                subjects = booking.get('subjects', [])
                subject_str = ', '.join(subjects)
                key = f"{user_id}_{name}"
            else:
                # Для учеников используем ID предмета
                subject = booking.get('subject', '')
                subject_str = subject
                key = f"{user_id}_{subject_str}"

            if key not in records:
                records[key] = {
                    'id': user_id,
                    'name': name,
                    'subject': subject_str,
                    'attention_need': booking.get('attention_need', ''),
                    'subject_name': booking.get('subject_name', ''),  # Сохраняем название предмета
                    'class_name': booking.get('class_name', ''),  # Сохраняем класс
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

            # Добавляем новые столбцы только для учеников
            if not is_teacher:
                row.extend([
                    record.get('subject_name', ''),  # Новый столбец "Предмет"
                    record.get('class_name', '')  # Новый столбец "Класс"
                ])

            if is_teacher:
                row.append(record.get('priority', ''))
            else:
                row.append(record.get('attention_need', ''))

            # Для пользователей без записей оставляем пустые ячейки
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

            headers = [h.lower() for h in data[0]]
            bookings = []
            reverse_qual_map = {v: k for k, v in self.qual_map.items()}

            # ДЕБАГ: Логируем структуру таблицы
            logger.info(f"Структура листа '{sheet_name}':")
            logger.info(f"Заголовки: {headers}")
            logger.info(f"Кол-во столбцов: {len(headers)}")

            # ОСНОВНОЕ ИСПРАВЛЕНИЕ: Определяем правильные индексы столбцов
            # Структура вашей таблицы:
            # A: ID, B: Имя, C: Предмет ID, D: Потребность во внимании,
            # E-N: дополнительные столбцы (не даты)
            # O-JF: Даты (начиная с 01.09.2025)

            # Определяем индекс начала столбцов с датами
            date_start_col = 14  # Столбец O (индекс 14) - первая дата 01.09.2025

            # Находим конец столбцов с датами - ищем первый пустой заголовок после начала дат
            date_end_col = date_start_col
            for i in range(date_start_col, len(headers)):
                if not headers[i] or headers[i].strip() == '':
                    break
                date_end_col = i
            date_end_col += 1  # включаем последний столбец

            logger.info(f"Столбцы с датами: с {date_start_col} по {date_end_col}")

            for row_idx, row in enumerate(data[1:], start=2):
                if not row or not row[0]:
                    continue

                try:
                    user_id = int(row[0]) if row[0].strip() else None
                except ValueError:
                    user_id = None

                user_name = row[1] if len(row) > 1 else ""

                if not is_teacher:  # Для учеников
                    subject = row[2] if len(row) > 2 else ""  # Столбец C - Предмет ID
                    attention_need = row[3] if len(row) > 3 else ""  # Столбец D - Потребность

                    # Дополнительные данные из второй части таблицы
                    subject_name = row[11] if len(row) > 11 else ""  # Столбец L - Предмет
                    class_name = row[10] if len(row) > 10 else ""  # Столбец K - Класс
                else:  # Для преподавателей
                    subject = row[2] if len(row) > 2 else ""  # Столбец C - Предметы
                    priority = row[3] if len(row) > 3 else ""  # Столбец D - Приоритет

                # Обрабатываем только столбцы с датами (начиная с O)
                for i in range(date_start_col, min(date_end_col, len(row)), 2):
                    if i + 1 >= len(row) or i >= len(headers):
                        break

                    # Получаем дату из заголовка
                    date_header = headers[i].split()[0] if i < len(headers) else ""
                    start_time = row[i] if i < len(row) else ""
                    end_time = row[i + 1] if i + 1 < len(row) else ""

                    # Пропускаем если нет времени или некорректная дата
                    if not date_header or not start_time or not end_time:
                        continue

                    try:
                        # Пытаемся распарсить дату (может быть в разных форматах)
                        date_formats = ["%d.%m.%Y", "%d.%m", "%d.%m.%y"]
                        date_obj = None

                        for date_format in date_formats:
                            try:
                                date_obj = datetime.strptime(date_header, date_format)
                                # Если год не указан, используем текущий
                                if date_format == "%d.%m":
                                    date_obj = date_obj.replace(year=datetime.now().year)
                                break
                            except ValueError:
                                continue

                        if not date_obj:
                            continue

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
                            booking["attention_need"] = attention_need
                            # Добавляем новые поля для учеников
                            booking["subject_name"] = subject_name
                            booking["class_name"] = class_name

                        bookings.append(booking)

                    except ValueError as e:
                        logger.debug(f"Ошибка обработки даты {date_header}: {e}")
                        continue

            logger.info(f"Успешно обработано {len(bookings)} записей из листа '{sheet_name}'")
            return bookings

        except Exception as e:
            logger.error(f"Ошибка чтения из листа '{sheet_name}': {e}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            return []
    def sync_from_gsheets_to_json(self, storage):
        """Синхронизирует данные из Google Sheets в JSON хранилище"""
        try:
            teacher_bookings = self.get_bookings_from_sheet("Преподаватели бот", is_teacher=True)
            student_bookings = self.get_bookings_from_sheet("Ученики бот", is_teacher=False)

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

            if cell:
                worksheet.update_cell(cell.row, 2, user_name)
            else:
                worksheet.append_row([user_id, user_name])

            return True
        except Exception as e:
            logger.error(f"User save error: {e}")
            return False

    def _get_or_create_users_worksheet(self):
        """Создает лист пользователей с колонками: user_id, user_name, roles, teacher_subjects"""
        try:
            worksheet = self.spreadsheet.worksheet("Пользователи бот")
            # Проверяем структуру
            headers = worksheet.row_values(1)
            expected_headers = ["user_id", "user_name", "roles", "teacher_subjects"]
            
            if len(headers) < len(expected_headers):
                # Добавляем недостающие заголовки
                for i in range(len(headers), len(expected_headers)):
                    worksheet.update_cell(1, i+1, expected_headers[i])
                    
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title="Пользователи",
                rows=100,
                cols=4
            )
            worksheet.update("A1:D1", [["user_id", "user_name", "roles", "teacher_subjects"]])
        return worksheet
    
    def get_user_roles(self, user_id: int) -> List[str]:
        """Получает роли пользователя из листа Пользователи"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            cell = worksheet.find(str(user_id), in_column=1)
            
            if cell:
                # Колонка C - роли (разделенные запятыми)
                roles_cell = worksheet.cell(cell.row, 3).value
                if roles_cell:
                    # Убираем дубликаты и возвращаем уникальные роли
                    roles = [role.strip().lower() for role in roles_cell.split(',')]
                    return list(set(roles))  # Убираем дубликаты
            return []
        except Exception as e:
            logger.error(f"Error getting user roles: {e}")
            return []
        
    def has_user_roles(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя назначенные роли"""
        roles = self.get_user_roles(user_id)
        return len(roles) > 0

    def save_user_info(self, user_id: int, user_name: str) -> bool:
        """Сохраняет ФИО пользователя (без ролей - роли только через админку)"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            cell = worksheet.find(str(user_id), in_column=1)
            
            if cell:
                # Обновляем только имя, не трогаем роли
                worksheet.update_cell(cell.row, 2, user_name)
            else:
                # Создаем новую запись только с ФИО, роли пустые
                worksheet.append_row([user_id, user_name, ""])
            
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

            row_num = None
            for i, record in enumerate(records, start=2):
                if str(record.get("user_id")) == user_id:
                    row_num = i
                    break

            data_to_save = [user_id, user_data.get("user_name", "")]

            if row_num:
                worksheet.update(f"A{row_num}:B{row_num}", [data_to_save])
            else:
                worksheet.append_row(data_to_save)

            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных пользователя: {e}")
            return False

    def save_user_subject(self, user_id: int, user_name: str, subject_id: str) -> bool:
        """Сохраняет связь пользователь-предмет для учеников"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            records = worksheet.get_all_records()

            row_num = None
            for i, record in enumerate(records, start=2):
                if (str(record.get('user_id')) == str(user_id) and
                        record.get('subject') == subject_id):
                    row_num = i
                    break

            if row_num:
                worksheet.update(f"A{row_num}:C{row_num}", [[user_id, user_name, subject_id]])
            else:
                worksheet.append_row([user_id, user_name, subject_id])

            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения предмета ученика: {e}")
            return False

    def get_teacher_subjects(self, user_id: int) -> List[str]:
        """Получает предметы преподавателя из листа Пользователи"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            records = worksheet.get_all_records()

            for record in records:
                # Преобразуем user_id к строке для сравнения
                record_user_id = str(record.get("user_id", ""))
                if record_user_id == str(user_id):
                    subjects = record.get("teacher_subjects", "")
                    if subjects:
                        # ДЕБАГ: Логируем что получаем
                        logger.info(f"Raw subjects for user {user_id}: {subjects} (type: {type(subjects)})")

                        # ОСНОВНОЕ ИСПРАВЛЕНИЕ: Преобразуем число в строку и разбиваем на отдельные цифры
                        subjects_str = str(subjects)

                        # Если это число без запятых (например 1234), разбиваем на отдельные цифры
                        if subjects_str.isdigit() and len(subjects_str) > 1:
                            subject_list = [digit for digit in subjects_str]
                            logger.info(f"Converted number {subjects_str} to subjects: {subject_list}")
                            return subject_list
                        # Если это строка с запятыми (например "1,2,3,4")
                        elif ',' in subjects_str:
                            subject_list = [subj.strip() for subj in subjects_str.split(',') if subj.strip()]
                            logger.info(f"Split comma-separated subjects: {subject_list}")
                            return subject_list
                        # Если это одиночный предмет (например "1")
                        else:
                            subject_list = [subjects_str.strip()]
                            logger.info(f"Single subject: {subject_list}")
                            return subject_list

            logger.warning(f"No subjects found for user {user_id}")
            return []
        except Exception as e:
            logger.error(f"Error getting teacher subjects: {e}")
            return []
        
    def _get_or_create_parents_worksheet(self):
        """Создает лист Родители с колонками: user_id, user_name, children_ids"""
        try:
            worksheet = self.spreadsheet.worksheet("Родители бот")
            # Проверяем структуру
            headers = worksheet.row_values(1)
            expected_headers = ["user_id", "user_name", "children_ids"]
            
            if len(headers) < len(expected_headers):
                # Добавляем недостающие заголовки
                for i in range(len(headers), len(expected_headers)):
                    worksheet.update_cell(1, i+1, expected_headers[i])
                    
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title="Родители",
                rows=100,
                cols=3
            )
            worksheet.update("A1:C1", [["user_id", "user_name", "children_ids"]])
        return worksheet

    def get_parent_children(self, parent_id: int) -> List[int]:
        """Получает список ID детей родителя"""
        try:
            worksheet = self._get_or_create_parents_worksheet()
            records = worksheet.get_all_records()
            
            for record in records:
                # Преобразуем parent_id к строке для сравнения
                if str(record.get("user_id")) == str(parent_id):
                    children_str = record.get("children_ids", "")
                    if children_str:
                        # Убеждаемся, что это строка перед split
                        children_str = str(children_str)
                        return [int(child_id.strip()) for child_id in children_str.split(',') if child_id.strip()]
            return []
        except Exception as e:
            logger.error(f"Error getting parent children: {e}")
            return []

    def get_child_info(self, child_id: int) -> dict:
        """Получает информацию о ребенке (ученике)"""
        try:
            # Получаем данные ученика из листа Пользователи
            user_data = self.get_user_data(child_id)
            if user_data and 'student' in user_data.get('roles', '').split(','):
                return user_data
            return {}
        except Exception as e:
            logger.error(f"Error getting child info: {e}")
            return {}

    def save_parent_info(self, parent_id: int, parent_name: str, children_ids: List[int] = None) -> bool:
        """Сохраняет информацию о родителе"""
        try:
            worksheet = self._get_or_create_parents_worksheet()
            records = worksheet.get_all_records()
            
            row_num = None
            for i, record in enumerate(records, start=2):
                if str(record.get("user_id")) == str(parent_id):
                    row_num = i
                    break
            
            children_str = ','.join(map(str, children_ids)) if children_ids else ''
            
            if row_num:
                worksheet.update(f"A{row_num}:C{row_num}", [[parent_id, parent_name, children_str]])
            else:
                worksheet.append_row([parent_id, parent_name, children_str])
            
            return True
        except Exception as e:
            logger.error(f"Error saving parent info: {e}")
            return False
        
    def get_available_subjects_for_student(self, user_id: int) -> List[str]:
        """Получает доступные предметы для ученика (ищет только по строкам с соответствующим user_id)"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()
            
            logger.info(f"Поиск предметов для user_id: {user_id}")
            logger.info(f"Всего строк в листе: {len(data)}")
            
            if not data or len(data) < 2:
                logger.info("Нет данных или только заголовок")
                return []
            
            available_subjects = []
            
            # Пропускаем заголовок (первую строку)
            for i, row in enumerate(data[1:], start=2):
                if not row:
                    continue
                    
                row_user_id = row[0].strip() if len(row) > 0 and row[0] else ""
                row_subject = row[2].strip() if len(row) > 2 and row[2] else ""
                
                logger.info(f"Строка {i}: user_id='{row_user_id}', subject='{row_subject}'")
                
                # Ищем только строки с соответствующим user_id
                if row_user_id == str(user_id) and row_subject:
                    logger.info(f"Найден предмет для user_id {user_id}: {row_subject}")
                    available_subjects.append(row_subject)
            
            logger.info(f"Итоговый список предметов для user_id {user_id}: {available_subjects}")
            return list(set(available_subjects))
            
        except Exception as e:
            logger.error(f"Ошибка получения доступных предметов для user_id {user_id}: {e}")
            return []
        
    def update_student_booking_cell(self, user_id: int, subject_id: str, date: str, 
                               start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для ученика"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()
            
            if len(data) < 2:
                return False
            
            # Находим заголовки
            headers = [h.lower() for h in data[0]]
            
            # Ищем колонку для даты
            date_col_start = -1
            date_col_end = -1
            
            formatted_date = self.format_date(date) if date else ''
            
            for i, header in enumerate(headers):
                if header.startswith(formatted_date.lower()):
                    if date_col_start == -1:
                        date_col_start = i
                    else:
                        date_col_end = i
                        break
            
            if date_col_start == -1:
                logger.error(f"Дата {formatted_date} не найдена в заголовках")
                return False
            
            # Ищем строку с user_id и subject_id
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):  # Пропускаем заголовок
                if (len(row) > 0 and str(row[0]).strip() == str(user_id) and 
                    len(row) > 2 and str(row[2]).strip() == str(subject_id)):
                    target_row = row_idx
                    break
            
            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id} и subject_id {subject_id}")
                return False
            
            # Обновляем только нужные ячейки
            if date_col_end != -1:  # Есть отдельная колонка для конца времени
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                worksheet.update_cell(target_row, date_col_end + 1, end_time)
            else:  # Только одна колонка для даты (предполагаем, что следующая - для конца)
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                if date_col_start + 2 <= len(data[0]):
                    worksheet.update_cell(target_row, date_col_start + 2, end_time)
            
            logger.info(f"Обновлена ячейка для user_id {user_id}, subject {subject_id}, date {formatted_date}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления ячейки: {e}")
            return False
        
    def update_teacher_booking_cell(self, user_id: int, subjects: List[str], date: str, 
                               start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для преподавателя"""
        try:
            worksheet = self._get_or_create_worksheet("Преподаватели бот")
            data = worksheet.get_all_values()
            
            if len(data) < 2:
                return False
            
            # Находим заголовки
            headers = [h.lower() for h in data[0]]
            
            # Ищем колонку для даты
            date_col_start = -1
            date_col_end = -1
            
            formatted_date = self.format_date(date) if date else ''
            
            for i, header in enumerate(headers):
                if header.startswith(formatted_date.lower()):
                    if date_col_start == -1:
                        date_col_start = i
                    else:
                        date_col_end = i
                        break
            
            if date_col_start == -1:
                logger.error(f"Дата {formatted_date} не найдена в заголовках")
                return False
            
            # Ищем строку с user_id и subjects
            target_row = -1
            subjects_str = ', '.join(subjects)
            
            for row_idx, row in enumerate(data[1:], start=2):  # Пропускаем заголовок
                if (len(row) > 0 and str(row[0]).strip() == str(user_id) and 
                    len(row) > 2 and str(row[2]).strip() == subjects_str):
                    target_row = row_idx
                    break
            
            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id} и subjects {subjects_str}")
                return False
            
            # Обновляем только нужные ячейки
            if date_col_end != -1:  # Есть отдельная колонка для конца времени
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                worksheet.update_cell(target_row, date_col_end + 1, end_time)
            else:  # Только одна колонка для даты (предполагаем, что следующая - для конца)
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                if date_col_start + 2 <= len(data[0]):
                    worksheet.update_cell(target_row, date_col_start + 2, end_time)
            
            logger.info(f"Обновлена ячейка для user_id {user_id}, subjects {subjects_str}, date {formatted_date}")
            return True
                
        except Exception as e:
            logger.error(f"Ошибка обновления ячейки преподавателя: {e}")
            return False