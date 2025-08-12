using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Shedule
{
    public class Person
    {
        public string Name { get;}
        public TimeOnly StartOfStudyingTime { get;}
        public TimeOnly EndOfStudyingTime { get; }
        public Person(string name, string startOfStudyTime, string endOfStudyTime)
        {
            Name = name;
            if (TimeOnly.TryParse(startOfStudyTime, out TimeOnly Start) && 
                TimeOnly.TryParse(endOfStudyTime, out TimeOnly End))
            {
                StartOfStudyingTime = Start;
                EndOfStudyingTime = End;
            } else
            {
                Console.WriteLine("Некорректный формат времени");
            }
        }
        public bool Comparison(Person other)
        {
            return Name == other.Name;
        }
    }
}
