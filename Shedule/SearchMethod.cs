using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using DocumentFormat.OpenXml.Vml.Office;

namespace Shedule
{
    public class mainMethod
    {

        public static List<List<Teacher>> GetMinTeachers(List<Teacher> teachers, List<Student> students)
        {
            List<List<Teacher>> res = new List<List<Teacher>>();
            List<List<Teacher>> uniqTeachers = HelperMethods.GetAllTeacherCombinations(teachers);
            int minCount = int.MaxValue;
            foreach(var combo in uniqTeachers)
            {
                if (School.CheckTeacherStudentAllocation(combo, students) && combo.Count != 0)
                {
                    if (combo.Count < minCount)
                    {
                        res.Clear();
                        res.Add(combo);
                        minCount = combo.Count;
                    } else if (combo.Count == minCount)
                    {
                        res.Add(combo);
                    } 
                }
            }
            return res;
        }

        public static List<Teacher> GetActiveTeachersAtMinute(List<Teacher> teachers, TimeOnly time)
        {
            List<Teacher> res = new List<Teacher>();
            foreach (var teacher in teachers)
            {
                if ((time >= teacher.StartOfStudyingTime) & (time <= teacher.EndOfStudyingTime))
                {
                    res.Add(teacher);
                }
            }
            return res;

        }

        public static List<Student> GetActiveStudentsAtMinute(List<Student> students, TimeOnly time)
        {
            List<Student> res = new List<Student>();
            foreach (var student in students)
            {
                if ((time >= student.StartOfStudyingTime) & (time <= student.EndOfStudyingTime))
                {
                    res.Add(student);
                }
            }
            return res;

        }

        public static bool CheckTeachersComboPerMinute(List<Student> students, List<Teacher> teachers, TimeOnly time)
        {
            return School.CheckTeacherStudentAllocation(
                GetActiveTeachersAtMinute(teachers,time), 
                GetActiveStudentsAtMinute(students,time)
                );
        }


        public static bool CheckTeachersComboForTheDay(List<Student> students, List<Teacher> teachers)
        {
            TimeOnly startStudTime = students.Select(x => x.StartOfStudyingTime).ToList().Min();
            TimeOnly currentTime = TimeOnly.FromTimeSpan(TimeSpan.FromHours(9));
            bool t = true;
            for (int i = 0; i < 660; i++)
            {
                currentTime = currentTime.AddMinutes(1);
                if (!CheckTeachersComboPerMinute(students, teachers, currentTime))
                {
                    t = false;
                    break;
                }
            }
            return t;
        }


        public static List<List<Teacher>> GetTeacherComboForTheDay(List<Student> students, List<Teacher> teachers)
        {
            List<List<Teacher>> uniqTeachers = HelperMethods.GetAllTeacherCombinations(teachers).OrderBy(x => x.Count).ToList();
            List<List<Teacher>> res = new List<List<Teacher>>();

            foreach (var combo in uniqTeachers)
            {
                if (CheckTeachersComboForTheDay(students, combo) && CheckForEntryinterruption(res, combo))
                {
                    res.Add(combo);
                }
            }

            return res.OrderBy(x => x.Select(y => y.Priority).Sum()).ToList();
        }
        //public static List<List<Teacher>> GetTeacherComboForTheDay(List<Student> students, List<Teacher> teachers)
        //{
        //    // Получаем все комбинации и сортируем по количеству преподавателей
        //    var uniqTeachers = HelperMethods.GetAllTeacherCombinations(teachers)
        //                                   .OrderBy(x => x.Count)
        //                                   .ToList(); // Явное преобразование в List

        //    List<List<Teacher>> res = new List<List<Teacher>>();

        //    foreach (var combo in uniqTeachers)
        //    {
        //        if (CheckTeachersComboForTheDay(students, combo) &&
        //            CheckForEntryinterruption(res, combo))
        //        {
        //            res.Add(combo);
        //        }
        //    }

        //    // Сортируем по сумме приоритетов и преобразуем в List
        //    return res.OrderBy(x => x.Sum(y => y.Priority))
        //             .ToList(); // Ключевое исправление - добавляем ToList()
        //}

        public static bool CheckForEntryinterruption(List<List<Teacher>> res, List<Teacher> combo)
        {
            if (res.Count == 0)
                return true;
            var t = true;
            foreach (var item in res)
            {
                if (FindingAnOccurrenceOfaCombination(combo, item))
                {
                    t = false;
                    break;
                }
            }
            return t;
        }

        public static bool FindingAnOccurrenceOfaCombination(List<Teacher> item, List<Teacher> combo)
        {
            int c = 0;
            foreach (var teacher in combo)
            {
                if (item.Select(x=>x.Name).ToList().Contains(teacher.Name))
                {
                    c++;
                }
            }
            return ((c == combo.Count()));
        }


        public static object[,] GenerateTeacherScheduleMatrix(List<Student> students, List<Teacher> teachers)
        {
            TimeOnly startTime = new TimeOnly(9, 0);
            TimeOnly endTime = new TimeOnly(20, 0);
            int totalMinutes = (int)(endTime - startTime).TotalMinutes;
            int timeSlots = (int)Math.Ceiling(totalMinutes / 15.0);

            object[,] matrix = new object[teachers.Count + 2, timeSlots + 1];

            // Заполняем заголовки
            matrix[0, 0] = "Teachers/Time";
            for (int i = 1; i <= timeSlots; i++)
            {
                TimeOnly slotStart = startTime.AddMinutes((i - 1) * 15);
                TimeOnly slotEnd = slotStart.AddMinutes(15);
                matrix[0, i] = $"{slotStart:HH:mm}-{slotEnd:HH:mm}";
            }

