using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Shedule
{
    public class HelperMethods
    {
        public static List<List<Teacher>> GetAllTeacherCombinations(List<Teacher> teachers)
        {
            return GenerateCombinations(teachers).ToList();
        }

        private static IEnumerable<List<Teacher>> GenerateCombinations(List<Teacher> teachers)
        {
            int totalCombinations = 1 << teachers.Count;

            for (int mask = 0; mask < totalCombinations; mask++)
            {
                var combination = new List<Teacher>();
                for (int i = 0; i < teachers.Count; i++)
                {
                    if ((mask & (1 << i)) != 0)
                    {
                        combination.Add(teachers[i]);
                    }
                }
                if (combination.Count > 0)
                    yield return combination;
            }
        }

        public static bool ClosureOfNeeds(List<Teacher> teachers, Dictionary<Lessons, int> personPerLesson)
        {
            // Словарь для подсчета количества преподавателей по каждому предмету
            Dictionary<int, int> coveredLessons = new Dictionary<int, int>();

            // Перебираем всех учителей и их предметы
            foreach (var teacher in teachers)
            {
                foreach (int lesson in teacher.SubjectsId)
                {
                    if (coveredLessons.ContainsKey(lesson))
                        coveredLessons[lesson]++;
                    else
                        coveredLessons[lesson] = 1;
                }
            }

            // Проверяем, все ли предметы покрыты в нужном количестве
            foreach (var requirement in personPerLesson)
            {
                int lesson = (int)requirement.Key;
                int requiredCount = requirement.Value;

                if (!coveredLessons.TryGetValue(lesson, out int actualCount) || actualCount < requiredCount)
                    return false;  // Предмет не покрыт или преподавателей недостаточно
            }

            return true;
        }

        public static bool ContainsForTeacher(List<Teacher> teachers, Teacher teacher)
        {
            bool t = true;
            foreach (var people in teachers)
            {
                if (!people.Comparison(teacher))
                {
                    t = false; 
                    break;
                }
            }
            return t;
        }


    }
}
