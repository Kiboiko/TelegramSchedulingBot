from dataclasses import dataclass, field
from datetime import time
from typing import List

@dataclass
class Person:
    name: str
    start_of_studying_time: time
    end_of_studying_time: time
    
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str):
        self.name = name
        try:
            self.start_of_studying_time = time.fromisoformat(start_of_study_time)
            self.end_of_studying_time = time.fromisoformat(end_of_study_time)
        except ValueError:
            print("Некорректный формат времени")
            raise
    
    def comparison(self, other: 'Person') -> bool:
        return self.name == other.name

@dataclass
class Teacher(Person):
    subjects_id: List[int] = field(default_factory=list)
    priority: int = 1
    maximum_attention: int = 15
    
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str, 
                 subjects: List[int], priority: int, maximum_attention: int):
        super().__init__(name, start_of_study_time, end_of_study_time)
        self.subjects_id = subjects
        self.priority = priority
        self.maximum_attention = maximum_attention
    
    def __str__(self) -> str:
        return (f"Имя: {self.name}\nКласс: Преподаватель\n"
                f"Предметы: {','.join(map(str, self.subjects_id))}\nПриоритет: {self.priority}\n"
                f"Время начала: {self.start_of_studying_time.strftime('%H:%M')}\n"
                f"Время конца: {self.end_of_studying_time.strftime('%H:%M')}")

@dataclass
class Student(Person):
    subject_id: int
    need_for_attention: int = 1
    
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str, 
                 subject_id: int, need_for_attention: int):
        super().__init__(name, start_of_study_time, end_of_study_time)
        self.subject_id = subject_id
        self.need_for_attention = need_for_attention
    
    def __str__(self) -> str:
        return (f"Класс: Ученик\nИмя: {self.name}\n"
                f"Время начала: {self.start_of_studying_time.strftime('%H:%M')}\n"
                f"Время конца: {self.end_of_studying_time.strftime('%H:%M')}\n"
                f"Предмет: {self.subject_id}\n"
                f"Потребность во внимании: {self.need_for_attention}")