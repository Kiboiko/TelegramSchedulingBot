//using System.ComponentModel;

//namespace Shedule
//{
//    public enum Lessons
//    {
//        [Description("математика")]
//        Math,
//        [Description("физика")]
//        Physic,
//        [Description("информатика")]
//        Informatic
//    }
//}

using System.ComponentModel;

namespace Shedule
{
    public enum Lessons
    {
        [Description("математика")]
        Math = 1,  

        [Description("физика")]
        Physic = 2,

        [Description("информатика")]
        Informatic = 3
    }
}