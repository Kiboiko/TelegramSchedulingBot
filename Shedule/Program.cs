//using System;
//using System.Collections.Generic;
//using System.Security.Cryptography.X509Certificates;

//namespace Shedule
//{
//    class Program
//    {
//        static void Main()
//        {
//            var Stepan = new Teacher("Stepan", "14:00", "20:00",
//                new List<Lessons> { Lessons.Math, Lessons.Informatic }, 1);
//            Console.WriteLine(Stepan.ToString());

//            var Kirill = new Teacher("Kirill", "15:00", "19:00",
//                new List<Lessons> { Lessons.Math, Lessons.Informatic }, 1);
//            Console.WriteLine(Kirill.ToString());
//            var Alexander = new Teacher("Alexander", "12:00", "21:00",
//                new List<Lessons> { Lessons.Math, Lessons.Informatic, Lessons.Physic }, 10);
//            Console.WriteLine(Alexander.ToString());

//            var stud1 = new Student("Veronica", "18:00", "20:00", Lessons.Math);
//            var stud2 = new Student("Roman", "16:00", "18:00", Lessons.Informatic);
//            var stud3 = new Student("Nikita", "17:00", "20:00", Lessons.Math);
//            var stud4 = new Student("Arthur", "14:00", "17:00", Lessons.Physic);
//            Console.WriteLine($"{stud1.ToString()}\n" +
//                $"{stud2.ToString()}\n" +
//                $"{stud3.ToString()}\n" +
//                $"{stud4.ToString()}\n");



//            var TeachList = new List<Teacher> { Stepan, Kirill, Alexander };
//            var studList = new List<Student> { stud1, stud2, stud3, stud4 };
//            mainMethod.SearchForTeachers(TeachList, studList);

//            //var parser = new ExcelParser();
//            //var studentsFromExcel = parser.ParseStudents("example.xlsx");

//            //// Вывод студентов из Excel
//            //Console.WriteLine("\nСтуденты из Excel:");
//            //foreach (var student in studentsFromExcel)
//            //{
//            //    Console.WriteLine(student.ToString());
//            //    Console.WriteLine("------------------");
//            //}
//        }



//    }
//}

//using System;
//using System.Collections.Generic;
//namespace Shedule
//{
//    class Program
//    {
//        static void Main()
//        {
//            var stud1 = new Student("Veronica", "18:00", "20:00", 1);
//            var stud2 = new Student("Roman", "16:00", "18:00", 3);
//            var stud3 = new Student("Nikita", "17:00", "20:00", 2);
//            var stud4 = new Student("Arthur", "14:00", "17:00", 2);
//            var stud5 = new Student("stud5", "14:00", "17:00", 2);
//            var stud6 = new Student("stud6", "14:00", "17:00", 2);
//            var stud7 = new Student("stud7", "12:00", "17:00", 2);

//            var Stepan = new Teacher("Stepan", "14:00", "20:00",
//                new List<int> { 1, 2, 3 }, 1);

//            var Kirill = new Teacher("Kirill", "15:00", "19:00",
//                new List<int> { 1, 3 }, 1);

//            var Alexander = new Teacher("Alexander", "12:00", "21:00",
//                new List<int> { 1, 2, 3 }, 10);


//            var teacherCombinations = mainMethod.GetTeacherComboForTheDay(
//                new List<Student> { stud1,stud2, stud3, stud4, stud5, stud6, stud7},
//                new List<Teacher> { Stepan,Kirill,Alexander}
//            );

//            Console.WriteLine("\n=== Результат подбора комбинаций на день ===");
//            if (teacherCombinations.Count == 0)
//            {
//                Console.WriteLine("Нет подходящих комбинаций преподавателей!");
//            }
//            else
//            {
//                foreach (var combo in teacherCombinations)
//                {
//                    /*Console.WriteLine($"Комбинация: {string.Join(", ", combo.Select(t => t.Name))}");
//                    Console.WriteLine($"Сумма приоритетов: {combo.Sum(t => t.Priority)}");
//                    Console.WriteLine($"Предметы: {string.Join(", ", combo.SelectMany(t => t.Subjects).Distinct())}");*/

//                    //bool worksAllDay = mainMethod.CheckTeachersComboForTheDay(students, combo);
//                    //Console.WriteLine($"Работает весь день: {(worksAllDay ? "Да" : "Нет")}\n");
//                    Console.WriteLine(String.Join(' ', combo.Select(x => x.Name)));
//                }
//            }

//            Console.ReadLine();
//        }
//    }
//}
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
            // Объявляем переменные в начале метода
            List<Student> students = null;
            List<Teacher> teachers = null;
            List<List<Teacher>> teacherCombinations = null;

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
                string spreadsheetId = "1_atz0H3GEjjGE6nSRuzgZklAqqZOSe2Vu-w26N7bRoc";

                // 3. Инициализация загрузчика Google Sheets
                var loader = new GoogleSheetsDataLoader(credentialsPath, spreadsheetId);

                // 4. Загрузка данных
                (teachers, students) = loader.LoadData();
                Console.WriteLine($"Успешно загружено:\n- Преподавателей: {teachers.Count}\n- Студентов: {students.Count}");

                // 5. Генерация комбинаций преподавателей
                teacherCombinations = mainMethod.GetTeacherComboForTheDay(students, teachers);
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

                Console.WriteLine($"\nРасписание успешно сохранено в Google Таблицу:\nhttps://docs.google.com/spreadsheets/d/{spreadsheetId}/edit");
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