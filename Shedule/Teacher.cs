using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Shedule
{
    public class Teacher : Person
    {
        public List<int> SubjectsId = new List<int>();
        public int Priority;
        public int MaximumAttention { get; }
        public Teacher(string name, string startOfStudyTime, string endOfStudyTime, List<int> _lessons,int priority, int _MaximumAttention)
            :base(name,startOfStudyTime,endOfStudyTime) {
            SubjectsId = _lessons;
            Priority = priority;
            MaximumAttention = _MaximumAttention;
        }

        public override string ToString()
        {
            return $"Имя: {Name}\nКласс: Преподаватель\n" +
                $"Предметы: {string.Join(',', SubjectsId)}\nПриоритет: {Priority}\n" +
                $"Время начала:{StartOfStudyingTime.ToString("HH:mm")}\n" +
                $"Время конца:{EndOfStudyingTime.ToString("HH:mm")}";
        }

        
    }
}
