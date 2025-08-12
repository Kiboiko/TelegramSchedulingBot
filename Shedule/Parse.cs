//using ClosedXML.Excel;
//using System;
//using System.IO;

//class Parse
//{
//    static void Main(string[] args)
//    {
//        // Путь к файлу (теперь он в той же папке, что и exe-файл)
//        string filePath = "example.xlsx";

//        // Проверка существования файла
//        if (!File.Exists(filePath))
//        {
//            Console.WriteLine($"Файл не найден!\nПолный путь: {Path.GetFullPath(filePath)}");
//            Console.ReadLine();
//            return;
//        }

//        try
//        {
//            using (var workbook = new XLWorkbook(filePath))
//            {
//                var worksheet = workbook.Worksheet(1); // Первый лист

//                // Выводим первую строку
//                Console.WriteLine("Первая строка:");
//                foreach (var cell in worksheet.Row(1).CellsUsed())
//                {
//                    Console.Write($"[{cell.Value}] ");
//                }
//                Console.WriteLine("\n");

//                // Выводим первый столбец
//                Console.WriteLine("Первый столбец:");
//                foreach (var cell in worksheet.Column(1).CellsUsed())
//                {
//                    Console.WriteLine($"[{cell.Value}]");
//                }
//            }
//        }
//        catch (Exception ex)
//        {
//            Console.WriteLine($"Ошибка при чтении файла: {ex.Message}");
//        }

//        Console.ReadLine();
//    }
//}