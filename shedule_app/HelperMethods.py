from datetime import time, timedelta
from typing import List, Dict
from models import Person,Teacher,Student

class School:
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
        teacher_assignments: Dict[Teacher, List[Student]] = {}
        unassigned_students = []

        # Инициализируем словарь назначений для каждого преподавателя
        for teacher in teachers:
            teacher_assignments[teacher] = []

        # Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
        subject_rarity = {}
        for student in students:
            subject_id = student.subject_id
            if subject_id not in subject_rarity:
                # Считаем количество преподавателей, которые могут вести этот предмет
                count = sum(1 for teacher in teachers if subject_id in teacher.subjects_id)
                subject_rarity[subject_id] = count

        # Сортируем студентов:
        # 1. Сначала студенты с редкими предметами (меньше преподавателей могут вести)
        # 2. Затем студенты с большей потребностью во внимании
        def sort_key(student):
            return (subject_rarity[student.subject_id], -student.need_for_attention)
        
        sorted_students = sorted(students, key=sort_key)

        for student in sorted_students:
            # Доступные преподаватели для этого предмета
            available_teachers = [
                teacher for teacher in teachers 
                if student.subject_id in teacher.subjects_id
            ]

            # Сортируем доступных преподавателей по:
            # 1. Текущей нагрузке (сумма NeedForAttention)
            # 2. Приоритету преподавателя
            def teacher_sort_key(teacher):
                current_load = sum(s.need_for_attention for s in teacher_assignments[teacher])
                return (current_load, teacher.priority)
            
            available_teachers.sort(key=teacher_sort_key)

            is_assigned = False
            for teacher in available_teachers:
                current_load = sum(s.need_for_attention for s in teacher_assignments[teacher])
                if current_load + student.need_for_attention <= teacher.maximum_attention:
                    teacher_assignments[teacher].append(student)
                    is_assigned = True
                    break

            if not is_assigned:
                unassigned_students.append(student)

        return len(unassigned_students) == 0
    
    @staticmethod
    def check_allocation_for_time_slots(students: List['Student'], teachers: List['Teacher'], 
                                      start_time: time, end_time: time, 
                                      interval_minutes: int = 30) -> Dict[time, bool]:
        """
        Проверяет возможность распределения для временных промежутков в течение дня
        
        Args:
            students: список студентов
            teachers: список преподавателей
            start_time: время начала дня
            end_time: время окончания дня
            interval_minutes: интервал между проверками в минутах (по умолчанию 30)
        
        Returns:
            Словарь с временем как ключ и boolean значением (можно распределить или нет)
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
        # Преобразуем time в datetime для удобства вычислений
        from datetime import datetime
        dummy_date = datetime(2023, 1, 1)  # произвольная дата
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