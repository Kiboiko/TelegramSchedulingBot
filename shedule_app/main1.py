from models import Person, Teacher, Student
from HelperMethods import School
from datetime import time
from typing import List, Dict
import os
from GoogleParser import GoogleSheetsDataLoader

CREDENTIALS_PATH = r"C:\Users\user\Documents\GitHub\TelegramSchedulingBot\credentials.json"
SPREADSHEET_ID = "1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU"
TARGET_DATE = "02.09.2025"

if not os.path.exists(CREDENTIALS_PATH):
    print("❌ Файл credentials.json не найден!")
    print("Поместите файл учетных данных в текущую директорию")
    exit(1)

# Загрузка данных
loader = GoogleSheetsDataLoader(CREDENTIALS_PATH, SPREADSHEET_ID, TARGET_DATE)
teachers, students = loader.load_data()

print(f"Загружено: {len(teachers)} преподавателей, {len(students)} студентов")

# Вывод подробной информации о преподавателях
print("\n" + "="*80)
print("ПРЕПОДАВАТЕЛИ:")
print("="*80)
for i, teacher in enumerate(teachers, 1):
    print(f"\n{i}. {teacher.name}")
    print(f"   Предметы: {teacher.subjects_id}")
    print(f"   Время работы: {teacher.start_of_studying_time.strftime('%H:%M')} - {teacher.end_of_studying_time.strftime('%H:%M')}")
    print(f"   Приоритет: {teacher.priority}")
    print(f"   Макс. внимание: {teacher.maximum_attention}")

# Вывод подробной информации о студентах
print("\n" + "="*80)
print("СТУДЕНТЫ:")
print("="*80)
for i, student in enumerate(students, 1):
    print(f"\n{i}. {student.name}")
    print(f"   Предмет: {student.subject_id}")
    print(f"   Потребность во внимании: {student.need_for_attention}")
    print(f"   Время занятий: {student.start_of_studying_time.strftime('%H:%M')} - {student.end_of_studying_time.strftime('%H:%M')}")

# Статистика
print("\n" + "="*80)
print("СТАТИСТИКА:")
print("="*80)
print(f"Всего преподавателей: {len(teachers)}")
print(f"Всего студентов: {len(students)}")

# Анализ предметов
subject_stats = {}
for student in students:
    subject_id = student.subject_id
    if subject_id not in subject_stats:
        subject_stats[subject_id] = {'students': 0, 'total_attention': 0}
    subject_stats[subject_id]['students'] += 1
    subject_stats[subject_id]['total_attention'] += student.need_for_attention

print("\nРаспределение по предметам:")
for subject_id, stats in subject_stats.items():
    print(f"  Предмет {subject_id}: {stats['students']} студентов, {stats['total_attention']} единиц внимания")

# Проверка распределения
start_time = time(9, 0)
end_time = time(20, 0)

print("\n" + "="*80)
print("ПРОВЕРКА РАСПРЕДЕЛЕНИЯ:")
print("="*80)

allocation_report = School.check_allocation_for_time_slots(
    students, teachers, start_time, end_time, 30
)

# Выводим отчет
School.print_allocation_report(allocation_report)

# Дополнительный анализ проблемных времен
problem_times = [t for t, can_allocate in allocation_report.items() if not can_allocate]
if problem_times:
    print(f"\n⚠️  Проблемные временные промежутки:")
    for time_slot in problem_times:
        print(f"  - {time_slot.strftime('%H:%M')}")
else:
    print("\n✅ Распределение возможно в течение всего дня!")