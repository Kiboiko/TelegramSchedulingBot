using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection.Metadata.Ecma335;
using System.Text;
using System.Threading.Tasks;

namespace Shedule
{
    public class Student : Person
    {
        public int SubjectId { get;}
        public int NeedForAttention { get; }
        public Student(string name, string startOfStudyTime, string endOfStudyTime,int subjectId, int _NeedForAttention) 
            : base(name, startOfStudyTime, endOfStudyTime)
        {
            SubjectId = subjectId;
            NeedForAttention = _NeedForAttention;
        }

        public override string ToString()
        {
            return $"Класс: Ученик\nИмя: {Name} \nВремя начала:{StartOfStudyingTime.ToString("HH:mm")}\n" +
                $"Время конца:{EndOfStudyingTime.ToString("HH:mm")} \nПредмет:{SubjectId}";
        }
    }
}
