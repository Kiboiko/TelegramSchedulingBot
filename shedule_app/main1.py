from models import Person,Teacher,Student
from HelperMethods import School
from datetime import time
from typing import List, Dict
students = [
    Student("РанняяПташка", "06:00", "10:00", 1, 5),
    Student("Утренний", "07:00", "11:00", 2, 4)
]

teachers = [
    Teacher("Дневной", "12:00", "18:00", [1, 2], 1, 10),
    Teacher("Вечерний", "14:00", "20:00", [1, 2], 2, 8)
]

# Проверяем распределение с 9:00 до 20:00 с интервалом 30 минут
start_time = time(9, 0)
end_time = time(20, 0)

allocation_report = School.check_allocation_for_time_slots(students, teachers, start_time, end_time)

# Выводим отчет
School.print_allocation_report(allocation_report)