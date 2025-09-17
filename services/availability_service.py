import logging
from datetime import datetime, time, date
from typing import Dict, List
from shedule_app.GoogleParser import GoogleSheetsDataLoader
from shedule_app.HelperMethods import School
from shedule_app.models import Student, Teacher
from utils import _create_empty_time_slots

logger = logging.getLogger(__name__)


def get_subject_distribution_by_time(loader, target_date: str, condition_check: bool = True) -> Dict[time, Dict]:
    """Получает распределение тем занятий по получасовым интервалам"""
    student_sheet = loader._get_sheet_data("Ученики бот")
    if not student_sheet:
        logger.error("Лист 'Ученики' не найден")
        return _create_empty_time_slots()

    date_columns = loader._find_date_columns(student_sheet, target_date)
    if date_columns == (-1, -1):
        logger.error(f"Дата {target_date} не найдена в листе учеников")
        return _create_empty_time_slots()

    start_col, end_col = date_columns
    loader._load_study_plan_cache()
    time_slots = _create_empty_time_slots()

    for row in student_sheet[1:]:
        if not row or len(row) <= max(start_col, end_col):
            continue

        name = str(row[1]).strip() if len(row) > 1 else ""
        if not name:
            continue

        start_time_str = str(row[start_col]).strip() if len(row) > start_col and row[start_col] else ""
        end_time_str = str(row[end_col]).strip() if len(row) > end_col and row[end_col] else ""

        if not start_time_str or not end_time_str:
            continue

        lesson_number = loader._calculate_lesson_number_for_student(row, start_col)
        topic = None

        if name in loader._study_plan_cache:
            student_plan = loader._study_plan_cache[name]
            topic = student_plan.get(lesson_number, "Неизвестная тема")
        else:
            if len(row) > 2 and row[2]:
                subject_id = str(row[2]).strip()
                topic = f"P{subject_id}"
            else:
                topic = "Тема не определена"

        try:
            start_time_parts = start_time_str.split(':')
            end_time_parts = end_time_str.split(':')

            if len(start_time_parts) >= 2 and len(end_time_parts) >= 2:
                start_hour = int(start_time_parts[0])
                start_minute = int(start_time_parts[1])
                end_hour = int(end_time_parts[0])
                end_minute = int(end_time_parts[1])

                lesson_start = time(start_hour, start_minute)
                lesson_end = time(end_hour, end_minute)

                current_interval = time(9, 0)
                while current_interval <= time(20, 0):
                    interval_end = _add_minutes_to_time(current_interval, 30)
                    if (current_interval >= lesson_start and interval_end <= lesson_end):
                        if topic not in time_slots[current_interval]['distribution']:
                            time_slots[current_interval]['distribution'][topic] = 0
                        time_slots[current_interval]['distribution'][topic] += 1

                    current_interval = interval_end

        except (ValueError, IndexError) as e:
            logger.warning(f"Ошибка парсинга времени для студента {name}: {e}")
            continue

    for time_slot, data in time_slots.items():
        topics_dict = data['distribution']
        p1_count = topics_dict.get("1", 0)
        p2_count = topics_dict.get("2", 0)
        p3_count = topics_dict.get("3", 0)
        p4_count = topics_dict.get("4", 0)

        data['condition_result'] = (p3_count < 5 and
                                    p1_count + p2_count + p3_count + p4_count < 25)

    return time_slots


def check_student_availability_for_slots(
        student: Student,
        all_students: List[Student],
        teachers: List[Teacher],
        target_date: date,
        start_time: time,
        end_time: time,
        interval_minutes: int = 30
) -> Dict[time, bool]:
    result = {}
    current_time = start_time

    logger.info(f"=== ДЕТАЛЬНАЯ ПРОВЕРКА ДОСТУПНОСТИ С generate_teacher_student_allocation ===")
    logger.info(f"Студент: {student.name}, предмет: {student.subject_id}, внимание: {student.need_for_attention}")

    while current_time <= end_time:
        active_students = [
            s for s in all_students
            if (s.start_of_studying_time <= current_time <= s.end_of_studying_time)
        ]

        active_teachers = [
            t for t in teachers
            if t.start_of_studying_time <= current_time <= t.end_of_studying_time
        ]

        can_allocate = False

        if not active_teachers:
            logger.info(f"Время {current_time}: нет активных преподавателей")
        else:
            logger.info(f"Время {current_time}: активных преподавателей - {len(active_teachers)}")
            for i, teacher in enumerate(active_teachers):
                logger.info(f"  Преподаватель {i + 1}: {teacher.name}, предметы: {teacher.subjects_id}")

            subject_available = False
            matching_teachers = []

            for teacher in active_teachers:
                teacher_subjects = [str(subj) for subj in teacher.subjects_id]
                if str(student.subject_id) in teacher_subjects:
                    subject_available = True
                    matching_teachers.append(teacher)

            if not subject_available:
                logger.info(f"Время {current_time}: нет преподавателя для предмета {student.subject_id}")
                logger.info(f"  Доступные предметы у преподавателей: {[t.subjects_id for t in active_teachers]}")
            else:
                logger.info(f"Время {current_time}: найдены преподаватели для предмета {student.subject_id}")
                logger.info(f"  Подходящие преподаватели: {[t.name for t in matching_teachers]}")

                try:
                    students_to_check = active_students + [student]
                    logger.info(f"  Всего студентов для распределения: {len(students_to_check)}")

                    success, allocation = School.generate_teacher_student_allocation(
                        active_teachers, students_to_check
                    )

                    if success:
                        can_allocate = True
                        logger.info(f"  КОМБИНАЦИЯ УСПЕШНА")
                    else:
                        logger.info(f"  КОМБИНАЦИЯ НЕВОЗМОЖНА")

                except Exception as e:
                    logger.error(f"Ошибка при проверке комбинации: {e}")
                    can_allocate = False

        result[current_time] = can_allocate
        current_time = School.add_minutes_to_time(current_time, interval_minutes)

    available_count = sum(1 for available in result.values() if available)
    total_count = len(result)
    logger.info(f"ИТОГ: доступно {available_count}/{total_count} слотов")

    return result