import os
from datetime import datetime, time
from typing import List, Tuple, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
import re
# Импортируем ваши модели
from models import Teacher, Student
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleSheetsDataLoader:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
    APPLICATION_NAME = 'Schedule App'

    def __init__(self, credentials_path: str, spreadsheet_id: str, target_date: str):
        self.spreadsheet_id = spreadsheet_id
        self.target_date = target_date
        self._study_plan_cache = {}

        # Аутентификация
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=self.SCOPES
        )

        self.service = build('sheets', 'v4', credentials=credentials)

    def export_schedule_to_google_sheets(self, matrix: List[List[Any]], combinations: List[List[Any]]):
        try:
            sheet_name = "Расписание_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            self._create_new_sheet(sheet_name)

            # Преобразуем матрицу в формат для Google Sheets
            values = []
            for row in matrix:
                values_row = [str(cell) if cell is not None else "" for cell in row]
                values.append(values_row)

            # Записываем данные
            body = {
                'values': values
            }

            request = self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption='RAW',
                body=body
            )
            response = request.execute()

            print(f"Данные сохранены в лист: {sheet_name}")

        except Exception as ex:
            print(f"Ошибка экспорта: {ex}")
            raise

    def load_data(self) -> Tuple[List[Teacher], List[Student]]:
        teachers = []
        students = []

        try:
            # Загрузка справочника предметов
            subject_map = self._load_subject_map()
            logger.info(f"Загружено предметов: {len(subject_map)}")

            # Загрузка плана обучения
            self._load_study_plan_cache()
            logger.info(f"Загружено планов обучения: {len(self._study_plan_cache)}")

            # Лист преподавателей
            teacher_sheet = self._get_sheet_data("Преподаватели")
            logger.info(f"Данные листа преподавателей: {len(teacher_sheet) if teacher_sheet else 0} строк")
            
            if not teacher_sheet:
                raise Exception("Лист 'Преподаватели' не найден")

            # Находим индексы колонок для выбранной даты
            date_columns = self._find_date_columns(teacher_sheet, self.target_date)
            logger.info(f"Колонки даты для преподавателей: {date_columns}")

            for i, row in enumerate(teacher_sheet[1:]):
                if not row:
                    continue
                teacher = self._parse_teacher_row(row, subject_map, date_columns)
                if teacher:
                    teachers.append(teacher)
                    logger.info(f"Добавлен преподаватель {i+1}: {teacher.name}")

            # Лист студентов
            student_sheet = self._get_sheet_data("Ученики")
            logger.info(f"Данные листа учеников: {len(student_sheet) if student_sheet else 0} строк")
            
            if not student_sheet:
                raise Exception("Лист 'Ученики' не найден")

            student_date_columns = self._find_date_columns(student_sheet, self.target_date)
            logger.info(f"Колонки даты для учеников: {student_date_columns}")

            for i, row in enumerate(student_sheet[1:]):
                if not row:
                    continue
                student = self._parse_student_row(row, subject_map, student_date_columns)
                if student:
                    students.append(student)
                    logger.info(f"Добавлен студент {i+1}: {student.name}")
            logger.info("\n=== ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ДАННЫХ ===")
            logger.info("ПРЕПОДАВАТЕЛИ:")
            for teacher in teachers:
                logger.info(
                    f"  {teacher.name}: предметы {teacher.subjects_id}, время {teacher.start_of_study_time}-{teacher.end_of_study_time}")

            logger.info("\nСТУДЕНТЫ:")
            for student in students:
                logger.info(
                    f"  {student.name}: предмет {student.subject_id}, потребность {student.need_for_attention}, время {student.start_of_study_time}-{student.end_of_study_time}")

            logger.info(f"\nСУММАРНАЯ ПОТРЕБНОСТЬ: {sum(s.need_for_attention for s in students)}")
            logger.info(f"СУММАРНАЯ ЕМКОСТЬ: {sum(t.maximum_attention for t in teachers)}")

            logger.info("\n=== ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ДАННЫХ ===")
            logger.info("ПРЕПОДАВАТЕЛИ:")
            for teacher in teachers:
                logger.info(
                    f"  {teacher.name}: предметы {teacher.subjects_id}, время {teacher.start_of_studying_time}-{teacher.end_of_studying_time}")  # Исправлено имя

            logger.info("\nСТУДЕНТЫ:")
            for student in students:
                logger.info(
                    f"  {student.name}: предмет {student.subject_id}, потребность {student.need_for_attention}, время {student.start_of_studying_time}-{student.end_of_studying_time}")  # Исправлено имя
        except Exception as ex:
            logger.error(f"Ошибка при загрузке данных: {ex}", exc_info=True)

        logger.info(f"Итог: {len(teachers)} преподавателей, {len(students)} студентов")
        return teachers, students

    def _find_date_columns(self, sheet: List[List[Any]], date: str) -> Tuple[int, int]:
        if not sheet:
            return (-1, -1)

        header_row = sheet[0]
        start_col = -1
        end_col = -1

        # Пробуем разные форматы даты
        target_date_formats = []

        # Пробуем распарсить входящую дату в разных форматах
        try:
            # Пробуем формат DD.MM.YYYY
            date_obj = datetime.strptime(date, "%d.%m.%Y")
            target_date_formats.extend([
                date_obj.strftime("%Y.%m.%d"),  # 2025.09.01
                date_obj.strftime("%Y/%m/%d"),  # 2025/09/01
                date_obj.strftime("%Y-%m-%d"),  # 2025-09-01
                date_obj.strftime("%d.%m.%Y"),  # 01.09.2025 (оригинальный)
                date_obj.strftime("%d/%m/%Y"),  # 01/09/2025
                date_obj.strftime("%d-%m-%Y"),  # 01-09-2025
                date,  # оригинальный формат
            ])
        except ValueError:
            try:
                # Пробуем формат YYYY.MM.DD
                date_obj = datetime.strptime(date, "%Y.%m.%d")
                target_date_formats.extend([
                    date_obj.strftime("%Y.%m.%d"),  # 2025.09.01
                    date_obj.strftime("%Y/%m/%d"),  # 2025/09/01
                    date_obj.strftime("%Y-%m-%d"),  # 2025-09-01
                    date_obj.strftime("%d.%m.%Y"),  # 01.09.2025
                    date_obj.strftime("%d/%m/%Y"),  # 01/09/2025
                    date_obj.strftime("%d-%m-%Y"),  # 01-09-2025
                    date,  # оригинальный формат
                ])
            except ValueError:
                # Если оба формата не подходят, используем оригинальный
                target_date_formats = [date]

        logger.info(f"Поиск даты '{date}' в форматах: {target_date_formats}")

        for i, cell in enumerate(header_row):
            cell_str = str(cell).strip()
            for date_format in target_date_formats:
                if cell_str == date_format:
                    if start_col == -1:
                        start_col = i
                        logger.info(f"Найдено начало: колонка {i} - '{cell_str}'")
                    else:
                        end_col = i
                        logger.info(f"Найдено окончание: колонка {i} - '{cell_str}'")
                    break

        logger.info(f"Результат поиска: start_col={start_col}, end_col={end_col}")
        return (start_col, end_col)

    def _load_subject_map(self) -> Dict[str, int]:
        subject_map = {}
        sheet = self._get_sheet_data("Предметы")
        if not sheet:
            return subject_map

        for row in sheet[1:]:
            if len(row) < 2:
                continue

            subject_name = str(row[0]).strip()
            try:
                subject_id = int(row[1])
                subject_map[subject_name] = subject_id
            except ValueError:
                continue

        return subject_map

    def _load_study_plan_cache(self):
        self._study_plan_cache = {}
        study_plan_sheet = self._get_sheet_data("План обучения")
        if not study_plan_sheet or len(study_plan_sheet) < 2:
            return

        # Парсим заголовки (номера занятий)
        lesson_numbers = []
        header_row = study_plan_sheet[0]
        for i in range(2, len(header_row)):  # Начинаем с колонки C (индекс 2)
            try:
                lesson_num = int(header_row[i])
                lesson_numbers.append(lesson_num)
            except ValueError:
                continue

        # Парсим данные учеников
        for row in study_plan_sheet[1:]:
            if len(row) < 3:
                continue

            student_name = str(row[0]).strip() if row[0] else ""  # Колонка A - ФИО
            if not student_name:
                continue

            student_plan = {}
            for col_index in range(2, len(row)):  # Начинаем с колонки C
                lesson_index = col_index - 2
                if lesson_index < len(lesson_numbers):
                    lesson_number = lesson_numbers[lesson_index]
                    topic = str(row[col_index]).strip() if row[col_index] else ""
                    if topic:
                        student_plan[lesson_number] = topic

            self._study_plan_cache[student_name] = student_plan

    def _calculate_lesson_number_for_student(self, student_row: List[Any], target_date_column_index: int) -> int:
        lesson_count = 0
        # Колонки с датами начинаются с индекса 4 (колонка E)
        first_date_column_index = 4

        for i in range(first_date_column_index, target_date_column_index, 2):  # Переходим через колонку
            if i < len(student_row) and student_row[i] and str(student_row[i]).strip():
                lesson_count += 1

        return lesson_count + 1  # Текущее занятие

    def _get_sheet_data(self, sheet_name: str) -> Optional[List[List[Any]]]:
        try:
            range_name = f"{sheet_name}!A:Z"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            return result.get('values', [])
        except HttpError as error:
            print(f"Ошибка при получении данных из листа {sheet_name}: {error}")
            return None

    def _parse_teacher_row(self, row: List[Any], subject_map: Dict[str, int],
                           date_columns: Tuple[int, int]) -> Optional[Teacher]:
        try:
            name = str(row[1]).strip() if len(row) > 1 else ""
            subjects_input = str(row[2]).strip() if len(row) > 2 else ""

            # Приоритет
            priority = 1
            if len(row) > 3 and row[3]:
                try:
                    priority = int(row[3])
                except ValueError:
                    priority = 1

            maximum_attention = 15

            # Время начала и конца
            start_col, end_col = date_columns
            start_time_str = ""
            end_time_str = ""

            if start_col != -1 and len(row) > start_col and row[start_col]:
                start_time_str = str(row[start_col])
            if end_col != -1 and len(row) > end_col and row[end_col]:
                end_time_str = str(row[end_col])

            if not start_time_str or not end_time_str:
                return None

            # Парсим предметы - исправленная логика
            subject_ids = []
            if subjects_input:
                # Убираем все пробелы и разбиваем по разделителям
                cleaned_input = re.sub(r'\s+', '', subjects_input)
                for subject in re.split(r'[,.;]+', cleaned_input):
                    subject = subject.strip()
                    if subject and subject.isdigit():
                        subject_ids.append(int(subject))
                    elif subject and subject in subject_map:
                        subject_ids.append(subject_map[subject])

            # Дополнительная проверка: если предметы не найдены, пробуем другие колонки
            if not subject_ids and len(row) > 4:
                for i in range(4, min(8, len(row))):  # Проверяем колонки 5-8
                    cell_value = str(row[i]).strip()
                    if cell_value and cell_value.isdigit():
                        subject_ids.append(int(cell_value))
                        break

            logger.info(f"Преподаватель {name}: предметы {subject_ids} из входных данных '{subjects_input}'")

            return Teacher(
                name=name,
                start_of_study_time=self._normalize_time(start_time_str),
                end_of_study_time=self._normalize_time(end_time_str),
                subjects_id=subject_ids,
                priority=priority,
                maximum_attention=maximum_attention
            )

        except Exception as ex:
            logger.error(f"Ошибка парсинга преподавателя: {ex}")
            return None

    def _parse_student_row(self, row: List[Any], subject_map: Dict[str, int],
                           date_columns: Tuple[int, int]) -> Optional[Student]:
        try:
            name = str(row[1]).strip() if len(row) > 1 else ""

            # Проверяем запись на выбранную дату
            start_col, end_col = date_columns
            start_time_str = ""
            end_time_str = ""

            if start_col != -1 and len(row) > start_col and row[start_col]:
                start_time_str = str(row[start_col])
            if end_col != -1 and len(row) > end_col and row[end_col]:
                end_time_str = str(row[end_col])

            if not start_time_str or not end_time_str:
                return None

            # Определяем номер занятия
            lesson_number = self._calculate_lesson_number_for_student(row, start_col)

            # Ищем тему в плане обучения
            topic = None
            if name in self._study_plan_cache:
                student_plan = self._study_plan_cache[name]
                topic = student_plan.get(lesson_number)

            subject_id_int = -1
            need_for_attention = 1

            # Сначала пробуем получить subject_id из колонки C (индекс 2)
            if len(row) > 2 and row[2]:
                try:
                    subject_id_int = int(row[2])
                except ValueError:
                    # Если колонка C не число, используем тему из плана обучения
                    if topic and topic.isdigit():
                        subject_id_int = int(topic)
                    else:
                        print(f"Ошибка: не удалось определить предмет для ученика {name}")
                        return None

            # Потребность во внимании - исправленная логика
            if len(row) > 3 and row[3]:
                try:
                    need_for_attention = int(row[3])
                except ValueError:
                    need_for_attention = 1
                    print(f"Внимание: некорректное значение потребности для ученика {name}, установлено значение 1")

            # Дополнительная проверка: если subject_id все еще -1, используем тему
            if subject_id_int == -1 and topic and topic.isdigit():
                subject_id_int = int(topic)

            if subject_id_int == -1:
                print(f"Ошибка: не удалось определить предмет для ученика {name}")
                return None

            return Student(
                name=name,
                start_of_study_time=self._normalize_time(start_time_str),
                end_of_study_time=self._normalize_time(end_time_str),
                subject_id=subject_id_int,
                need_for_attention=need_for_attention
            )

        except Exception as ex:
            print(f"Ошибка парсинга студента {name if 'name' in locals() else 'unknown'}: {ex}")
            return None

    def _parse_student_row(self, row: List[Any], subject_map: Dict[str, int],
                           date_columns: Tuple[int, int]) -> Optional[Student]:
        try:
            name = str(row[1]).strip() if len(row) > 1 else ""

            # Проверяем запись на выбранную дату
            start_col, end_col = date_columns
            start_time_str = ""
            end_time_str = ""

            if start_col != -1 and len(row) > start_col and row[start_col]:
                start_time_str = str(row[start_col])
            if end_col != -1 and len(row) > end_col and row[end_col]:
                end_time_str = str(row[end_col])

            if not start_time_str or not end_time_str:
                return None

            # Определяем номер занятия
            lesson_number = self._calculate_lesson_number_for_student(row, start_col)

            # Ищем тему в плане обучения
            topic = None
            if name in self._study_plan_cache:
                student_plan = self._study_plan_cache[name]
                topic = student_plan.get(lesson_number)

            # Парсим предмет и потребность во внимании
            subject_id_int = -1
            need_for_attention = 1

            # Предмет из колонки C (индекс 2)
            if len(row) > 2 and row[2]:
                try:
                    subject_id_int = int(row[2])
                except ValueError:
                    # Если колонка C не число, пробуем тему из плана обучения
                    if topic and topic.isdigit():
                        subject_id_int = int(topic)
                    else:
                        logger.warning(f"Не удалось определить предмет для ученика {name}")
                        return None

            # Потребность во внимании из колонки D (индекс 3)
            if len(row) > 3 and row[3]:
                try:
                    need_for_attention = int(row[3])
                except ValueError:
                    need_for_attention = 1
                    logger.warning(f"Некорректное значение потребности для ученика {name}, установлено значение 1")

            # Дополнительная проверка: если subject_id все еще -1, используем тему
            if subject_id_int == -1 and topic and topic.isdigit():
                subject_id_int = int(topic)

            if subject_id_int == -1:
                logger.warning(f"Не удалось определить предмет для ученика {name}")
                return None

            return Student(
                name=name,
                start_of_study_time=self._normalize_time(start_time_str),
                end_of_study_time=self._normalize_time(end_time_str),
                subject_id=subject_id_int,
                need_for_attention=need_for_attention
            )

        except Exception as ex:
            logger.error(f"Ошибка парсинга студента {name if 'name' in locals() else 'unknown'}: {ex}")
            return None

    def _normalize_time(self, time_str: str) -> str:
        # Убираем лишние пробелы
        time_str = time_str.strip()

        # Если время содержит точку вместо двоеточия
        if '.' in time_str and ':' not in time_str:
            time_str = time_str.replace('.', ':')

        # Разбиваем на части
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) >= 2:
                # Убеждаемся, что часы и минуты состоят из двух цифр
                hours = parts[0].zfill(2)
                minutes = parts[1].zfill(2)
                return f"{hours}:{minutes}"

        # Если время в формате "HHMM"
        elif len(time_str) == 4 and time_str.isdigit():
            return f"{time_str[:2]}:{time_str[2:]}"

        return time_str

    def export_schedule_to_google_sheets(self, matrix: List[List[Any]], combinations: List[List[Teacher]]):
        try:
            sheet_name = "Расписание_" + datetime.now().strftime("%Y%m%d_%H%M%S")

            # 1. Создаем новый лист
            self._create_new_sheet(sheet_name)

            # 2. Подготавливаем данные
            values = self._convert_to_value_list(matrix)
            value_range = {
                'values': values,
                'range': f"{sheet_name}!A1"
            }

            # 3. Отправляем данные
            request = self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption='RAW',
                body=value_range
            )
            response = request.execute()

            print(f"Данные сохранены в лист: {sheet_name}")

        except Exception as ex:
            print(f"Ошибка экспорта: {ex}")
            raise

    def _convert_to_value_list(self, matrix: List[List[Any]]) -> List[List[Any]]:
        values = []
        for row in matrix:
            values_row = [cell if cell is not None else "" for cell in row]
            values.append(values_row)
        return values

    def _delete_sheet_if_exists(self, sheet_name: str):
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()

            sheets = spreadsheet.get('sheets', [])
            for sheet in sheets:
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']

                    requests = [{
                        'deleteSheet': {
                            'sheetId': sheet_id
                        }
                    }]

                    body = {'requests': requests}
                    self.service.spreadsheets().batchUpdate(
                        spreadsheetId=self.spreadsheet_id,
                        body=body
                    ).execute()
                    break

        except HttpError as error:
            print(f"Ошибка при удалении листа: {error}")

    def _create_new_sheet(self, sheet_name: str):
        try:
            requests = [{
                'addSheet': {
                    'properties': {
                        'title': sheet_name
                    }
                }
            }]

            body = {'requests': requests}
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()

        except HttpError as error:
            print(f"Ошибка при создании листа: {error}")
            raise

    def get_student_topic_by_user_id(self, user_id: str, target_date: str) -> Optional[str]:
        """
        Получает тему занятия для ученика по user_id на указанную дату
        
        Args:
            user_id: ID ученика (обычно из колонки A в листе Ученики)
            target_date: Дата в формате DD.MM.YYYY или YYYY.MM.DD
        
        Returns:
            Название темы занятия или None, если не найдено
        """
        try:
            # Загружаем план обучения, если еще не загружен
            if not self._study_plan_cache:
                self._load_study_plan_cache()
            
            # Получаем данные студента
            student_sheet = self._get_sheet_data("Ученики")
            if not student_sheet:
                logger.warning("Лист 'Ученики' не найден")
                return None
            
            # Находим колонки для указанной даты
            date_columns = self._find_date_columns(student_sheet, target_date)
            if date_columns[0] == -1:
                logger.warning(f"Дата {target_date} не найдена в расписании учеников")
                return None
            
            # Ищем студента по user_id (колонка A)
            student_name = None
            student_row = None
            
            for row in student_sheet[1:]:  # Пропускаем заголовок
                if len(row) > 0 and str(row[0]).strip() == user_id:
                    student_row = row
                    if len(row) > 1:
                        student_name = str(row[1]).strip()
                    break
            
            if not student_row:
                logger.warning(f"Ученик с user_id {user_id} не найден")
                return None
            
            if not student_name:
                logger.warning(f"Не удалось получить имя ученика для user_id {user_id}")
                return None
            
            # Определяем номер занятия для этой даты
            lesson_number = self._calculate_lesson_number_for_student(student_row, date_columns[0])
            
            # Получаем тему из плана обучения
            if student_name in self._study_plan_cache:
                student_plan = self._study_plan_cache[student_name]
                topic = student_plan.get(lesson_number)
                
                if topic:
                    logger.info(f"Для ученика {student_name} (ID: {user_id}) на {target_date} (занятие {lesson_number}): {topic}")
                    return topic
                else:
                    logger.warning(f"Тема для занятия {lesson_number} не найдена в плане ученика {student_name}")
            else:
                logger.warning(f"План обучения для ученика {student_name} не найден")
            
            return None
            
        except Exception as ex:
            logger.error(f"Ошибка при получении темы для ученика с ID {user_id}: {ex}")
            return None