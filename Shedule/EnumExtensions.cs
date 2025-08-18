using System;
using System.ComponentModel;

namespace Shedule
{
    public static class EnumExtensions
    {
        private static readonly Dictionary<Type, Dictionary<string, Enum>> DescriptionCache =
            new Dictionary<Type, Dictionary<string, Enum>>();

        public static T ParseFromDescription<T>(this string description) where T : Enum
        {
            var type = typeof(T);

            if (!DescriptionCache.TryGetValue(type, out var cache))
            {
                cache = new Dictionary<string, Enum>(StringComparer.OrdinalIgnoreCase);
                foreach (var value in Enum.GetValues(type))
                {
                    var field = type.GetField(value.ToString());
                    if (Attribute.GetCustomAttribute(field, typeof(DescriptionAttribute))
                        is DescriptionAttribute attr)
                    {
                        cache[attr.Description] = (Enum)value;
                    }
                }
                DescriptionCache[type] = cache;
            }

            if (cache.TryGetValue(description, out var result))
            {
                return (T)result;
            }

            throw new ArgumentException($"{description} не найден в enum {type.Name}");
        }
    }
}