# models.py - исправляем имена атрибутов и типы времени
from datetime import time
from typing import List


class Person:
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str):
        self.name = name
        self.start_of_study_time_str = start_of_study_time  # Сохраняем оригинальную строку
        self.end_of_study_time_str = end_of_study_time  # Сохраняем оригинальную строку

        # Преобразуем строки времени в объекты time
        try:
            self.start_of_studying_time = self._parse_time(start_of_study_time)
            self.end_of_studying_time = self._parse_time(end_of_study_time)
        except ValueError:
            print(f"Некорректный формат времени: {start_of_study_time} или {end_of_study_time}")
            self.start_of_studying_time = time(0, 0)
            self.end_of_studying_time = time(0, 0)

    def _parse_time(self, time_str: str) -> time:
        """Парсит строку времени в объект time"""
        time_str = time_str.strip()

        # Если время содержит точку вместо двоеточия
        if '.' in time_str and ':' not in time_str:
            time_str = time_str.replace('.', ':')

        # Разбиваем на части
        if ':' in time_str:
            parts = time_str.split(':')
            if len(parts) >= 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                return time(hours, minutes)

        # Если время в формате "HHMM"
        elif len(time_str) == 4 and time_str.isdigit():
            hours = int(time_str[:2])
            minutes = int(time_str[2:])
            return time(hours, minutes)

        # Если не удалось распарсить, возвращаем время по умолчанию
        return time(0, 0)

    def comparison(self, other) -> bool:
        return self.name == other.name

    def __str__(self):
        return f"Имя: {self.name}\nВремя начала: {self.start_of_studying_time.strftime('%H:%M')}\n" \
               f"Время конца: {self.end_of_studying_time.strftime('%H:%M')}"


class Teacher(Person):
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str,
                 subjects_id: List[int], priority: int = 1, maximum_attention: int = 15):
        super().__init__(name, start_of_study_time, end_of_study_time)
        self.subjects_id = subjects_id
        self.priority = priority
        self.maximum_attention = maximum_attention
        self.current_attention_used = 0  # Для отслеживания текущей нагрузки


class Student(Person):
    def __init__(self, name: str, start_of_study_time: str, end_of_study_time: str,
                 subject_id: int, need_for_attention: int):
        super().__init__(name, start_of_study_time, end_of_study_time)
        self.subject_id = subject_id
        self.need_for_attention = need_for_attention