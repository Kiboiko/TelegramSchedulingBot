# from datetime import time, timedelta
# from typing import List, Dict
# from models import Person,Teacher,Student
# import logging
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

from datetime import time, timedelta
from typing import List, Dict, Tuple, Optional
from models import Teacher, Student
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class School:
    # Существующие методы остаются без изменений
    @staticmethod
    def check_teachers_combo_per_minute(students: List['Student'], teachers: List['Teacher'], time: time) -> bool:
        active_teachers = School.get_active_teachers_at_minute(teachers, time)
        active_students = School.get_active_students_at_minute(students, time)
        return School.check_teacher_student_allocation(active_teachers, active_students)

    @staticmethod
    def get_active_teachers_at_minute(teachers: List['Teacher'], time: time) -> List['Teacher']:
        res = []
        for teacher in teachers:
            if (time >= teacher.start_of_studying_time) and (time <= teacher.end_of_studying_time):
                res.append(teacher)
        return res

    @staticmethod
    def get_active_students_at_minute(students: List['Student'], time: time) -> List['Student']:
        res = []
        for student in students:
            if (time >= student.start_of_studying_time) and (time <= student.end_of_studying_time):
                res.append(student)
        return res

    @staticmethod
    def check_teacher_student_allocation(teachers: List['Teacher'], students: List['Student']) -> bool:
        logger.info(f"Проверка распределения: {len(teachers)} преподавателей, {len(students)} студентов")

        if not teachers:
            logger.warning("Нет преподавателей для распределения")
            return len(students) == 0

        if not students:
            logger.warning("Нет студентов для распределения")
            return True

        # Проверяем базовую возможность распределения
        total_attention_needed = sum(s.need_for_attention for s in students)
        total_teacher_capacity = sum(t.maximum_attention for t in teachers)

        if total_attention_needed > total_teacher_capacity:
            logger.warning(
                f"Недостаточно общей емкости: нужно {total_attention_needed}, доступно {total_teacher_capacity}")
            return False

        # Проверяем, есть ли преподаватели для каждого предмета
        student_subjects = set(s.subject_id for s in students)
        teacher_subjects = set()
        for teacher in teachers:
            teacher_subjects.update(teacher.subjects_id)

        missing_subjects = student_subjects - teacher_subjects
        if missing_subjects:
            logger.warning(f"Нет преподавателей для предметов: {missing_subjects}")
            return False

        return True

    # НОВЫЙ МЕТОД: Генерация конкретного распределения студентов по преподавателям
    @staticmethod
    def generate_teacher_student_allocation(teachers: List[Teacher], students: List[Student]) -> Tuple[
        bool, Dict[Teacher, List[Student]]]:
        """
        Генерирует конкретное распределение студентов по преподавателям

        Args:
            teachers: список преподавателей
            students: список студентов

        Returns:
            Tuple[bool, Dict[Teacher, List[Student]]]:
            - Флаг успешности распределения
            - Словарь с распределением: преподаватель -> список его студентов
        """
        logger.info(f"Генерация распределения: {len(teachers)} преподавателей, {len(students)} студентов")

        teacher_assignments = {teacher: [] for teacher in teachers}
        unassigned_students = []

        if not teachers:
            logger.warning("Нет преподавателей для распределения")
            return (len(students) == 0, teacher_assignments)

        if not students:
            logger.warning("Нет студентов для распределения")
            return (True, teacher_assignments)

        # Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
        subject_rarity = {}
        for student in students:
            if student.subject_id not in subject_rarity:
                subject_rarity[student.subject_id] = sum(1 for t in teachers
                                                         if student.subject_id in t.subjects_id)

        # Сортируем студентов:
        # 1. Сначала студенты с редкими предметами (меньше преподавателей могут вести)
        # 2. Затем студенты с большей потребностью во внимании
        sorted_students = sorted(students,
                                 key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))

        for student in sorted_students:
            # Доступные преподаватели для этого предмета, отсортированные по:
            # 1. Текущей нагрузке (сумма need_for_attention)
            # 2. Приоритету преподавателя
            available_teachers = [
                t for t in teachers
                if student.subject_id in t.subjects_id
            ]

            # Сортируем по текущей нагрузке и приоритету
            available_teachers.sort(key=lambda t: (
                sum(s.need_for_attention for s in teacher_assignments[t]),
                t.priority
            ))

            is_assigned = False
            for teacher in available_teachers:
                current_load = sum(s.need_for_attention for s in teacher_assignments[teacher])
                if current_load + student.need_for_attention <= teacher.maximum_attention:
                    teacher_assignments[teacher].append(student)
                    is_assigned = True
                    logger.debug(f"Студент {student.name} назначен преподавателю {teacher.name}")
                    break

            if not is_assigned:
                unassigned_students.append(student)
                logger.warning(f"Не удалось назначить студента {student.name}")

        success = len(unassigned_students) == 0

        if success:
            logger.info("Распределение успешно завершено!")
        else:
            logger.warning(f"Не удалось распределить {len(unassigned_students)} студентов")

        return (success, teacher_assignments)

    # НОВЫЙ МЕТОД: Получение работающих преподавателей (тех, кому назначены студенты)
    @staticmethod
    def get_working_teachers(teachers: List[Teacher], students: List[Student]) -> List[Teacher]:
        """
        Возвращает список преподавателей, которым назначены студенты

        Args:
            teachers: список всех преподавателей
            students: список студентов

        Returns:
            List[Teacher]: список работающих преподавателей
        """
        success, allocation = School.generate_teacher_student_allocation(teachers, students)

        if not success:
            logger.warning("Не удалось полностью распределить студентов")

        # Возвращаем только тех преподавателей, у кого есть студенты
        working_teachers = [teacher for teacher, assigned_students in allocation.items()
                            if assigned_students]

        logger.info(f"Работающих преподавателей: {len(working_teachers)}")
        return working_teachers

    @staticmethod
    def check_allocation_for_time_slots(students: List['Student'], teachers: List['Teacher'],
                                        start_time: time, end_time: time,
                                        interval_minutes: int = 30) -> Dict[time, bool]:
        """
        Проверяет возможность распределения для временных промежутков в течение дня
        """
        time_slots = {}
        current_time = start_time

        # Создаем временные промежутки
        while current_time <= end_time:
            # Проверяем распределение для текущего времени
            can_allocate = School.check_teachers_combo_per_minute(students, teachers, current_time)
            time_slots[current_time] = can_allocate

            # Добавляем интервал к текущему времени
            current_time = School.add_minutes_to_time(current_time, interval_minutes)

        return time_slots

    @staticmethod
    def add_minutes_to_time(time_obj: time, minutes: int) -> time:
        """
        Добавляет минуты к объекту time
        """
        from datetime import datetime
        dummy_date = datetime(2023, 1, 1)
        combined_datetime = datetime.combine(dummy_date, time_obj)
        new_datetime = combined_datetime + timedelta(minutes=minutes)
        return new_datetime.time()

    @staticmethod
    def print_allocation_report(time_slots: Dict[time, bool]):
        """
        Выводит красивый отчет о распределении по времени
        """
        print("Отчет о возможности распределения:")
        print("=" * 40)
        print("Время\t\tСтатус")
        print("-" * 40)

        for time_slot, can_allocate in time_slots.items():
            status = "✅ Можно" if can_allocate else "❌ Нельзя"
            print(f"{time_slot.strftime('%H:%M')}\t\t{status}")

    # НОВЫЙ МЕТОД: Печать детального отчета о распределении
    @staticmethod
    def print_detailed_allocation_report(allocation: Dict[Teacher, List[Student]]):
        """
        Выводит детальный отчет о распределении студентов по преподавателям
        """
        print("\n" + "=" * 60)
        print("ДЕТАЛЬНОЕ РАСПРЕДЕЛЕНИЕ СТУДЕНТОВ ПО ПРЕПОДАВАТЕЛЯМ")
        print("=" * 60)

        total_assigned = 0
        for teacher, students in allocation.items():
            if students:
                total_assigned += len(students)
                load = sum(s.need_for_attention for s in students)
                print(f"\nПреподаватель: {teacher.name}")
                print(f"Предметы: {teacher.subjects_id}")
                print(f"Нагрузка: {load}/{teacher.maximum_attention}")
                print(f"Студенты ({len(students)}):")
                for student in students:
                    print(f"  - {student.name} (предмет: {student.subject_id}, внимание: {student.need_for_attention})")

        print(f"\nИтого распределено: {total_assigned} студентов")