import pandas as pd
import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import os
import time
import re
import traceback

logger = logging.getLogger(__name__)


class GoogleSheetsManager:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        # Для Excel файла нам не нужны credentials, но сохраняем интерфейс
        self.excel_file_path = spreadsheet_id  # Используем как путь к Excel файлу
        self.workbook = None
        self.qual_map = {}
        self.qual_links = {}
        self._cache = {}
        self._cache_timeout = 60

    def connect(self):
        """Устанавливает соединение с Excel файлом"""
        try:
            if not os.path.exists(self.excel_file_path):
                # Создаем новый файл, если не существует
                self.workbook = Workbook()
                # Создаем основные листы
                self._create_basic_sheets()
                self.workbook.save(self.excel_file_path)
                logger.info(f"Создан новый Excel файл: {self.excel_file_path}")
            else:
                self.workbook = load_workbook(self.excel_file_path)
                logger.info(f"Успешное подключение к Excel файлу: {self.excel_file_path}")

            self._load_qualifications()
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к Excel: {e}")
            return False

    def _create_basic_sheets(self):
        """Создает основные листы в Excel файле"""
        # Удаляем лист по умолчанию
        if 'Sheet' in self.workbook.sheetnames:
            del self.workbook['Sheet']

        # Создаем основные листы
        sheets_to_create = [
            "Ученики бот",
            "Преподаватели бот",
            "Пользователи бот",
            "Родители бот",
            "Самозанятые бот",
            "Предметы бот"
        ]

        for sheet_name in sheets_to_create:
            self.workbook.create_sheet(sheet_name)

    def _get_or_create_worksheet(self, sheet_name: str):
        """Получает или создает лист в Excel"""
        try:
            if sheet_name in self.workbook.sheetnames:
                return self.workbook[sheet_name]
            else:
                worksheet = self.workbook.create_sheet(sheet_name)
                logger.info(f"Создан новый лист: '{sheet_name}'")
                return worksheet
        except Exception as e:
            logger.error(f"Ошибка при получении листа '{sheet_name}': {e}")
            return None

    def _load_qualifications(self):
        """Загружает соответствия предметов из листа Предметы бот"""
        try:
            worksheet = self._get_or_create_worksheet("Предметы бот")
            data = list(worksheet.values)

            self.qual_map = {}
            self.qual_links = {}

            if not data:
                return

            logger.info("=== ДАННЫЕ ИЗ ЛИСТА 'Предметы бот' ===")
            for i, row in enumerate(data):
                row_list = list(row)
                logger.info(f"Строка {i}: {row_list}")
                if len(row_list) >= 2 and str(row_list[0]).strip().isdigit():
                    subject_id = str(row_list[0]).strip()
                    subject_name = str(row_list[1]).strip().lower()
                    self.qual_map[subject_name] = subject_id

                    # Загружаем ссылку из колонки C (индекс 2)
                    if len(row_list) >= 3:
                        self.qual_links[subject_id] = str(row_list[2]).strip()

                    logger.info(
                        f"Добавлено: '{subject_name}' -> '{subject_id}', ссылка: {self.qual_links.get(subject_id, 'нет')}")

            logger.info(f"Итоговый qual_map: {self.qual_map}")
            logger.info(f"Ссылки на материалы: {self.qual_links}")
        except Exception as e:
            logger.error(f"Ошибка загрузки квалификаций: {e}")

    def format_date(self, date_str: str) -> str:
        """Форматирует дату из YYYY-MM-DD в DD.MM.YYYY"""
        try:
            input_formats = ['%Y-%m-%d', '%d.%m.%Y', '%d.%m.%y']
            date_obj = None

            for fmt in input_formats:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

            if date_obj:
                return date_obj.strftime('%d.%m.%Y')
            else:
                logger.error(f"Не удалось распарсить дату: {date_str}")
                return date_str
        except Exception as e:
            logger.error(f"Ошибка форматирования даты {date_str}: {e}")
            return date_str

    def _get_cached_data(self, key):
        """Получает данные из кэша"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_timeout:
                return data
        return None

    def _set_cached_data(self, key, data):
        """Сохраняет данные в кэш"""
        self._cache[key] = (data, time.time())

    def clear_sheet(self, sheet_name: str):
        """Полностью очищает лист"""
        try:
            worksheet = self._get_or_create_worksheet(sheet_name)
            worksheet.delete_rows(1, worksheet.max_row)
            logger.info(f"Лист '{sheet_name}' полностью очищен")
            return True
        except Exception as e:
            logger.error(f"Ошибка при очистке листа: {e}")
            return False

    def update_all_sheets(self, bookings: List[Dict[str, Any]]):
        """Полностью перезаписывает данные в таблицах"""
        if not self.workbook and not self.connect():
            return False

        try:
            logger.info(f"Начато обновление Excel. Всего броней: {len(bookings)}")

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
                self.workbook.save(self.excel_file_path)
                logger.info("Excel успешно обновлен!")
            return success
        except Exception as e:
            logger.error(f"Критическая ошибка при обновлении: {e}")
            return False

    def _add_users_without_bookings(self, bookings: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
        """Добавляет пользователей с ролями, но без записей"""
        try:
            users_worksheet = self._get_or_create_users_worksheet()
            users_data = list(users_worksheet.values)

            if len(users_data) <= 1:  # Только заголовок или пусто
                return bookings

            headers = [str(cell).lower() for cell in users_data[0]]
            user_id_idx = headers.index('user_id') if 'user_id' in headers else 0
            user_name_idx = headers.index('user_name') if 'user_name' in headers else 1
            roles_idx = headers.index('roles') if 'roles' in headers else 2

            users_with_role = []
            for row in users_data[1:]:
                row_list = list(row)
                if len(row_list) > max(user_id_idx, roles_idx):
                    user_roles = str(row_list[roles_idx]).lower().split(',') if row_list[roles_idx] else []
                    if role in user_roles:
                        users_with_role.append({
                            'user_id': row_list[user_id_idx],
                            'user_name': row_list[user_name_idx] if len(row_list) > user_name_idx else "",
                            'user_role': role
                        })

            # Находим пользователей с ролью, но без записей
            existing_user_ids = {str(booking.get('user_id')) for booking in bookings}

            for user in users_with_role:
                user_id_str = str(user.get('user_id'))
                if user_id_str not in existing_user_ids:
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
        # Очищаем лист
        worksheet.delete_rows(1, worksheet.max_row)

        headers = ['ID', 'Имя', 'Предмет ID']

        # Добавляем новые столбцы только для учеников
        if not is_teacher:
            headers.extend(['Предмет', 'Класс'])

        if is_teacher:
            headers.append('Приоритет')
        else:
            headers.append('Потребность во внимании (мин)')

        headers += [date for date in formatted_dates for _ in (0, 1)]

        # Записываем заголовки
        for col_idx, header in enumerate(headers, 1):
            worksheet.cell(row=1, column=col_idx, value=header)

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
                subjects = booking.get('subjects', [])
                subject_str = ', '.join(subjects)
                key = f"{user_id}_{name}"
            else:
                subject = booking.get('subject', '')
                subject_str = subject
                key = f"{user_id}_{subject_str}"

            if key not in records:
                records[key] = {
                    'id': user_id,
                    'name': name,
                    'subject': subject_str,
                    'attention_need': booking.get('attention_need', ''),
                    'subject_name': booking.get('subject_name', ''),
                    'class_name': booking.get('class_name', ''),
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
            logger.info("Нет данных для вставки - лист очищен")
            return

        row_num = 2  # Начинаем со второй строки (после заголовков)
        for record in records.values():
            col_num = 1
            row_data = [
                record['id'],
                record['name'],
                record['subject']
            ]

            # Добавляем новые столбцы только для учеников
            if not is_teacher:
                row_data.extend([
                    record.get('subject_name', ''),
                    record.get('class_name', '')
                ])

            if is_teacher:
                row_data.append(record.get('priority', ''))
            else:
                row_data.append(record.get('attention_need', ''))

            # Для пользователей без записей оставляем пустые ячейки
            for date in formatted_dates:
                if date in record['bookings']:
                    row_data.extend([
                        record['bookings'][date]['start'],
                        record['bookings'][date]['end']
                    ])
                else:
                    row_data.extend(['', ''])

            # Записываем строку
            for col_idx, value in enumerate(row_data, 1):
                worksheet.cell(row=row_num, column=col_idx, value=value)

            row_num += 1

        logger.info(f"Обновлено {len(records)} строк в листе '{worksheet.title}'")

    def get_bookings_from_sheet(self, sheet_name: str, is_teacher: bool) -> List[Dict[str, Any]]:
        """Читает данные из Excel листа"""
        try:
            worksheet = self._get_or_create_worksheet(sheet_name)
            data = list(worksheet.values)

            if len(data) < 3:
                return []

            headers = [str(h).lower() for h in data[0]]
            bookings = []
            reverse_qual_map = {v: k for k, v in self.qual_map.items()}

            # Определяем индексы столбцов
            date_start_col = 14  # Столбец O (индекс 14) - первая дата

            # Находим конец столбцов с датами
            date_end_col = date_start_col
            for i in range(date_start_col, len(headers)):
                if not headers[i] or headers[i].strip() == '':
                    break
                date_end_col = i
            date_end_col += 1

            logger.info(f"Столбцы с датами: с {date_start_col} по {date_end_col}")

            for row_idx, row in enumerate(data[2:], start=3):
                row_list = list(row)
                if not row_list or not row_list[0]:
                    continue

                try:
                    user_id = int(row_list[0]) if str(row_list[0]).strip() else None
                except ValueError:
                    user_id = None

                user_name = row_list[1] if len(row_list) > 1 else ""

                if not is_teacher:
                    subject = row_list[2] if len(row_list) > 2 else ""
                    attention_need = row_list[3] if len(row_list) > 3 else ""
                    subject_name = row_list[11] if len(row_list) > 11 else ""
                    class_name = row_list[10] if len(row_list) > 10 else ""
                else:
                    subject = row_list[2] if len(row_list) > 2 else ""
                    priority = row_list[3] if len(row_list) > 3 else ""

                # Обрабатываем столбцы с датами
                for i in range(date_start_col, min(date_end_col, len(row_list)), 2):
                    if i + 1 >= len(row_list) or i >= len(headers):
                        break

                    date_header = headers[i].split()[0] if i < len(headers) else ""
                    start_time = row_list[i] if i < len(row_list) else ""
                    end_time = row_list[i + 1] if i + 1 < len(row_list) else ""

                    if not date_header or not start_time or not end_time:
                        continue

                    try:
                        date_formats = ["%d.%m.%Y", "%d.%m", "%d.%m.%y"]
                        date_obj = None

                        for date_format in date_formats:
                            try:
                                date_obj = datetime.strptime(date_header, date_format)
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
                            for subj in str(subject).split(","):
                                subj = subj.strip()
                                if subj in reverse_qual_map:
                                    subjects.append(reverse_qual_map[subj])
                                else:
                                    subjects.append(subj)
                            booking["subjects"] = subjects
                            booking["booking_type"] = "Тип1"
                            booking["priority"] = priority
                        else:
                            if str(subject) in reverse_qual_map:
                                booking["subject"] = reverse_qual_map[str(subject)]
                            else:
                                booking["subject"] = subject
                            booking["booking_type"] = "Тип1"
                            booking["attention_need"] = attention_need
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
            return []

    def sync_from_gsheets_to_json(self, storage):
        """Синхронизирует данные из Excel в JSON хранилище"""
        try:
            teacher_bookings = self.get_bookings_from_sheet("Преподаватели бот", is_teacher=True)
            student_bookings = self.get_bookings_from_sheet("Ученики бот", is_teacher=False)

            all_bookings = teacher_bookings + student_bookings

            if hasattr(storage, 'replace_all_bookings'):
                storage.replace_all_bookings(all_bookings)
                logger.info(f"Успешно синхронизировано {len(all_bookings)} записей из Excel в JSON")
                return True
            else:
                storage.save(all_bookings, sync_to_gsheets=False)
                logger.warning("Использован fallback метод save вместо replace_all_bookings")
                return True

        except Exception as e:
            logger.error(f"Ошибка синхронизации из Excel: {e}")
            return False

    def _get_or_create_users_worksheet(self):
        """Создает лист пользователей"""
        worksheet = self._get_or_create_worksheet("Пользователи бот")

        # Проверяем структуру
        if worksheet.max_row == 0 or worksheet.max_row == 1:
            headers = ["user_id", "user_name", "roles", "teacher_subjects"]
            for col_idx, header in enumerate(headers, 1):
                worksheet.cell(row=1, column=col_idx, value=header)

        return worksheet

    def get_user_name(self, user_id: int) -> str:
        """Получает ФИО пользователя"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            data = list(worksheet.values)

            if len(data) < 2:
                return ""

            headers = [str(cell).lower() for cell in data[0]]
            user_id_idx = headers.index('user_id') if 'user_id' in headers else 0
            user_name_idx = headers.index('user_name') if 'user_name' in headers else 1

            for row in data[1:]:
                row_list = list(row)
                if len(row_list) > user_id_idx and str(row_list[user_id_idx]) == str(user_id):
                    return str(row_list[user_name_idx]) if len(row_list) > user_name_idx else ""
            return ""
        except Exception as e:
            logger.error(f"User lookup error: {e}")
            return ""

    def save_user_name(self, user_id: int, user_name: str) -> bool:
        """Обновляет или создает запись пользователя"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            data = list(worksheet.values)

            if len(data) < 2:  # Только заголовок
                worksheet.append_row([user_id, user_name])
                self.workbook.save(self.excel_file_path)
                return True

            headers = [str(cell).lower() for cell in data[0]]
            user_id_idx = headers.index('user_id') if 'user_id' in headers else 0
            user_name_idx = headers.index('user_name') if 'user_name' in headers else 1

            found = False
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > user_id_idx and str(row_list[user_id_idx]) == str(user_id):
                    worksheet.cell(row=row_idx, column=user_name_idx + 1, value=user_name)
                    found = True
                    break

            if not found:
                worksheet.append_row([user_id, user_name])

            self.workbook.save(self.excel_file_path)
            return True
        except Exception as e:
            logger.error(f"User save error: {e}")
            return False

    def get_user_roles(self, user_id: int) -> List[str]:
        """Получает роли пользователя"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            data = list(worksheet.values)

            if len(data) < 2:
                return []

            headers = [str(cell).lower() for cell in data[0]]
            user_id_idx = headers.index('user_id') if 'user_id' in headers else 0
            roles_idx = headers.index('roles') if 'roles' in headers else 2

            for row in data[1:]:
                row_list = list(row)
                if len(row_list) > user_id_idx and str(row_list[user_id_idx]) == str(user_id):
                    if len(row_list) > roles_idx and row_list[roles_idx]:
                        roles = [role.strip().lower() for role in str(row_list[roles_idx]).split(',')]
                        return list(set(roles))
            return []
        except Exception as e:
            logger.error(f"Error getting user roles: {e}")
            return []

    def has_user_roles(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя назначенные роли"""
        roles = self.get_user_roles(user_id)
        return len(roles) > 0

    def save_user_info(self, user_id: int, user_name: str) -> bool:
        """Сохраняет ФИО пользователя"""
        return self.save_user_name(user_id, user_name)

    def get_user_data(self, user_id: int) -> dict:
        """Получает все данные пользователя по ID"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            data = list(worksheet.values)

            if len(data) < 2:
                return {}

            headers = [str(cell).lower() for cell in data[0]]
            user_id_idx = headers.index('user_id') if 'user_id' in headers else 0

            for row in data[1:]:
                row_list = list(row)
                if len(row_list) > user_id_idx and str(row_list[user_id_idx]) == str(user_id):
                    result = {}
                    for i, header in enumerate(headers):
                        if i < len(row_list):
                            result[header] = str(row_list[i]) if row_list[i] is not None else ""
                        else:
                            result[header] = ""

                    # Обрабатываем предметы преподавателя
                    if 'teacher_subjects' in result and result['teacher_subjects']:
                        result['subjects'] = [subj.strip() for subj in result['teacher_subjects'].split(',') if
                                              subj.strip()]
                    return result
            return {}
        except Exception as e:
            logger.error(f"Ошибка при получении данных пользователя: {e}")
            return {}

    def save_user_data(self, user_data: dict) -> bool:
        """Сохраняет или обновляет данные пользователя"""
        try:
            worksheet = self._get_or_create_users_worksheet()
            data = list(worksheet.values)
            user_id = str(user_data["user_id"])

            headers = [str(cell).lower() for cell in data[0]] if data else []
            if not headers:
                headers = ["user_id", "user_name", "roles", "teacher_subjects"]
                for col_idx, header in enumerate(headers, 1):
                    worksheet.cell(row=1, column=col_idx, value=header)

            row_num = None
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]) == user_id:
                    row_num = row_idx
                    break

            data_to_save = []
            for header in headers:
                if header in user_data:
                    data_to_save.append(user_data[header])
                else:
                    data_to_save.append("")

            if row_num:
                for col_idx, value in enumerate(data_to_save, 1):
                    worksheet.cell(row=row_num, column=col_idx, value=value)
            else:
                worksheet.append_row(data_to_save)

            self.workbook.save(self.excel_file_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных пользователя: {e}")
            return False

    def save_user_subject(self, user_id: int, user_name: str, subject_id: str) -> bool:
        """Сохраняет связь пользователь-предмет для учеников"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            # Ищем существующую запись
            found = False
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if (len(row_list) > 0 and str(row_list[0]) == str(user_id) and
                        len(row_list) > 2 and str(row_list[2]) == str(subject_id)):
                    # Обновляем существующую запись
                    worksheet.cell(row=row_idx, column=1, value=user_id)
                    worksheet.cell(row=row_idx, column=2, value=user_name)
                    worksheet.cell(row=row_idx, column=3, value=subject_id)
                    found = True
                    break

            if not found:
                worksheet.append_row([user_id, user_name, subject_id])

            self.workbook.save(self.excel_file_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения предмета ученика: {e}")
            return False

    def get_teacher_subjects(self, user_id: int) -> List[str]:
        """Получает предметы преподавателя"""
        try:
            user_data = self.get_user_data(user_id)
            if not user_data:
                return []

            subjects = user_data.get("teacher_subjects", "")
            if not subjects:
                return []

            logger.info(f"Raw subjects for user {user_id}: {subjects} (type: {type(subjects)})")

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

        except Exception as e:
            logger.error(f"Error getting teacher subjects: {e}")
            return []

    def _get_or_create_parents_worksheet(self):
        """Создает лист Родители"""
        worksheet = self._get_or_create_worksheet("Родители бот")

        # Проверяем структуру
        if worksheet.max_row == 0 or worksheet.max_row == 1:
            headers = ["user_id", "user_name", "children_ids"]
            for col_idx, header in enumerate(headers, 1):
                worksheet.cell(row=1, column=col_idx, value=header)

        return worksheet

    def get_parent_children(self, parent_id: int) -> List[int]:
        """Получает список ID детей родителя"""
        try:
            worksheet = self._get_or_create_parents_worksheet()
            data = list(worksheet.values)

            if len(data) < 2:
                return []

            headers = [str(cell).lower() for cell in data[0]]
            user_id_idx = headers.index('user_id') if 'user_id' in headers else 0
            children_idx = headers.index('children_ids') if 'children_ids' in headers else 2

            for row in data[1:]:
                row_list = list(row)
                if len(row_list) > user_id_idx and str(row_list[user_id_idx]) == str(parent_id):
                    children_str = row_list[children_idx] if len(row_list) > children_idx else ""
                    if children_str:
                        children_str = str(children_str)
                        return [int(child_id.strip()) for child_id in children_str.split(',') if child_id.strip()]
            return []
        except Exception as e:
            logger.error(f"Error getting parent children: {e}")
            return []

    def get_child_info(self, child_id: int) -> dict:
        """Получает информацию о ребенке (ученике)"""
        try:
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
            data = list(worksheet.values)

            headers = [str(cell).lower() for cell in data[0]] if data else []
            if not headers:
                headers = ["user_id", "user_name", "children_ids"]
                for col_idx, header in enumerate(headers, 1):
                    worksheet.cell(row=1, column=col_idx, value=header)

            row_num = None
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]) == str(parent_id):
                    row_num = row_idx
                    break

            children_str = ','.join(map(str, children_ids)) if children_ids else ''

            if row_num:
                worksheet.cell(row=row_num, column=1, value=parent_id)
                worksheet.cell(row=row_num, column=2, value=parent_name)
                worksheet.cell(row=row_num, column=3, value=children_str)
            else:
                worksheet.append_row([parent_id, parent_name, children_str])

            self.workbook.save(self.excel_file_path)
            return True
        except Exception as e:
            logger.error(f"Error saving parent info: {e}")
            return False

    def get_available_subjects_for_student(self, user_id: int) -> List[str]:
        """Получает доступные предметы для ученика"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            logger.info(f"Поиск предметов для user_id: {user_id}")
            logger.info(f"Всего строк в листе: {len(data)}")

            if not data or len(data) < 3:
                logger.info("Нет данных или только заголовок")
                return []

            available_subjects = []

            # Пропускаем заголовок (первую строку)
            for i, row in enumerate(data[2:], start=3):
                row_list = list(row)
                if not row_list:
                    continue

                row_user_id = row_list[0].strip() if len(row_list) > 0 and row_list[0] else ""
                row_subject = row_list[2].strip() if len(row_list) > 2 and row_list[2] else ""

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
            data = list(worksheet.values)

            if len(data) < 2:
                return False

            # Находим заголовки
            headers = [str(h).lower() for h in data[0]]

            # Ищем колонку для даты
            date_col_start = -1
            formatted_date = self.format_date(date) if date else ''

            for i, header in enumerate(headers):
                if header.startswith(formatted_date.lower()):
                    date_col_start = i
                    break

            if date_col_start == -1:
                logger.error(f"Дата {formatted_date} не найдена в заголовках")
                return False

            # Ищем строку с user_id и subject_id
            target_row = -1
            search_subject_id = subject_id

            # Если subject_id - это название предмета, преобразуем в числовой ID
            if not subject_id.isdigit():
                if subject_id.lower() in self.qual_map:
                    search_subject_id = self.qual_map[subject_id.lower()]
                elif subject_id in self.qual_map.values():
                    for id_key, name_value in self.qual_map.items():
                        if name_value == subject_id:
                            search_subject_id = id_key
                            break

            logger.info(f"Поиск строки: user_id={user_id}, subject_id={search_subject_id} (оригинальный: {subject_id})")

            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]).strip() == str(user_id):
                    if len(row_list) > 2 and str(row_list[2]).strip() == str(search_subject_id):
                        target_row = row_idx
                        logger.info(
                            f"Найдена строка {target_row} для user_id {user_id} и subject_id {search_subject_id}")
                        break

            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id} и subject_id {search_subject_id}")
                return False

            # Обновляем ячейки
            if date_col_start + 1 <= len(headers):
                worksheet.cell(row=target_row, column=date_col_start + 1, value=start_time)
            if date_col_start + 2 <= len(headers):
                worksheet.cell(row=target_row, column=date_col_start + 2, value=end_time)

            self.workbook.save(self.excel_file_path)
            logger.info(f"Обновлена ячейка для user_id {user_id}, subject {search_subject_id}, date {formatted_date}")
            return True

        except Exception as e:
            logger.error(f"Ошибка обновления ячейки: {e}")
            return False

    def update_teacher_booking_cell(self, user_id: int, subjects: List[str], date: str,
                                    start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для преподавателя"""
        try:
            worksheet = self._get_or_create_worksheet("Преподаватели бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return False

            headers = [str(h).lower() for h in data[0]]

            # Ищем колонку для даты
            date_col_start = -1
            formatted_date = self.format_date(date) if date else ''

            for i, header in enumerate(headers):
                if header.startswith(formatted_date.lower()):
                    date_col_start = i
                    break

            if date_col_start == -1:
                logger.error(f"Дата {formatted_date} не найдена в заголовках")
                return False

            # Ищем строку ТОЛЬКО по user_id
            target_row = -1
            logger.info(f"Поиск строки преподавателя по user_id: {user_id}")

            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]).strip() == str(user_id):
                    target_row = row_idx
                    logger.info(f"Найдена строка {target_row} для user_id {user_id}")
                    break

            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id}")
                return False

            # Обновляем ячейки
            if date_col_start + 1 <= len(headers):
                worksheet.cell(row=target_row, column=date_col_start + 1, value=start_time)
            if date_col_start + 2 <= len(headers):
                worksheet.cell(row=target_row, column=date_col_start + 2, value=end_time)

            self.workbook.save(self.excel_file_path)
            logger.info(f"Обновлена ячейка для user_id {user_id}, date {formatted_date}")
            return True

        except Exception as e:
            logger.error(f"Ошибка обновления ячейки преподавателя: {e}")
            return False

    def get_student_finances(self, user_id: int, subject_id: str, selected_date: str) -> Dict[str, float]:
        """Получает финансовую информацию для ученика по предмету и дате - ПОЛНАЯ ВЕРСИЯ"""
        try:
            cache_key = f"finances_{user_id}_{subject_id}_{selected_date}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                logger.info(f"Используем кэшированные финансовые данные для {cache_key}")
                return cached_result

            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                logger.error("В таблице 'Ученики бот' недостаточно данных")
                result = {"replenished": 0.0, "withdrawn": 0.0, "tariff": 0.0}
                self._set_cached_data(cache_key, result)
                return result

            # Находим строку ученика с указанным subject_id
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if (len(row_list) > 0 and str(row_list[0]).strip() == str(user_id) and
                        len(row_list) > 2 and str(row_list[2]).strip() == str(subject_id)):
                    target_row = row_idx
                    logger.info(f"Найдена строка ученика: строка {target_row}")
                    break

            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id} и subject_id {subject_id}")
                result = {"replenished": 0.0, "withdrawn": 0.0, "tariff": 0.0}
                self._set_cached_data(cache_key, result)
                return result

            # Получаем тариф ученика (столбец N, индекс 13)
            tariff = 0.0
            row_data = data[target_row - 1]
            if len(row_data) > 13 and row_data[13]:
                try:
                    tariff_str = str(row_data[13]).replace(',', '.').strip()
                    # Обрабатываем неразрывные пробелы и другие символы
                    tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                    tariff = float(tariff_str) if tariff_str else 0.0
                    logger.info(f"Тариф ученика: {tariff}")
                except ValueError as e:
                    logger.error(f"Ошибка преобразования тарифа: {e}")
                    tariff = 0.0

            # Форматируем выбранную дату для поиска
            formatted_date = self.format_date(selected_date)
            logger.info(f"Ищем финансовые данные для даты: {formatted_date}")

            # Получаем заголовки
            headers = [str(h).strip().lower() for h in data[0]]

            # 1. Сначала проверяем, было ли занятие в выбранную дату
            withdrawn = 0.0
            schedule_found = False

            # Ищем столбцы расписания (первые 245 столбцов)
            for i in range(min(245, len(headers))):
                header = headers[i]
                if formatted_date.lower() in header:
                    # Проверяем время занятия
                    if len(row_data) > i + 1:
                        start_time = row_data[i] if i < len(row_data) else ""
                        end_time = row_data[i + 1] if i + 1 < len(row_data) else ""

                        logger.info(f"Проверяем занятие: дата '{header}', время '{start_time}-{end_time}'")

                        if start_time and end_time and str(start_time).strip() and str(end_time).strip():
                            withdrawn = tariff
                            schedule_found = True
                            logger.info(f"✅ Найдено занятие: {start_time}-{end_time}, списание: {withdrawn} руб.")
                            break  # Прерываем после первого найденного занятия
                        else:
                            logger.info(f"❌ Занятие не найдено: start_time='{start_time}', end_time='{end_time}'")

            if not schedule_found:
                logger.info(f"Занятие на {formatted_date} не найдено")

            # 2. Ищем финансовые данные (столбцы начиная с JG)
            replenished = 0.0
            finance_found = False

            # Ищем финансовые столбцы для выбранной даты (начиная с столбца 245)
            # ОСНОВНОЕ ИСПРАВЛЕНИЕ: Ищем ПЕРВЫЙ столбец с нужной датой для пополнений
            for i in range(245, len(headers), 2):  # Шаг 2 - только столбцы пополнений
                if i >= len(headers):
                    break

                header = headers[i]
                if formatted_date.lower() in header:
                    # Нашли финансовый столбец для нужной даты - это столбец пополнений
                    if len(row_data) > i:
                        replenishment_str = row_data[i]
                        logger.info(
                            f"Найден финансовый столбец {i} для даты {formatted_date}: значение='{replenishment_str}'")

                        if replenishment_str and str(replenishment_str).strip():
                            try:
                                # ОБРАБАТЫВАЕМ НЕРАЗРЫВНЫЕ ПРОБЕЛЫ И РАЗНЫЕ ФОРМАТЫ ЧИСЕЛ
                                clean_str = str(replenishment_str)

                                # Заменяем неразрывные пробелы, обычные пробелы, запятые
                                clean_str = clean_str.replace('\xa0', '')  # неразрывный пробел
                                clean_str = clean_str.replace(' ', '')  # обычный пробел
                                clean_str = clean_str.replace(',', '.')  # запятая как разделитель дробей

                                # Убираем все нецифровые символы, кроме точки и минуса
                                import re
                                clean_str = re.sub(r'[^\d.-]', '', clean_str)

                                # Если после очистки строка пустая, значит было 0
                                if not clean_str:
                                    replenished = 0.0
                                    finance_found = True
                                    logger.info("После очистки строка пустая - пополнение = 0")
                                else:
                                    replenished = float(clean_str)
                                    finance_found = True
                                    logger.info(f"Пополнение найдено: {replenished} руб.")

                                break  # Выходим после нахождения первого совпадения даты
                            except ValueError as e:
                                logger.error(
                                    f"Ошибка преобразования пополнения '{replenishment_str}' (очищенное: '{clean_str}'): {e}")
                        else:
                            logger.info(f"Ячейка пополнения пустая: '{replenishment_str}'")
                    else:
                        logger.warning(f"Строка слишком короткая для столбца {i}")

                    break  # Выходим после нахождения первого совпадения даты

            if not finance_found:
                logger.info(f"Финансовые данные для {formatted_date} не найдены или равны 0")

            result = {
                "replenished": replenished,
                "withdrawn": withdrawn,
                "tariff": tariff
            }

            logger.info(f"Итоговые данные: {result}")
            self._set_cached_data(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Ошибка получения финансов для user_id {user_id}: {e}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            result = {"replenished": 0.0, "withdrawn": 0.0, "tariff": 0.0}
            self._set_cached_data(cache_key, result)
            return result

    def get_available_finance_dates(self, user_id: int, subject_id: str) -> List[str]:
        """Получает доступные даты для просмотра финансов"""
        try:
            cache_key = f"finance_dates_{user_id}_{subject_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return []

            # Находим строку ученика
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if (len(row_list) > 0 and str(row_list[0]).strip() == str(user_id) and
                        len(row_list) > 2 and str(row_list[2]).strip() == str(subject_id)):
                    target_row = row_idx
                    break

            if target_row == -1:
                return []

            # Получаем только заголовки финансовых столбцов (начиная с JG)
            headers = [str(h).strip().lower() for h in data[0]]

            available_dates = []

            # Только финансовые столбцы (начиная с 245)
            for i in range(245, min(len(headers), 500)):
                if i < len(headers) and headers[i]:
                    # Извлекаем дату из заголовка
                    date_header = headers[i].split()[0] if ' ' in headers[i] else headers[i]

                    try:
                        date_formats = ["%d.%m.%Y", "%d.%m", "%d.%m.%y"]
                        date_obj = None

                        for date_format in date_formats:
                            try:
                                date_obj = datetime.strptime(date_header, date_format)
                                if date_format == "%d.%m":
                                    date_obj = date_obj.replace(year=datetime.now().year)
                                break
                            except ValueError:
                                continue

                        if date_obj:
                            formatted_date = date_obj.strftime("%Y-%m-%d")
                            available_dates.append(formatted_date)

                    except ValueError:
                        continue

            # Убираем дубликаты и сортируем
            available_dates = sorted(list(set(available_dates)))
            logger.info(f"Доступные финансовые даты: {len(available_dates)} дат")

            self._set_cached_data(cache_key, available_dates)
            return available_dates

        except Exception as e:
            logger.error(f"Ошибка получения доступных дат финансов: {e}")
            return []

    def get_student_balance(self, student_id: int) -> float:
        """Получает текущий баланс студента на основе всей истории"""
        try:
            finance_history = self.get_student_finance_history(student_id)

            total_replenished = 0.0
            total_withdrawn = 0.0

            for operation in finance_history:
                total_replenished += operation["replenished"]
                total_withdrawn += operation["withdrawn"]

            balance = total_replenished - total_withdrawn
            logger.info(
                f"Balance for student {student_id}: {balance} (replenished: {total_replenished}, withdrawn: {total_withdrawn})")

            return balance

        except Exception as e:
            logger.error(f"Error calculating balance for student {student_id}: {e}")
            return 0.0

    def update_student_balance(self, student_id: int, amount: float):
        """Обновляет баланс студента в Excel"""
        try:
            worksheet = self._get_or_create_worksheet("Балансы")
            data = list(worksheet.values)

            # Ищем существующую запись
            found = False
            for i, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if row_list and len(row_list) >= 1 and str(row_list[0]).strip() == str(student_id):
                    worksheet.cell(row=i, column=2, value=amount)
                    found = True
                    break

            # Если не нашли, добавляем новую запись
            if not found:
                next_row = len(data) + 1
                worksheet.cell(row=next_row, column=1, value=student_id)
                worksheet.cell(row=next_row, column=2, value=amount)

            self.workbook.save(self.excel_file_path)

        except Exception as e:
            logger.error(f"Error updating balance in Excel: {e}")

    def get_student_finances_with_balance(self, student_id: int, subject_id: str, date: str) -> Dict:
        """Получает финансовую информацию с учетом баланса"""
        finances = self.get_student_finances(student_id, subject_id, date)
        finances["balance"] = self.get_student_balance(student_id)
        return finances

    def process_daily_finances(self):
        """Обрабатывает дневные финансы и обновляет балансы"""
        try:
            # Получаем все финансовые операции за сегодня
            today = datetime.now().strftime("%Y-%m-%d")
            worksheet = self._get_or_create_worksheet("Финансы")
            data = list(worksheet.values)

            # Пропускаем заголовок
            for row in data[1:]:
                row_list = list(row)
                if len(row_list) >= 5 and row_list[3] == today:
                    student_id = int(row_list[0])
                    replenished = float(row_list[4] or 0)
                    withdrawn = float(row_list[5] or 0)

                    # Получаем текущий баланс
                    current_balance = self.get_student_balance(student_id)

                    # Обновляем баланс
                    new_balance = current_balance + replenished - withdrawn
                    self.update_student_balance(student_id, new_balance)

            logger.info("Daily finances processed successfully")

        except Exception as e:
            logger.error(f"Error processing daily finances: {e}")

    def get_student_finance_history(self, student_id: int) -> List[Dict]:
        """Получает полную историю финансовых операций студента"""
        try:
            cache_key = f"finance_history_{student_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return []

            # Находим все строки студента
            student_rows = []
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]).strip() == str(student_id):
                    subject_id = row_list[2].strip() if len(row_list) > 2 and row_list[2] else ""
                    if subject_id:
                        student_rows.append({
                            'row_idx': row_idx,
                            'subject_id': subject_id,
                            'row_data': row_list
                        })

            if not student_rows:
                return []

            finance_history = []
            headers = [str(h).strip().lower() for h in data[0]]

            # Словарь для объединения операций по дате и предмету
            operations_dict = {}

            # Для каждой строки студента (каждого предмета) собираем операции
            for student_row in student_rows:
                subject_id = student_row['subject_id']
                row_data = student_row['row_data']

                # Получаем тариф для этого предмета
                tariff = 0.0
                if len(row_data) > 13 and row_data[13]:
                    try:
                        tariff_str = str(row_data[13]).replace(',', '.').strip()
                        tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                        tariff = float(tariff_str) if tariff_str else 0.0
                        logger.info(f"Тариф для предмета {subject_id}: {tariff} руб.")
                    except ValueError:
                        tariff = 0.0

                # 1. Сначала собираем ВСЕ занятия из расписания (столбцы 14-244)
                schedule_lessons = {}
                for schedule_col in range(14, min(245, len(headers)), 2):
                    if schedule_col >= len(headers) or not headers[schedule_col]:
                        continue

                    # Извлекаем дату из заголовка расписания
                    schedule_date_header = headers[schedule_col].split()[0] if ' ' in headers[schedule_col] else \
                    headers[schedule_col]

                    try:
                        date_formats = ["%d.%m.%Y", "%d.%m", "%d.%m.%y"]
                        date_obj = None

                        for date_format in date_formats:
                            try:
                                date_obj = datetime.strptime(schedule_date_header, date_format)
                                if date_format == "%d.%m":
                                    date_obj = date_obj.replace(year=datetime.now().year)
                                break
                            except ValueError:
                                continue

                        if not date_obj:
                            continue

                        formatted_date = date_obj.strftime("%Y-%m-%d")

                    except ValueError:
                        continue

                    # Проверяем, есть ли время занятия
                    has_start_time = len(row_data) > schedule_col and row_data[schedule_col] and str(
                        row_data[schedule_col]).strip()
                    has_end_time = len(row_data) > schedule_col + 1 and row_data[schedule_col + 1] and str(
                        row_data[schedule_col + 1]).strip()

                    if has_start_time and has_end_time:
                        start_time = row_data[schedule_col].strip()
                        end_time = row_data[schedule_col + 1].strip()

                        # Занятие было - сохраняем в словарь
                        schedule_lessons[formatted_date] = {
                            'start_time': start_time,
                            'end_time': end_time
                        }
                        logger.info(
                            f"Найдено занятие в расписании: дата {formatted_date}, время {start_time}-{end_time}, предмет {subject_id}")

                # 2. Обрабатываем финансовые столбцы (начиная с 245)
                for i in range(245, min(len(headers), 500)):
                    if i >= len(headers) or not headers[i]:
                        continue

                    # Извлекаем дату из заголовка финансового столбца
                    date_header = headers[i].split()[0] if ' ' in headers[i] else headers[i]

                    try:
                        date_formats = ["%d.%m.%Y", "%d.%m", "%d.%m.%y"]
                        date_obj = None

                        for date_format in date_formats:
                            try:
                                date_obj = datetime.strptime(date_header, date_format)
                                if date_format == "%d.%m":
                                    date_obj = date_obj.replace(year=datetime.now().year)
                                break
                            except ValueError:
                                continue

                        if not date_obj:
                            continue

                        formatted_date = date_obj.strftime("%Y-%m-%d")

                    except ValueError:
                        continue

                    # Обрабатываем значение ячейки пополнения
                    replenished = 0.0
                    if len(row_data) > i and row_data[i]:
                        try:
                            cell_value = str(row_data[i]).strip()

                            # Очищаем строку от лишних символов
                            clean_str = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                            clean_str = re.sub(r'[^\d.-]', '', clean_str)

                            if clean_str and self._is_float(clean_str):
                                raw_value = float(clean_str)

                                # Учитываем только положительные пополнения
                                if raw_value > 0:
                                    replenished = raw_value
                                    logger.info(
                                        f"Найдено пополнение: дата {formatted_date}, сумма {replenished}, предмет {subject_id}")

                        except (ValueError, TypeError) as e:
                            logger.debug(f"Ошибка обработки пополнения '{cell_value}': {e}")
                            continue

                    # 3. Проверяем, было ли занятие в эту дату
                    withdrawn = 0.0
                    if formatted_date in schedule_lessons:
                        withdrawn = tariff
                        lesson_info = schedule_lessons[formatted_date]
                        logger.info(
                            f"Найдено списание за занятие: дата {formatted_date}, время {lesson_info['start_time']}-{lesson_info['end_time']}, сумма {withdrawn}, предмет {subject_id}")

                    # Создаем уникальный ключ для операции (дата + предмет)
                    operation_key = f"{formatted_date}_{subject_id}"

                    # Если операция с таким ключом уже существует, объединяем значения
                    if operation_key in operations_dict:
                        existing_op = operations_dict[operation_key]
                        existing_op["replenished"] += replenished
                        if withdrawn > 0 and existing_op["withdrawn"] == 0:
                            existing_op["withdrawn"] = withdrawn
                    else:
                        # Добавляем операцию только если есть движение средств
                        if replenished != 0 or withdrawn != 0:
                            operations_dict[operation_key] = {
                                "date": formatted_date,
                                "replenished": replenished,
                                "withdrawn": withdrawn,
                                "tariff": tariff,
                                "subject": subject_id
                            }

            # Преобразуем словарь обратно в список
            finance_history = list(operations_dict.values())

            # Сортируем по дате
            finance_history.sort(key=lambda x: x["date"])

            logger.info(f"=== ИТОГОВАЯ ИСТОРИЯ ОПЕРАЦИЙ ДЛЯ {student_id} ===")
            for op in finance_history:
                logger.info(f"Операция: {op['date']} {op['subject']} +{op['replenished']} -{op['withdrawn']}")

            self._set_cached_data(cache_key, finance_history)
            return finance_history

        except Exception as e:
            logger.error(f"Error getting finance history for student {student_id}: {e}")
            return []

    def get_student_balance_by_subjects(self, student_id: int) -> Dict[str, float]:
        """Получает баланс студента разбитый по предметам"""
        try:
            cache_key = f"balance_by_subjects_{student_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return {}

            # Находим все строки студента
            student_rows = []
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]).strip() == str(student_id):
                    subject_id = row_list[2].strip() if len(row_list) > 2 and row_list[2] else ""
                    if subject_id:
                        student_rows.append({
                            'row_idx': row_idx,
                            'subject_id': subject_id,
                            'row_data': row_list
                        })

            if not student_rows:
                return {}

            headers = [str(h).strip().lower() for h in data[0]]
            subject_balances = {}

            # Для каждой строки студента (каждого предмета) вычисляем баланс
            for student_row in student_rows:
                subject_id = student_row['subject_id']
                total_replenished = 0.0
                total_withdrawn = 0.0
                row_data = student_row['row_data']

                # Получаем тариф для этого предмета
                tariff = 0.0
                if len(row_data) > 13 and row_data[13]:
                    try:
                        tariff_str = str(row_data[13]).replace(',', '.').strip()
                        tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                        tariff = float(tariff_str) if tariff_str else 0.0
                        logger.info(f"Тариф для предмета {subject_id}: {tariff}")
                    except ValueError:
                        tariff = 0.0

                # 1. Учитываем финансовые операции (столбцы пополнений начиная с 245)
                for i in range(245, min(len(headers), 500)):
                    if i >= len(headers) or not headers[i]:
                        continue

                    # Обрабатываем значение ячейки пополнения
                    if len(row_data) > i and row_data[i]:
                        try:
                            cell_value = str(row_data[i]).strip()

                            # Очищаем строку от лишних символов
                            clean_str = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                            clean_str = re.sub(r'[^\d.-]', '', clean_str)

                            if clean_str and self._is_float(clean_str):
                                amount = float(clean_str)
                                # Учитываем только положительные пополнения
                                if amount > 0:
                                    total_replenished += amount
                                    logger.info(
                                        f"Найдено пополнение для предмета {subject_id}: {amount} руб. в столбце {i}")
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Ошибка обработки пополнения '{cell_value}': {e}")
                            continue

                # 2. Учитываем списания за занятия (расписание в столбцах 14-244)
                for i in range(14, min(245, len(headers)), 2):
                    if (i < len(headers) and headers[i] and
                            len(row_data) > i + 1 and row_data[i] and row_data[i + 1]):
                        # Если есть время начала и окончания - занятие было проведено
                        start_time = row_data[i].strip()
                        end_time = row_data[i + 1].strip()
                        if start_time and end_time:
                            total_withdrawn += tariff
                            logger.info(
                                f"Найдено занятие для предмета {subject_id}: время {start_time}-{end_time}, списание {tariff} руб.")

                # Итоговый баланс = пополнения - списания
                final_balance = total_replenished - total_withdrawn
                subject_balances[subject_id] = final_balance

                logger.info(
                    f"Баланс по предмету {subject_id}: пополнения={total_replenished}, списания={total_withdrawn}, итого={final_balance}")

            self._set_cached_data(cache_key, subject_balances)
            return subject_balances

        except Exception as e:
            logger.error(f"Ошибка получения баланса по предметам для student_id {student_id}: {e}")
            return {}

    def get_self_employed_with_lowest_balance(self, money: float) -> Dict[str, any]:
        """Находит самозанятого преподавателя с наименьшим балансом, учитывая лимиты - ПОЛНАЯ ВЕРСИЯ"""
        try:
            # Используем кэш
            cache_key = f"self_employed_lowest_balance_{money}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            logger.info("=== ПОИСК САМОЗАНЯТОГО С НАИМЕНЬШИМ БАЛАНСОМ (С УЧЕТОМ ЛИМИТОВ) ===")

            # Получаем список самозанятых
            self_employed_worksheet = self._get_or_create_worksheet("Самозанятые бот")
            self_employed_data = list(self_employed_worksheet.values)

            logger.info(f"Найдено строк в 'Самозанятые бот': {len(self_employed_data)}")

            if len(self_employed_data) < 2:
                logger.warning("В листе 'Самозанятые бот' нет данных")
                return {}

            # Получаем данные преподавателей для балансов
            teachers_worksheet = self._get_or_create_worksheet("Преподаватели бот")
            teachers_data = list(teachers_worksheet.values)

            logger.info(f"Найдено строк в 'Преподаватели бот': {len(teachers_data)}")

            if len(teachers_data) < 2:
                logger.warning("В листе 'Преподаватели бот' нет данных")
                return {}

            # Получаем текущий месяц
            from datetime import datetime
            current_month = datetime.now().month
            logger.info(f"Текущий месяц: {current_month}")

            # Собираем имена самозанятых и их лимиты
            self_employed_info = {}
            logger.info("Самозанятые в таблице:")

            # Анализируем заголовки для определения столбцов месяцев
            headers = self_employed_data[0]
            month_columns = {}  # {номер_месяца: индекс_столбца}

            for i, header in enumerate(headers):
                header_str = str(header).strip()
                if header_str.isdigit():
                    month_num = int(header_str)
                    month_columns[month_num] = i
                    logger.info(f"Найден столбец для месяца {month_num}: индекс {i}")

            for row in self_employed_data[1:]:  # Пропускаем заголовок
                row_list = list(row)
                if len(row_list) > 0 and row_list[0].strip():
                    name = row_list[0].strip()

                    # Получаем лимит (столбец E, индекс 4)
                    monthly_limit = 0
                    if len(row_list) > 4 and row_list[4].strip():
                        try:
                            monthly_limit = float(row_list[4].strip().replace(',', '.'))
                        except ValueError:
                            logger.warning(f"Некорректный лимит для {name}: '{row_list[4]}'")
                            monthly_limit = 0

                    # Получаем выплачено за текущий месяц
                    paid_amount = 0
                    if current_month in month_columns:
                        col_index = month_columns[current_month]
                        if len(row_list) > col_index and row_list[col_index].strip():
                            try:
                                paid_amount = float(row_list[col_index].strip().replace(',', '.'))
                            except ValueError:
                                logger.warning(
                                    f"Некорректное значение выплачено для {name} за месяц {current_month}: '{row_list[col_index]}'")
                                paid_amount = 0

                    self_employed_info[name.lower()] = {
                        'name': name,
                        'monthly_limit': monthly_limit,
                        'paid_amount': paid_amount,
                        'remaining_limit': monthly_limit - paid_amount,
                        'row_data': row_list,  # Сохраняем всю строку для обновления
                        'month_column': month_columns.get(current_month)  # Сохраняем индекс столбца месяца
                    }

                    logger.info(
                        f"  - {name}: лимит={monthly_limit}, выплачено={paid_amount}, остаток={monthly_limit - paid_amount}")

            if not self_employed_info:
                logger.warning("Не найдено имен самозанятых")
                return {}

            # Получаем заголовки преподавателей
            teachers_headers = [str(h).strip().lower() for h in teachers_data[0]]

            # Ищем столбец с балансом (столбец F, индекс 5)
            balance_col_index = -1
            for i, header in enumerate(teachers_headers):
                if 'баланс' in header or i == 5:  # Столбец F
                    balance_col_index = i
                    logger.info(f"Найден столбец баланса: индекс {i}, заголовок '{header}'")
                    break

            if balance_col_index == -1:
                logger.error("Не найден столбец с балансом в листе 'Преподаватели бот'")
                # Пробуем по индексу 5 как запасной вариант
                if len(teachers_headers) > 5:
                    balance_col_index = 5
                    logger.info(f"Используем столбец по индексу {balance_col_index}")
                else:
                    return {}

            self_employed_list = []

            # Ищем самозанятых в листе преподавателей и получаем их балансы
            logger.info("Поиск самозанятых в листе преподавателей:")
            for row in teachers_data[1:]:  # Пропускаем заголовок
                row_list = list(row)
                if len(row_list) <= max(1, balance_col_index):
                    continue

                name = row_list[1].strip() if len(row_list) > 1 and row_list[1] else ""
                if not name:
                    continue

                name_lower = name.lower()

                # Проверяем, есть ли этот преподаватель в списке самозанятых
                if name_lower not in self_employed_info:
                    continue

                # Получаем информацию о лимитах
                emp_info = self_employed_info[name_lower]

                # Парсим баланс (берем модуль значения)
                balance_str = row_list[balance_col_index] if len(row_list) > balance_col_index else "0"
                try:
                    # Обрабатываем формулу или числовое значение
                    balance_value = self._parse_balance_from_cell(balance_str)
                    # Берем модуль значения
                    balance_abs = balance_value

                    logger.info(
                        f"  - Найден: {name}, баланс: {balance_abs:.2f} (оригинал: {balance_value:.2f}), остаток лимита: {emp_info['remaining_limit']:.2f}")

                    self_employed_list.append({
                        'name': name,
                        'balance': balance_abs,  # Используем только для внутренней сортировки
                        'original_balance': balance_value,
                        'monthly_limit': emp_info['monthly_limit'],
                        'paid_amount': emp_info['paid_amount'],
                        'remaining_limit': emp_info['remaining_limit'],
                        'month_column': emp_info['month_column'],  # Добавляем индекс столбца месяца
                        'row_data': row_list
                    })

                except (ValueError, TypeError) as e:
                    logger.warning(f"Ошибка парсинга баланса для {name}: '{balance_str}', ошибка: {e}")
                    continue

            if not self_employed_list:
                logger.info("Не найдено самозанятых с балансами в листе преподавателей")
                return {}

            # Фильтруем самозанятых с положительным остатком лимита
            available_self_employed = [emp for emp in self_employed_list if emp['remaining_limit'] - money > 0]

            if not available_self_employed:
                logger.warning("Нет самозанятых с доступным лимитом")
                return {}

            # Находим самозанятого с наименьшим балансом среди доступных
            lowest_balance_person = min(available_self_employed, key=lambda x: x['balance'])
            logger.info(
                f"Самозанятый с наименьшим балансом: {lowest_balance_person['name']} - "
                f"{lowest_balance_person['balance']:.2f} руб., "
                f"остаток лимита: {lowest_balance_person['remaining_limit']:.2f} руб."
            )

            # Получаем дополнительные данные из листа самозанятых
            result = self._extract_self_employed_details(lowest_balance_person['name'], self_employed_data)

            # Добавляем информацию о лимитах и столбце месяца
            result.update({
                'monthly_limit': lowest_balance_person['monthly_limit'],
                'paid_amount': lowest_balance_person['paid_amount'],
                'remaining_limit': lowest_balance_person['remaining_limit'],
                'month_column': lowest_balance_person['month_column']  # Добавляем индекс столбца месяца
            })

            logger.info(
                f"Данные для перевода: карта={result.get('card_number', 'нет')}, "
                f"телефон={result.get('phone', 'нет')}, банк={result.get('bank', 'нет')}, "
                f"остаток лимита={result.get('remaining_limit', 0):.2f}, "
                f"столбец_месяца={result.get('month_column', 'нет')}"
            )

            self._set_cached_data(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Ошибка поиска самозанятого с наименьшим балансом: {e}")
            return {}

    def _parse_balance_from_cell(self, balance_str: str) -> float:
        """Парсит значение баланса из ячейки, может содержать формулы - ПОЛНАЯ ВЕРСИЯ"""
        try:
            clean_str = str(balance_str).strip()

            # Если это формула, пробуем извлечь числовое значение
            if '=' in clean_str:
                # Упрощенная обработка формул - ищем числовые значения
                import re
                numbers = re.findall(r'-?\d+[,.]?\d*', clean_str)
                if numbers:
                    # Берем последнее число в формуле (часто это результат)
                    number_str = numbers[-1]
                    clean_str = number_str

            # Очищаем строку
            clean_str = clean_str.replace('\xa0', '').replace(' ', '').replace(',', '.')
            import re
            clean_str = re.sub(r'[^\d.-]', '', clean_str)

            if not clean_str:
                return 0.0

            return float(clean_str)

        except Exception as e:
            logger.error(f"Ошибка парсинга баланса '{balance_str}': {e}")
            return 0.0

    def _extract_self_employed_details(self, name: str, self_employed_data: List[List]) -> Dict:
        """Извлекает детальную информацию о самозанятом из листа самозанятых - ПОЛНАЯ ВЕРСИЯ"""
        try:
            # Ищем строку с данным именем в листе самозанятых
            target_name_lower = name.lower()

            logger.info(f"Поиск данных для: {name}")

            for i, row in enumerate(self_employed_data[1:], start=2):  # Пропускаем заголовок
                row_list = list(row)
                if not row_list or len(row_list) == 0:
                    continue

                row_name = row_list[0].strip() if row_list[0] else ""
                if row_name.lower() == target_name_lower:
                    # Нашли совпадение - извлекаем данные
                    # Структура: A-Имя, B-Телефон, C-Карта, D-Банк, E-Лимит, F-... месяцы
                    details = {
                        'name': row_name,
                        'phone': row_list[1] if len(row_list) > 1 and row_list[1] else "",
                        'card_number': row_list[2] if len(row_list) > 2 and row_list[2] else "",
                        'bank': row_list[3] if len(row_list) > 3 and row_list[3] else "",
                        'monthly_limit': 0,
                        'paid_amount': 0,
                        'remaining_limit': 0
                    }

                    # Получаем лимит (столбец E, индекс 4)
                    if len(row_list) > 4 and row_list[4]:
                        try:
                            details['monthly_limit'] = float(row_list[4].strip().replace(',', '.'))
                        except ValueError:
                            logger.warning(f"Некорректный лимит для {name}: '{row_list[4]}'")

                    # Получаем выплачено за текущий месяц (будет вычислено в основном методе)
                    # Вычисляем остаток лимита
                    details['remaining_limit'] = details['monthly_limit'] - details['paid_amount']

                    # Очищаем данные
                    for key in ['phone', 'card_number', 'bank']:
                        if details[key]:
                            details[key] = str(details[key]).strip()

                    # Проверяем, есть ли хоть какие-то контактные данные
                    has_contact = bool(details['phone'] or details['card_number'])
                    logger.info(
                        f"Найдены данные в строке {i}: "
                        f"телефон='{details['phone']}', карта='{details['card_number']}', "
                        f"банк='{details['bank']}', лимит={details['monthly_limit']:.2f}, "
                        f"есть_контакты={has_contact}"
                    )

                    return details

            # Если не нашли, возвращаем базовую информацию
            logger.warning(f"Не найдены контактные данные для: {name}")
            return {
                'name': name,
                'phone': '',
                'card_number': '',
                'bank': '',
                'monthly_limit': 0,
                'paid_amount': 0,
                'remaining_limit': 0
            }

        except Exception as e:
            logger.error(f"Ошибка извлечения деталей самозанятого: {e}")
            return {
                'name': name,
                'phone': '',
                'card_number': '',
                'bank': '',
                'monthly_limit': 0,
                'paid_amount': 0,
                'remaining_limit': 0
            }

    def update_self_employed_payment(self, teacher_name: str, amount: float) -> bool:
        """Обновляет столбец текущего месяца для самозанятого преподавателя - ПОЛНАЯ ВЕРСИЯ"""
        try:
            worksheet = self._get_or_create_worksheet("Самозанятые бот")
            if not worksheet:
                logger.error("В листе 'Самозанятые бот' нет данных")
                return False

            data = list(worksheet.values)

            if len(data) < 2:
                logger.error("В листе 'Самозанятые бот' нет данных")
                return False

            # Получаем текущий месяц
            from datetime import datetime
            current_month = datetime.now().month
            logger.info(f"Текущий месяц для обновления: {current_month}")

            # Анализируем заголовки для определения столбца текущего месяца
            headers = data[0]
            current_month_col = None

            for i, header in enumerate(headers):
                header_str = str(header).strip()
                if header_str.isdigit():
                    month_num = int(header_str)
                    if month_num == current_month:
                        current_month_col = i
                        logger.info(f"Найден столбец для текущего месяца {current_month}: индекс {i}")
                        break

            if current_month_col is None:
                logger.error(f"Не найден столбец для текущего месяца {current_month}")
                return False

            # Ищем строку преподавателя
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):  # Пропускаем заголовок
                row_list = list(row)
                if len(row_list) > 0 and row_list[0].strip().lower() == teacher_name.lower():
                    target_row = row_idx
                    break

            if target_row == -1:
                logger.error(f"Не найдена строка для самозанятого: {teacher_name}")
                return False

            # Получаем текущее значение выплачено за текущий месяц
            current_paid = 0.0
            if len(data[target_row - 1]) > current_month_col and data[target_row - 1][current_month_col]:
                try:
                    current_paid_str = data[target_row - 1][current_month_col].replace(',', '.').strip()
                    current_paid_str = current_paid_str.replace('\xa0', '').replace(' ', '')
                    # ПРЕОБРАЗУЕМ В FLOAT
                    current_paid = float(current_paid_str) if current_paid_str else 0.0
                except ValueError as e:
                    logger.warning(f"Ошибка преобразования текущего выплачено для {teacher_name}: {e}")
                    current_paid = 0.0

            # Вычисляем новое значение - ПРЕОБРАЗУЕМ amount в float
            amount_float = float(amount)
            new_paid = current_paid + amount_float

            try:
                # Обновляем ячейку
                worksheet.cell(row=target_row, column=current_month_col + 1, value=f"{new_paid:.2f}")

                logger.info(
                    f"Обновлены выплаты для {teacher_name} за месяц {current_month}: было {current_paid:.2f}, стало {new_paid:.2f}, добавлено {amount_float:.2f}")
                return True
            except Exception as e:
                logger.error(f"Ошибка обновления ячейки для самозанятого {teacher_name}: {e}")
                return False

        except Exception as e:
            logger.error(f"Ошибка обновления выплат для самозанятого {teacher_name}: {e}")
            return False

    def debug_specific_date(self, student_id: int, date_str: str):
        """Отладочный метод для проверки данных по конкретной дате - ПОЛНАЯ ВЕРСИЯ"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return

            logger.info(f"=== ОТЛАДКА ДАТЫ {date_str} ДЛЯ {student_id} ===")

            # Форматируем дату для поиска
            formatted_date = self.format_date(date_str)

            headers = [str(h).strip().lower() for h in data[0]]

            # Ищем все строки студента
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]).strip() == str(student_id):
                    subject_id = row_list[2].strip() if len(row_list) > 2 and row_list[2] else "N/A"

                    logger.info(f"Строка {row_idx}, предмет {subject_id}:")

                    # Проверяем расписание (столбцы 14-244)
                    for i in range(14, min(245, len(headers)), 2):
                        if i < len(headers) and formatted_date.lower() in headers[i]:
                            start_time = row_list[i] if i < len(row_list) else ""
                            end_time = row_list[i + 1] if i + 1 < len(row_list) else ""
                            logger.info(f"  Расписание: {headers[i]} = {start_time}-{end_time}")

                    # Проверяем финансы (столбцы 245+)
                    for i in range(245, min(len(headers), 500)):
                        if i < len(headers) and formatted_date.lower() in headers[i]:
                            value = row_list[i] if i < len(row_list) else ""
                            logger.info(f"  Финансы: {headers[i]} = {value}")

        except Exception as e:
            logger.error(f"Ошибка при отладке даты: {e}")

    def debug_finance_structure(self, student_id: int, subject_id: str):
        """Отладочный метод для просмотра структуры финансовых данных - ПОЛНАЯ ВЕРСИЯ"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return

            # Находим строку ученика
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if (len(row_list) > 0 and str(row_list[0]).strip() == str(student_id) and
                        len(row_list) > 2 and str(row_list[2]).strip() == str(subject_id)):
                    target_row = row_idx
                    break

            if target_row == -1:
                logger.error(f"Строка не найдена для student_id {student_id}, subject_id {subject_id}")
                return

            headers = [str(h).strip() for h in data[0]]
            row_data = data[target_row - 1]

            logger.info("=== ОТЛАДКА ФИНАНСОВОЙ СТРУКТУРЫ ===")
            logger.info(f"Заголовки финансовых столбцов (245+):")

            # Показываем финансовые столбцы
            for i in range(245, min(len(headers), 300)):  # Первые 55 финансовых столбцов
                if i < len(headers) and headers[i]:
                    value = row_data[i] if i < len(row_data) else "N/A"
                    logger.info(f"Столбец {i}: '{headers[i]}' = '{value}'")

        except Exception as e:
            logger.error(f"Ошибка при отладке структуры: {e}")

    def debug_schedule_lessons(self, student_id: int, subject_id: str):
        """Отладочный метод для проверки занятий в расписании - ПОЛНАЯ ВЕРСИЯ"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return

            # Находим строку студента
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if (len(row_list) > 0 and str(row_list[0]).strip() == str(student_id) and
                        len(row_list) > 2 and str(row_list[2]).strip() == str(subject_id)):
                    target_row = row_idx
                    break

            if target_row == -1:
                logger.error(f"Строка не найдена")
                return

            headers = [str(h).strip().lower() for h in data[0]]
            row_data = data[target_row - 1]

            logger.info(f"=== ОТЛАДКА РАСПИСАНИЯ ДЛЯ {subject_id} ===")

            # Проверяем столбцы расписания (14-244)
            for i in range(14, min(245, len(headers)), 2):
                if i < len(headers) and headers[i]:
                    start_time = row_data[i] if i < len(row_data) else ""
                    end_time = row_data[i + 1] if i + 1 < len(row_data) else ""

                    if start_time and end_time and str(start_time).strip() and str(end_time).strip():
                        logger.info(f"Найдено занятие: столбец {i}, время {start_time}-{end_time}, дата '{headers[i]}'")

        except Exception as e:
            logger.error(f"Ошибка при отладке расписания: {e}")

    def _is_float(self, value: str) -> bool:
        """Проверяет, можно ли преобразовать строку в float"""
        try:
            float(value)
            return True
        except ValueError:
            return False

    def get_student_finance_history_last_month(self, student_id: int) -> List[Dict]:
        """Получает историю финансовых операций студента за последний месяц"""
        try:
            cache_key = f"finance_history_last_month_{student_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            # Получаем полную историю
            full_history = self.get_student_finance_history(student_id)

            # Фильтруем за последний месяц
            from datetime import datetime, timedelta
            one_month_ago = datetime.now() - timedelta(days=30)

            last_month_history = []
            for operation in full_history:
                try:
                    operation_date = datetime.strptime(operation["date"], "%Y-%m-%d")
                    if operation_date >= one_month_ago:
                        last_month_history.append(operation)
                except ValueError:
                    continue

            # Сортируем по дате (от старых к новым)
            last_month_history.sort(key=lambda x: x["date"])

            logger.info(f"=== ОТЛАДКА ИСТОРИИ ЗА ПОСЛЕДНИЙ МЕСЯЦ ДЛЯ {student_id} ===")
            for op in last_month_history:
                logger.info(f"Операция: {op['date']} {op['subject']} +{op['replenished']} -{op['withdrawn']}")

            self._set_cached_data(cache_key, last_month_history)
            return last_month_history

        except Exception as e:
            logger.error(f"Error getting last month finance history for student {student_id}: {e}")
            return []

    def get_subject_with_lowest_balance(self, user_id: int) -> str:
        """Определяет предмет с наименьшим балансом для ученика"""
        try:
            cache_key = f"lowest_balance_subject_{user_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            subject_balances = self.get_student_balance_by_subjects(user_id)
            if not subject_balances:
                return ""

            # Находим предмет с минимальным балансом
            min_balance = min(subject_balances.values())
            min_balance_subjects = [subj for subj, bal in subject_balances.items() if bal == min_balance]

            result = min_balance_subjects[0] if min_balance_subjects else ""

            logger.info(
                f"Предмет с наименьшим балансом для user_id {user_id}: {result} (баланс: {min_balance:.2f} руб.)")

            self._set_cached_data(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Ошибка определения предмета с наименьшим балансом для user_id {user_id}: {e}")
            return ""

    # Отладочные методы
    def debug_finance_columns(self, target_date: str):
        """Отладочный метод для просмотра структуры финансовых столбцов - ПОЛНАЯ ВЕРСИЯ"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 1:
                return

            headers = [str(h).strip() for h in data[0]]
            formatted_date = self.format_date(target_date)

            logger.info(f"=== ОТЛАДКА СТОЛБЦОВ ДЛЯ ДАТЫ {formatted_date} ===")

            # Ищем все столбцы с этой датой
            date_columns = []
            for i, header in enumerate(headers):
                if formatted_date.lower() in header.lower():
                    date_columns.append((i, header))

            logger.info(f"Найдено столбцов с датой {formatted_date}: {len(date_columns)}")
            for col_idx, header in date_columns:
                logger.info(f"Столбец {col_idx}: '{header}'")

                # Покажем значения из первых 3 строк для этого столбца
                for row_idx in range(1, min(4, len(data))):
                    if len(data[row_idx]) > col_idx:
                        value = data[row_idx][col_idx]
                        logger.info(f"  Строка {row_idx + 1}: '{value}'")

            # Покажем структуру вокруг финансовых столбцов
            logger.info("=== СТРУКТУРА ФИНАНСОВЫХ СТОЛБЦОВ (240-250) ===")
            for i in range(240, min(251, len(headers))):
                header = headers[i] if i < len(headers) else "N/A"
                logger.info(f"Столбец {i}: '{header}'")

        except Exception as e:
            logger.error(f"Ошибка при отладке столбцов: {e}")

    def debug_subject_tariffs(self, student_id: int):
        """Отладочный метод для проверки тарифов по предметам"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = list(worksheet.values)

            if len(data) < 2:
                return

            logger.info(f"=== ОТЛАДКА ТАРИФОВ ДЛЯ STUDENT_ID {student_id} ===")

            for row_idx, row in enumerate(data[1:], start=2):
                row_list = list(row)
                if len(row_list) > 0 and str(row_list[0]).strip() == str(student_id):
                    subject_id = row_list[2].strip() if len(row_list) > 2 and row_list[2] else "N/A"
                    tariff = row_list[13] if len(row_list) > 13 else "N/A"
                    logger.info(f"Строка {row_idx}: subject_id={subject_id}, tariff={tariff}")

        except Exception as e:
            logger.error(f"Ошибка при отладке тарифов: {e}")

    def debug_self_employed_structure(self):
        """Отладочный метод для просмотра структуры таблиц самозанятых"""
        try:
            logger.info("=== ОТЛАДКА СТРУКТУРЫ САМОЗАНЯТЫХ ===")

            # Смотрим структуру листа самозанятых
            self_employed_worksheet = self._get_or_create_worksheet("Самозанятые бот")
            self_employed_data = list(self_employed_worksheet.values)

            logger.info(f"Лист 'Самозанятые бот': {len(self_employed_data)} строк")
            if self_employed_data:
                logger.info(f"Заголовки: {self_employed_data[0]}")
                for i, row in enumerate(self_employed_data[1:6], start=2):
                    logger.info(f"Строка {i}: {row}")

        except Exception as e:
            logger.error(f"Ошибка при отладке структуры: {e}")