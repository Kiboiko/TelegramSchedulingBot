from datetime import time
from typing import List

class Person:
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str):
        self.name = name
        
        try:
            start_h, start_m = map(int, start_of_study_time.split(':'))
            end_h, end_m = map(int, end_of_study_time.split(':'))
            self.start_of_studying_time = time(start_h, start_m)
            self.end_of_studying_time = time(end_h, end_m)
        except ValueError:
            print("Некорректный формат времени")
            self.start_of_studying_time = time(0, 0)
            self.end_of_studying_time = time(0, 0)
    
    def comparison(self, other) -> bool:
        return self.name == other.name

    def __str__(self):
        return f"Имя: {self.name}\nВремя начала: {self.start_of_studying_time.strftime('%H:%M')}\n" \
               f"Время конца: {self.end_of_studying_time.strftime('%H:%M')}"


class Student(Person):
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str, 
                 subject_id: int, need_for_attention: int):
        super().__init__(name, start_of_study_time, end_of_study_time)
        self.subject_id = subject_id
        self.need_for_attention = need_for_attention
    
    def __str__(self):
        return f"Класс: Ученик\nИмя: {self.name}\n" \
               f"Время начала: {self.start_of_studying_time.strftime('%H:%M')}\n" \
               f"Время конца: {self.end_of_studying_time.strftime('%H:%M')}\n" \
               f"Предмет: {self.subject_id}\n" \
               f"Потребность во внимании: {self.need_for_attention}"


class Teacher(Person):
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str, 
                 subjects_id: List[int], priority: int, maximum_attention: int):
        super().__init__(name, start_of_study_time, end_of_study_time)
        self.subjects_id = subjects_id
        self.priority = priority
        self.maximum_attention = maximum_attention
        self.start_of_study_time = start_of_study_time
        self.end_of_study_time = end_of_study_time
    
    def __str__(self):
        return f"Имя: {self.name}\nКласс: Преподаватель\n" \
               f"Предметы: {', '.join(map(str, self.subjects_id))}\n" \
               f"Приоритет: {self.priority}\n" \
               f"Максимальное внимание: {self.maximum_attention}\n" \
               f"Время начала: {self.start_of_studying_time.strftime('%H:%M')}\n" \
               f"Время конца: {self.end_of_studying_time.strftime('%H:%M')}"