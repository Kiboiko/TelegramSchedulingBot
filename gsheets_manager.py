import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
import traceback

logger = logging.getLogger(__name__)


class GoogleSheetsManager:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None
        self.qual_map = {}
        self._cache = {}  # Добавляем кэш
        self._cache_timeout = 60  # Кэш на 60 секунд

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
            self.qual_links = {}  # Словарь для хранения ссылок
            logger.info("=== ДАННЫЕ ИЗ ЛИСТА 'Предметы бот' ===")
            for i, row in enumerate(data):
                logger.info(f"Строка {i}: {row}")
                if len(row) >= 2 and row[0].strip().isdigit():  # ID в колонке A
                    subject_id = row[0].strip()
                    subject_name = row[1].strip().lower()
                    self.qual_map[subject_name] = subject_id

                    # Загружаем ссылку из колонки C (индекс 2)
                    if len(row) >= 3:
                        self.qual_links[subject_id] = row[2].strip()

                    logger.info(
                        f"Добавлено: '{subject_name}' -> '{subject_id}', ссылка: {self.qual_links.get(subject_id, 'нет')}")

            logger.info(f"Итоговый qual_map: {self.qual_map}")
            logger.info(f"Ссылки на материалы: {self.qual_links}")
        except Exception as e:
            logger.error(f"Ошибка загрузки квалификаций: {e}")

    def format_date(self, date_str: str) -> str:
        """Форматирует дату из YYYY-MM-DD в DD.MM.YYYY"""
        try:
            # Пробуем разные форматы на входе
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

    # gsheets_manager.py (добавьте в класс GoogleSheetsManager)

    def get_student_finances(self, user_id: int, subject_id: str, selected_date: str) -> Dict[str, float]:
        """Получает финансовую информацию для ученика по предмету и дате"""
        try:
            # Используем кэш
            cache_key = f"finances_{user_id}_{subject_id}_{selected_date}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                logger.info(f"Используем кэшированные финансовые данные для {cache_key}")
                return cached_result

            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()

            if len(data) < 2:
                logger.error("В таблице 'Ученики бот' недостаточно данных")
                result = {"replenished": 0.0, "withdrawn": 0.0, "tariff": 0.0}
                self._set_cached_data(cache_key, result)
                return result

            # Находим строку ученика с указанным subject_id
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                if (len(row) > 0 and str(row[0]).strip() == str(user_id) and
                        len(row) > 2 and str(row[2]).strip() == str(subject_id)):
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
            if len(data[target_row - 1]) > 13 and data[target_row - 1][13]:
                try:
                    tariff_str = str(data[target_row - 1][13]).replace(',', '.').strip()
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
                    if len(data[target_row - 1]) > i + 1:
                        start_time = data[target_row - 1][i] if i < len(data[target_row - 1]) else ""
                        end_time = data[target_row - 1][i + 1] if i + 1 < len(data[target_row - 1]) else ""

                        if start_time and end_time and str(start_time).strip() and str(end_time).strip():
                            withdrawn = tariff
                            schedule_found = True
                            logger.info(f"Найдено занятие: {start_time}-{end_time}, списание: {withdrawn} руб.")
                            break

            if not schedule_found:
                logger.info(f"Занятие на {formatted_date} не найдено")

            # 2. Ищем финансовые данные (столбцы начиная с JG)
            replenished = 0.0
            finance_found = False

            # Ищем финансовые столбцы для выбранной даты (начиная с столбца 245)
            for i in range(245, len(headers)):
                header = headers[i]
                if formatted_date.lower() in header:
                    # Нашли финансовый столбец для нужной даты
                    # Это ПЕРВАЯ колонка с датой - в ней должно быть пополнение
                    if len(data[target_row - 1]) > i:
                        replenishment_str = data[target_row - 1][i]
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
                                # Но оставляем точку как разделитель дробей
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

                                break
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

    def debug_finance_columns(self, target_date: str):
        """Отладочный метод для просмотра структуры финансовых столбцов"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()

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
    def get_available_finance_dates(self, user_id: int, subject_id: str) -> List[str]:
        """Получает доступные даты для просмотра финансов"""
        try:
            # Используем кэш
            cache_key = f"finance_dates_{user_id}_{subject_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()

            if len(data) < 2:
                return []

            # Находим строку ученика
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                if (len(row) > 0 and str(row[0]).strip() == str(user_id) and
                        len(row) > 2 and str(row[2]).strip() == str(subject_id)):
                    target_row = row_idx
                    break

            if target_row == -1:
                return []

            # Получаем только заголовки финансовых столбцов (начиная с JG)
            headers = [str(h).strip().lower() for h in data[0]]

            available_dates = []

            # Только финансовые столбцы (начиная с 245)
            for i in range(245, min(len(headers), 500)):  # Ограничиваем поиск 500 столбцами
                if i < len(headers) and headers[i]:
                    # Извлекаем дату из заголовка
                    date_header = headers[i].split()[0] if ' ' in headers[i] else headers[i]

                    try:
                        # Пробуем разные форматы дат
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

            if len(data) < 3:
                return []

            headers = [h.lower() for h in data[0]]
            bookings = []
            reverse_qual_map = {v: k for k, v in self.qual_map.items()}

            # ДЕБАГ: Логируем структуру таблицы
            # logger.info(f"Структура листа '{sheet_name}':")
            # logger.info(f"Заголовки: {headers}")
            # logger.info(f"Кол-во столбцов: {len(headers)}")

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

            for row_idx, row in enumerate(data[2:], start=3):
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
                logger.info("Поиск по ID" + str(user_id) + ": " + roles_cell)
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
            # logger.error(f"Ошибка сохранения предмета ученика: {e}")
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
            
            if not data or len(data) < 3:
                logger.info("Нет данных или только заголовок")
                return []
            
            available_subjects = []
            
            # Пропускаем заголовок (первую строку)
            for i, row in enumerate(data[2:], start=3):
                if not row:
                    continue
                    
                row_user_id = row[0].strip() if len(row) > 0 and row[0] else ""
                row_subject = row[2].strip() if len(row) > 2 and row[2] else ""
                
                # logger.info(f"Строка {i}: user_id='{row_user_id}', subject='{row_subject}'")
                
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
            logger.info("ищется предмет: " + subject_id)
            
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
            
            # ПРЕОБРАЗУЕМ subject_id ТОЛЬКО если это не числовой ID
            search_subject_id = subject_id
            
            # Если subject_id - это название предмета (например "информатика"), преобразуем в числовой ID
            if not subject_id.isdigit():  # Если это не число
                if subject_id.lower() in self.qual_map:
                    # Если subject_id это название в нижнем регистре (например "информатика")
                    search_subject_id = self.qual_map[subject_id.lower()]
                elif subject_id in self.qual_map.values():
                    # Если subject_id это название предмета в правильном регистре
                    for id_key, name_value in self.qual_map.items():
                        if name_value == subject_id:
                            search_subject_id = id_key
                            break
            
            logger.info(f"Поиск строки: user_id={user_id}, subject_id={search_subject_id} (оригинальный: {subject_id})")
            
            for row_idx, row in enumerate(data[1:], start=2):  # Пропускаем заголовок
                if len(row) > 0 and str(row[0]).strip() == str(user_id):
                    # Проверяем subject_id в столбце C (индекс 2)
                    if len(row) > 2 and str(row[2]).strip() == str(search_subject_id):
                        target_row = row_idx
                        logger.info(f"Найдена строка {target_row} для user_id {user_id} и subject_id {search_subject_id}")
                        break
            
            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id} и subject_id {search_subject_id}")
                logger.info(f"Доступные subject_id в таблице:")
                for row_idx, row in enumerate(data[1:], start=2):
                    if len(row) > 0 and str(row[0]).strip() == str(user_id):
                        row_subject = row[2] if len(row) > 2 else "нет данных"
                        logger.info(f"Строка {row_idx}: user_id={row[0]}, subject_id={row_subject}")
                return False
            
            # Обновляем только нужные ячейки
            if date_col_end != -1:  # Есть отдельная колонка для конца времени
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                worksheet.update_cell(target_row, date_col_end + 1, end_time)
            else:  # Только одна колонка для даты (предполагаем, что следующая - для конца)
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                if date_col_start + 2 <= len(data[0]):
                    worksheet.update_cell(target_row, date_col_start + 2, end_time)
            
            logger.info(f"Обновлена ячейка для user_id {user_id}, subject {search_subject_id}, date {formatted_date}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления ячейки: {e}")
            return False
        
    def update_teacher_booking_cell(self, user_id: int, subjects: List[str], date: str, 
                           start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для преподавателя (ищет только по user_id)"""
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
            
            # Ищем строку ТОЛЬКО по user_id (игнорируем subjects)
            target_row = -1
            
            logger.info(f"Поиск строки преподавателя по user_id: {user_id}")
            
            for row_idx, row in enumerate(data[1:], start=2):  # Пропускаем заголовок
                if len(row) > 0 and str(row[0]).strip() == str(user_id):
                    target_row = row_idx
                    logger.info(f"Найдена строка {target_row} для user_id {user_id}")
                    break
            
            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id}")
                logger.info(f"Доступные преподаватели в таблице:")
                for row_idx, row in enumerate(data[1:], start=2):
                    if len(row) > 0:
                        row_user_id = row[0] if row[0] else "пусто"
                        row_name = row[1] if len(row) > 1 else "нет имени"
                        logger.info(f"Строка {row_idx}: user_id={row_user_id}, имя={row_name}")
                return False
            
            # Обновляем только нужные ячейки
            if date_col_end != -1:  # Есть отдельная колонка для конца времени
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                worksheet.update_cell(target_row, date_col_end + 1, end_time)
            else:  # Только одна колонка для даты (предполагаем, что следующая - для конца)
                worksheet.update_cell(target_row, date_col_start + 1, start_time)
                if date_col_start + 2 <= len(data[0]):
                    worksheet.update_cell(target_row, date_col_start + 2, end_time)
            
            logger.info(f"Обновлена ячейка для user_id {user_id}, date {formatted_date}")
            return True
                
        except Exception as e:
            logger.error(f"Ошибка обновления ячейки преподавателя: {e}")
            return False
        
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
            logger.info(f"Balance for student {student_id}: {balance} (replenished: {total_replenished}, withdrawn: {total_withdrawn})")
            
            return balance
            
        except Exception as e:
            logger.error(f"Error calculating balance for student {student_id}: {e}")
            return 0.0

    def update_student_balance(self, student_id: int, amount: float):
        """Обновляет баланс студента в Google Sheets"""
        try:
            worksheet = self._get_or_create_worksheet("Балансы")
            data = worksheet.get_all_values()
            
            # Ищем существующую запись
            found = False
            for i, row in enumerate(data[1:], start=2):  # start=2 потому что 1 строка - заголовок
                if row and len(row) >= 1 and str(row[0]).strip() == str(student_id):
                    worksheet.update_cell(i, 2, amount)  # Колонка B - баланс
                    found = True
                    break
            
            # Если не нашли, добавляем новую запись
            if not found:
                next_row = len(data) + 1
                worksheet.update(f'A{next_row}:B{next_row}', [[student_id, amount]])
                
        except Exception as e:
            logger.error(f"Error updating balance in sheets: {e}")

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
            data = worksheet.get_all_values()
            
            # Пропускаем заголовок
            for row in data[1:]:
                if len(row) >= 5 and row[3] == today:  # Дата в колонке D
                    student_id = int(row[0])
                    replenished = float(row[4] or 0)  # Колонка E - пополнение
                    withdrawn = float(row[5] or 0)    # Колонка F - списание
                    
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
            data = worksheet.get_all_values()

            if len(data) < 2:
                return []

            # Находим все строки студента
            student_rows = []
            for row_idx, row in enumerate(data[1:], start=2):
                if len(row) > 0 and str(row[0]).strip() == str(student_id):
                    student_rows.append((row_idx, row))

            if not student_rows:
                return []

            finance_history = []
            headers = [str(h).strip().lower() for h in data[0]]

            # Получаем тариф студента
            tariff = 0.0
            if student_rows[0][1] and len(student_rows[0][1]) > 13 and student_rows[0][1][13]:
                try:
                    tariff_str = str(student_rows[0][1][13]).replace(',', '.').strip()
                    tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                    tariff = float(tariff_str) if tariff_str else 0.0
                except ValueError:
                    tariff = 0.0

            # Собираем все финансовые столбцы (начиная с 245)
            for i in range(245, min(len(headers), 500)):
                if i < len(headers) and headers[i]:
                    date_header = headers[i].split()[0] if ' ' in headers[i] else headers[i]
                    
                    # Парсим дату
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
                        
                        # Для каждой строки студента (каждого предмета)
                        for row_idx, row in student_rows:
                            if len(row) <= i:
                                continue

                            replenishment_str = row[i]
                            withdrawn = 0.0
                            replenished = 0.0

                            # Проверяем, было ли занятие в эту дату
                            # Ищем столбцы расписания (первые 245 столбцов)
                            schedule_found = False
                            for schedule_col in range(14, min(245, len(headers)), 2):
                                if (schedule_col < len(headers) and 
                                    formatted_date.lower() in headers[schedule_col].lower()):
                                    
                                    if (len(row) > schedule_col + 1 and 
                                        row[schedule_col] and row[schedule_col + 1]):
                                        start_time = row[schedule_col]
                                        end_time = row[schedule_col + 1]
                                        if start_time.strip() and end_time.strip():
                                            withdrawn = tariff
                                            schedule_found = True
                                            break

                            # Обрабатываем пополнение
                            if replenishment_str and str(replenishment_str).strip():
                                try:
                                    clean_str = str(replenishment_str)
                                    clean_str = clean_str.replace('\xa0', '')
                                    clean_str = clean_str.replace(' ', '')
                                    clean_str = clean_str.replace(',', '.')
                                    import re
                                    clean_str = re.sub(r'[^\d.-]', '', clean_str)
                                    
                                    if clean_str:
                                        replenished = float(clean_str)
                                except ValueError:
                                    replenished = 0.0

                            # Добавляем операцию только если есть движение средств
                            if replenished != 0 or withdrawn != 0:
                                finance_history.append({
                                    "date": formatted_date,
                                    "replenished": replenished,
                                    "withdrawn": withdrawn,
                                    "tariff": tariff,
                                    "subject": row[2] if len(row) > 2 else ""
                                })

                    except ValueError:
                        continue

            # Сортируем по дате
            finance_history.sort(key=lambda x: x["date"])
            
            self._set_cached_data(cache_key, finance_history)
            return finance_history

        except Exception as e:
            logger.error(f"Error getting finance history for student {student_id}: {e}")
            return []
        
    def get_student_balance_for_subject(self, user_id: int, subject_id: str) -> float:
        """Получает баланс студента для конкретного предмета"""
        try:
            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()
            
            if len(data) < 1:
                return 0.0

            headers = [str(h).strip().lower() for h in data[0]]
            
            # Находим индексы колонок с датами (финансовые колонки)
            date_columns = []
            for i, header in enumerate(headers):
                if 'финансы' in header and any(char.isdigit() for char in header):
                    date_columns.append(i)

            # Ищем строку пользователя с указанным subject_id
            for row in data[1:]:  # Пропускаем заголовок
                if (len(row) > 0 and str(row[0]).strip() == str(user_id) and
                    len(row) > 2 and str(row[2]).strip() == str(subject_id)):
                    
                    total_balance = 0.0
                    
                    # Суммируем все финансовые операции для этого предмета
                    for col_idx in date_columns:
                        if len(row) > col_idx and row[col_idx].strip():
                            try:
                                # Пытаемся преобразовать значение в число
                                cell_value = row[col_idx].strip()
                                # Убираем возможные символы валюты и пробелы
                                cell_value = cell_value.replace('₽', '').replace('руб', '').replace(' ', '')
                                # Заменяем запятые на точки для корректного преобразования
                                cell_value = cell_value.replace(',', '.')
                                
                                if cell_value and self._is_float(cell_value):
                                    amount = float(cell_value)
                                    total_balance += amount
                            except (ValueError, TypeError):
                                continue
                    
                    return total_balance
                    
            return 0.0
            
        except Exception as e:
            logger.error(f"Ошибка получения баланса для user_id {user_id}, subject {subject_id}: {e}")
            return 0.0

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
            # Используем кэш
            cache_key = f"lowest_balance_subject_{user_id}"
            cached_result = self._get_cached_data(cache_key)
            if cached_result:
                return cached_result

            worksheet = self._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()

            if len(data) < 2:
                logger.info(f"В таблице 'Ученики бот' недостаточно данных для user_id {user_id}")
                return ""

            # Находим все строки ученика
            student_rows = []
            for row_idx, row in enumerate(data[1:], start=2):
                if len(row) > 0 and str(row[0]).strip() == str(user_id):
                    student_rows.append({
                        'row_idx': row_idx,
                        'subject_id': row[2].strip() if len(row) > 2 and row[2] else "",
                        'row_data': row
                    })

            if not student_rows:
                logger.info(f"Не найдено строк для user_id {user_id}")
                return ""

            headers = [str(h).strip().lower() for h in data[0]]
            
            # Получаем текущую дату для поиска актуальных финансовых данных
            from datetime import datetime
            current_date = datetime.now()
            current_month = current_date.strftime("%m.%Y")
            current_month_short = current_date.strftime("%m.%y")

            subject_balances = {}

            # Для каждой строки ученика (каждого предмета) вычисляем баланс
            for student_row in student_rows:
                subject_id = student_row['subject_id']
                if not subject_id:
                    continue

                total_balance = 0.0
                row_data = student_row['row_data']

                # Ищем финансовые столбцы (начиная с 245)
                for i in range(245, min(len(headers), 500)):
                    if i >= len(headers) or not headers[i]:
                        continue

                    # Проверяем, относится ли столбец к текущему или предыдущим месяцам
                    header_date = headers[i].split()[0] if ' ' in headers[i] else headers[i]
                    
                    # Пропускаем столбцы не с датами
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
                                    date_obj = date_obj.replace(year=current_date.year)
                                break
                            except ValueError:
                                continue

                        if not date_obj:
                            continue

                        # Учитываем данные за последние 3 месяца для актуальности
                        months_diff = (current_date.year - date_obj.year) * 12 + current_date.month - date_obj.month
                        if months_diff > 3:
                            continue

                    except Exception:
                        continue

                    # Обрабатываем значение ячейки
                    if len(row_data) > i and row_data[i]:
                        try:
                            cell_value = str(row_data[i]).strip()
                            
                            # Очищаем строку от лишних символов
                            clean_str = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                            import re
                            clean_str = re.sub(r'[^\d.-]', '', clean_str)
                            
                            if clean_str and self._is_float(clean_str):
                                amount = float(clean_str)
                                total_balance += amount
                        except (ValueError, TypeError) as e:
                            logger.debug(f"Ошибка обработки значения '{cell_value}': {e}")
                            continue

                # Также учитываем тариф и проведенные занятия (списания)
                tariff = 0.0
                if len(row_data) > 13 and row_data[13]:
                    try:
                        tariff_str = str(row_data[13]).replace(',', '.').strip()
                        tariff_str = tariff_str.replace('\xa0', '').replace(' ', '')
                        tariff = float(tariff_str) if tariff_str else 0.0
                    except ValueError:
                        tariff = 0.0

                # Учитываем списания за занятия (расписание в столбцах 14-244)
                total_withdrawn = 0.0
                for i in range(14, min(245, len(headers)), 2):
                    if (i < len(headers) and headers[i] and 
                        len(row_data) > i + 1 and row_data[i] and row_data[i + 1]):
                        # Если есть время начала и окончания - занятие было проведено
                        start_time = row_data[i].strip()
                        end_time = row_data[i + 1].strip()
                        if start_time and end_time:
                            total_withdrawn += tariff

                # Итоговый баланс = пополнения - списания
                final_balance = total_balance - total_withdrawn
                subject_balances[subject_id] = final_balance

                logger.info(f"Предмет {subject_id}: баланс {final_balance:.2f} руб. (пополнения: {total_balance:.2f}, списания: {total_withdrawn:.2f})")

            if not subject_balances:
                logger.info(f"Не найдено финансовых данных для user_id {user_id}")
                return ""

            # Находим предмет с минимальным балансом
            min_balance = min(subject_balances.values())
            min_balance_subjects = [subj for subj, bal in subject_balances.items() if bal == min_balance]
            
            # Если несколько предметов с одинаковым минимальным балансом, выбираем первый
            result = min_balance_subjects[0] if min_balance_subjects else ""
            
            logger.info(f"Предмет с наименьшим балансом для user_id {user_id}: {result} (баланс: {min_balance:.2f} руб.)")
            
            self._set_cached_data(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Ошибка определения предмета с наименьшим балансом для user_id {user_id}: {e}")
            return ""