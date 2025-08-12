//using ClosedXML.Excel;
//using System;
//using System.Collections.Generic;
//using System.IO;
//using System.Linq;

//namespace Shedule
//{
//    public class ExcelDataLoader
//    {
//        public (List<Teacher> teachers, List<Student> students) LoadData(string filePath)
//        {
//            var teachers = new List<Teacher>();
//            var students = new List<Student>();

//            if (!File.Exists(filePath))
//            {
//                Console.WriteLine($"Файл не найден: {filePath}");
//                return (teachers, students);
//            }

//            try
//            {
//                using (var workbook = new XLWorkbook(filePath))
//                {
//                    // Загрузка справочника предметов
//                    var subjectMap = LoadSubjectMap(workbook);

//                    // Лист преподавателей
//                    var teacherSheet = workbook.Worksheet("преподы");
//                    if (teacherSheet == null) throw new Exception("Лист 'преподы' не найден");

//                    foreach (var row in teacherSheet.RowsUsed().Skip(1))
//                    {
//                        if (row.IsEmpty()) continue;
//                        var teacher = ParseTeacherRow(row, subjectMap);
//                        if (teacher != null) teachers.Add(teacher);
//                    }

//                    // Лист студентов
//                    var studentSheet = workbook.Worksheet("ученики");
//                    if (studentSheet == null) throw new Exception("Лист 'ученики' не найден");

//                    foreach (var row in studentSheet.RowsUsed().Skip(1))
//                    {
//                        if (row.IsEmpty()) continue;
//                        var student = ParseStudentRow(row, subjectMap);
//                        if (student != null) students.Add(student);
//                    }
//                }
//            }
//            catch (Exception ex)
//            {
//                Console.WriteLine($"Ошибка при загрузке данных: {ex.Message}");
//            }

//            return (teachers, students);
//        }

//        private Dictionary<string, int> LoadSubjectMap(XLWorkbook workbook)
//        {
//            var map = new Dictionary<string, int>();
//            var sheet = workbook.Worksheet("квалификации");
//            if (sheet == null) return map;

//            foreach (var row in sheet.RowsUsed().Skip(1))
//            {
//                var subjectName = row.Cell(1).Value.ToString().Trim();
//                if (int.TryParse(row.Cell(2).Value.ToString(), out int id))
//                {
//                    map[subjectName] = id;
//                }
//            }
//            return map;
//        }

//        private Teacher ParseTeacherRow(IXLRow row, Dictionary<string, int> subjectMap)
//        {
//            try
//            {
//                // Основные данные
//                string name = row.Cell(2).Value.ToString().Trim();
//                string subjectsInput = row.Cell(3).Value.ToString().Trim();
//                string startTimeStr = row.Cell(4).Value.ToString();
//                string endTimeStr = row.Cell(5).Value.ToString();
//                int priority = int.TryParse(row.Cell(6).Value.ToString(), out int p) ? p : 1;

//                // Расчет MaximumAttention на основе рабочего времени
//                /*TimeSpan startTime = TimeSpan.Parse(startTimeStr);
//                TimeSpan endTime = TimeSpan.Parse(endTimeStr);
//                TimeSpan workingTime = endTime - startTime;
//                int maximumAttention = (int)workingTime.TotalMinutes;*/
//                int maximumAttention = 15;

//                // Парсинг ID предметов
//                var subjectIds = subjectsInput
//                    .Split(new[] { ',', '.', ';' }, StringSplitOptions.RemoveEmptyEntries)
//                    .Select(id => id.Trim())
//                    .Where(id => subjectMap.ContainsValue(int.Parse(id)))
//                    .Select(id => int.Parse(id))
//                    .ToList();

//                return new Teacher(
//                    name: name,
//                    startOfStudyTime: NormalizeTime(startTimeStr),
//                    endOfStudyTime: NormalizeTime(endTimeStr),
//                    _lessons: subjectIds,
//                    priority: priority,
//                    _MaximumAttention: maximumAttention
//                );
//            }
//            catch (Exception ex)
//            {
//                Console.WriteLine($"Ошибка парсинга преподавателя (строка {row.RowNumber()}): {ex.Message}");
//                return null;
//            }
//        }

//        private Student ParseStudentRow(IXLRow row, Dictionary<string, int> subjectMap)
//        {
//            try
//            {
//                // Основные данные
//                string name = row.Cell(2).Value.ToString().Trim();
//                string subjectId = row.Cell(3).Value.ToString().Trim();
//                string startTimeStr = row.Cell(4).Value.ToString();
//                string endTimeStr = row.Cell(5).Value.ToString();

