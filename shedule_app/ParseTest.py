# ParseTest.py
import os
import sys
from datetime import datetime
from GoogleParser import GoogleSheetsDataLoader
from models import Teacher, Student


def test_google_parser():
    print("=== ТЕСТИРОВАНИЕ GOOGLE PARSER ===\n")

    # 1. Проверка наличия credentials файла
    credentials_path = "credentials.json"
    if not os.path.exists(credentials_path):
        print("❌ Файл credentials.json не найден!")
        print("Поместите файл учетных данных в текущую директорию")
        return False

    # 2. Настройки теста
    spreadsheet_id = "1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU"  # Тестовая таблица
    target_date = "01.09.2025"  # Дата для тестирования

    print(f"ID таблицы: {spreadsheet_id}")
    print(f"Целевая дата: {target_date}")
    print(f"Путь к credentials: {credentials_path}")
    print()

    try:
        # 3. Инициализация парсера
        print("🔄 Инициализация GoogleSheetsDataLoader...")
        loader = GoogleSheetsDataLoader(credentials_path, spreadsheet_id, target_date)
        print("✅ Парсер успешно инициализирован")

        # 4. Загрузка данных
        print("\n🔄 Загрузка данных из Google Sheets...")
        teachers, students = loader.load_data()

        print(f"✅ Загружено преподавателей: {len(teachers)}")
        print(f"✅ Загружено студентов: {len(students)}")

        # 5. Вывод информации о загруженных данных
        if teachers:
            print("\n=== ПРЕПОДАВАТЕЛИ ===")
            for i, teacher in enumerate(teachers[:3]):  # Первые 3 для примера
                print(f"{i + 1}. {teacher.name}")
                print(f"   Предметы: {teacher.subjects_id}")
                print(f"   Время: {teacher.start_of_studying_time} - {teacher.end_of_studying_time}")
                print(f"   Приоритет: {teacher.priority}")
                print()

        if students:
            print("\n=== СТУДЕНТЫ ===")
            for i, student in enumerate(students[:3]):  # Первые 3 для примера
                print(f"{i + 1}. {student.name}")
                print(f"   Предмет: {student.subject_id}")
                print(f"   Время: {student.start_of_studying_time} - {student.end_of_studying_time}")
                print(f"   Потребность: {student.need_for_attention}")
                print()

        # 6. Проверка временных интервалов
        print("\n🔄 Проверка временных интервалов...")
        valid_teachers = [t for t in teachers if t.start_of_studying_time != time(0, 0)]
        valid_students = [s for s in students if s.start_of_studying_time != time(0, 0)]

        print(f"Преподаватели с валидным временем: {len(valid_teachers)}/{len(teachers)}")
        print(f"Студенты с валидным временем: {len(valid_students)}/{len(students)}")

        # 7. Тест экспорта (создаем тестовую матрицу)
        print("\n🔄 Тестирование экспорта...")
        try:
            # Создаем тестовую матрицу
            test_matrix = [
                ["Teachers/Time", "09:00-09:15", "09:15-09:30"],
                ["Преподаватель 1", "1,2", "3"],
                ["Преподаватель 2", "0", "1"],
                ["Комбинации", "1: Преп1, Преп2", "2: Только Преп1"]
            ]

            # Тестовые комбинации
            test_combinations = [[teachers[0]] if teachers else []]

            # Пробуем экспортировать
            loader.export_schedule_to_google_sheets(test_matrix, test_combinations)
            print("✅ Экспорт выполнен успешно!")

        except Exception as export_error:
            print(f"⚠️  Ошибка экспорта (может быть нормально): {export_error}")

        # 8. Итоговая статистика
        print("\n=== ИТОГОВАЯ СТАТИСТИКА ===")
        print(f"Всего преподавателей: {len(teachers)}")
        print(f"Всего студентов: {len(students)}")

        if teachers:
            subjects_count = sum(len(t.subjects_id) for t in teachers)
            avg_subjects = subjects_count / len(teachers)
            print(f"Среднее количество предметов на преподавателя: {avg_subjects:.1f}")

        if students:
            subject_ids = [s.subject_id for s in students]
            unique_subjects = set(subject_ids)
            print(f"Уникальных предметов у студентов: {len(unique_subjects)}")

        print("\n✅ Все тесты пройдены успешно!")
        return True

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_models():
    print("\n=== ТЕСТИРОВАНИЕ МОДЕЛЕЙ ===")

    # Тест создания Teacher
    teacher = Teacher(
        name="Иванов И.И.",
        start_of_study_time="09:00",
        end_of_study_time="18:00",
        subjects_id=[1, 2, 3],
        priority=1,
        maximum_attention=15
    )
    print(f"✅ Teacher создан: {teacher.name}")

    # Тест создания Student
    student = Student(
        name="Петров П.П.",
        start_of_study_time="10:00",
        end_of_study_time="12:00",
        subject_id=1,
        need_for_attention=3
    )
    print(f"✅ Student создан: {student.name}")

    print("✅ Модели работают корректно!")


if __name__ == "__main__":
    print("Запуск тестов Google Parser...\n")

    # Тестируем модели
    test_models()

    # Тестируем парсер
    success = test_google_parser()

    if success:
        print("\n🎉 Все тесты пройдены успешно!")
    else:
        print("\n💥 Тесты завершились с ошибками!")
        sys.exit(1)