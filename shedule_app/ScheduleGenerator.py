from typing import List, Dict, Any, Tuple
from datetime import time, timedelta
from models import Teacher, Student
from HelperMethods import School
import itertools


class ScheduleGenerator:
    @staticmethod
    def generate_teacher_schedule_matrix(students: List[Student], teachers: List[Teacher]) -> List[List[Any]]:
        start_time = time(9, 0)
        end_time = time(20, 0)

        # Вычисляем общее количество минут и количество 15-минутных интервалов
        total_minutes = (end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)
        time_slots = (total_minutes + 14) // 15  # Округляем вверх

        # Создаем матрицу: строки - преподаватели + комбинации, столбцы - временные слоты
        matrix = [[None] * (time_slots + 1) for _ in range(len(teachers) + 2)]

        # Заполняем заголовки
        matrix[0][0] = "Teachers/Time"
        for i in range(1, time_slots + 1):
            slot_start = ScheduleGenerator.add_minutes_to_time(start_time, (i - 1) * 15)
            slot_end = ScheduleGenerator.add_minutes_to_time(slot_start, 15)
            matrix[0][i] = f"{slot_start.strftime('%H:%M')}-{slot_end.strftime('%H:%M')}"

        # Заполняем имена преподавателей
        for i, teacher in enumerate(teachers):
            matrix[i + 1][0] = teacher.name
        matrix[len(teachers) + 1][0] = "Комбинации"

        # Обрабатываем каждый тайм-слот
        for slot in range(1, time_slots + 1):
            slot_start = ScheduleGenerator.add_minutes_to_time(start_time, (slot - 1) * 15)
            slot_end = ScheduleGenerator.add_minutes_to_time(slot_start, 15)

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

            # Генерируем все возможные комбинации активных преподавателей
            all_combinations = ScheduleGenerator.get_all_teacher_combinations(active_teachers)

            # Находим валидные комбинации
            valid_combinations = []
            for combo in all_combinations:
                if School.check_teacher_student_allocation(combo, active_students):
                    valid_combinations.append(combo)

            # Сортируем по сумме приоритетов (по убыванию)
            valid_combinations.sort(
                key=lambda x: sum(t.priority for t in x),
                reverse=True
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
    def get_all_teacher_combinations(teachers: List[Teacher]) -> List[List[Teacher]]:
        """Генерирует все возможные комбинации преподавателей"""
        combinations = []
        for r in range(1, len(teachers) + 1):
            for combo in itertools.combinations(teachers, r):
                combinations.append(list(combo))
        return combinations

    @staticmethod
    def add_minutes_to_time(time_obj: time, minutes: int) -> time:
        """Добавляет минуты к объекту time"""
        from datetime import datetime, timedelta
        dummy_date = datetime(2023, 1, 1)
        combined_datetime = datetime.combine(dummy_date, time_obj)
        new_datetime = combined_datetime + timedelta(minutes=minutes)
        return new_datetime.time()

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