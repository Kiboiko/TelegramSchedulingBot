# excel_manager.py
import time
import pandas as pd
import openpyxl
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
import traceback
import os

logger = logging.getLogger(__name__)


class ExcelManager:
    def __init__(self, excel_file_path: str):
        self.excel_file_path = excel_file_path
        self.qual_map = {}
        self.qual_links = {}
        self._cache = {}
        self._cache_timeout = 60
        self._workbook = None

        # Имена листов в вашем файле Excel
        self.sheets = {
            'users': 'Пользователи бот',
            'students': 'Ученики бот',
            'teachers': 'Преподаватели бот',
            'self_employed': 'Самозанятые бот',
            'subjects': 'Предметы бот',
            'parents': 'Родители бот',
            'finances': 'Финансы',
            'balances': 'Балансы'
        }

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

    def connect(self):
        """Подключается к Excel файлу и проверяет листы"""
        try:
            if not os.path.exists(self.excel_file_path):
                logger.warning(f"Файл {self.excel_file_path} не найден, будет создан при первой записи")
                # Создаем базовую структуру файла
                self._create_excel_file()
                return True

            # Проверяем доступность файла
            self._workbook = openpyxl.load_workbook(self.excel_file_path)
            logger.info(f"Успешное подключение к Excel файлу: {self.excel_file_path}")

            # Проверяем наличие всех необходимых листов
            self._ensure_sheets_exist()

            self._load_qualifications()
            return True
        except Exception as e:
            logger.error(f"Ошибка подключения к Excel: {e}")
            return False

    def _create_excel_file(self):
        """Создает новый Excel файл с базовой структурой"""
        try:
            self._workbook = openpyxl.Workbook()
            # Удаляем лист по умолчанию
            default_sheet = self._workbook.active
            self._workbook.remove(default_sheet)

            # Создаем все необходимые листы
            for sheet_name in self.sheets.values():
                self._workbook.create_sheet(sheet_name)

            self._workbook.save(self.excel_file_path)
            logger.info(f"Создан новый Excel файл: {self.excel_file_path}")
        except Exception as e:
            logger.error(f"Ошибка создания Excel файла: {e}")

    def _ensure_sheets_exist(self):
        """Проверяет и создает отсутствующие листы"""
        try:
            existing_sheets = self._workbook.sheetnames
            sheets_created = False

            for sheet_name in self.sheets.values():
                if sheet_name not in existing_sheets:
                    self._workbook.create_sheet(sheet_name)
                    sheets_created = True
                    logger.info(f"Создан лист: {sheet_name}")

            if sheets_created:
                self._workbook.save(self.excel_file_path)

        except Exception as e:
            logger.error(f"Ошибка проверки листов: {e}")

    def _load_worksheet_data(self, sheet_key: str) -> pd.DataFrame:
        """Загружает данные из листа Excel файла"""
        try:
            if not os.path.exists(self.excel_file_path):
                return pd.DataFrame()

            sheet_name = self.sheets[sheet_key]
            df = pd.read_excel(self.excel_file_path, sheet_name=sheet_name, engine='openpyxl')
            return df
        except Exception as e:
            logger.error(f"Ошибка загрузки листа '{sheet_key}': {e}")
            return pd.DataFrame()

    def _save_worksheet_data(self, sheet_key: str, df: pd.DataFrame):
        """Сохраняет данные в лист Excel файла"""
        try:
            sheet_name = self.sheets[sheet_key]

            # Загружаем workbook
            if self._workbook is None:
                self._workbook = openpyxl.load_workbook(self.excel_file_path)

            # Удаляем существующий лист и создаем новый
            if sheet_name in self._workbook.sheetnames:
                del self._workbook[sheet_name]

            new_sheet = self._workbook.create_sheet(sheet_name)

            # Записываем заголовки
            for col_idx, column in enumerate(df.columns, 1):
                new_sheet.cell(row=1, column=col_idx, value=column)

            # Записываем данные
            for row_idx, row in df.iterrows():
                for col_idx, value in enumerate(row, 1):
                    new_sheet.cell(row=row_idx + 2, column=col_idx, value=value)

            self._workbook.save(self.excel_file_path)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения листа '{sheet_key}': {e}")
            return False

    def _load_qualifications(self):
        """Загружает соответствия предметов из листа предметов"""
        try:
            df = self._load_worksheet_data('subjects')

            self.qual_map = {}
            self.qual_links = {}

            if df.empty:
                logger.warning("Лист предметов пуст или не найден")
                return

            logger.info("=== ДАННЫЕ ИЗ ЛИСТА 'Предметы бот' ===")

            for _, row in df.iterrows():
                subject_id = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                subject_name = str(row.iloc[1]).strip().lower() if pd.notna(row.iloc[1]) else ""

                if subject_id.isdigit() and subject_name:
                    self.qual_map[subject_name] = subject_id

                    if len(row) >= 3 and pd.notna(row.iloc[2]):
                        self.qual_links[subject_id] = str(row.iloc[2]).strip()

                    logger.info(f"Добавлено: '{subject_name}' -> '{subject_id}'")

            logger.info(f"Итоговый qual_map: {self.qual_map}")

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

    def clear_sheet(self, file_key: str):
        """Полностью очищает файл"""
        try:
            empty_df = pd.DataFrame()
            return self._save_worksheet_data(file_key, empty_df)
        except Exception as e:
            logger.error(f"Ошибка при очистке файла {file_key}: {e}")
            return False

    def update_all_sheets(self, bookings: List[Dict[str, Any]]):
        """Полностью перезаписывает данные в таблицах"""
        try:
            logger.info(f"Начато обновление Excel файлов. Всего броней: {len(bookings)}")

            teachers = [b for b in bookings if b.get('user_role') == 'teacher']
            students = [b for b in bookings if b.get('user_role') == 'student']

            # Добавляем пользователей с ролями, но без записей
            teachers = self._add_users_without_bookings(teachers, 'teacher')
            students = self._add_users_without_bookings(students, 'student')

            success = True
            if not self._update_sheet('teachers', teachers, is_teacher=True):
                success = False
            if not self._update_sheet('students', students, is_teacher=False):
                success = False

            if success:
                logger.info("Excel файлы успешно обновлены!")
            return success
        except Exception as e:
            logger.error(f"Критическая ошибка при обновлении: {e}")
            return False

    def _add_users_without_bookings(self, bookings: List[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
        """Добавляет пользователей с ролями, но без записей"""
        try:
            users_df = self._load_worksheet_data('users')

            if users_df.empty:
                return bookings

            users_with_role = []
            for _, user in users_df.iterrows():
                user_roles = str(user.get('roles', '')).lower().split(',')
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

    def _update_sheet(self, file_key: str, bookings: List[Dict[str, Any]], is_teacher: bool):
        """Полностью перезаписывает данные в файле"""
        try:
            start_date = datetime(2025, 9, 1)
            end_date = datetime(2026, 1, 4)
            formatted_dates = self._generate_formatted_dates(start_date, end_date)

            records = self._prepare_records(bookings, formatted_dates, is_teacher)
            self._update_worksheet_data(file_key, records, formatted_dates, is_teacher)
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении файла '{file_key}': {e}")
            return False

    def _generate_formatted_dates(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Генерирует список отформатированных дат"""
        dates = []
        current_date = start_date
        while current_date <= end_date:
            dates.append(self.format_date(current_date.strftime('%Y-%m-%d')))
            current_date += timedelta(days=1)
        return dates

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

    def _update_worksheet_data(self, file_key: str, records: Dict[str, Any],
                               formatted_dates: List[str], is_teacher: bool):
        """Вставляет данные в файл"""
        if not records:
            logger.info("Нет данных для вставки - файл будет очищен")
            self.clear_sheet(file_key)
            return

        rows = []
        for record in records.values():
            row = [record['id'], record['name'], record['subject']]

            if not is_teacher:
                row.extend([
                    record.get('subject_name', ''),
                    record.get('class_name', '')
                ])

            if is_teacher:
                row.append(record.get('priority', ''))
            else:
                row.append(record.get('attention_need', ''))

            for date in formatted_dates:
                if date in record['bookings']:
                    row.extend([
                        record['bookings'][date]['start'],
                        record['bookings'][date]['end']
                    ])
                else:
                    row.extend(['', ''])
            rows.append(row)

        # Создаем DataFrame
        headers = ['ID', 'Имя', 'Предмет ID']
        if not is_teacher:
            headers.extend(['Предмет', 'Класс'])

        if is_teacher:
            headers.append('Приоритет')
        else:
            headers.append('Потребность во внимании (мин)')

        headers += [date for date in formatted_dates for _ in (0, 1)]

        # Обрезаем строки до длины заголовков
        max_cols = len(headers)
        processed_rows = []
        for row in rows:
            if len(row) > max_cols:
                processed_rows.append(row[:max_cols])
            else:
                processed_rows.append(row + [''] * (max_cols - len(row)))

        df = pd.DataFrame(processed_rows, columns=headers)
        self._save_worksheet_data(file_key, df)

        logger.info(f"Обновлено {len(rows)} строк в файле '{file_key}'")

    def get_bookings_from_sheet(self, file_key: str, is_teacher: bool) -> List[Dict[str, Any]]:
        """Загружает бронирования из Excel файла"""
        try:
            df = self._load_worksheet_data(file_key)

            if df.empty or len(df) < 3:
                return []

            bookings = []
            reverse_qual_map = {v: k for k, v in self.qual_map.items()}
            headers = [str(h).lower() for h in df.columns.tolist()]

            # Определяем индекс начала столбцов с датами
            date_start_col = 14  # Столбец O (индекс 14)

            for row_idx, row in df.iloc[2:].iterrows():  # Пропускаем заголовок и первую строку
                if pd.isna(row.iloc[0]):
                    continue

                try:
                    user_id = int(row.iloc[0]) if pd.notna(row.iloc[0]) else None
                except ValueError:
                    user_id = None

                user_name = row.iloc[1] if len(row) > 1 and pd.notna(row.iloc[1]) else ""

                if not is_teacher:
                    subject = row.iloc[2] if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                    attention_need = row.iloc[3] if len(row) > 3 and pd.notna(row.iloc[3]) else ""
                    subject_name = row.iloc[11] if len(row) > 11 and pd.notna(row.iloc[11]) else ""
                    class_name = row.iloc[10] if len(row) > 10 and pd.notna(row.iloc[10]) else ""
                else:
                    subject = row.iloc[2] if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                    priority = row.iloc[3] if len(row) > 3 and pd.notna(row.iloc[3]) else ""

                # Обрабатываем столбцы с датами
                for i in range(date_start_col, min(len(headers), 245), 2):
                    if i + 1 >= len(row) or i >= len(headers):
                        break

                    date_header = headers[i].split()[0] if i < len(headers) else ""
                    start_time = row.iloc[i] if i < len(row) and pd.notna(row.iloc[i]) else ""
                    end_time = row.iloc[i + 1] if i + 1 < len(row) and pd.notna(row.iloc[i + 1]) else ""

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
                            "start_time": str(start_time),
                            "end_time": str(end_time),
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
                            if subject in reverse_qual_map:
                                booking["subject"] = reverse_qual_map[subject]
                            else:
                                booking["subject"] = subject
                            booking["booking_type"] = "Тип1"
                            booking["attention_need"] = attention_need
                            booking["subject_name"] = subject_name
                            booking["class_name"] = class_name

                        bookings.append(booking)

                    except ValueError:
                        continue

            logger.info(f"Успешно обработано {len(bookings)} записей из файла '{file_key}'")
            return bookings

        except Exception as e:
            logger.error(f"Ошибка чтения из файла '{file_key}': {e}")
            return []

    def sync_from_gsheets_to_json(self, storage):
        """Синхронизирует данные из Excel в JSON хранилище"""
        try:
            teacher_bookings = self.get_bookings_from_sheet('teachers', is_teacher=True)
            student_bookings = self.get_bookings_from_sheet('students', is_teacher=False)

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

    def get_user_name(self, user_id: int) -> str:
        """Получает ФИО пользователя"""
        try:
            df = self._load_worksheet_data('users')

            if df.empty:
                return ""

            user_row = df[df.iloc[:, 0].astype(str) == str(user_id)]

            if not user_row.empty:
                return user_row.iloc[0, 1] if len(user_row.iloc[0]) > 1 else ""
            return ""
        except Exception as e:
            logger.error(f"User lookup error: {e}")
            return ""

    def save_user_name(self, user_id: int, user_name: str) -> bool:
        """Обновляет или создает запись пользователя"""
        try:
            df = self._load_worksheet_data('users')

            # Проверяем структуру
            if df.empty or len(df.columns) < 2:
                df = pd.DataFrame(columns=['user_id', 'user_name', 'roles', 'teacher_subjects'])

            # Ищем пользователя
            user_mask = df.iloc[:, 0].astype(str) == str(user_id)

            if user_mask.any():
                # Обновляем существующего
                df.loc[user_mask, df.columns[1]] = user_name
            else:
                # Добавляем нового
                new_row = {'user_id': user_id, 'user_name': user_name}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            return self._save_worksheet_data('users', df)
        except Exception as e:
            logger.error(f"User save error: {e}")
            return False

    def get_user_roles(self, user_id: int) -> List[str]:
        """Получает роли пользователя"""
        try:
            df = self._load_worksheet_data('users')

            if df.empty or len(df.columns) < 3:
                return []

            user_row = df[df.iloc[:, 0].astype(str) == str(user_id)]

            if not user_row.empty:
                roles_cell = user_row.iloc[0, 2] if len(user_row.iloc[0]) > 2 else ""
                if pd.notna(roles_cell) and roles_cell:
                    roles = [role.strip().lower() for role in str(roles_cell).split(',')]
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
            df = self._load_worksheet_data('users')

            if df.empty:
                return {}

            user_row = df[df.iloc[:, 0].astype(str) == str(user_id)]

            if not user_row.empty:
                row = user_row.iloc[0]
                result = {}
                for i, col_name in enumerate(df.columns):
                    if i < len(row):
                        result[col_name] = row.iloc[i] if pd.notna(row.iloc[i]) else ""
                return result
            return {}
        except Exception as e:
            logger.error(f"Ошибка при получении данных пользователя: {e}")
            return {}

    def save_user_data(self, user_data: dict) -> bool:
        """Сохраняет или обновляет данные пользователя"""
        try:
            df = self._load_worksheet_data('users')

            if df.empty or len(df.columns) < 2:
                df = pd.DataFrame(columns=['user_id', 'user_name', 'roles', 'teacher_subjects'])

            user_id = str(user_data["user_id"])
            user_mask = df.iloc[:, 0].astype(str) == user_id

            if user_mask.any():
                # Обновляем существующего
                for key, value in user_data.items():
                    if key in df.columns:
                        df.loc[user_mask, key] = value
            else:
                # Добавляем нового
                new_row = {col: user_data.get(col, "") for col in df.columns}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            return self._save_worksheet_data('users', df)
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных пользователя: {e}")
            return False

    def save_user_subject(self, user_id: int, user_name: str, subject_id: str) -> bool:
        """Сохраняет связь пользователь-предмет для учеников"""
        try:
            df = self._load_worksheet_data('students')

            if df.empty or len(df.columns) < 3:
                df = pd.DataFrame(columns=['user_id', 'user_name', 'subject_id'])

            # Ищем существующую запись
            user_mask = (df.iloc[:, 0].astype(str) == str(user_id)) & (df.iloc[:, 2].astype(str) == str(subject_id))

            if user_mask.any():
                # Обновляем
                df.loc[user_mask, df.columns[1]] = user_name
            else:
                # Добавляем новую
                new_row = {'user_id': user_id, 'user_name': user_name, 'subject_id': subject_id}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            return self._save_worksheet_data('students', df)
        except Exception as e:
            return False

    def get_teacher_subjects(self, user_id: int) -> List[str]:
        """Получает предметы преподавателя"""
        try:
            df = self._load_worksheet_data('users')

            if df.empty or len(df.columns) < 4:
                return []

            user_row = df[df.iloc[:, 0].astype(str) == str(user_id)]

            if not user_row.empty:
                subjects = user_row.iloc[0, 3] if len(user_row.iloc[0]) > 3 else ""
                if pd.notna(subjects) and subjects:
                    subjects_str = str(subjects)

                    if subjects_str.isdigit() and len(subjects_str) > 1:
                        return [digit for digit in subjects_str]
                    elif ',' in subjects_str:
                        return [subj.strip() for subj in subjects_str.split(',') if subj.strip()]
                    else:
                        return [subjects_str.strip()]

            return []
        except Exception as e:
            logger.error(f"Error getting teacher subjects: {e}")
            return []

    def get_parent_children(self, parent_id: int) -> List[int]:
        """Получает список ID детей родителя"""
        try:
            df = self._load_worksheet_data('parents')

            if df.empty or len(df.columns) < 3:
                return []

            parent_row = df[df.iloc[:, 0].astype(str) == str(parent_id)]

            if not parent_row.empty:
                children_str = parent_row.iloc[0, 2] if len(parent_row.iloc[0]) > 2 else ""
                if pd.notna(children_str) and children_str:
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
            df = self._load_worksheet_data('parents')

            if df.empty or len(df.columns) < 3:
                df = pd.DataFrame(columns=['user_id', 'user_name', 'children_ids'])

            children_str = ','.join(map(str, children_ids)) if children_ids else ''
            parent_mask = df.iloc[:, 0].astype(str) == str(parent_id)

            if parent_mask.any():
                # Обновляем
                df.loc[parent_mask, [df.columns[1], df.columns[2]]] = [parent_name, children_str]
            else:
                # Добавляем нового
                new_row = {'user_id': parent_id, 'user_name': parent_name, 'children_ids': children_str}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            return self._save_worksheet_data('parents', df)
        except Exception as e:
            logger.error(f"Error saving parent info: {e}")
            return False

    def get_available_subjects_for_student(self, user_id: int) -> List[str]:
        """Получает доступные предметы для ученика"""
        try:
            df = self._load_worksheet_data('students')

            if df.empty or len(df.columns) < 3:
                return []

            user_rows = df[df.iloc[:, 0].astype(str) == str(user_id)]
            available_subjects = []

            for _, row in user_rows.iterrows():
                if len(row) > 2 and pd.notna(row.iloc[2]):
                    subject = str(row.iloc[2]).strip()
                    if subject:
                        available_subjects.append(subject)

            return list(set(available_subjects))
        except Exception as e:
            logger.error(f"Ошибка получения доступных предметов для user_id {user_id}: {e}")
            return []

    def update_student_booking_cell(self, user_id: int, subject_id: str, date: str,
                                    start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для ученика"""
        try:
            df = self._load_worksheet_data('students')

            if df.empty:
                return False

            formatted_date = self.format_date(date) if date else ''
            headers = df.columns.tolist()

            # Ищем колонку для даты
            date_col_start = -1

            for i, header in enumerate(headers):
                header_str = str(header).strip().lower()
                if header_str.startswith(formatted_date.lower()):
                    date_col_start = i
                    break

            if date_col_start == -1:
                logger.error(f"Дата {formatted_date} не найдена в заголовках")
                return False

            # Ищем строку с user_id и subject_id
            target_mask = (df.iloc[:, 0].astype(str) == str(user_id)) & (df.iloc[:, 2].astype(str) == str(subject_id))

            if not target_mask.any():
                logger.error(f"Не найдена строка для user_id {user_id} и subject_id {subject_id}")
                return False

            # Обновляем ячейки
            df.loc[target_mask, df.columns[date_col_start]] = start_time
            if date_col_start + 1 < len(headers):
                df.loc[target_mask, df.columns[date_col_start + 1]] = end_time

            return self._save_worksheet_data('students', df)
        except Exception as e:
            logger.error(f"Ошибка обновления ячейки: {e}")
            return False

    def update_teacher_booking_cell(self, user_id: int, subjects: List[str], date: str,
                                    start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для преподавателя"""
        try:
            df = self._load_worksheet_data('teachers')

            if df.empty:
                return False

            formatted_date = self.format_date(date) if date else ''
            headers = df.columns.tolist()

            # Ищем колонку для даты
            date_col_start = -1

            for i, header in enumerate(headers):
                header_str = str(header).strip().lower()
                if header_str.startswith(formatted_date.lower()):
                    date_col_start = i
                    break

            if date_col_start == -1:
                logger.error(f"Дата {formatted_date} не найдена в заголовках")
                return False

            # Ищем строку по user_id
            target_mask = df.iloc[:, 0].astype(str) == str(user_id)

            if not target_mask.any():
                logger.error(f"Не найдена строка для user_id {user_id}")
                return False

            # Обновляем ячейки
            df.loc[target_mask, df.columns[date_col_start]] = start_time
            if date_col_start + 1 < len(headers):
                df.loc[target_mask, df.columns[date_col_start + 1]] = end_time

            return self._save_worksheet_data('teachers', df)
        except Exception as e:
            logger.error(f"Ошибка обновления ячейки преподавателя: {e}")
            return False

    def get_student_finances(self, user_id: int, subject_id: str, selected_date: str) -> Dict[str, float]:
        """Получает финансовую информацию для ученика по предмету и дате"""
        try:
            cache_key = f"finances_{user_id}_{subject_id}_{selected_date}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            df = self._load_worksheet_data('students')

            if df.empty:
                result = {"replenished": 0.0, "withdrawn": 0.0, "tariff": 0.0}
                self._set_cached_data(cache_key, result)
                return result

            # Находим строку ученика
            target_row = df[
                (df.iloc[:, 0].astype(str) == str(user_id)) &
                (df.iloc[:, 2].astype(str) == str(subject_id))
                ]

            if target_row.empty:
                result = {"replenished": 0.0, "withdrawn": 0.0, "tariff": 0.0}
                self._set_cached_data(cache_key, result)
                return result

            row_data = target_row.iloc[0]

            # Получаем тариф ученика (столбец N, индекс 13)
            tariff = 0.0
            if len(row_data) > 13 and pd.notna(row_data.iloc[13]):
                try:
                    tariff_str = str(row_data.iloc[13]).replace(',', '.').strip()
                    tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                    tariff = float(tariff_str) if tariff_str else 0.0
                except ValueError:
                    tariff = 0.0

            formatted_date = self.format_date(selected_date)

            # Проверяем занятие в расписании (столбцы 14-244)
            withdrawn = 0.0
            headers = df.columns.tolist()

            for i in range(14, min(245, len(headers)), 2):
                if i >= len(headers):
                    break

                header = str(headers[i]).strip().lower()
                if formatted_date.lower() in header:
                    start_time = row_data.iloc[i] if i < len(row_data) and pd.notna(row_data.iloc[i]) else ""
                    end_time = row_data.iloc[i + 1] if i + 1 < len(row_data) and pd.notna(row_data.iloc[i + 1]) else ""

                    if start_time and end_time and str(start_time).strip() and str(end_time).strip():
                        withdrawn = tariff
                        break

            # Ищем финансовые данные (столбцы 245+)
            replenished = 0.0

            for i in range(245, min(len(headers), 500)):
                if i >= len(headers):
                    break

                header = str(headers[i]).strip().lower()
                if formatted_date.lower() in header:
                    if i < len(row_data) and pd.notna(row_data.iloc[i]):
                        try:
                            replenishment_str = str(row_data.iloc[i])
                            clean_str = replenishment_str.replace('\xa0', '').replace(' ', '').replace(',', '.')
                            import re
                            clean_str = re.sub(r'[^\d.-]', '', clean_str)

                            if clean_str and self._is_float(clean_str):
                                replenished = float(clean_str)
                            break
                        except ValueError:
                            continue
                    break

            result = {
                "replenished": replenished,
                "withdrawn": withdrawn,
                "tariff": tariff
            }

            self._set_cached_data(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Ошибка получения финансов для user_id {user_id}: {e}")
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

            df = self._load_worksheet_data('students')

            if df.empty:
                return []

            # Находим строку ученика
            target_row = df[
                (df.iloc[:, 0].astype(str) == str(user_id)) &
                (df.iloc[:, 2].astype(str) == str(subject_id))
                ]

            if target_row.empty:
                return []

            available_dates = []
            headers = df.columns.tolist()

            # Финансовые столбцы (начиная с 245)
            for i in range(245, min(len(headers), 500)):
                if i >= len(headers) or not headers[i]:
                    continue

                date_header = str(headers[i]).split()[0] if ' ' in str(headers[i]) else str(headers[i])

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

            available_dates = sorted(list(set(available_dates)))
            self._set_cached_data(cache_key, available_dates)
            return available_dates

        except Exception as e:
            logger.error(f"Ошибка получения доступных дат финансов: {e}")
            return []

    def get_student_balance(self, student_id: int) -> float:
        """Получает текущий баланс студента"""
        try:
            finance_history = self.get_student_finance_history(student_id)

            total_replenished = 0.0
            total_withdrawn = 0.0

            for operation in finance_history:
                total_replenished += operation["replenished"]
                total_withdrawn += operation["withdrawn"]

            balance = total_replenished - total_withdrawn
            return balance
        except Exception as e:
            logger.error(f"Error calculating balance for student {student_id}: {e}")
            return 0.0

    def get_student_finance_history(self, student_id: int) -> List[Dict]:
        """Получает полную историю финансовых операций студента"""
        try:
            cache_key = f"finance_history_{student_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            df = self._load_worksheet_data('students')

            if df.empty:
                return []

            # Находим все строки студента
            student_rows = []
            for row_idx, row in df.iterrows():
                if len(row) > 0 and str(row.iloc[0]).strip() == str(student_id):
                    subject_id = row.iloc[2].strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                    if subject_id:
                        student_rows.append({
                            'row_idx': row_idx,
                            'subject_id': subject_id,
                            'row_data': row
                        })

            if not student_rows:
                return []

            finance_history = []
            headers = [str(h).strip().lower() for h in df.columns.tolist()]

            # Для каждой строки студента (каждого предмета) собираем операции
            for student_row in student_rows:
                subject_id = student_row['subject_id']
                row_data = student_row['row_data']

                # Получаем тариф для этого предмета
                tariff = 0.0
                if len(row_data) > 13 and pd.notna(row_data.iloc[13]):
                    try:
                        tariff_str = str(row_data.iloc[13]).replace(',', '.').strip()
                        tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                        tariff = float(tariff_str) if tariff_str else 0.0
                    except ValueError:
                        tariff = 0.0

                # Собираем занятия из расписания (столбцы 14-244)
                schedule_lessons = {}
                for i in range(14, min(245, len(headers)), 2):
                    if i >= len(headers) or not headers[i]:
                        continue

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

                    # Проверяем, есть ли время занятия
                    has_start_time = i < len(row_data) and pd.notna(row_data.iloc[i]) and str(row_data.iloc[i]).strip()
                    has_end_time = i + 1 < len(row_data) and pd.notna(row_data.iloc[i + 1]) and str(
                        row_data.iloc[i + 1]).strip()

                    if has_start_time and has_end_time:
                        schedule_lessons[formatted_date] = {
                            'start_time': str(row_data.iloc[i]).strip(),
                            'end_time': str(row_data.iloc[i + 1]).strip()
                        }

                # Обрабатываем финансовые столбцы (начиная с 245)
                for i in range(245, min(len(headers), 500)):
                    if i >= len(headers) or not headers[i]:
                        continue

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
                    if i < len(row_data) and pd.notna(row_data.iloc[i]):
                        try:
                            cell_value = str(row_data.iloc[i]).strip()
                            clean_str = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                            import re
                            clean_str = re.sub(r'[^\d.-]', '', clean_str)

                            if clean_str and self._is_float(clean_str):
                                raw_value = float(clean_str)
                                if raw_value > 0:
                                    replenished = raw_value
                        except (ValueError, TypeError):
                            continue

                    # Проверяем, было ли занятие в эту дату
                    withdrawn = 0.0
                    if formatted_date in schedule_lessons:
                        withdrawn = tariff

                    # Добавляем операцию только если есть движение средств
                    if replenished != 0 or withdrawn != 0:
                        operation = {
                            "date": formatted_date,
                            "replenished": replenished,
                            "withdrawn": withdrawn,
                            "tariff": tariff,
                            "subject": subject_id
                        }
                        finance_history.append(operation)

            # Сортируем по дате
            finance_history.sort(key=lambda x: x["date"])

            self._set_cached_data(cache_key, finance_history)
            return finance_history

        except Exception as e:
            logger.error(f"Error getting finance history for student {student_id}: {e}")
            return []

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

            last_month_history.sort(key=lambda x: x["date"])

            self._set_cached_data(cache_key, last_month_history)
            return last_month_history

        except Exception as e:
            logger.error(f"Error getting last month finance history for student {student_id}: {e}")
            return []

    def get_student_balance_by_subjects(self, student_id: int) -> Dict[str, float]:
        """Получает баланс студента разбитый по предметам"""
        try:
            cache_key = f"balance_by_subjects_{student_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            df = self._load_worksheet_data('students')

            if df.empty:
                return {}

            # Находим все строки студента
            student_rows = []
            for row_idx, row in df.iterrows():
                if len(row) > 0 and str(row.iloc[0]).strip() == str(student_id):
                    subject_id = row.iloc[2].strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                    if subject_id:
                        student_rows.append({
                            'row_idx': row_idx,
                            'subject_id': subject_id,
                            'row_data': row
                        })

            if not student_rows:
                return {}

            headers = [str(h).strip().lower() for h in df.columns.tolist()]
            subject_balances = {}

            # Для каждой строки студента (каждого предмета) вычисляем баланс
            for student_row in student_rows:
                subject_id = student_row['subject_id']
                total_replenished = 0.0
                total_withdrawn = 0.0
                row_data = student_row['row_data']

                # Получаем тариф для этого предмета
                tariff = 0.0
                if len(row_data) > 13 and pd.notna(row_data.iloc[13]):
                    try:
                        tariff_str = str(row_data.iloc[13]).replace(',', '.').strip()
                        tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                        tariff = float(tariff_str) if tariff_str else 0.0
                    except ValueError:
                        tariff = 0.0

                # Учитываем финансовые операции (столбцы пополнений начиная с 245)
                for i in range(245, min(len(headers), 500)):
                    if i >= len(headers) or not headers[i]:
                        continue

                    if i < len(row_data) and pd.notna(row_data.iloc[i]):
                        try:
                            cell_value = str(row_data.iloc[i]).strip()
                            clean_str = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                            import re
                            clean_str = re.sub(r'[^\d.-]', '', clean_str)

                            if clean_str and self._is_float(clean_str):
                                amount = float(clean_str)
                                if amount > 0:
                                    total_replenished += amount
                        except (ValueError, TypeError):
                            continue

                # Учитываем списания за занятия (расписание в столбцах 14-244)
                for i in range(14, min(245, len(headers)), 2):
                    if (i < len(headers) and headers[i] and
                            i + 1 < len(row_data) and pd.notna(row_data.iloc[i]) and pd.notna(row_data.iloc[i + 1])):
                        start_time = str(row_data.iloc[i]).strip()
                        end_time = str(row_data.iloc[i + 1]).strip()
                        if start_time and end_time:
                            total_withdrawn += tariff

                # Итоговый баланс = пополнения - списания
                final_balance = total_replenished - total_withdrawn
                subject_balances[subject_id] = final_balance

            self._set_cached_data(cache_key, subject_balances)
            return subject_balances

        except Exception as e:
            logger.error(f"Ошибка получения баланса по предметам для student_id {student_id}: {e}")
            return {}

    def _is_float(self, value: str) -> bool:
        """Проверяет, можно ли преобразовать строку в float"""
        try:
            float(value)
            return True
        except ValueError:
            return False

    def get_subject_with_lowest_balance(self, user_id: int) -> str:
        """Определяет предмет с наименьшим балансом для ученика"""
        try:
            cache_key = f"lowest_balance_subject_{user_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            df = self._load_worksheet_data('students')

            if df.empty:
                return ""

            # Находим все строки ученика
            student_rows = []
            for row_idx, row in df.iterrows():
                if len(row) > 0 and str(row.iloc[0]).strip() == str(user_id):
                    subject_id = row.iloc[2].strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""
                    if subject_id:
                        student_rows.append({
                            'row_idx': row_idx,
                            'subject_id': subject_id,
                            'row_data': row
                        })

            if not student_rows:
                return ""

            headers = [str(h).strip().lower() for h in df.columns.tolist()]
            subject_balances = {}

            # Для каждой строки ученика (каждого предмета) вычисляем баланс
            for student_row in student_rows:
                subject_id = student_row['subject_id']
                total_balance = 0.0
                row_data = student_row['row_data']

                # Получаем тариф для этого предмета
                tariff = 0.0
                if len(row_data) > 13 and pd.notna(row_data.iloc[13]):
                    try:
                        tariff_str = str(row_data.iloc[13]).replace(',', '.').strip()
                        tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                        tariff = float(tariff_str) if tariff_str else 0.0
                    except ValueError:
                        tariff = 0.0

                # Ищем финансовые столбцы (начиная с 245)
                for i in range(245, min(len(headers), 500)):
                    if i >= len(headers) or not headers[i]:
                        continue

                    # Пропускаем столбцы не с датами
                    header_date = headers[i].split()[0] if ' ' in headers[i] else headers[i]
                    if not any(char.isdigit() for char in header_date):
                        continue

                    try:
                        # Парсим дату из заголовка
                        date_formats = ["%d.%m.%Y", "%d.%m", "%d.%m.%y"]
                        date_obj = None

                        for date_format in date_formats:
                            try:
                                date_obj = datetime.strptime(header_date, date_format)
                                if date_format == "%d.%m":
                                    date_obj = date_obj.replace(year=datetime.now().year)
                                break
                            except ValueError:
                                continue

                        if not date_obj:
                            continue

                        # Учитываем данные за последние 3 месяца
                        from datetime import datetime
                        current_date = datetime.now()
                        months_diff = (current_date.year - date_obj.year) * 12 + current_date.month - date_obj.month
                        if months_diff > 3:
                            continue

                    except Exception:
                        continue

                    # Обрабатываем значение ячейки
                    if i < len(row_data) and pd.notna(row_data.iloc[i]):
                        try:
                            cell_value = str(row_data.iloc[i]).strip()
                            clean_str = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                            import re
                            clean_str = re.sub(r'[^\d.-]', '', clean_str)

                            if clean_str and self._is_float(clean_str):
                                amount = float(clean_str)
                                total_balance += amount
                        except (ValueError, TypeError):
                            continue

                # Учитываем списания за занятия
                total_withdrawn = 0.0
                for i in range(14, min(245, len(headers)), 2):
                    if (i < len(headers) and headers[i] and
                            i + 1 < len(row_data) and pd.notna(row_data.iloc[i]) and pd.notna(row_data.iloc[i + 1])):
                        start_time = str(row_data.iloc[i]).strip()
                        end_time = str(row_data.iloc[i + 1]).strip()
                        if start_time and end_time:
                            total_withdrawn += tariff

                # Итоговый баланс = пополнения - списания
                final_balance = total_balance - total_withdrawn
                subject_balances[subject_id] = final_balance

            if not subject_balances:
                return ""

            # Находим предмет с минимальным балансом
            min_balance = min(subject_balances.values())
            min_balance_subjects = [subj for subj, bal in subject_balances.items() if bal == min_balance]

            result = min_balance_subjects[0] if min_balance_subjects else ""

            self._set_cached_data(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Ошибка определения предмета с наименьшим балансом для user_id {user_id}: {e}")
            return ""

    def get_self_employed_with_lowest_balance(self, money: float) -> Dict[str, any]:
        """Находит самозанятого преподавателя с наименьшим балансом, учитывая лимиты"""
        try:
            cache_key = f"self_employed_lowest_balance_{money}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            logger.info("=== ПОИСК САМОЗАНЯТОГО С НАИМЕНЬШИМ БАЛАНСОМ (С УЧЕТОМ ЛИМИТОВ) ===")

            # Получаем список самозанятых
            self_employed_df = self._load_worksheet_data('self_employed')
            teachers_df = self._load_worksheet_data('teachers')

            logger.info(f"Найдено строк в 'Самозанятые бот': {len(self_employed_df)}")
            logger.info(f"Найдено строк в 'Преподаватели бот': {len(teachers_df)}")

            if self_employed_df.empty or teachers_df.empty:
                logger.warning("В файлах самозанятых или преподавателей нет данных")
                return {}

            # Получаем текущий месяц
            from datetime import datetime
            current_month = datetime.now().month
            logger.info(f"Текущий месяц: {current_month}")

            # Собираем имена самозанятых и их лимиты
            self_employed_info = {}
            headers = self_employed_df.columns.tolist()

            # Анализируем заголовки для определения столбцов месяцев
            month_columns = {}  # {номер_месяца: индекс_столбца}

            for i, header in enumerate(headers):
                header_str = str(header).strip()
                if header_str.isdigit():
                    month_num = int(header_str)
                    month_columns[month_num] = i
                    logger.info(f"Найден столбец для месяца {month_num}: индекс {i}")

            for _, row in self_employed_df.iterrows():
                if len(row) > 0 and pd.notna(row.iloc[0]):
                    name = str(row.iloc[0]).strip()

                    # Получаем лимит (столбец E, индекс 4)
                    monthly_limit = 0
                    if len(row) > 4 and pd.notna(row.iloc[4]):
                        try:
                            monthly_limit = float(str(row.iloc[4]).strip().replace(',', '.'))
                        except ValueError:
                            monthly_limit = 0

                    # Получаем выплачено за текущий месяц
                    paid_amount = 0
                    if current_month in month_columns:
                        col_index = month_columns[current_month]
                        if len(row) > col_index and pd.notna(row.iloc[col_index]):
                            try:
                                paid_amount = float(str(row.iloc[col_index]).strip().replace(',', '.'))
                            except ValueError:
                                paid_amount = 0

                    self_employed_info[name.lower()] = {
                        'name': name,
                        'monthly_limit': monthly_limit,
                        'paid_amount': paid_amount,
                        'remaining_limit': monthly_limit - paid_amount,
                        'row_data': row
                    }

            if not self_employed_info:
                logger.warning("Не найдено имен самозанятых")
                return {}

            # Получаем заголовки преподавателей
            teachers_headers = [str(h).strip().lower() for h in teachers_df.columns.tolist()]

            # Ищем столбец с балансом (столбец F, индекс 5)
            balance_col_index = -1
            for i, header in enumerate(teachers_headers):
                if 'баланс' in header or i == 5:  # Столбец F
                    balance_col_index = i
                    logger.info(f"Найден столбец баланса: индекс {i}, заголовок '{header}'")
                    break

            if balance_col_index == -1:
                logger.error("Не найден столбец с балансом в файле 'Преподаватели бот'")
                return {}

            self_employed_list = []

            # Ищем самозанятых в файле преподавателей и получаем их балансы
            logger.info("Поиск самозанятых в файле преподавателей:")
            for _, row in teachers_df.iterrows():
                if len(row) <= max(1, balance_col_index):
                    continue

                name = str(row.iloc[1]).strip() if len(row) > 1 and pd.notna(row.iloc[1]) else ""
                if not name:
                    continue

                name_lower = name.lower()

                # Проверяем, есть ли этот преподаватель в списке самозанятых
                if name_lower not in self_employed_info:
                    continue

                # Получаем информацию о лимитах
                emp_info = self_employed_info[name_lower]

                # Парсим баланс
                balance_str = row.iloc[balance_col_index] if len(row) > balance_col_index and pd.notna(
                    row.iloc[balance_col_index]) else "0"
                try:
                    balance_value = self._parse_balance_from_cell(str(balance_str))
                    balance_abs = abs(balance_value)

                    logger.info(
                        f"  - Найден: {name}, баланс: {balance_abs:.2f}, остаток лимита: {emp_info['remaining_limit']:.2f}")

                    self_employed_list.append({
                        'name': name,
                        'balance': balance_abs,
                        'original_balance': balance_value,
                        'monthly_limit': emp_info['monthly_limit'],
                        'paid_amount': emp_info['paid_amount'],
                        'remaining_limit': emp_info['remaining_limit'],
                        'row_data': row
                    })

                except (ValueError, TypeError) as e:
                    logger.warning(f"Ошибка парсинга баланса для {name}: '{balance_str}', ошибка: {e}")
                    continue

            if not self_employed_list:
                logger.info("Не найдено самозанятых с балансами в файле преподавателей")
                return {}

            # Фильтруем самозанятых с положительным остатком лимита
            available_self_employed = [emp for emp in self_employed_list if emp['remaining_limit'] - money > 0]

            if not available_self_employed:
                logger.warning("Нет самозанятых с доступным лимитом")
                return {}

            # Находим самозанятого с наименьшим балансом среди доступных
            lowest_balance_person = min(available_self_employed, key=lambda x: x['balance'])
            logger.info(f"Самозанятый с наименьшим балансом: {lowest_balance_person['name']}")

            # Получаем дополнительные данные из файла самозанятых
            result = self._extract_self_employed_details(lowest_balance_person['name'], self_employed_df)

            # Добавляем информацию о лимитах
            result.update({
                'monthly_limit': lowest_balance_person['monthly_limit'],
                'paid_amount': lowest_balance_person['paid_amount'],
                'remaining_limit': lowest_balance_person['remaining_limit']
            })

            self._set_cached_data(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Ошибка поиска самозанятого с наименьшим балансом: {e}")
            return {}

    def update_self_employed_payment(self, teacher_name: str, amount: float) -> bool:
        """Обновляет столбец текущего месяца для самозанятого преподавателя"""
        try:
            df = self._load_worksheet_data('self_employed')
            if df.empty:
                logger.error("В файле 'Самозанятые бот' нет данных")
                return False

            # Получаем текущий месяц
            from datetime import datetime
            current_month = datetime.now().month
            logger.info(f"Текущий месяц для обновления: {current_month}")

            # Анализируем заголовки для определения столбца текущего месяца
            headers = df.columns.tolist()
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
            target_mask = df.iloc[:, 0].astype(str).str.strip().str.lower() == teacher_name.lower()

            if not target_mask.any():
                logger.error(f"Не найдена строка для самозанятого: {teacher_name}")
                return False

            # Получаем текущее значение выплачено за текущий месяц
            current_paid = 0.0
            target_row = df[target_mask].iloc[0]
            if len(target_row) > current_month_col and pd.notna(target_row.iloc[current_month_col]):
                try:
                    current_paid_str = str(target_row.iloc[current_month_col]).replace(',', '.').strip()
                    current_paid_str = current_paid_str.replace('\xa0', '').replace(' ', '')
                    current_paid = float(current_paid_str) if current_paid_str else 0.0
                except ValueError as e:
                    logger.warning(f"Ошибка преобразования текущего выплачено для {teacher_name}: {e}")
                    current_paid = 0.0

            # Вычисляем новое значение
            amount_float = float(amount)
            new_paid = current_paid + amount_float

            # Обновляем ячейку
            df.loc[target_mask, df.columns[current_month_col]] = f"{new_paid:.2f}"

            logger.info(
                f"Обновлены выплаты для {teacher_name} за месяц {current_month}: было {current_paid:.2f}, стало {new_paid:.2f}")
            return self._save_worksheet_data('self_employed', df)

        except Exception as e:
            logger.error(f"Ошибка обновления выплат для самозанятого {teacher_name}: {e}")
            return False

    def _parse_balance_from_cell(self, balance_str: str) -> float:
        """Парсит значение баланса из ячейки, может содержать формулы"""
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

    def _extract_self_employed_details(self, name: str, self_employed_df: pd.DataFrame) -> Dict:
        """Извлекает детальную информацию о самозанятом из файла самозанятых"""
        try:
            target_name_lower = name.lower()

            logger.info(f"Поиск данных для: {name}")

            for _, row in self_employed_df.iterrows():
                if len(row) == 0:
                    continue

                row_name = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                if row_name.lower() == target_name_lower:
                    # Нашли совпадение - извлекаем данные
                    details = {
                        'name': row_name,
                        'phone': row.iloc[1] if len(row) > 1 and pd.notna(row.iloc[1]) else "",
                        'card_number': row.iloc[2] if len(row) > 2 and pd.notna(row.iloc[2]) else "",
                        'bank': row.iloc[3] if len(row) > 3 and pd.notna(row.iloc[3]) else "",
                        'monthly_limit': 0,
                        'paid_amount': 0,
                        'remaining_limit': 0
                    }

                    # Получаем лимит (столбец E, индекс 4)
                    if len(row) > 4 and pd.notna(row.iloc[4]):
                        try:
                            details['monthly_limit'] = float(str(row.iloc[4]).strip().replace(',', '.'))
                        except ValueError:
                            logger.warning(f"Некорректный лимит для {name}: '{row.iloc[4]}'")

                    # Очищаем данные
                    for key in ['phone', 'card_number', 'bank']:
                        if details[key]:
                            details[key] = str(details[key]).strip()

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

    def _get_or_create_users_worksheet(self):
        """Создает или возвращает DataFrame пользователей (для совместимости)"""
        return self._load_worksheet_data('users')

    def update_student_balance(self, student_id: int, amount: float):
        """Обновляет баланс студента в Excel файле"""
        try:
            # Создаем или загружаем файл балансов
            df = self._load_worksheet_data('balances')

            if df.empty or len(df.columns) < 2:
                df = pd.DataFrame(columns=['student_id', 'balance'])

            # Ищем существующую запись
            target_mask = df.iloc[:, 0].astype(str) == str(student_id)

            if target_mask.any():
                # Обновляем существующую запись
                df.loc[target_mask, df.columns[1]] = amount
            else:
                # Добавляем новую запись
                new_row = {'student_id': student_id, 'balance': amount}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

            self._save_worksheet_data('balances', df)

        except Exception as e:
            logger.error(f"Error updating balance in Excel: {e}")

    def process_daily_finances(self):
        """Обрабатывает дневные финансы и обновляет балансы"""
        try:
            # Получаем все финансовые операции за сегодня
            today = datetime.now().strftime("%Y-%m-%d")
            df = self._load_worksheet_data('finances')

            if df.empty:
                return

            # Пропускаем заголовок
            for _, row in df.iterrows():
                if len(row) >= 5 and str(row.iloc[3]) == today:  # Дата в колонке D
                    try:
                        student_id = int(row.iloc[0])
                        replenished = float(row.iloc[4] or 0)  # Колонка E - пополнение
                        withdrawn = float(row.iloc[5] or 0)  # Колонка F - списание

                        # Получаем текущий баланс
                        current_balance = self.get_student_balance(student_id)

                        # Обновляем баланс
                        new_balance = current_balance + replenished - withdrawn
                        self.update_student_balance(student_id, new_balance)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Ошибка обработки финансовой операции: {e}")
                        continue

            logger.info("Daily finances processed successfully")

        except Exception as e:
            logger.error(f"Error processing daily finances: {e}")

    def debug_self_employed_structure(self):
        """Отладочный метод для просмотра структуры таблиц самозанятых"""
        try:
            logger.info("=== ОТЛАДКА СТРУКТУРЫ САМОЗАНЯТЫХ ===")

            # Смотрим структуру файла самозанятых
            self_employed_df = self._load_worksheet_data('self_employed')
            logger.info(f"Файл 'Самозанятые бот': {len(self_employed_df)} строк")
            if not self_employed_df.empty:
                logger.info(f"Заголовки: {self_employed_df.columns.tolist()}")
                for i, row in self_employed_df.head().iterrows():
                    logger.info(f"Строка {i}: {row.tolist()}")

            # Смотрим структуру файла преподавателей
            teachers_df = self._load_worksheet_data('teachers')
            logger.info(f"Файл 'Преподаватели бот': {len(teachers_df)} строк")
            if not teachers_df.empty:
                headers = [str(h).strip() for h in teachers_df.columns.tolist()]
                logger.info(f"Заголовки: {headers}")

                # Ищем столбец баланса
                balance_col_index = -1
                for i, header in enumerate(headers):
                    if 'баланс' in header.lower() or i == 5:
                        balance_col_index = i
                        logger.info(f"Столбец баланса найден: индекс {i}, заголовок '{header}'")
                        break

                # Показываем первые 5 преподавателей с балансами
                for i, row in teachers_df.head().iterrows():
                    balance = row.iloc[balance_col_index] if len(row) > balance_col_index else "N/A"
                    name = row.iloc[1] if len(row) > 1 else "N/A"
                    logger.info(f"Преподаватель {i}: {name}, баланс: {balance}")

        except Exception as e:
            logger.error(f"Ошибка при отладке структуры: {e}")

    def debug_finance_columns(self, target_date: str):
        """Отладочный метод для просмотра структуры финансовых столбцов"""
        try:
            df = self._load_worksheet_data('students')

            if df.empty:
                return

            headers = [str(h).strip() for h in df.columns.tolist()]
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

        except Exception as e:
            logger.error(f"Ошибка при отладке столбцов: {e}")

# Закрывающая скобка класса