import os
from datetime import datetime, time
from typing import List, Tuple, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Импортируем ваши модели
from models import Teacher, Student


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

            # Загрузка плана обучения
            self._load_study_plan_cache()

            # Лист преподавателей
            teacher_sheet = self._get_sheet_data("Преподаватели")
            if not teacher_sheet:
                raise Exception("Лист 'Преподаватели' не найден")

            # Находим индексы колонок для выбранной даты
            date_columns = self._find_date_columns(teacher_sheet, self.target_date)

            for row in teacher_sheet[1:]:
                if not row:
                    continue
                teacher = self._parse_teacher_row(row, subject_map, date_columns)
                if teacher:
                    teachers.append(teacher)

            # Лист студентов
            student_sheet = self._get_sheet_data("Ученики")
            if not student_sheet:
                raise Exception("Лист 'Ученики' не найден")

            student_date_columns = self._find_date_columns(student_sheet, self.target_date)

            for row in student_sheet[1:]:
                if not row:
                    continue
                student = self._parse_student_row(row, subject_map, student_date_columns)
                if student:
                    students.append(student)

        except Exception as ex:
            print(f"Ошибка при загрузке данных: {ex}")

        return teachers, students

    def _find_date_columns(self, sheet: List[List[Any]], date: str) -> Tuple[int, int]:
        if not sheet:
            return (-1, -1)

        header_row = sheet[0]
        start_col = -1
        end_col = -1

        for i, cell in enumerate(header_row):
            if str(cell).strip() == date:
                if start_col == -1:
                    start_col = i
                else:
                    end_col = i

        return (start_col, end_col)

    def _load_subject_map(self) -> Dict[str, int]:
        subject_map = {}
        sheet = self._get_sheet_data("Квалификации")
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

            # Парсим предметы
            subject_ids = []
            for subject in subjects_input.split(','):
                subject = subject.strip('.; ')
                if subject.isdigit():
                    subject_ids.append(int(subject))

            return Teacher(
                name=name,
                start_of_study_time=self._normalize_time(start_time_str),
                end_of_study_time=self._normalize_time(end_time_str),
                subjects_id=subject_ids,
                priority=priority,
                maximum_attention=maximum_attention
            )

        except Exception as ex:
            print(f"Ошибка парсинга преподавателя: {ex}")
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
            if topic and topic.isdigit():
                subject_id_int = int(topic)
            else:
                # Fallback: используем предмет из колонки C
                if len(row) > 2 and row[2]:
                    try:
                        subject_id_int = int(row[2])
                        print(f"Внимание: для ученика {name} не найдена тема для занятия №{lesson_number}. "
                              f"Использован предмет из столбца C: {subject_id_int}")
                    except ValueError:
                        print(f"Ошибка: не удалось преобразовать предмет из столбца C для ученика {name}")
                        return None
                else:
                    print(f"Ошибка: отсутствует предмет для ученика {name}")
                    return None

            # Потребность во внимании
            need_for_attention = 1
            if len(row) > 3 and row[3]:
                try:
                    need_for_attention = int(row[3])
                except ValueError:
                    need_for_attention = 1

            return Student(
                name=name,
                start_of_study_time=self._normalize_time(start_time_str),
                end_of_study_time=self._normalize_time(end_time_str),
                subject_id=subject_id_int,
                need_for_attention=need_for_attention
            )

        except Exception as ex:
            print(f"Ошибка парсинга студента: {ex}")
            return None

    def _normalize_time(self, time_str: str) -> str:
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) >= 2:
                return f"{parts[0]}:{parts[1]}"
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