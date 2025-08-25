from typing import List, Dict, Tuple
from datetime import time, timedelta
from models import Teacher, Student
from helper_methods import get_all_teacher_combinations

class School:
    @staticmethod
    def check_teacher_student_allocation(teachers: List[Teacher], students: List[Student]) -> bool:
        if not teachers or not students:
            return False
            
        teacher_assignments: Dict[Teacher, List[Student]] = {teacher: [] for teacher in teachers}
        unassigned_students: List[Student] = []
        
        # Вычисляем редкость предметов
        subject_rarity = {}
        for student in students:
            if student.subject_id not in subject_rarity:
                subject_rarity[student.subject_id] = sum(1 for t in teachers 
                                                       if student.subject_id in t.subjects_id)
        
        # Сортируем студентов: сначала редкие предметы, потом по потребности во внимании
        sorted_students = sorted(students, 
                               key=lambda s: (subject_rarity[s.subject_id], -s.need_for_attention))
        
        for student in sorted_students:
            available_teachers = [
                t for t in teachers 
                if student.subject_id in t.subjects_id
            ]
            
            # Сортируем по нагрузке и приоритету
            available_teachers.sort(key=lambda t: (
                sum(s.need_for_attention for s in teacher_assignments[t]),
                t.priority
            ))
            
            assigned = False
            for teacher in available_teachers:
                current_load = sum(s.need_for_attention for s in teacher_assignments[teacher])
                if current_load + student.need_for_attention <= teacher.maximum_attention:
                    teacher_assignments[teacher].append(student)
                    assigned = True
                    break
            
            if not assigned:
                unassigned_students.append(student)
        
        return len(unassigned_students) == 0

class SearchMethod:
    @staticmethod
    def get_active_teachers_at_minute(teachers: List[Teacher], current_time: time) -> List[Teacher]:
        return [
            teacher for teacher in teachers
            if teacher.start_of_studying_time <= current_time <= teacher.end_of_studying_time
        ]
    
    @staticmethod
    def get_active_students_at_minute(students: List[Student], current_time: time) -> List[Student]:
        return [
            student for student in students
            if student.start_of_studying_time <= current_time <= student.end_of_studying_time
        ]
    
    @staticmethod
    def check_teachers_combo_per_minute(students: List[Student], teachers: List[Teacher], 
                                      current_time: time) -> bool:
        active_teachers = SearchMethod.get_active_teachers_at_minute(teachers, current_time)
        active_students = SearchMethod.get_active_students_at_minute(students, current_time)
        return School.check_teacher_student_allocation(active_teachers, active_students)
    
    @staticmethod
    def check_teachers_combo_for_the_day(students: List[Student], teachers: List[Teacher]) -> bool:
        if not students:
            return True
            
        start_time = time(9, 0)
        current_time = start_time
        
        for minute in range(660):  # 11 часов * 60 минут = 660 минут
            if not SearchMethod.check_teachers_combo_per_minute(students, teachers, current_time):
                return False
            
            # Добавляем 1 минуту
            current_time = SearchMethod.add_minutes_to_time(current_time, 1)
        
        return True
    
    @staticmethod
    def add_minutes_to_time(t: time, minutes: int) -> time:
        full_datetime = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second) + timedelta(minutes=minutes)
        total_seconds = int(full_datetime.total_seconds())
        return time(total_seconds // 3600, (total_seconds % 3600) // 60)
    
    @staticmethod
    def get_teacher_combo_for_the_day(students: List[Student], teachers: List[Teacher]) -> List[List[Teacher]]:
        all_combinations = get_all_teacher_combinations(teachers)
        all_combinations.sort(key=len)  # Сортируем по количеству преподавателей
        
        result: List[List[Teacher]] = []
        
        for combo in all_combinations:
            if (SearchMethod.check_teachers_combo_for_the_day(students, combo) and 
                SearchMethod.check_for_entry_interruption(result, combo)):
                result.append(combo)
        
        # Сортируем по сумме приоритетов
        result.sort(key=lambda x: sum(teacher.priority for teacher in x))
        return result
    
    @staticmethod
    def check_for_entry_interruption(result: List[List[Teacher]], combo: List[Teacher]) -> bool:
        if not result:
            return True
            
        for item in result:
            if SearchMethod.finding_an_occurrence_of_combination(combo, item):
                return False
        return True
    
    @staticmethod
    def finding_an_occurrence_of_combination(item: List[Teacher], combo: List[Teacher]) -> bool:
        item_names = {teacher.name for teacher in item}
        combo_names = {teacher.name for teacher in combo}
        return combo_names.issubset(item_names)