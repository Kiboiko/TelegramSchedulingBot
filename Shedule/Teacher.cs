using System;
using System.Collections.Generic;

namespace Shedule
{
    public class Teacher : Person
    {
        public List<int> SubjectsId = new List<int>();
        public int Priority;
        public int MaximumAttention { get; }
        public List<DateTime> AvailableDates { get; } = new List<DateTime>();

        public Teacher(string name, string startOfStudyTime, string endOfStudyTime,
                      List<int> _lessons, int priority, int _MaximumAttention)
            : base(name, startOfStudyTime, endOfStudyTime)
        {
            SubjectsId = _lessons;
            Priority = priority;
            MaximumAttention = _MaximumAttention;
        }

        public bool IsAvailableOnDate(DateTime date)
        {
            return AvailableDates.Contains(date.Date);
        }

        public void AddAvailableDate(DateTime date)
        {
            if (!AvailableDates.Contains(date.Date))
                AvailableDates.Add(date.Date);
        }

        public override string ToString()
        {
            return $"Имя: {Name}\nКласс: Преподаватель\n" +
                   $"Предметы: {string.Join(',', SubjectsId)}\nПриоритет: {Priority}\n" +
                   $"Время начала:{StartOfStudyingTime.ToString("HH:mm")}\n" +
                   $"Время конца:{EndOfStudyingTime.ToString("HH:mm")}\n" +
                   $"Доступные даты: {string.Join(", ", AvailableDates.Select(d => d.ToString("dd.MM.yyyy")))}";
        }
    }
}