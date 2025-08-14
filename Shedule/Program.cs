using System;
using System.IO;

namespace Shedule
{
    class Program
    {
        static void Main()
        {
            Console.WriteLine("Программа составления расписания\n");

            DateTime targetDate;
            while (true)
            {
                Console.WriteLine("Введите дату для составления расписания (формат ДД.ММ.ГГГГ):");
                string dateInput = Console.ReadLine();

                if (DateTime.TryParse(dateInput, out targetDate))
                {
                    break;
                }
                Console.WriteLine("Некорректный формат даты. Попробуйте снова.");
            }

            try
            {
                string projectDir = Directory.GetParent(Directory.GetCurrentDirectory()).Parent.Parent.FullName;
                string credentialsPath = Path.Combine(projectDir, "credentials.json");

                if (!File.Exists(credentialsPath))
                {
                    Console.WriteLine($"Файл учетных данных не найден: {credentialsPath}");
                    Console.ReadKey();
                    return;
                }

                string spreadsheetId = "1r1MU8k8umwHx_E4Z-jFHRJ-kdwC43Jw0nwpVeH7T1GU";
                var loader = new GoogleSheetsDataLoader(credentialsPath, spreadsheetId);

                Console.WriteLine($"\nЗагрузка данных на {targetDate:dd.MM.yyyy}...");
                var (teachers, students) = loader.LoadData(targetDate);

                Console.WriteLine($"\nНайдено:\n- Преподавателей: {teachers.Count}\n- Студентов: {students.Count}");

                if (teachers.Count == 0 || students.Count == 0)
                {
                    Console.WriteLine("\nНедостаточно данных для составления расписания.");
                    Console.ReadKey();
                    return;
                }

                Console.WriteLine("\nСоставление расписания...");
                var teacherCombinations = mainMethod.GetTeacherComboForTheDay(students, teachers);
                var scheduleMatrix = mainMethod.GenerateTeacherScheduleMatrix(students, teachers);

                Console.WriteLine("\nЭкспорт в Google Таблицу...");
                loader.ExportScheduleToGoogleSheets(scheduleMatrix, teacherCombinations);

                Console.WriteLine($"\nРасписание на {targetDate:dd.MM.yyyy} успешно создано!");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"\nОшибка: {ex.Message}");
            }
            finally
            {
                Console.WriteLine("\nНажмите любую клавишу для выхода...");
                Console.ReadKey();
            }
        }
    }
}