//                // Потребность во внимании (обязательное поле)
//                if (!int.TryParse(row.Cell(6).Value.ToString(), out int needForAttention))
//                {
//                    throw new ArgumentException($"Не указана потребность во внимании для студента {name}");
//                }

//                if (!int.TryParse(subjectId, out int subjectIdInt))
//                {
//                    throw new ArgumentException($"Неверный ID предмета: {subjectId}");
//                }

//                return new Student(
//                    name: name,
//                    startOfStudyTime: NormalizeTime(startTimeStr),
//                    endOfStudyTime: NormalizeTime(endTimeStr),
//                    subjectId: subjectIdInt,
//                    _NeedForAttention: needForAttention
//                );
//            }
//            catch (Exception ex)
//            {
//                Console.WriteLine($"Ошибка парсинга студента (строка {row.RowNumber()}): {ex.Message}");
//                return null;
//            }
//        }

//        private string NormalizeTime(string timeStr)
//        {
//            if (timeStr.Length > 5 && timeStr.Contains(':'))
//            {
//                var parts = timeStr.Split(':');
//                if (parts.Length >= 2)
//                {
//                    return $"{parts[0]}:{parts[1]}";
//                }
//            }
//            return timeStr;
//        }

//        public static void ExportScheduleToExcel(object[,] matrix, List<List<Teacher>> teacherCombinations, string originalFilePath)
//        {
//            if (!File.Exists(originalFilePath))
//            {
//                throw new FileNotFoundException("Исходный файл не найден", originalFilePath);
//            }

//            try
//            {
//                using (var workbook = new XLWorkbook(originalFilePath))
//                {
//                    // Удаляем старый лист, если он существует
//                    RemoveWorksheetIfExists(workbook, "Расписание и комбинации");

//                    // Создаем новый лист
//                    var worksheet = workbook.Worksheets.Add("Расписание и комбинации");

//                    // 1. Заполняем таблицу расписания
//                    int startRow = 1;
//                    FillScheduleSheet(worksheet, matrix, startRow);

//                    // Добавляем границы для всей таблицы расписания
//                    int lastScheduleRow = startRow + matrix.GetLength(0) - 1;
//                    int lastScheduleCol = matrix.GetLength(1);
//                    var scheduleRange = worksheet.Range(startRow, 1, lastScheduleRow, lastScheduleCol);
//                    scheduleRange.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
//                    scheduleRange.Style.Border.InsideBorder = XLBorderStyleValues.Thin;

//                    // 2. Добавляем заголовок для комбинаций (2 строки после таблицы)
//                    int comboStartRow = lastScheduleRow + 3;
//                    worksheet.Cell(comboStartRow, 1).Value = "Список комбинаций преподавателей";
//                    worksheet.Cell(comboStartRow, 1).Style.Font.Bold = true;
//                    worksheet.Cell(comboStartRow, 1).Style.Font.FontSize = 12;

//                    // 3. Заполняем список комбинаций
//                    FillCombinationsSheet(worksheet, teacherCombinations, comboStartRow + 1);

//                    // Сохраняем изменения
//                    workbook.Save();
//                    Console.WriteLine($"Данные успешно добавлены в файл: {originalFilePath}");
//                }
//            }
//            catch (Exception ex)
//            {
//                Console.WriteLine($"Ошибка при сохранении в файл: {ex.Message}");
//                throw;
//            }
//        }

//        private static void RemoveWorksheetIfExists(XLWorkbook workbook, string sheetName)
//        {
//            if (workbook.Worksheets.Any(ws => ws.Name == sheetName))
//            {
//                workbook.Worksheets.Delete(sheetName);
//            }
//        }

//        private static void FillScheduleSheet(IXLWorksheet sheet, object[,] matrix, int startRow)
//        {
//            // 1. Настраиваем столбец с именами преподавателей
//            sheet.Column(1).Width = GetOptimalColumnWidth(matrix, 0) + 2; // +2 для запаса

//            // 2. Настраиваем столбцы с тайм-слотами
//            for (int col = 1; col < matrix.GetLength(1); col++)
//            {
//                sheet.Column(col + 1).Width = GetOptimalColumnWidth(matrix, col);
//            }

