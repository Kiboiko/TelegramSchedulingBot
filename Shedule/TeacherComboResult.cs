using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Shedule
{
    public class TeacherComboResult
    {
        public List<Teacher> Teachers { get; set; }
        public Dictionary<Teacher, (TimeOnly Start, TimeOnly End)> WorkingHours { get; set; }
        public int TotalPriority => Teachers.Sum(t => t.Priority);
    }
}
