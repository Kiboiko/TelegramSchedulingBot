using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;

namespace Shedule
{
    class Program
    {
        static void Main()
        {
            Console.WriteLine("Введите дату для составления расписания (в формате ДД.ММ.ГГГГ):");
            string targetDate = Console.ReadLine();

            if (!DateTime.TryParse(targetDate, out _))
            {
                Console.WriteLine("Неверный формат даты!");
                Console.ReadKey();
                return;
            }

            try
            {
                // 1. Настройка пути к credentials.json
                string projectDir = Directory.GetParent(Directory.GetCurrentDirectory()).Parent.Parent.FullName;
                string credentialsPath = Path.Combine(projectDir, "credentials.json");

                if (!File.Exists(credentialsPath))
                {
                    Console.WriteLine($"Поместите файл учетных данных 'credentials.json' в папку:\n{projectDir}");
                    Console.ReadKey();
                    return;
                }

                // 2. ID вашей Google Таблицы
                string spreadsheetId = "1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU";

                // 3. Инициализация загрузчика Google Sheets
                var loader = new GoogleSheetsDataLoader(credentialsPath, spreadsheetId, targetDate);

                // 4. Загрузка данных
                var (teachers, students) = loader.LoadData();
                Console.WriteLine($"Успешно загружено:\n- Преподавателей: {teachers.Count}\n- Студентов: {students.Count}");

                // 5. Генерация комбинаций преподавателей
                var teacherCombinations = mainMethod.GetTeacherComboForTheDay(students, teachers);
                if (teacherCombinations.Count == 0)
                {
                    Console.WriteLine("Не найдено подходящих комбинаций преподавателей!");
                    return;
                }

                // 6. Генерация и экспорт расписания
                var scheduleMatrix = mainMethod.GenerateTeacherScheduleMatrix(students, teachers);

                // 7. Вывод в консоль для проверки
                mainMethod.PrintTeacherScheduleMatrix(scheduleMatrix, teacherCombinations);

                // 8. Экспорт в Google Таблицу
                loader.ExportScheduleToGoogleSheets(scheduleMatrix, teacherCombinations);

                Console.WriteLine($"\nРасписание на {targetDate} успешно сохранено в Google Таблицу:");
                Console.WriteLine($"https://docs.google.com/spreadsheets/d/{spreadsheetId}/edit");
            }
            catch (Google.GoogleApiException ex)
            {
                Console.WriteLine($"Ошибка Google API: {ex.Message}");
                if (ex.Message.Contains("does not match value's range"))
                {
                    Console.WriteLine("Проверьте соответствие размеров матрицы расписания");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Критическая ошибка: {ex.Message}");
            }
            finally
            {
                Console.WriteLine("\nНажмите любую клавишу для выхода...");
                Console.ReadKey();
            }
        }
    }
}