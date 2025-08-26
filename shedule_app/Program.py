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

        # Генерируем расписание
        print("\nГенерация расписания...")
        schedule_matrix = ScheduleGenerator.generate_teacher_schedule_matrix(students, teachers)

        # Выводим расписание в консоль
        ScheduleGenerator.print_schedule_matrix(schedule_matrix, teachers)

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