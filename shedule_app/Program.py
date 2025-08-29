# # Program.py
# import os
# from datetime import datetime
# from typing import List, Tuple
# from GoogleParser import GoogleSheetsDataLoader
# from models import Teacher, Student
# from HelperMethods import School, CSAllocationMethods  # Импортируем новые методы
# from datetime import time
#
#
# def main():
#     print("Введите дату для составления расписания (в формате ДД.ММ.ГГГГ):")
#     target_date = input().strip()
#
#     try:
#         datetime.strptime(target_date, "%d.%m.%Y")
#     except ValueError:
#         print("Неверный формат даты!")
#         input()
#         return
#
#     try:
#         current_dir = os.path.dirname(os.path.abspath(__file__))
#         credentials_path = os.path.join(current_dir, "credentials.json")
#
#         if not os.path.exists(credentials_path):
#             print(f"Поместите файл учетных данных 'credentials.json' в папку:\n{current_dir}")
#             input()
#             return
#
#         spreadsheet_id = "1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU"
#         loader = GoogleSheetsDataLoader(credentials_path, spreadsheet_id, target_date)
#
#         teachers, students = loader.load_data()
#         print(f"Успешно загружено:\n- Преподавателей: {len(teachers)}\n- Студентов: {len(students)}")
#
#         # После загрузки teachers и students
#         print("\n=== ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ДАННЫХ ===")
#         print("ПРЕПОДАВАТЕЛИ:")
#         for teacher in teachers:
#             print(
#                 f"  {teacher.name}: предметы {teacher.subjects_id}, время {teacher.start_of_studying_time}-{teacher.end_of_studying_time}")
#
#         print("\nСТУДЕНТЫ:")
#         for student in students:
#             print(
#                 f"  {student.name}: предмет {student.subject_id}, потребность {student.need_for_attention}, время {student.start_of_studying_time}-{student.end_of_studying_time}")
#
#         print("\nСУММАРНАЯ ПОТРЕБНОСТЬ:", sum(s.need_for_attention for s in students))
#         print("СУММАРНАЯ ЕМКОСТЬ:", sum(t.maximum_attention for t in teachers))
#
#         if not teachers or not students:
#             print("Не удалось загрузить данные преподавателей или студентов!")
#             return
#
#         # Генерируем расписание с помощью нового CS-стиля методов
#         print("\nГенерация расписания (CS стиль)...")
#         schedule_matrix = CSAllocationMethods.generate_teacher_schedule_matrix_cs_style(students, teachers)
#
#         # Выводим расписание в консоль
#         School.print_schedule_matrix(schedule_matrix, teachers)
#
#         # Экспортируем в Google Sheets
#         print("\nЭкспорт в Google Sheets...")
#         loader.export_schedule_to_google_sheets(schedule_matrix, [])
#         print("✅ Расписание успешно экспортировано!")
#
#     except Exception as ex:
#         print(f"Критическая ошибка: {ex}")
#         import traceback
#         traceback.print_exc()
#     finally:
#         print("\nНажмите любую клавишу для выхода...")
#         input()
#
#
# if __name__ == "__main__":
#     main()
# Program.py
import os
from datetime import datetime
from typing import List, Tuple
from GoogleParser import GoogleSheetsDataLoader
from models import Teacher, Student
from HelperMethods import School
from datetime import time

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

        # Детальная информация о данных
        print("\n=== ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О ДАННЫХ ===")
        print("ПРЕПОДАВАТЕЛИ:")
        for teacher in teachers:
            print(f"  {teacher.name}: предметы {teacher.subjects_id}, емкость {teacher.maximum_attention}, "
                  f"время {teacher.start_of_studying_time.strftime('%H:%M')}-{teacher.end_of_studying_time.strftime('%H:%M')}")

        print("\nСТУДЕНТЫ:")
        for student in students:
            print(f"  {student.name}: предмет {student.subject_id}, потребность {student.need_for_attention}, "
                  f"время {student.start_of_studying_time.strftime('%H:%M')}-{student.end_of_studying_time.strftime('%H:%M')}")

        print("\nСУММАРНАЯ ПОТРЕБНОСТЬ:", sum(s.need_for_attention for s in students))
        print("СУММАРНАЯ ЕМКОСТЬ:", sum(t.maximum_attention for t in teachers))

        if not teachers or not students:
            print("Не удалось загрузить данные преподавателей или студентов!")
            return

        # Генерируем расписание
        print("\nГенерация расписания...")
        schedule_matrix = School.generate_teacher_schedule_matrix(students, teachers)

        # Выводим расписание в консоль
        School.print_schedule_matrix(schedule_matrix, teachers)

        # Экспортируем в Google Sheets
        print("\nЭкспорт в Google Sheets...")
        loader.export_schedule_to_google_sheets(schedule_matrix, [])
        print("✅ Расписание успешно экспортировано!")

    except Exception as ex:
        print(f"Критическая ошибка: {ex}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nНажмите любую клавишу для выхода...")
        input()

if __name__ == "__main__":
    main()