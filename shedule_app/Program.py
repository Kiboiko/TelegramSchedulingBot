import os
from datetime import datetime
from typing import List, Tuple
from GoogleParser import GoogleSheetsDataLoader
from models import Teacher, Student
from HelperMethods import School
from ScheduleGenerator import ScheduleGenerator


def main():
    print("Введите дату для составления расписания (в формате ДД.ММ.ГГГГ):")
    target_date = input().strip()

    try:
        datetime.strptime(target_date, "%d.%m.%Y")
    except ValueError:
        print("Неверный формат даты!")
        input()
        return

    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        credentials_path = os.path.join(current_dir, "credentials.json")

        if not os.path.exists(credentials_path):
            print(f"Поместите файл учетных данных 'credentials.json' в папку:\n{current_dir}")
            input()
            return

        spreadsheet_id = "1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU"
        loader = GoogleSheetsDataLoader(credentials_path, spreadsheet_id, target_date)

        teachers, students = loader.load_data()
        print(f"Успешно загружено:\n- Преподавателей: {len(teachers)}\n- Студентов: {len(students)}")

        if not teachers or not students:
            print("Не удалось загрузить данные преподавателей или студентов!")
            return

        # ПРОВЕРКА И ГЕНЕРАЦИЯ РАСПРЕДЕЛЕНИЯ СТУДЕНТОВ
        print("\n" + "=" * 60)
        print("ПРОВЕРКА И ГЕНЕРАЦИЯ РАСПРЕДЕЛЕНИЯ СТУДЕНТОВ")
        print("=" * 60)

        # Проверяем возможность распределения
        can_allocate = School.check_teacher_student_allocation(teachers, students)

        if not can_allocate:
            print("❌ Невозможно распределить студентов по преподавателям!")
            print("Причины могут быть:")
            print("- Недостаточно общей емкости преподавателей")
            print("- Отсутствуют преподаватели для некоторых предметов")
            print("- Не хватает преподавательских ресурсов")
        else:
            print("✅ Возможность распределения подтверждена!")

            # Генерируем конкретное распределение
            success, allocation = School.generate_teacher_student_allocation(teachers, students)

            if success:
                print("✅ Распределение студентов успешно сгенерировано!")

                # Выводим детальный отчет о распределении
                School.print_detailed_allocation_report(allocation)

                # Получаем только работающих преподавателей
                working_teachers = School.get_working_teachers(teachers, students)
                print(f"\n🎯 Работающих преподавателей: {len(working_teachers)}")

                # Генерируем расписание только для работающих преподавателей
                print("\n" + "=" * 60)
                print("ГЕНЕРАЦИЯ РАСПИСАНИЯ ДЛЯ РАБОТАЮЩИХ ПРЕПОДАВАТЕЛЕЙ")
                print("=" * 60)

                schedule_matrix = ScheduleGenerator.generate_teacher_schedule_matrix(students, working_teachers)

                # Выводим расписание в консоль
                ScheduleGenerator.print_schedule_matrix(schedule_matrix, working_teachers)

                # Экспортируем в Google Sheets
                print("\nЭкспорт в Google Sheets...")
                loader.export_schedule_to_google_sheets(schedule_matrix, [])
                print("✅ Расписание успешно экспортировано!")

            else:
                print("❌ Не удалось распределить всех студентов!")
                print("Возможно, требуется дополнительная оптимизация или больше преподавателей")

        # Дополнительная проверка по временным слотам
        print("\n" + "=" * 60)
        print("ПРОВЕРКА РАСПРЕДЕЛЕНИЯ ПО ВРЕМЕННЫМ СЛОТАМ")
        print("=" * 60)

        # Проверяем распределение для всего дня с интервалом 30 минут
        start_time = datetime.strptime("09:00", "%H:%M").time()
        end_time = datetime.strptime("20:00", "%H:%M").time()

        time_slots = School.check_allocation_for_time_slots(
            students, teachers, start_time, end_time, 30
        )

        School.print_allocation_report(time_slots)

    except Exception as ex:
        print(f"Критическая ошибка: {ex}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nНажмите любую клавишу для выхода...")
        input()


def analyze_data(teachers: List[Teacher], students: List[Student]):
    """Анализирует загруженные данные и выводит статистику"""
    print("\n" + "=" * 60)
    print("АНАЛИЗ ДАННЫХ")
    print("=" * 60)

    # Общая статистика
    total_attention_needed = sum(s.need_for_attention for s in students)
    total_teacher_capacity = sum(t.maximum_attention for t in teachers)

    print(f"Общая потребность студентов: {total_attention_needed}")
    print(f"Общая емкость преподавателей: {total_teacher_capacity}")
    print(f"Баланс: {'✅ Достаточно' if total_attention_needed <= total_teacher_capacity else '❌ Недостаточно'}")

    # Анализ по предметам
    student_subjects = set(s.subject_id for s in students)
    teacher_subjects = set()
    for teacher in teachers:
        teacher_subjects.update(teacher.subjects_id)

    missing_subjects = student_subjects - teacher_subjects
    if missing_subjects:
        print(f"❌ Отсутствуют преподаватели для предметов: {missing_subjects}")
    else:
        print("✅ Все предметы студентов покрыты преподавателями")

    # Анализ по времени
    print(
        f"\nПреподаватели доступны с {min(t.start_of_studying_time for t in teachers)} до {max(t.end_of_studying_time for t in teachers)}")
    print(
        f"Студенты занимаются с {min(s.start_of_studying_time for s in students)} до {max(s.end_of_studying_time for s in students)}")


if __name__ == "__main__":
    main()