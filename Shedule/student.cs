using System;

namespace Shedule
{
    public class Student : Person
    {
        public int SubjectId { get; }
        public int NeedForAttention { get; }
        public List<DateTime> LessonDates { get; } = new List<DateTime>();

        public Student(string name, string startOfStudyTime, string endOfStudyTime,
                      int subjectId, int _NeedForAttention)
            : base(name, startOfStudyTime, endOfStudyTime)
        {
            SubjectId = subjectId;
            NeedForAttention = _NeedForAttention;
        }

        public bool NeedsLessonOnDate(DateTime date)
        {
            return LessonDates.Contains(date.Date);
        }

        public void AddLessonDate(DateTime date)
        {
            if (!LessonDates.Contains(date.Date))
                LessonDates.Add(date.Date);
        }

        public override string ToString()
        {
            return $"Класс: Ученик\nИмя: {Name} \nВремя начала:{StartOfStudyingTime.ToString("HH:mm")}\n" +
                   $"Время конца:{EndOfStudyingTime.ToString("HH:mm")} \nПредмет:{SubjectId}\n" +
                   $"Даты занятий: {string.Join(", ", LessonDates.Select(d => d.ToString("dd.MM.yyyy")))}";
        }
    }
}