//            // 3. Заполняем данные с сохранением всех стилей
//            for (int row = 0; row < matrix.GetLength(0); row++)
//            {
//                for (int col = 0; col < matrix.GetLength(1); col++)
//                {
//                    var cell = sheet.Cell(startRow + row, col + 1);
//                    cell.Value = matrix[row, col]?.ToString();

//                    // Стилизация ячеек
//                    if (row == 0) // Заголовки
//                    {
//                        cell.Style.Font.Bold = true;
//                        cell.Style.Fill.BackgroundColor = XLColor.LightGray;
//                    }
//                    else if (matrix[row, col]?.ToString() == "0")
//                    {
//                        cell.Style.Fill.BackgroundColor = XLColor.LightGray;
//                        cell.Style.Font.FontColor = XLColor.DarkGray;
//                    }
//                    else if (col == 0) // Имена преподавателей
//                    {
//                        cell.Style.Font.Bold = true;
//                    }
//                    else // Активные слоты
//                    {
//                        cell.Style.Fill.BackgroundColor = XLColor.LightGreen;
//                    }

//                    // Границы
//                    cell.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
//                }
//            }
//        }

//        // Метод для расчета оптимальной ширины столбца
//        private static double GetOptimalColumnWidth(object[,] matrix, int colIndex)
//        {
//            double maxWidth = 8.0; // Минимальная ширина по умолчанию

//            for (int row = 0; row < matrix.GetLength(0); row++)
//            {
//                string content = matrix[row, colIndex]?.ToString() ?? "";
//                double contentWidth = content.Length * 1.2; // Эмпирический коэффициент

//                if (colIndex == 0) // Для столбца с именами
//                    contentWidth = content.Length * 1.5;

//                if (contentWidth > maxWidth)
//                    maxWidth = contentWidth;
//            }

//            return Math.Min(maxWidth, 50.0); // Ограничиваем максимальную ширину
//        }

//        private static void FillCombinationsSheet(IXLWorksheet sheet, List<List<Teacher>> teacherCombinations, int startRow)
//        {
//            // Заголовки таблицы комбинаций
//            sheet.Cell(startRow, 1).Value = "№";
//            sheet.Cell(startRow, 2).Value = "Состав комбинации";

//            var headerRange = sheet.Range(startRow, 1, startRow, 2);
//            headerRange.Style.Font.Bold = true;
//            headerRange.Style.Fill.BackgroundColor = XLColor.LightGray;
//            headerRange.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;

//            // Данные комбинаций
//            for (int i = 0; i < teacherCombinations.Count; i++)
//            {
//                sheet.Cell(startRow + i + 1, 1).Value = i + 1;
//                sheet.Cell(startRow + i + 1, 2).Value = string.Join(", ", teacherCombinations[i].Select(t => t.Name));

//                // Добавляем границы для каждой строки комбинаций
//                var rowRange = sheet.Range(startRow + i + 1, 1, startRow + i + 1, 2);
//                rowRange.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
//            }

//            // Настраиваем ширину столбцов
//            sheet.Column(1).Width = 5;  // Номер
//            sheet.Column(2).Width = 50; // Состав комбинации
//        }
//    }
//}