            // Заполняем имена преподавателей
            for (int i = 0; i < teachers.Count; i++)
            {
                matrix[i + 1, 0] = teachers[i].Name;
            }
            matrix[teachers.Count + 1, 0] = "Комбинации";

            // Обрабатываем каждый тайм-слот независимо
            for (int slot = 1; slot <= timeSlots; slot++)
            {
                TimeOnly slotStart = startTime.AddMinutes((slot - 1) * 15);
                TimeOnly slotEnd = slotStart.AddMinutes(15);

                // 1. Получаем активных участников
                var activeStudents = students
                    .Where(s => s.StartOfStudyingTime < slotEnd &&
                               s.EndOfStudyingTime > slotStart)
                    .ToList();

                var activeTeachers = teachers
                    .Where(t => t.StartOfStudyingTime <= slotStart &&
                                t.EndOfStudyingTime >= slotEnd)
                    .ToList();

                // 2. Если нет студентов - все "0"
                if (activeStudents.Count == 0)
                {
                    for (int t = 0; t < teachers.Count; t++)
                    {
                        matrix[t + 1, slot] = "0";
                    }
                    matrix[teachers.Count + 1, slot] = "-";
                    continue;
                }

                // 3. Генерируем комбинации только для активных преподавателей
                var allCombinations = HelperMethods.GetAllTeacherCombinations(activeTeachers)
                    .Where(c => c.Count > 0)
                    .ToList();

                // 4. Находим валидные комбинации с учетом фильтрации
                var validCombinations = new List<List<Teacher>>();
                foreach (var combo in allCombinations)
                {
                    if (School.CheckTeacherStudentAllocation(combo, activeStudents) &&
                        CheckForEntryinterruption(validCombinations, combo))
                    {
                        validCombinations.Add(combo);
                    }
                }
                //validCombinations = (List<List<Teacher>>)validCombinations.OrderByDescending(x => x.Select(y => y.Priority).Sum());
                validCombinations = validCombinations
    .OrderByDescending(x => x.Sum(y => y.Priority))
    .ToList();

                // 5. Записываем номера комбинаций для преподавателей
                for (int t = 0; t < teachers.Count; t++)
                {
                    var teacher = teachers[t];
                    matrix[t + 1, slot] = "0"; // Значение по умолчанию

                    if (activeTeachers.Contains(teacher))
                    {
                        var teacherCombos = validCombinations
                            .Select((combo, index) => new { combo, index })
                            .Where(x => x.combo.Any(tch => tch.Name == teacher.Name))
                            .Select(x => x.index + 1)
                            .ToList();

                        if (teacherCombos.Count > 0)
                        {
                            matrix[t + 1, slot] = string.Join(",", teacherCombos);
                        }
                    }
                }

                // 6. Записываем состав комбинаций
                matrix[teachers.Count + 1, slot] = validCombinations.Count > 0
                    ? string.Join("; ", validCombinations.Select((c, i) =>
                        $"{i + 1}: {string.Join(", ", c.Select(t => t.Name))}"))
                    : "Нет валидных комбинаций";
            }

            return matrix;
        }

        // Генератор всех возможных комбинаций
        /*private static List<List<Teacher>> GenerateAllCombinations(List<Teacher> teachers)
        {
            var result = new List<List<Teacher>>();
            for (int i = 1; i <= teachers.Count; i++)
            {
                result.AddRange(GetCombinations(teachers, i));
            }
            return result;
        }

        private static IEnumerable<List<Teacher>> GetCombinations(List<Teacher> teachers, int k)
        {
            return k == 0 ? new List<List<Teacher>> { new List<Teacher>() } :
                teachers.SelectMany((t, i) =>
                    GetCombinations(teachers.Skip(i + 1).ToList(), (t, c) =>
                        new List<Teacher> { t }.Concat(c).ToList());
        }*/

        public static void PrintTeacherScheduleMatrix(object[,] matrix, List<List<Teacher>> teacherCombinations)
        {
            int rows = matrix.GetLength(0);
            int cols = matrix.GetLength(1);

            // Определяем максимальную ширину для каждого столбца
            int[] columnWidths = new int[cols];
            for (int col = 0; col < cols; col++)
            {
                for (int row = 0; row < rows; row++)
                {
                    int length = matrix[row, col]?.ToString()?.Length ?? 0;
                    if (length > columnWidths[col])
                    {
                        columnWidths[col] = length;
                    }
                }
                // Минимальная ширина для столбца - 3 символа
                columnWidths[col] = Math.Max(columnWidths[col], 3);
            }

            Console.WriteLine("РАСПИСАНИЕ ПРЕПОДАВАТЕЛЕЙ ПО ТАЙМ-СЛОТАМ");

            for (int col = 0; col < cols; col++)
            {
                string format = $"| {{0,-{columnWidths[col]}}} ";
                Console.Write(format, matrix[0, col]);
            }
            Console.WriteLine("|");


            for (int row = 1; row < rows; row++)
            {
                for (int col = 0; col < cols; col++)
                {
                    string format = $"| {{0,-{columnWidths[col]}}} ";
                    Console.Write(format, matrix[row, col]);
                }
                Console.WriteLine("|");
            }

            Console.WriteLine("\nСПИСОК КОМБИНАЦИЙ ПРЕПОДАВАТЕЛЕЙ:");
            for (int i = 0; i < teacherCombinations.Count; i++)
            {
                string comboTeachers = string.Join(", ", teacherCombinations[i].Select(t => t.Name));
                Console.WriteLine($"[{i + 1}] {comboTeachers}");
            }
        }




    }
}