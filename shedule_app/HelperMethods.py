# from typing import List, Dict, Tuple, Optional, Any, Set
# from datetime import time, timedelta
# from models import Teacher, Student
# import itertools
# import logging
#
#
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)
#
# class School:
#     @staticmethod
#     def check_teachers_combo_per_minute(students: List['Student'], teachers: List['Teacher'], time: time) -> bool:
#         active_teachers = School.get_active_teachers_at_minute(teachers, time)
#         active_students = School.get_active_students_at_minute(students, time)
#         return School.check_teacher_student_allocation(active_teachers, active_students)
#
#     @staticmethod
#     def get_active_teachers_at_minute(teachers: List['Teacher'], time: time) -> List['Teacher']:
#         res = []
#         for teacher in teachers:
#             if (time >= teacher.start_of_studying_time) and (time <= teacher.end_of_studying_time):
#                 res.append(teacher)
#         return res
#
#     @staticmethod
#     def get_active_students_at_minute(students: List['Student'], time: time) -> List['Student']:
#         res = []
#         for student in students:
#             if (time >= student.start_of_studying_time) and (time <= student.end_of_studying_time):
#                 res.append(student)
#         return res
#
#     @staticmethod
#     def check_teacher_student_allocation(teachers: List['Teacher'], students: List['Student']) -> bool:
#         logger.info(f"Проверка распределения: {len(teachers)} преподавателей, {len(students)} студентов")
#
#         if not teachers:
#             logger.warning("Нет преподавателей для распределения")
#             return len(students) == 0  # Если нет студентов - можно, иначе нельзя
#
#         if not students:
#             logger.warning("Нет студентов для распределения")
#             return True
#
#         # Проверяем базовую возможность распределения
#         total_attention_needed = sum(s.need_for_attention for s in students)
#         total_teacher_capacity = sum(t.maximum_attention for t in teachers)
#
#         if total_attention_needed > total_teacher_capacity:
#             logger.warning(f"Недостаточно общей емкости: нужно {total_attention_needed}, доступно {total_teacher_capacity}")
#             return False
#
#         # Проверяем, есть ли преподаватели для каждого предмета
#         student_subjects = set(s.subject_id for s in students)
#         teacher_subjects = set()
#         for teacher in teachers:
#             teacher_subjects.update(teacher.subjects_id)
#
#         missing_subjects = student_subjects - teacher_subjects
#         if missing_subjects:
#             logger.warning(f"Нет преподавателей для предметов: {missing_subjects}")
#             return False
#
#         # Упрощенная проверка - если общая емкость достаточна и есть преподаватели для всех предметов
#         # считаем что можно распределить (детальное распределение будет в основном алгоритме)
#         return True
#
#     @staticmethod
#     def check_allocation_for_time_slots(students: List['Student'], teachers: List['Teacher'],
#                                       start_time: time, end_time: time,
#                                       interval_minutes: int = 30) -> Dict[time, bool]:
#         """
#         Проверяет возможность распределения для временных промежутков в течение дня
#
#         Args:
#             students: список студентов
#             teachers: список преподавателей
#             start_time: время начала дня
#             end_time: время окончания дня
#             interval_minutes: интервал между проверками в минутах (по умолчанию 30)
#
#         Returns:
#             Словарь с временем как ключ и boolean значением (можно распределить или нет)
#         """
#         time_slots = {}
#         current_time = start_time
#
#         # Создаем временные промежутки
#         while current_time <= end_time:
#             # Проверяем распределение для текущего времени
#             can_allocate = School.check_teachers_combo_per_minute(students, teachers, current_time)
#             time_slots[current_time] = can_allocate
#
#             # Добавляем интервал к текущему времени
#             current_time = School.add_minutes_to_time(current_time, interval_minutes)
#
#         return time_slots
#
#     @staticmethod
#     def add_minutes_to_time(time_obj: time, minutes: int) -> time:
#         """
#         Добавляет минуты к объекту time
#         """
#         # Преобразуем time в datetime для удобства вычислений
#         from datetime import datetime
#         dummy_date = datetime(2023, 1, 1)  # произвольная дата
#         combined_datetime = datetime.combine(dummy_date, time_obj)
#         new_datetime = combined_datetime + timedelta(minutes=minutes)
#         return new_datetime.time()
#
#     @staticmethod
#     def print_allocation_report(time_slots: Dict[time, bool]):
#         """
#         Выводит красивый отчет о распределении по времени
#         """
#         print("Отчет о возможности распределения:")
#         print("=" * 40)
#         print("Время\t\tСтатус")
#         print("-" * 40)
#
#         for time_slot, can_allocate in time_slots.items():
#             status = "✅ Можно" if can_allocate else "❌ Нельзя"
#             print(f"{time_slot.strftime('%H:%M')}\t\t{status}")
#
#     @staticmethod
#     def find_valid_teacher_combinations(teachers: List[Teacher], students: List[Student]) -> List[List[Teacher]]:
#         """
#         Находит все валидные комбинации преподавателей для данных студентов
#         """
#         logger.info(f"Поиск валидных комбинаций: {len(teachers)} преподавателей, {len(students)} студентов")
#
#         if not students:
#             logger.info("Нет студентов - возвращаем все комбинации преподавателей")
#             return School.get_all_teacher_combinations(teachers)
#
#         if not teachers:
#             logger.warning("Нет преподавателей")
#             return []
#
#         # Генерируем все возможные комбинации преподавателей
#         all_combinations = School.get_all_teacher_combinations(teachers)
#         valid_combinations = []
#
#         # Проверяем каждую комбинацию
#         for combo in all_combinations:
#             if School.check_teacher_student_allocation(combo, students):
#                 valid_combinations.append(combo)
#
#         # Сортируем по сумме приоритетов (по убыванию)
#         valid_combinations.sort(
#             key=lambda x: sum(t.priority for t in x),
#             reverse=True
#         )
#
#         logger.info(f"Найдено {len(valid_combinations)} валидных комбинаций")
#         return valid_combinations
#
#     @staticmethod
#     def get_all_teacher_combinations(teachers: List[Teacher]) -> List[List[Teacher]]:
#         """Генерирует все возможные комбинации преподавателей"""
#         combinations = []
#         for r in range(1, len(teachers) + 1):
#             for combo in itertools.combinations(teachers, r):
#                 combinations.append(list(combo))
#         return combinations
#
#     @staticmethod
#     def generate_schedule_for_time_slot(
#             active_teachers: List[Teacher],
#             active_students: List[Student]
#     ) -> Tuple[List[List[Teacher]], Dict[Teacher, List[int]]]:
#         """
#         Генерирует расписание для конкретного временного слота
#         Возвращает:
#         - valid_combinations: список валидных комбинаций преподавателей
#         - teacher_combinations: словарь с номерами комбинаций для каждого преподавателя
#         """
#         if not active_students:
#             return [], {t: [] for t in active_teachers}
#
#         # Находим валидные комбинации
#         valid_combinations = School.find_valid_teacher_combinations(active_teachers, active_students)
#
#         # Создаем словарь для хранения номеров комбинаций для каждого преподавателя
#         teacher_combinations = {}
#         for teacher in active_teachers:
#             teacher_combos = []
#             for i, combo in enumerate(valid_combinations):
#                 if teacher in combo:
#                     teacher_combos.append(i + 1)  # Нумерация с 1
#             teacher_combinations[teacher] = teacher_combos
#
#         return valid_combinations, teacher_combinations
#
#     @staticmethod
#     def generate_daily_schedule(
#             students: List[Student],
#             teachers: List[Teacher],
#             start_time: time = time(9, 0),
#             end_time: time = time(20, 0),
#             interval_minutes: int = 15
#     ) -> Dict[time, Tuple[List[List[Teacher]], Dict[Teacher, List[int]]]]:
#         """
#         Генерирует расписание на весь день с заданным интервалом
#         Возвращает словарь, где ключ - время, значение - кортеж:
#         (valid_combinations, teacher_combinations)
#         """
#         schedule = {}
#         current_time = start_time
#
#         while current_time <= end_time:
#             # Получаем активных участников в текущее время
#             active_students = [
#                 s for s in students
#                 if s.start_of_studying_time < current_time and s.end_of_studying_time > current_time
#             ]
#
#             active_teachers = [
#                 t for t in teachers
#                 if t.start_of_studying_time <= current_time and t.end_of_studying_time >= current_time
#             ]
#
#             # Генерируем расписание для текущего времени
#             valid_combinations, teacher_combinations = School.generate_schedule_for_time_slot(
#                 active_teachers, active_students
#             )
#
#             schedule[current_time] = (valid_combinations, teacher_combinations)
#
#             # Переходим к следующему временному слоту
#             current_time = School.add_minutes_to_time(current_time, interval_minutes)
#
#         return schedule
#
#     @staticmethod
#     def get_best_combination(valid_combinations: List[List[Teacher]]) -> Optional[List[Teacher]]:
#         """
#         Возвращает лучшую комбинацию преподавателей на основе приоритетов
#         """
#         if not valid_combinations:
#             return None
#
#         return max(valid_combinations, key=lambda x: sum(t.priority for t in x))
#
#     @staticmethod
#     def print_schedule_report(schedule: Dict[time, Tuple[List[List[Teacher]], Dict[Teacher, List[int]]]]):
#         """
#         Выводит красивый отчет о расписании
#         """
#         print("=" * 80)
#         print("ОТЧЕТ О РАСПИСАНИИ")
#         print("=" * 80)
#
#         for time_slot, (combinations, teacher_combos) in schedule.items():
#             print(f"\nВремя: {time_slot.strftime('%H:%M')}")
#             print(f"Количество валидных комбинаций: {len(combinations)}")
#
#             if combinations:
#                 best_combo = School.get_best_combination(combinations)
#                 print(f"Лучшая комбинация: {', '.join(t.name for t in best_combo)}")
#                 print(f"Сумма приоритетов: {sum(t.priority for t in best_combo)}")
#
#             # Выводим комбинации для каждого преподавателя
#             for teacher, combos in teacher_combos.items():
#                 if combos:
#                     print(f"  {teacher.name}: комбинации {', '.join(map(str, combos))}")
#                 else:
#                     print(f"  {teacher.name}: нет валидных комбинаций")
#
#     @staticmethod
#     def find_valid_teacher_combinations_for_time_slot(
#             active_teachers: List[Teacher],
#             active_students: List[Student]
#     ) -> List[List[Teacher]]:
#         """
#         Находит все валидные комбинации преподавателей для конкретного временного слота
#         с учетом максимальной емкости и потребностей студентов (аналогично C# версии)
#         """
#         logger.info(
#             f"Поиск комбинаций (CS стиль): {len(active_teachers)} преподавателей, {len(active_students)} студентов")
#
#         if not active_students:
#             logger.info("Нет студентов - возвращаем все комбинации преподавателей")
#             return School.get_all_teacher_combinations(active_teachers)
#
#         if not active_teachers:
#             logger.warning("Нет преподавателей")
#             return []
#
#         # Генерируем все возможные комбинации преподавателей
#         all_combinations = School.get_all_teacher_combinations(active_teachers)
#         valid_combinations = []
#
#         # Проверяем каждую комбинацию (как в C# версии)
#         for combo in all_combinations:
#             if School.check_teacher_student_allocation_detailed(combo, active_students):
#                 valid_combinations.append(combo)
#
#         # Сортируем по сумме приоритетов (по убыванию)
#         valid_combinations.sort(
#             key=lambda x: sum(t.priority for t in x),
#             reverse=True
#         )
#
#         logger.info(f"Найдено {len(valid_combinations)} валидных комбинаций (CS стиль)")
#         return valid_combinations
#
#     @staticmethod
#     def check_teacher_student_allocation_detailed(teachers: List[Teacher], students: List[Student]) -> bool:
#         """
#         Детальная проверка распределения как в C# версии
#         с учетом потребности во внимании и максимальной емкости
#         """
#         if not teachers:
#             return len(students) == 0
#
#         if not students:
#             return True
#
#         # Сбрасываем текущую нагрузку преподавателей
#         for teacher in teachers:
#             teacher.current_attention_used = 0
#
#         # Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
#         subject_rarity = {}
#         for student in students:
#             if student.subject_id not in subject_rarity:
#                 subject_rarity[student.subject_id] = len([
#                     t for t in teachers if student.subject_id in t.subjects_id
#                 ])
#
#         # Сортируем студентов: сначала с редкими предметами, затем с большей потребностью
#         sorted_students = sorted(students,
#                                  key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))
#
#         # Распределяем студентов по преподавателям
#         for student in sorted_students:
#             # Находим подходящих преподавателей, отсортированных по текущей нагрузке и приоритету
#             available_teachers = [
#                 t for t in teachers
#                 if student.subject_id in t.subjects_id
#             ]
#
#             available_teachers.sort(key=lambda t: (
#                 t.current_attention_used,  # Сначала преподаватели с минимальной нагрузкой
#                 t.priority  # Затем по приоритету
#             ))
#
#             assigned = False
#             for teacher in available_teachers:
#                 if teacher.current_attention_used + student.need_for_attention <= teacher.maximum_attention:
#                     teacher.current_attention_used += student.need_for_attention
#                     assigned = True
#                     break
#
#             if not assigned:
#                 return False
#
#         return True
#
#     @staticmethod
#     def _can_distribute_students(teachers: List[Teacher], students: List[Student]) -> bool:
#         """
#         Проверяет, можно ли распределить студентов по преподавателям
#         с учетом предметов и емкости
#         """
#         # Группируем студентов по предметам
#         students_by_subject = {}
#         for student in students:
#             if student.subject_id not in students_by_subject:
#                 students_by_subject[student.subject_id] = []
#             students_by_subject[student.subject_id].append(student)
#
#         # Для каждого предмета проверяем, хватит ли преподавателей
#         for subject_id, subject_students in students_by_subject.items():
#             subject_teachers = [t for t in teachers if subject_id in t.subjects_id]
#
#             if not subject_teachers:
#                 return False
#
#             # Суммарная потребность во внимании для этого предмета
#             subject_attention_needed = sum(s.need_for_attention for s in subject_students)
#             subject_capacity = sum(t.maximum_attention for t in subject_teachers)
#
#             if subject_attention_needed > subject_capacity:
#                 return False
#
#         return True
#
#     @staticmethod
#     def generate_schedule_matrix(
#             students: List[Student],
#             teachers: List[Teacher],
#             start_time: time = time(9, 0),
#             end_time: time = time(20, 0),
#             interval_minutes: int = 15
#     ) -> List[List[Any]]:
#         """
#         Генерирует матрицу расписания аналогично C# версии
#         """
#         # Вычисляем количество временных слотов
#         total_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
#         time_slots = (total_minutes + interval_minutes - 1) // interval_minutes
#
#         # Создаем матрицу
#         matrix = [[None] * (time_slots + 1) for _ in range(len(teachers) + 2)]
#
#         # Заполняем заголовки
#         matrix[0][0] = "Teachers/Time"
#         for i in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (i - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#             matrix[0][i] = f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"
#
#         # Заполняем имена преподавателей
#         for i, teacher in enumerate(teachers):
#             matrix[i + 1][0] = teacher.name
#         matrix[len(teachers) + 1][0] = "Комбинации"
#
#         # Обрабатываем каждый временной слот
#         for slot in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (slot - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#
#             # Получаем активных участников
#             active_students = [
#                 s for s in students
#                 if s.start_of_studying_time < slot_end and s.end_of_studying_time > slot_start
#             ]
#
#             active_teachers = [
#                 t for t in teachers
#                 if t.start_of_studying_time <= slot_start and t.end_of_studying_time >= slot_end
#             ]
#
#             # Если нет студентов - все "0"
#             if not active_students:
#                 for t in range(len(teachers)):
#                     matrix[t + 1][slot] = "0"
#                 matrix[len(teachers) + 1][slot] = "-"
#                 continue
#
#             # Находим валидные комбинации
#             valid_combinations = School.find_valid_teacher_combinations_for_time_slot(
#                 active_teachers, active_students
#             )
#
#             # Записываем номера комбинаций для преподавателей
#             for t, teacher in enumerate(teachers):
#                 matrix[t + 1][slot] = "0"  # Значение по умолчанию
#
#                 if teacher in active_teachers:
#                     teacher_combos = []
#                     for i, combo in enumerate(valid_combinations):
#                         if teacher in combo:
#                             teacher_combos.append(str(i + 1))
#
#                     if teacher_combos:
#                         matrix[t + 1][slot] = ",".join(teacher_combos)
#
#             # Записываем состав комбинаций
#             if valid_combinations:
#                 combo_descriptions = []
#                 for i, combo in enumerate(valid_combinations):
#                     teacher_names = ", ".join(t.name for t in combo)
#                     combo_descriptions.append(f"{i + 1}: {teacher_names}")
#
#                 matrix[len(teachers) + 1][slot] = "; ".join(combo_descriptions)
#             else:
#                 matrix[len(teachers) + 1][slot] = "Нет валидных комбинаций"
#
#         return matrix
#
#     @staticmethod
#     def print_schedule_matrix(matrix: List[List[Any]], teachers: List[Teacher]):
#         """
#         Выводит матрицу расписания в консоль
#         """
#         if not matrix or not matrix[0]:
#             print("Матрица расписания пуста")
#             return
#
#         # Определяем максимальную ширину для каждого столбца
#         col_widths = [0] * len(matrix[0])
#         for row in matrix:
#             for i, cell in enumerate(row):
#                 cell_str = str(cell) if cell is not None else ""
#                 col_widths[i] = max(col_widths[i], len(cell_str))
#
#         # Минимальная ширина 3 символа
#         col_widths = [max(width, 3) for width in col_widths]
#
#         print("РАСПИСАНИЕ ПРЕПОДАВАТЕЛЕЙ ПО ТАЙМ-СЛОТАМ")
#         print()
#
#         # Выводим заголовки
#         for i, cell in enumerate(matrix[0]):
#             cell_str = str(cell) if cell is not None else ""
#             print(f"| {cell_str:<{col_widths[i]}} ", end="")
#         print("|")
#
#         # Выводим разделитель
#         for width in col_widths:
#             print(f"+{'-' * (width + 2)}", end="")
#         print("+")
#
#         # Выводим данные преподавателей
#         for row_idx in range(1, len(matrix) - 1):
#             for col_idx, cell in enumerate(matrix[row_idx]):
#                 cell_str = str(cell) if cell is not None else ""
#                 print(f"| {cell_str:<{col_widths[col_idx]}} ", end="")
#             print("|")
#
#         # Выводим разделитель для комбинаций
#         for width in col_widths:
#             print(f"+{'-' * (width + 2)}", end="")
#         print("+")
#
#         # Выводим комбинации
#         for col_idx, cell in enumerate(matrix[-1]):
#             cell_str = str(cell) if cell is not None else ""
#             print(f"| {cell_str:<{col_widths[col_idx]}} ", end="")
#         print("|")
#
#     @staticmethod
#     def get_best_combination_for_time_slot(
#             active_teachers: List[Teacher],
#             active_students: List[Student]
#     ) -> Optional[List[Teacher]]:
#         """
#         Возвращает лучшую комбинацию преподавателей для временного слота
#         """
#         valid_combinations = School.find_valid_teacher_combinations_for_time_slot(
#             active_teachers, active_students
#         )
#
#         if not valid_combinations:
#             return None
#
#         # Выбираем комбинацию с максимальной суммой приоритетов
#         return max(valid_combinations, key=lambda x: sum(t.priority for t in x))
#
#     # Добавьте эти методы в класс School в файле HelperMethods.py
#
#     @staticmethod
#     def generate_teacher_schedule_matrix_python(
#             students: List[Student],
#             teachers: List[Teacher],
#             start_time: time = time(9, 0),
#             end_time: time = time(20, 0),
#             interval_minutes: int = 15
#     ) -> List[List[Any]]:
#         """
#         Генерирует матрицу расписания аналогично C# версии
#         """
#         # Вычисляем количество временных слотов
#         total_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
#         time_slots = (total_minutes + interval_minutes - 1) // interval_minutes
#
#         # Создаем матрицу
#         matrix = [[None] * (time_slots + 1) for _ in range(len(teachers) + 2)]
#
#         # Заполняем заголовки
#         matrix[0][0] = "Teachers/Time"
#         for i in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (i - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#             matrix[0][i] = f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"
#
#         # Заполняем имена преподавателей
#         for i, teacher in enumerate(teachers):
#             matrix[i + 1][0] = teacher.name
#         matrix[len(teachers) + 1][0] = "Комбинации"
#
#         # Обрабатываем каждый временной слот
#         for slot in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (slot - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#
#             # Получаем активных участников (как в C# версии)
#             active_students = [
#                 s for s in students
#                 if s.start_of_studying_time < slot_end and s.end_of_studying_time > slot_start
#             ]
#
#             active_teachers = [
#                 t for t in teachers
#                 if t.start_of_studying_time <= slot_start and t.end_of_studying_time >= slot_end
#             ]
#
#             # Если нет студентов - все "0"
#             if not active_students:
#                 for t in range(len(teachers)):
#                     matrix[t + 1][slot] = "0"
#                 matrix[len(teachers) + 1][slot] = "-"
#                 continue
#
#             # Находим валидные комбинации (используем CS-стиль)
#             valid_combinations = School.find_valid_teacher_combinations_for_time_slot(
#                 active_teachers, active_students
#             )
#
#             # Записываем номера комбинаций для преподавателей
#             for t, teacher in enumerate(teachers):
#                 matrix[t + 1][slot] = "0"  # Значение по умолчанию
#
#                 if teacher in active_teachers:
#                     teacher_combos = []
#                     for i, combo in enumerate(valid_combinations):
#                         if teacher in combo:
#                             teacher_combos.append(str(i + 1))
#
#                     if teacher_combos:
#                         matrix[t + 1][slot] = ",".join(teacher_combos)
#
#             # Записываем состав комбинаций
#             if valid_combinations:
#                 combo_descriptions = []
#                 for i, combo in enumerate(valid_combinations):
#                     teacher_names = ", ".join(t.name for t in combo)
#                     combo_descriptions.append(f"{i + 1}: {teacher_names}")
#
#                 matrix[len(teachers) + 1][slot] = "; ".join(combo_descriptions)
#             else:
#                 matrix[len(teachers) + 1][slot] = "Нет валидных комбинаций"
#
#         return matrix
#
#     # @staticmethod
#     # def find_valid_teacher_combinations_for_time_slot(
#     #         active_teachers: List[Teacher],
#     #         active_students: List[Student]
#     # ) -> List[List[Teacher]]:
#     #     """
#     #     Находит все валидные комбинации преподавателей для конкретного временного слота
#     #     с учетом максимальной емкости и потребностей студентов
#     #     """
#     #     logger.info(f"Поиск комбинаций: {len(active_teachers)} преподавателей, {len(active_students)} студентов")
#     #
#     #     if not active_students:
#     #         logger.info("Нет студентов - возвращаем все комбинации преподавателей")
#     #         return School.get_all_teacher_combinations(active_teachers)
#     #
#     #     if not active_teachers:
#     #         logger.warning("Нет преподавателей")
#     #         return []
#     #
#     #     # Генерируем все возможные комбинации преподавателей
#     #     all_combinations = School.get_all_teacher_combinations(active_teachers)
#     #     valid_combinations = []
#     #
#     #     # Проверяем каждую комбинацию
#     #     for combo in all_combinations:
#     #         if School.check_teacher_student_allocation_detailed(combo, active_students):
#     #             valid_combinations.append(combo)
#     #
#     #     # Сортируем по сумме приоритетов (по убыванию)
#     #     valid_combinations.sort(
#     #         key=lambda x: sum(t.priority for t in x),
#     #         reverse=True
#     #     )
#     #
#     #     logger.info(f"Найдено {len(valid_combinations)} валидных комбинаций")
#     #     return valid_combinations
#     #
#     # @staticmethod
#     # def check_teacher_student_allocation_detailed(teachers: List[Teacher], students: List[Student]) -> bool:
#     #     """
#     #     Детальная проверка возможности распределения студентов по преподавателям
#     #     с учетом максимальной емкости и потребностей
#     #     """
#     #     if not teachers:
#     #         return len(students) == 0
#     #
#     #     if not students:
#     #         return True
#     #
#     #     # Проверяем базовую возможность распределения
#     #     total_attention_needed = sum(s.need_for_attention for s in students)
#     #     total_teacher_capacity = sum(t.maximum_attention for t in teachers)
#     #
#     #     if total_attention_needed > total_teacher_capacity:
#     #         logger.warning(
#     #             f"Недостаточно общей емкости: нужно {total_attention_needed}, доступно {total_teacher_capacity}")
#     #         return False
#     #
#     #     # Проверяем, есть ли преподаватели для каждого предмета
#     #     student_subjects = set(s.subject_id for s in students)
#     #     teacher_subjects = set()
#     #     for teacher in teachers:
#     #         teacher_subjects.update(teacher.subjects_id)
#     #
#     #     missing_subjects = student_subjects - teacher_subjects
#     #     if missing_subjects:
#     #         logger.warning(f"Нет преподавателей для предметов: {missing_subjects}")
#     #         return False
#     #
#     #     # Детальная проверка распределения студентов по преподавателям
#     #     return School._can_distribute_students(teachers, students)
#
#     @staticmethod
#     def _can_distribute_students(teachers: List[Teacher], students: List[Student]) -> bool:
#         """
#         Проверяет, можно ли распределить студентов по преподавателям
#         с учетом предметов и емкости
#         """
#         # Группируем студентов по предметам
#         students_by_subject = {}
#         for student in students:
#             if student.subject_id not in students_by_subject:
#                 students_by_subject[student.subject_id] = []
#             students_by_subject[student.subject_id].append(student)
#
#         # Для каждого предмета проверяем, хватит ли преподавателей
#         for subject_id, subject_students in students_by_subject.items():
#             subject_teachers = [t for t in teachers if subject_id in t.subjects_id]
#
#             if not subject_teachers:
#                 return False
#
#             # Суммарная потребность во внимании для этого предмета
#             subject_attention_needed = sum(s.need_for_attention for s in subject_students)
#             subject_capacity = sum(t.maximum_attention for t in subject_teachers)
#
#             if subject_attention_needed > subject_capacity:
#                 return False
#
#         return True
#
#     @staticmethod
#     def print_schedule_matrix(matrix: List[List[Any]], teachers: List[Teacher]):
#         """
#         Выводит матрицу расписания в консоль
#         """
#         if not matrix or not matrix[0]:
#             print("Матрица расписания пуста")
#             return
#
#         # Определяем максимальную ширину для каждого столбца
#         col_widths = [0] * len(matrix[0])
#         for row in matrix:
#             for i, cell in enumerate(row):
#                 cell_str = str(cell) if cell is not None else ""
#                 col_widths[i] = max(col_widths[i], len(cell_str))
#
#         # Минимальная ширина 3 символа
#         col_widths = [max(width, 3) for width in col_widths]
#
#         print("РАСПИСАНИЕ ПРЕПОДАВАТЕЛЕЙ ПО ТАЙМ-СЛОТАМ")
#         print()
#
#         # Выводим заголовки
#         for i, cell in enumerate(matrix[0]):
#             cell_str = str(cell) if cell is not None else ""
#             print(f"| {cell_str:<{col_widths[i]}} ", end="")
#         print("|")
#
#         # Выводим разделитель
#         for width in col_widths:
#             print(f"+{'-' * (width + 2)}", end="")
#         print("+")
#
#         # Выводим данные преподавателей
#         for row_idx in range(1, len(matrix) - 1):
#             for col_idx, cell in enumerate(matrix[row_idx]):
#                 cell_str = str(cell) if cell is not None else ""
#                 print(f"| {cell_str:<{col_widths[col_idx]}} ", end="")
#             print("|")
#
#         # Выводим разделитель для комбинаций
#         for width in col_widths:
#             print(f"+{'-' * (width + 2)}", end="")
#         print("+")
#
#         # Выводим комбинации
#         for col_idx, cell in enumerate(matrix[-1]):
#             cell_str = str(cell) if cell is not None else ""
#             print(f"| {cell_str:<{col_widths[col_idx]}} ", end="")
#         print("|")
#
#     # Добавьте эти методы в класс School в файле HelperMethods.py
#
#     # Добавьте эти методы в класс School в файле HelperMethods.py
#
#     @staticmethod
#     def check_teacher_student_allocation_detailed_cs(teachers: List[Teacher], students: List[Student]) -> bool:
#         """
#         Детальная проверка распределения как в C# версии
#         с учетом потребности во внимании и максимальной емкости
#         """
#         if not teachers:
#             return len(students) == 0
#
#         if not students:
#             return True
#
#         # Сбрасываем текущую нагрузку преподавателей
#         for teacher in teachers:
#             teacher.current_attention_used = 0
#
#         # Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
#         subject_rarity = {}
#         for student in students:
#             if student.subject_id not in subject_rarity:
#                 subject_rarity[student.subject_id] = len([
#                     t for t in teachers if student.subject_id in t.subjects_id
#                 ])
#
#         # Сортируем студентов: сначала с редкими предметами, затем с большей потребностью
#         sorted_students = sorted(students,
#                                  key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))
#
#         # Распределяем студентов по преподавателям
#         for student in sorted_students:
#             # Находим подходящих преподавателей, отсортированных по текущей нагрузке и приоритету
#             available_teachers = [
#                 t for t in teachers
#                 if student.subject_id in t.subjects_id
#             ]
#
#             available_teachers.sort(key=lambda t: (
#                 t.current_attention_used,  # Сначала преподаватели с минимальной нагрузкой
#                 t.priority  # Затем по приоритету
#             ))
#
#             assigned = False
#             for teacher in available_teachers:
#                 if teacher.current_attention_used + student.need_for_attention <= teacher.maximum_attention:
#                     teacher.current_attention_used += student.need_for_attention
#                     assigned = True
#                     break
#
#             if not assigned:
#                 return False
#
#         return True
#
#
#     @staticmethod
#     def _can_distribute_students_cs(teachers: List[Teacher], students: List[Student]) -> bool:
#         """
#         Проверяет, можно ли распределить студентов по преподавателям
#         с учетом предметов и емкости (аналогично C# версии)
#         """
#         # Группируем студентов по предметам
#         students_by_subject = {}
#         for student in students:
#             if student.subject_id not in students_by_subject:
#                 students_by_subject[student.subject_id] = []
#             students_by_subject[student.subject_id].append(student)
#
#         # Для каждого предмета проверяем, хватит ли преподавателей
#         for subject_id, subject_students in students_by_subject.items():
#             subject_teachers = [t for t in teachers if subject_id in t.subjects_id]
#
#             if not subject_teachers:
#                 return False
#
#             # Суммарная потребность во внимании для этого предмета
#             subject_attention_needed = sum(s.need_for_attention for s in subject_students)
#             subject_capacity = sum(t.maximum_attention for t in subject_teachers)
#
#             if subject_attention_needed > subject_capacity:
#                 return False
#
#         return True
#
#     @staticmethod
#     def find_valid_teacher_combinations_cs(active_teachers: List[Teacher], active_students: List[Student]) -> List[List[Teacher]]:
#         """
#         Находит все валидные комбинации преподавателей для конкретного временного слота
#         с учетом максимальной емкости и потребностей студентов (аналогично C# версии)
#         """
#         logger.info(f"Поиск комбинаций (CS стиль): {len(active_teachers)} преподавателей, {len(active_students)} студентов")
#
#         if not active_students:
#             logger.info("Нет студентов - возвращаем все комбинации преподавателей")
#             return School.get_all_teacher_combinations(active_teachers)
#
#         if not active_teachers:
#             logger.warning("Нет преподавателей")
#             return []
#
#         # Генерируем все возможные комбинации преподавателей
#         all_combinations = School.get_all_teacher_combinations(active_teachers)
#         valid_combinations = []
#
#         # Проверяем каждую комбинацию (как в C# версии)
#         for combo in all_combinations:
#             if School.check_teacher_student_allocation_detailed_cs(combo, active_students):
#                 valid_combinations.append(combo)
#
#         # Сортируем по сумме приоритетов (по убыванию)
#         valid_combinations.sort(
#             key=lambda x: sum(t.priority for t in x),
#             reverse=True
#         )
#
#         logger.info(f"Найдено {len(valid_combinations)} валидных комбинаций (CS стиль)")
#         return valid_combinations
#
#     # @staticmethod
#     # def generate_teacher_schedule_matrix_cs_style(
#     #     students: List[Student],
#     # teachers: List[Teacher],
#     # start_time: time = time(9, 0),
#     # end_time: time = time(20, 0),
#     # interval_minutes: int = 15
#     # ) -> List[List[Any]]:
#     # """
#     # Генерирует матрицу расписания аналогично C# версии
#     # """
#     # # Вычисляем количество временных слотов
#     # total_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
#     # time_slots = (total_minutes + interval_minutes - 1) // interval_minutes
#     #
#     # # Создаем матрицу
#     # matrix = [[None] * (time_slots + 1) for _ in range(len(teachers) + 2)]
#     #
#     # # Заполняем заголовки
#     # matrix[0][0] = "Teachers/Time"
#     # for i in range(1, time_slots + 1):
#     #     slot_start = School.add_minutes_to_time(start_time, (i - 1) * interval_minutes)
#     #     slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#     #     matrix[0][i] = f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"
#     #
#     # # Заполняем имена преподавателей
#     # for i, teacher in enumerate(teachers):
#     #     matrix[i + 1][0] = teacher.name
#     # matrix[len(teachers) + 1][0] = "Комбинации"
#     #
#     # # Обрабатываем каждый временной слот
#     # for slot in range(1, time_slots + 1):
#     #     slot_start = School.add_minutes_to_time(start_time, (slot - 1) * interval_minutes)
#     #     slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#     #
#     #     # Получаем активных участников (как в C# версии)
#     #     active_students = [
#     #         s for s in students
#     #         if s.start_of_studying_time < slot_end and s.end_of_studying_time > slot_start
#     #     ]
#     #
#     #     active_teachers = [
#     #         t for t in teachers
#     #         if t.start_of_studying_time <= slot_start and t.end_of_studying_time >= slot_end
#     #     ]
#     #
#     #     # Если нет студентов - все "0"
#     #     if not active_students:
#     #         for t in range(len(teachers)):
#     #             matrix[t + 1][slot] = "0"
#     #         matrix[len(teachers) + 1][slot] = "-"
#     #         continue
#     #
#     #     # Находим валидные комбинации (используем CS-стиль)
#     #     valid_combinations = School.find_valid_teacher_combinations_cs(
#     #         active_teachers, active_students
#     #     )
#     #
#     #     # Записываем номера комбинаций для преподавателей
#     #     for t, teacher in enumerate(teachers):
#     #         matrix[t + 1][slot] = "0"  # Значение по умолчанию
#     #
#     #         if teacher in active_teachers:
#     #             teacher_combos = []
#     #             for i, combo in enumerate(valid_combinations):
#     #                 if teacher in combo:
#     #                     teacher_combos.append(str(i + 1))
#     #
#     #             if teacher_combos:
#     #                 matrix[t + 1][slot] = ",".join(teacher_combos)
#     #
#     #     # Записываем состав комбинаций
#     #     if valid_combinations:
#     #         combo_descriptions = []
#     #         for i, combo in enumerate(valid_combinations):
#     #             teacher_names = ", ".join(t.name for t in combo)
#     #             combo_descriptions.append(f"{i + 1}: {teacher_names}")
#     #
#     #         matrix[len(teachers) + 1][slot] = "; ".join(combo_descriptions)
#     #     else:
#     #         matrix[len(teachers) + 1][slot] = "Нет валидных комбинаций"
#     #
#     # return matrix
#
#     @staticmethod
#     def check_for_entry_interruption(res: List[List[Teacher]], combo: List[Teacher]) -> bool:
#         """
#         Проверяет, не является ли комбинация подмножеством уже существующих комбинаций
#         (аналогично C# методу CheckForEntryinterruption)
#         """
#         if not res:
#             return True
#
#         for item in res:
#             if School.finding_an_occurrence_of_combination(item, combo):
#                 return False
#         return True
#
#     @staticmethod
#     def finding_an_occurrence_of_combination(item: List[Teacher], combo: List[Teacher]) -> bool:
#         """
#         Проверяет, является ли комбинация подмножеством другой комбинации
#         (аналогично C# методу FindingAnOccurrenceOfaCombination)
#         """
#         item_names = {t.name for t in item}
#         combo_names = {t.name for t in combo}
#         return combo_names.issubset(item_names)
#
#     @staticmethod
#     def get_teacher_combo_for_the_day(students: List[Student], teachers: List[Teacher]) -> List[List[Teacher]]:
#         """
#         Получает все комбинации преподавателей на весь день (аналогично C# методу GetTeacherComboForTheDay)
#         """
#         all_combinations = School.get_all_teacher_combinations(teachers)
#         valid_combinations = []
#
#         for combo in all_combinations:
#             if (School.check_teachers_combo_for_the_day(students, combo) and
#                     School.check_for_entry_interruption(valid_combinations, combo)):
#                 valid_combinations.append(combo)
#
#         # Сортируем по сумме приоритетов
#         valid_combinations.sort(key=lambda x: sum(t.priority for t in x))
#         return valid_combinations
#
#     @staticmethod
#     def check_teachers_combo_for_the_day(students: List[Student], teachers: List[Teacher]) -> bool:
#         """
#         Проверяет комбинацию преподавателей на весь день (аналогично C# методу CheckTeachersComboForTheDay)
#         """
#         from datetime import time
#
#         current_time = time(9, 0)
#         for i in range(660):  # 11 часов * 60 минут = 660 минут
#             current_time = School.add_minutes_to_time(current_time, 1)
#             if not School.check_teachers_combo_per_minute(students, teachers, current_time):
#                 return False
#         return True
#
#     @staticmethod
#     def generate_detailed_schedule_matrix(
#             students: List[Student],
#             teachers: List[Teacher],
#             start_time: time = time(9, 0),
#             end_time: time = time(20, 0),
#             interval_minutes: int = 15
#     ) -> List[List[Any]]:
#         """
#         Генерирует матрицу расписания с детальной логикой распределения как в C#
#         """
#         # Вычисляем количество временных слотов
#         total_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
#         time_slots = (total_minutes + interval_minutes - 1) // interval_minutes
#
#         # Создаем матрицу
#         matrix = [[None] * (time_slots + 1) for _ in range(len(teachers) + 2)]
#
#         # Заполняем заголовки
#         matrix[0][0] = "Teachers/Time"
#         for i in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (i - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#             matrix[0][i] = f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"
#
#         # Заполняем имена преподавателей
#         for i, teacher in enumerate(teachers):
#             matrix[i + 1][0] = teacher.name
#         matrix[len(teachers) + 1][0] = "Комбинации"
#
#         # Обрабатываем каждый временной слот
#         for slot in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (slot - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#
#             # Получаем активных участников (как в C# версии)
#             active_students = [
#                 s for s in students
#                 if s.start_of_studying_time < slot_end and s.end_of_studying_time > slot_start
#             ]
#
#             active_teachers = [
#                 t for t in teachers
#                 if t.start_of_studying_time <= slot_start and t.end_of_studying_time >= slot_end
#             ]
#
#             # Если нет студентов - все "0"
#             if not active_students:
#                 for t in range(len(teachers)):
#                     matrix[t + 1][slot] = "0"
#                 matrix[len(teachers) + 1][slot] = "-"
#                 continue
#
#             # Находим валидные комбинации с детальной проверкой
#             valid_combinations = DetailedAllocation.find_valid_teacher_combinations_detailed(
#                 active_teachers, active_students
#             )
#
#             # Записываем номера комбинаций для преподавателей
#             for t, teacher in enumerate(teachers):
#                 matrix[t + 1][slot] = "0"  # Значение по умолчанию
#
#                 if teacher in active_teachers:
#                     teacher_combos = []
#                     for i, combo in enumerate(valid_combinations):
#                         if teacher in combo:
#                             teacher_combos.append(str(i + 1))
#
#                     if teacher_combos:
#                         matrix[t + 1][slot] = ",".join(teacher_combos)
#
#             # Записываем состав комбинаций
#             if valid_combinations:
#                 combo_descriptions = []
#                 for i, combo in enumerate(valid_combinations):
#                     teacher_names = ", ".join(t.name for t in combo)
#                     combo_descriptions.append(f"{i + 1}: {teacher_names}")
#
#                 matrix[len(teachers) + 1][slot] = "; ".join(combo_descriptions)
#             else:
#                 matrix[len(teachers) + 1][slot] = "Нет валидных комбинаций"
#
#         return matrix
#
#
# class DetailedAllocation:
#     @staticmethod
#     def check_teacher_student_allocation_detailed(teachers: List[Teacher], students: List[Student]) -> bool:
#         """
#         Детальная проверка распределения как в C# версии
#         с учетом потребности во внимании и максимальной емкости
#         """
#         if not teachers:
#             return len(students) == 0
#
#         if not students:
#             return True
#
#         # Сбрасываем текущую нагрузку преподавателей
#         for teacher in teachers:
#             teacher.current_attention_used = 0
#
#         # Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
#         subject_rarity = {}
#         for student in students:
#             if student.subject_id not in subject_rarity:
#                 subject_rarity[student.subject_id] = len([
#                     t for t in teachers if student.subject_id in t.subjects_id
#                 ])
#
#         # Сортируем студентов: сначала с редкими предметами, затем с большей потребностью
#         sorted_students = sorted(students,
#                                  key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))
#
#         # Распределяем студентов по преподавателям
#         for student in sorted_students:
#             # Находим подходящих преподавателей, отсортированных по текущей нагрузке и приоритету
#             available_teachers = [
#                 t for t in teachers
#                 if student.subject_id in t.subjects_id
#             ]
#
#             available_teachers.sort(key=lambda t: (
#                 t.current_attention_used,  # Сначала преподаватели с минимальной нагрузкой
#                 t.priority  # Затем по приоритету
#             ))
#
#             assigned = False
#             for teacher in available_teachers:
#                 if teacher.current_attention_used + student.need_for_attention <= teacher.maximum_attention:
#                     teacher.current_attention_used += student.need_for_attention
#                     assigned = True
#                     break
#
#             if not assigned:
#                 return False
#
#         return True
#
#     @staticmethod
#     def find_valid_teacher_combinations_detailed(teachers: List[Teacher], students: List[Student]) -> List[
#         List[Teacher]]:
#         """
#         Находит все валидные комбинации с детальной проверкой распределения
#         """
#         if not students:
#             return School.get_all_teacher_combinations(teachers)
#
#         if not teachers:
#             return []
#
#         all_combinations = School.get_all_teacher_combinations(teachers)
#         valid_combinations = []
#
#         for combo in all_combinations:
#             if DetailedAllocation.check_teacher_student_allocation_detailed(combo, students):
#                 valid_combinations.append(combo)
#
#         # Сортируем по сумме приоритетов (по убыванию)
#         valid_combinations.sort(key=lambda x: sum(t.priority for t in x), reverse=True)
#
#         return valid_combinations
#
#
# class DebugUtils:
#     @staticmethod
#     def print_allocation_debug(teachers: List[Teacher], students: List[Student]):
#         """
#         Выводит детальную информацию о распределении для отладки
#         """
#         print("\n=== ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О РАСПРЕДЕЛЕНИИ ===")
#
#         # Информация о преподавателях
#         print("ПРЕПОДАВАТЕЛИ:")
#         for teacher in teachers:
#             print(f"  {teacher.name}: предметы {teacher.subjects_id}, "
#                   f"емкость {teacher.maximum_attention}, приоритет {teacher.priority}")
#
#         # Информация о студентах
#         print("\nСТУДЕНТЫ:")
#         for student in students:
#             print(f"  {student.name}: предмет {student.subject_id}, "
#                   f"потребность {student.need_for_attention}")
#
#         # Проверяем распределение
#         can_allocate = DetailedAllocation.check_teacher_student_allocation_detailed(teachers, students)
#         print(f"\nМожно распределить: {'✅ Да' if can_allocate else '❌ Нет'}")
#
#         if can_allocate:
#             # Показываем как распределились студенты
#             print("\nРАСПРЕДЕЛЕНИЕ СТУДЕНТОВ:")
#             # Сбрасываем нагрузку
#             for teacher in teachers:
#                 teacher.current_attention_used = 0
#
#             subject_rarity = {}
#             for student in students:
#                 if student.subject_id not in subject_rarity:
#                     subject_rarity[student.subject_id] = len([
#                         t for t in teachers if student.subject_id in t.subjects_id
#                     ])
#
#             sorted_students = sorted(students,
#                                      key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))
#
#             for student in sorted_students:
#                 available_teachers = [
#                     t for t in teachers
#                     if student.subject_id in t.subjects_id
#                 ]
#                 available_teachers.sort(key=lambda t: (t.current_attention_used, t.priority))
#
#                 for teacher in available_teachers:
#                     if teacher.current_attention_used + student.need_for_attention <= teacher.maximum_attention:
#                         teacher.current_attention_used += student.need_for_attention
#                         print(f"  {student.name} -> {teacher.name} "
#                               f"(нагрузка: {teacher.current_attention_used}/{teacher.maximum_attention})")
#                         break
#
#
# # Добавьте эти методы в класс School в файле HelperMethods.py
#
# class CSAllocationMethods:
#     """Класс с методами распределения в стиле C#"""
#
#     @staticmethod
#     def check_teacher_student_allocation_cs_style(teachers: List[Teacher], students: List[Student]) -> bool:
#         """
#         Детальная проверка распределения как в C# версии
#         с учетом потребности во внимании и максимальной емкости
#         """
#         if not teachers:
#             return len(students) == 0
#
#         if not students:
#             return True
#
#         # Сбрасываем текущую нагрузку преподавателей
#         for teacher in teachers:
#             teacher.current_attention_used = 0
#
#         # Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
#         subject_rarity = {}
#         for student in students:
#             if student.subject_id not in subject_rarity:
#                 subject_rarity[student.subject_id] = len([
#                     t for t in teachers if student.subject_id in t.subjects_id
#                 ])
#
#         # Сортируем студентов: сначала с редкими предметами, затем с большей потребностью
#         sorted_students = sorted(students,
#                                  key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))
#
#         # Распределяем студентов по преподавателям
#         for student in sorted_students:
#             # Находим подходящих преподавателей, отсортированных по текущей нагрузке и приоритету
#             available_teachers = [
#                 t for t in teachers
#                 if student.subject_id in t.subjects_id
#             ]
#
#             available_teachers.sort(key=lambda t: (
#                 t.current_attention_used,  # Сначала преподаватели с минимальной нагрузкой
#                 t.priority  # Затем по приоритету
#             ))
#
#             assigned = False
#             for teacher in available_teachers:
#                 if teacher.current_attention_used + student.need_for_attention <= teacher.maximum_attention:
#                     teacher.current_attention_used += student.need_for_attention
#                     assigned = True
#                     break
#
#             if not assigned:
#                 return False
#
#         return True
#
#     @staticmethod
#     def find_valid_teacher_combinations_cs_style(teachers: List[Teacher], students: List[Student]) -> List[
#         List[Teacher]]:
#         """
#         Находит все валидные комбинации преподавателей в стиле C#
#         """
#         if not students:
#             return School.get_all_teacher_combinations(teachers)
#
#         if not teachers:
#             return []
#
#         # Генерируем все возможные комбинации преподавателей
#         all_combinations = School.get_all_teacher_combinations(teachers)
#         valid_combinations = []
#
#         # Проверяем каждую комбинацию (как в C# версии)
#         for combo in all_combinations:
#             if CSAllocationMethods.check_teacher_student_allocation_cs_style(combo, students):
#                 valid_combinations.append(combo)
#
#         # Сортируем по сумме приоритетов (по убыванию)
#         valid_combinations.sort(
#             key=lambda x: sum(t.priority for t in x),
#             reverse=True
#         )
#
#         return valid_combinations
#
#     @staticmethod
#     def generate_teacher_schedule_matrix_cs_style(
#             students: List[Student],
#             teachers: List[Teacher],
#             start_time: time = time(9, 0),
#             end_time: time = time(20, 0),
#             interval_minutes: int = 15
#     ) -> List[List[Any]]:
#         """
#         Генерирует матрицу расписания аналогично C# версии
#         """
#         # Вычисляем количество временных слотов
#         total_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
#         time_slots = (total_minutes + interval_minutes - 1) // interval_minutes
#
#         # Создаем матрицу
#         matrix = [[None] * (time_slots + 1) for _ in range(len(teachers) + 2)]
#
#         # Заполняем заголовки
#         matrix[0][0] = "Teachers/Time"
#         for i in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (i - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#             matrix[0][i] = f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"
#
#         # Заполняем имена преподавателей
#         for i, teacher in enumerate(teachers):
#             matrix[i + 1][0] = teacher.name
#         matrix[len(teachers) + 1][0] = "Комбинации"
#
#         # Обрабатываем каждый временной слот
#         for slot in range(1, time_slots + 1):
#             slot_start = School.add_minutes_to_time(start_time, (slot - 1) * interval_minutes)
#             slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
#
#             # Получаем активных участников (как в C# версии)
#             active_students = [
#                 s for s in students
#                 if s.start_of_studying_time < slot_end and s.end_of_studying_time > slot_start
#             ]
#
#             active_teachers = [
#                 t for t in teachers
#                 if t.start_of_studying_time <= slot_start and t.end_of_studying_time >= slot_end
#             ]
#
#             # Если нет студентов - все "0"
#             if not active_students:
#                 for t in range(len(teachers)):
#                     matrix[t + 1][slot] = "0"
#                 matrix[len(teachers) + 1][slot] = "-"
#                 continue
#
#             # Находим валидные комбинации (используем CS-стиль)
#             valid_combinations = CSAllocationMethods.find_valid_teacher_combinations_cs_style(
#                 active_teachers, active_students
#             )
#
#             # Записываем номера комбинаций для преподавателей
#             for t, teacher in enumerate(teachers):
#                 matrix[t + 1][slot] = "0"  # Значение по умолчанию
#
#                 if teacher in active_teachers:
#                     teacher_combos = []
#                     for i, combo in enumerate(valid_combinations):
#                         if teacher in combo:
#                             teacher_combos.append(str(i + 1))
#
#                     if teacher_combos:
#                         matrix[t + 1][slot] = ",".join(teacher_combos)
#
#             # Записываем состав комбинаций
#             if valid_combinations:
#                 combo_descriptions = []
#                 for i, combo in enumerate(valid_combinations):
#                     teacher_names = ", ".join(t.name for t in combo)
#                     combo_descriptions.append(f"{i + 1}: {teacher_names}")
#
#                 matrix[len(teachers) + 1][slot] = "; ".join(combo_descriptions)
#             else:
#                 matrix[len(teachers) + 1][slot] = "Нет валидных комбинаций"
#
#         return matrix
from typing import List, Dict, Tuple, Optional, Any, Set
from datetime import time, timedelta
from models import Teacher, Student
import itertools
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class School:
    @staticmethod
    def check_teacher_student_allocation_detailed(teachers: List[Teacher], students: List[Student]) -> bool:
        """
        Детальная проверка распределения как в C# версии
        с учетом потребности во внимании и максимальной емкости
        """
        if not teachers:
            return len(students) == 0

        if not students:
            return True

        # Сбрасываем текущую нагрузку преподавателей
        for teacher in teachers:
            teacher.current_attention_used = 0

        # Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
        subject_rarity = {}
        for student in students:
            if student.subject_id not in subject_rarity:
                subject_rarity[student.subject_id] = len([
                    t for t in teachers if student.subject_id in t.subjects_id
                ])

        # Сортируем студентов: сначала с редкими предметами, затем с большей потребностью
        sorted_students = sorted(students,
                                 key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))

        # Распределяем студентов по преподавателям
        for student in sorted_students:
            # Находим подходящих преподавателей, отсортированных по текущей нагрузке и приоритету
            available_teachers = [
                t for t in teachers
                if student.subject_id in t.subjects_id
            ]

            available_teachers.sort(key=lambda t: (
                t.current_attention_used,  # Сначала преподаватели с минимальной нагрузкой
                -t.priority  # Затем по приоритету (высокий приоритет сначала)
            ))

            assigned = False
            for teacher in available_teachers:
                if teacher.current_attention_used + student.need_for_attention <= teacher.maximum_attention:
                    teacher.current_attention_used += student.need_for_attention
                    assigned = True
                    break

            if not assigned:
                return False

        return True

    @staticmethod
    def get_all_teacher_combinations(teachers: List[Teacher]) -> List[List[Teacher]]:
        """Генерирует все возможные комбинации преподавателей"""
        combinations = []
        for r in range(1, len(teachers) + 1):
            for combo in itertools.combinations(teachers, r):
                combinations.append(list(combo))
        return combinations

    @staticmethod
    def find_valid_teacher_combinations_for_time_slot(
            active_teachers: List[Teacher],
            active_students: List[Student]
    ) -> List[List[Teacher]]:
        """
        Находит все валидные комбинации преподавателей для конкретного временного слота
        """
        logger.info(f"Поиск комбинаций: {len(active_teachers)} преподавателей, {len(active_students)} студентов")

        if not active_students:
            logger.info("Нет студентов - возвращаем все комбинации преподавателей")
            return School.get_all_teacher_combinations(active_teachers)

        if not active_teachers:
            logger.warning("Нет преподавателей")
            return []

        # Генерируем все возможные комбинации преподавателей
        all_combinations = School.get_all_teacher_combinations(active_teachers)
        valid_combinations = []

        # Проверяем каждую комбинацию - УБИРАЕМ ФИЛЬТРАЦИЮ CheckForEntryinterruption!
        for combo in all_combinations:
            if School.check_teacher_student_allocation_detailed(combo, active_students):
                valid_combinations.append(combo)

        # Сортируем по сумме приоритетов (по убыванию)
        valid_combinations.sort(
            key=lambda x: sum(t.priority for t in x),
            reverse=True
        )

        logger.info(f"Найдено {len(valid_combinations)} валидных комбинаций")
        return valid_combinations

    @staticmethod
    def add_minutes_to_time(time_obj: time, minutes: int) -> time:
        """Добавляет минуты к объекту time"""
        from datetime import datetime
        dummy_date = datetime(2023, 1, 1)
        combined_datetime = datetime.combine(dummy_date, time_obj)
        new_datetime = combined_datetime + timedelta(minutes=minutes)
        return new_datetime.time()

    @staticmethod
    def generate_teacher_schedule_matrix(
            students: List[Student],
            teachers: List[Teacher],
            start_time: time = time(9, 0),
            end_time: time = time(20, 0),
            interval_minutes: int = 15
    ) -> List[List[Any]]:
        """
        Генерирует матрицу расписания аналогично C# версии
        """
        # Вычисляем количество временных слотов
        total_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
        time_slots = (total_minutes + interval_minutes - 1) // interval_minutes

        # Создаем матрицу
        matrix = [[None] * (time_slots + 1) for _ in range(len(teachers) + 2)]

        # Заполняем заголовки
        matrix[0][0] = "Teachers/Time"
        for i in range(1, time_slots + 1):
            slot_start = School.add_minutes_to_time(start_time, (i - 1) * interval_minutes)
            slot_end = School.add_minutes_to_time(slot_start, interval_minutes)
            matrix[0][i] = f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"

        # Заполняем имена преподавателей
        for i, teacher in enumerate(teachers):
            matrix[i + 1][0] = teacher.name
        matrix[len(teachers) + 1][0] = "Комбинации"

        # Обрабатываем каждый временной слот
        for slot in range(1, time_slots + 1):
            slot_start = School.add_minutes_to_time(start_time, (slot - 1) * interval_minutes)
            slot_end = School.add_minutes_to_time(slot_start, interval_minutes)

            # Получаем активных участников
            active_students = [
                s for s in students
                if s.start_of_studying_time < slot_end and s.end_of_studying_time > slot_start
            ]

            active_teachers = [
                t for t in teachers
                if t.start_of_studying_time <= slot_start and t.end_of_studying_time >= slot_end
            ]

            # Если нет студентов - все "0"
            if not active_students:
                for t in range(len(teachers)):
                    matrix[t + 1][slot] = "0"
                matrix[len(teachers) + 1][slot] = "-"
                continue

            # Находим валидные комбинации
            valid_combinations = School.find_valid_teacher_combinations_for_time_slot(
                active_teachers, active_students
            )

            # Записываем номера комбинаций для преподавателей
            for t, teacher in enumerate(teachers):
                matrix[t + 1][slot] = "0"  # Значение по умолчанию

                if teacher in active_teachers:
                    teacher_combos = []
                    for i, combo in enumerate(valid_combinations):
                        if teacher in combo:
                            teacher_combos.append(str(i + 1))

                    if teacher_combos:
                        matrix[t + 1][slot] = ",".join(teacher_combos)
            # Записываем состав комбинаций
            if valid_combinations:
                combo_descriptions = []
                for i, combo in enumerate(valid_combinations):
                    teacher_names = ", ".join(t.name for t in combo)
                    combo_descriptions.append(f"{i + 1}: {teacher_names}")

                matrix[len(teachers) + 1][slot] = "; ".join(combo_descriptions)
            else:
                matrix[len(teachers) + 1][slot] = "Нет валидных комбинаций"

        return matrix

    @staticmethod
    def print_schedule_matrix(matrix: List[List[Any]], teachers: List[Teacher]):
        """Выводит матрицу расписания в консоль"""
        if not matrix or not matrix[0]:
            print("Матрица расписания пуста")
            return

        # Определяем максимальную ширину для каждого столбца
        col_widths = [0] * len(matrix[0])
        for row in matrix:
            for i, cell in enumerate(row):
                cell_str = str(cell) if cell is not None else ""
                col_widths[i] = max(col_widths[i], len(cell_str))

        # Минимальная ширина 3 символа
        col_widths = [max(width, 3) for width in col_widths]

        print("РАСПИСАНИЕ ПРЕПОДАВАТЕЛЕЙ ПО ТАЙМ-СЛОТАМ")
        print()

        # Выводим заголовки
        for i, cell in enumerate(matrix[0]):
            cell_str = str(cell) if cell is not None else ""
            print(f"| {cell_str:<{col_widths[i]}} ", end="")
        print("|")

        # Выводим разделитель
        for width in col_widths:
            print(f"+{'-' * (width + 2)}", end="")
        print("+")

        # Выводим данные преподавателей
        for row_idx in range(1, len(matrix) - 1):
            for col_idx, cell in enumerate(matrix[row_idx]):
                cell_str = str(cell) if cell is not None else ""
                print(f"| {cell_str:<{col_widths[col_idx]}} ", end="")
            print("|")

        # Выводим разделитель для комбинаций
        for width in col_widths:
            print(f"+{'-' * (width + 2)}", end="")
        print("+")

        # Выводим комбинации
        for col_idx, cell in enumerate(matrix[-1]):
            cell_str = str(cell) if cell is not None else ""
            print(f"| {cell_str:<{col_widths[col_idx]}} ", end="")
        print("|")