using Google.Apis.Auth.OAuth2;
using Google.Apis.Sheets.v4;
using Google.Apis.Sheets.v4.Data;
using Google.Apis.Services;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Shedule
{
    public class GoogleSheetsDataLoader
    {
        private readonly string[] Scopes = { SheetsService.Scope.Spreadsheets };
        private readonly string ApplicationName = "Schedule App";
        private SheetsService service;
        private string spreadsheetId;

        public GoogleSheetsDataLoader(string credentialsPath, string spreadsheetId)
        {
            this.spreadsheetId = spreadsheetId;

            GoogleCredential credential;
            using (var stream = new FileStream(credentialsPath, FileMode.Open, FileAccess.Read))
            {
                credential = GoogleCredential.FromStream(stream)
                    .CreateScoped(Scopes);
            }

            service = new SheetsService(new BaseClientService.Initializer()
            {
                HttpClientInitializer = credential,
                ApplicationName = ApplicationName,
            });
        }

        public (List<Teacher> teachers, List<Student> students) LoadData()
        {
            var teachers = new List<Teacher>();
            var students = new List<Student>();

            try
            {
                // Загрузка справочника предметов
                var subjectMap = LoadSubjectMap();

                // Лист преподавателей
                var teacherSheet = GetSheetData("преподы");
                if (teacherSheet == null) throw new Exception("Лист 'преподы' не найден");

                foreach (var row in teacherSheet.Skip(1))
                {
                    if (row.Count == 0) continue;
                    var teacher = ParseTeacherRow(row, subjectMap);
                    if (teacher != null) teachers.Add(teacher);
                }

                // Лист студентов
                var studentSheet = GetSheetData("ученики");
                if (studentSheet == null) throw new Exception("Лист 'ученики' не найден");

                foreach (var row in studentSheet.Skip(1))
                {
                    if (row.Count == 0) continue;
                    var student = ParseStudentRow(row, subjectMap);
                    if (student != null) students.Add(student);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка при загрузке данных: {ex.Message}");
            }

            return (teachers, students);
        }

        private Dictionary<string, int> LoadSubjectMap()
        {
            var map = new Dictionary<string, int>();
            var sheet = GetSheetData("квалификации");
            if (sheet == null) return map;

            foreach (var row in sheet.Skip(1))
            {
                if (row.Count < 2) continue;

                var subjectName = row[0].ToString().Trim();
                if (int.TryParse(row[1].ToString(), out int id))
                {
                    map[subjectName] = id;
                }
            }
            return map;
        }

        private IList<IList<object>> GetSheetData(string sheetName)
        {
            var range = $"{sheetName}!A:Z";
            var request = service.Spreadsheets.Values.Get(spreadsheetId, range);
            var response = request.Execute();
            return response.Values;
        }

        private Teacher ParseTeacherRow(IList<object> row, Dictionary<string, int> subjectMap)
        {
            try
            {
                string name = row[1].ToString().Trim();
                string subjectsInput = row[2].ToString().Trim();
                string startTimeStr = row[3].ToString();
                string endTimeStr = row[4].ToString();
                int priority = row.Count > 5 && int.TryParse(row[5].ToString(), out int p) ? p : 1;
                int maximumAttention = 15;

                var subjectIds = subjectsInput
                    .Split(new[] { ',', '.', ';' }, StringSplitOptions.RemoveEmptyEntries)
                    .Select(id => id.Trim())
                    .Where(id => subjectMap.ContainsValue(int.Parse(id)))
                    .Select(id => int.Parse(id))
                    .ToList();

                return new Teacher(
                    name: name,
                    startOfStudyTime: NormalizeTime(startTimeStr),
                    endOfStudyTime: NormalizeTime(endTimeStr),
                    _lessons: subjectIds,
                    priority: priority,
                    _MaximumAttention: maximumAttention
                );
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка парсинга преподавателя: {ex.Message}");
                return null;
            }
        }

        private Student ParseStudentRow(IList<object> row, Dictionary<string, int> subjectMap)
        {
            try
            {
                string name = row[1].ToString().Trim();
                string subjectId = row[2].ToString().Trim();
                string startTimeStr = row[3].ToString();
                string endTimeStr = row[4].ToString();

                if (row.Count < 6 || !int.TryParse(row[5].ToString(), out int needForAttention))
                {
                    throw new ArgumentException($"Не указана потребность во внимании для студента {name}");
                }

                if (!int.TryParse(subjectId, out int subjectIdInt))
                {
                    throw new ArgumentException($"Неверный ID предмета: {subjectId}");
                }

                return new Student(
                    name: name,
                    startOfStudyTime: NormalizeTime(startTimeStr),
                    endOfStudyTime: NormalizeTime(endTimeStr),
                    subjectId: subjectIdInt,
                    _NeedForAttention: needForAttention
                );
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка парсинга студента: {ex.Message}");
                return null;
            }
        }

        private string NormalizeTime(string timeStr)
        {
            if (timeStr.Length > 5 && timeStr.Contains(':'))
            {
                var parts = timeStr.Split(':');
                if (parts.Length >= 2)
                {
                    return $"{parts[0]}:{parts[1]}";
                }
            }
            return timeStr;
        }

        public void ExportScheduleToGoogleSheets(object[,] matrix, List<List<Teacher>> combinations)
        {
            try
            {
                string sheetName = "Расписание_" + DateTime.Now.ToString("yyyyMMdd_HHmmss");

                // 1. Создаем новый лист
                CreateNewSheet(sheetName);

                // 2. Подготавливаем данные
                var valueRange = new ValueRange
                {
                    Values = ConvertToValueList(matrix),
                    Range = $"{sheetName}!A1" // Указываем только начальную ячейку
                };

                // 3. Отправляем данные
                var request = service.Spreadsheets.Values.Update(
                    valueRange,
                    spreadsheetId,
                    $"{sheetName}!A1"); // Используем только начальную точку

                request.ValueInputOption = SpreadsheetsResource.ValuesResource.UpdateRequest.ValueInputOptionEnum.RAW;
                var response = request.Execute();

                Console.WriteLine($"Данные сохранены в лист: {sheetName}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка экспорта: {ex.Message}");
                throw;
            }
        }

        private IList<IList<object>> ConvertToValueList(object[,] matrix)
        {
            var values = new List<IList<object>>();
            for (int i = 0; i < matrix.GetLength(0); i++)
            {
                var row = new List<object>();
                for (int j = 0; j < matrix.GetLength(1); j++)
                {
                    row.Add(matrix[i, j] ?? "");
                }
                values.Add(row);
            }
            return values;
        }

        private void DeleteSheetIfExists(string sheetName)
        {
            var spreadsheet = service.Spreadsheets.Get(spreadsheetId).Execute();
            var sheet = spreadsheet.Sheets.FirstOrDefault(s => s.Properties.Title == sheetName);
            if (sheet != null)
            {
                var deleteRequest = new Request
                {
                    DeleteSheet = new DeleteSheetRequest { SheetId = sheet.Properties.SheetId }
                };
                var batchUpdateRequest = new BatchUpdateSpreadsheetRequest
                {
                    Requests = new List<Request> { deleteRequest }
                };
                service.Spreadsheets.BatchUpdate(batchUpdateRequest, spreadsheetId).Execute();
            }
        }

        private void CreateNewSheet(string sheetName)
        {
            var addSheetRequest = new Request
            {
                AddSheet = new AddSheetRequest
                {
                    Properties = new SheetProperties { Title = sheetName }
                }
            };
            var batchUpdateRequest = new BatchUpdateSpreadsheetRequest
            {
                Requests = new List<Request> { addSheetRequest }
            };
            service.Spreadsheets.BatchUpdate(batchUpdateRequest, spreadsheetId).Execute();
        }

        private void UpdateScheduleMatrix(object[,] matrix)
        {
            var valueRange = new ValueRange();
            var values = new List<IList<object>>();

            for (int row = 0; row < matrix.GetLength(0); row++)
            {
                var rowValues = new List<object>();
                for (int col = 0; col < matrix.GetLength(1); col++)
                {
                    rowValues.Add(matrix[row, col]?.ToString());
                }
                values.Add(rowValues);
            }

            valueRange.Values = values;
            valueRange.Range = $"A1:{GetColumnLetter(matrix.GetLength(1))}{matrix.GetLength(0)}";

            var request = service.Spreadsheets.Values.Update(
                valueRange,
                spreadsheetId,
                "Расписание и комбинации!" + valueRange.Range);
            request.ValueInputOption = SpreadsheetsResource.ValuesResource.UpdateRequest.ValueInputOptionEnum.RAW;
            request.Execute();
        }

        private void AddTeacherCombinations(List<List<Teacher>> combinations, int startRow)
        {
            var valueRange = new ValueRange();
            var values = new List<IList<object>>();

            // Заголовок
            values.Add(new List<object> { "Список комбинаций преподавателей" });
            values.Add(new List<object>()); // Пустая строка
            values.Add(new List<object> { "№", "Состав комбинации" });

            // Данные
            for (int i = 0; i < combinations.Count; i++)
            {
                values.Add(new List<object>
                {
                    i + 1,
                    string.Join(", ", combinations[i].Select(t => t.Name))
                });
            }

            valueRange.Values = values;
            valueRange.Range = $"A{startRow}:B{startRow + combinations.Count + 2}";

            var request = service.Spreadsheets.Values.Update(
                valueRange,
                spreadsheetId,
                $"Расписание и комбинации!A{startRow}");
            request.ValueInputOption = SpreadsheetsResource.ValuesResource.UpdateRequest.ValueInputOptionEnum.RAW;
            request.Execute();
        }

        private string GetColumnLetter(int columnNumber)
        {
            if (columnNumber < 1) return "A";

            string columnName = "";
            while (columnNumber > 0)
            {
                int remainder = (columnNumber - 1) % 26;
                columnName = Convert.ToChar('A' + remainder) + columnName;
                columnNumber = (columnNumber - 1) / 26;
            }
            return columnName;
        }
    }
}