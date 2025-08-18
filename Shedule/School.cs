using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Shedule
{
    public class School
    {
        //public static bool CheckTeacherStudentAllocation(List<Teacher> teachers, List<Student> students)
        //{
        //    var teacherAssignments = new Dictionary<Teacher, List<Student>>();
        //    var unassignedStudents = new List<Student>();

        //    foreach (var teacher in teachers)
        //    {
        //        teacherAssignments[teacher] = new List<Student>();
        //    }

        //    // Сначала распределяем учеников с "редкими" предметами (где меньше учителей)
        //    var studentsBySubjectAvailability = students
        //        .OrderBy(s => teachers.Count(t => t.SubjectsId.Contains(s.SubjectId)))
        //        .ToList();

        //    foreach (var student in studentsBySubjectAvailability)
        //    {
        //        var availableTeachers = teachers
        //            .Where(t => t.SubjectsId.Contains(student.SubjectId) &&
        //                        teacherAssignments[t].Count < 4)
        //            .OrderBy(t => teacherAssignments[t].Count); // Выбираем учителей с минимальной нагрузкой

        //        var assignedTeacher = availableTeachers.FirstOrDefault();

        //        if (assignedTeacher != null)
        //        {
        //            teacherAssignments[assignedTeacher].Add(student);
        //        }
        //        else
        //        {
        //            unassignedStudents.Add(student);
        //        }
        //    }


        //    return unassignedStudents.Count == 0;

        //}

        /*public static bool CheckTeacherStudentAllocation(List<Teacher> teachers, List<Student> students)
        {
            var teacherAssignments = new Dictionary<Teacher, List<Student>>();
            var unassignedStudents = new List<Student>();

            foreach (var teacher in teachers)
            {
                teacherAssignments[teacher] = new List<Student>();
            }

            // Сначала распределяем учеников с наибольшей потребностью во внимании
            var sortedStudents = students
                .OrderByDescending(s => s.NeedForAttention)
                .ToList();

            foreach (var student in sortedStudents)
            {
                var availableTeachers = teachers
                    .Where(t => t.SubjectsId.Contains(student.SubjectId))
                    .OrderBy(t => teacherAssignments[t].Sum(s => s.NeedForAttention)) // Сначала преподаватели с минимальной текущей нагрузкой
                    .ThenBy(t => t.Priority); // Затем по приоритету

                bool isAssigned = false;
                foreach (var teacher in availableTeachers)
                {
                    int currentLoad = teacherAssignments[teacher].Sum(s => s.NeedForAttention);
                    if (currentLoad + student.NeedForAttention <= teacher.MaximumAttention)
                    {
                        teacherAssignments[teacher].Add(student);
                        isAssigned = true;
                        break;
                    }
                }

                if (!isAssigned)
                {
                    unassignedStudents.Add(student);
                }
            }

            return unassignedStudents.Count == 0;
        }*/

        public static bool CheckTeacherStudentAllocation(List<Teacher> teachers, List<Student> students)
        {
            var teacherAssignments = new Dictionary<Teacher, List<Student>>();
            var unassignedStudents = new List<Student>();

            foreach (var teacher in teachers)
            {
                teacherAssignments[teacher] = new List<Student>();
            }

            // Вычисляем редкость предметов (сколько преподавателей могут вести каждый предмет)
            var subjectRarity = students
                .GroupBy(s => s.SubjectId)
                .ToDictionary(g => g.Key, g => teachers.Count(t => t.SubjectsId.Contains(g.Key)));

            // Сортируем студентов:
            // 1. Сначала студенты с редкими предметами (меньше преподавателей могут вести)
            // 2. Затем студенты с большей потребностью во внимании
            var sortedStudents = students
                .OrderBy(s => subjectRarity[s.SubjectId])
                .ThenByDescending(s => s.NeedForAttention)
                .ToList();

            foreach (var student in sortedStudents)
            {
                // Доступные преподаватели для этого предмета, отсортированные по:
                // 1. Текущей нагрузке (сумма NeedForAttention)
                // 2. Приоритету преподавателя
                var availableTeachers = teachers
                    .Where(t => t.SubjectsId.Contains(student.SubjectId))
                    .OrderBy(t => teacherAssignments[t].Sum(s => s.NeedForAttention))
                    .ThenBy(t => t.Priority)
                    .ToList();

                bool isAssigned = false;
                foreach (var teacher in availableTeachers)
                {
                    int currentLoad = teacherAssignments[teacher].Sum(s => s.NeedForAttention);
                    if (currentLoad + student.NeedForAttention <= teacher.MaximumAttention)
                    {
                        teacherAssignments[teacher].Add(student);
                        isAssigned = true;
                        break;
                    }
                }

                if (!isAssigned)
                {
                    unassignedStudents.Add(student);
                }
            }

            return unassignedStudents.Count == 0;
        }

        public static List<Teacher> WorkingTeachers (List<Teacher> teachers, List<Student> students)
        {
            var teacherAssignments = new Dictionary<Teacher, List<Student>>();
            var unassignedStudents = new List<Student>();
            var res = new List<Teacher>();


            foreach (var teacher in teachers)
            {
                teacherAssignments[teacher] = new List<Student>();
            }

            // Сначала распределяем учеников с "редкими" предметами (где меньше учителей)
            var studentsBySubjectAvailability = students
                .OrderBy(s => teachers.Count(t => t.SubjectsId.Contains(s.SubjectId)))
                .ToList();

            foreach (var student in studentsBySubjectAvailability)
            {
                var availableTeachers = teachers
                    .Where(t => t.SubjectsId.Contains(student.SubjectId) &&
                                teacherAssignments[t].Count < 4)
                    .OrderBy(t => teacherAssignments[t].Count); // Выбираем учителей с минимальной нагрузкой

                var assignedTeacher = availableTeachers.FirstOrDefault();

                if (assignedTeacher != null)
                {
                    teacherAssignments[assignedTeacher].Add(student);
                    res.Add(assignedTeacher);
                }
                else
                {
                    unassignedStudents.Add(student);
                }
            }


            return res.DistinctBy(x => x.Name).ToList();

        }

        public static List<List<Teacher>> GetMinTeachersInCombo(List<Teacher> teachers, List<Student> students)
        {
            List<List<Teacher>> res = new List<List<Teacher>>();
            List<List<Teacher>> uniqTeachers = HelperMethods.GetAllTeacherCombinations(teachers);
            int minCount = int.MaxValue;
            foreach (var combo in uniqTeachers)
            {
                if (School.CheckTeacherStudentAllocation(combo, students) && combo.Count != 0)
                {
                    if (combo.Count < minCount)
                    {
                        res.Clear();
                        res.Add(combo);
                        minCount = combo.Count;
                    }
                    else if (combo.Count == minCount)
                    {
                        res.Add(combo);
                    }
                }
            }
            return res;
        }
    }
}

