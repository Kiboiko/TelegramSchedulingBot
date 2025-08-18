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
        private string targetDate;

        public GoogleSheetsDataLoader(string credentialsPath, string spreadsheetId, string targetDate)
        {
            this.spreadsheetId = spreadsheetId;
            this.targetDate = targetDate;

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
                var teacherSheet = GetSheetData("Преподаватели");
                if (teacherSheet == null) throw new Exception("Лист 'Преподаватели' не найден");

                // Находим индексы колонок для выбранной даты
                var dateColumns = FindDateColumns(teacherSheet, targetDate);

                foreach (var row in teacherSheet.Skip(1))
                {
                    if (row.Count == 0) continue;
                    var teacher = ParseTeacherRow(row, subjectMap, dateColumns);
                    if (teacher != null) teachers.Add(teacher);
                }

                // Лист студентов
                var studentSheet = GetSheetData("Ученики");
                if (studentSheet == null) throw new Exception("Лист 'Ученики' не найден");

                var studentDateColumns = FindDateColumns(studentSheet, targetDate);

                foreach (var row in studentSheet.Skip(1))
                {
                    if (row.Count == 0) continue;
                    var student = ParseStudentRow(row, subjectMap, studentDateColumns);
                    if (student != null) students.Add(student);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка при загрузке данных: {ex.Message}");
            }

            return (teachers, students);
        }

        private (int startCol, int endCol) FindDateColumns(IList<IList<object>> sheet, string date)
        {
            if (sheet.Count == 0) return (-1, -1);

            var headerRow = sheet[0];
            int startCol = -1, endCol = -1;

            for (int i = 0; i < headerRow.Count; i++)
            {
                if (headerRow[i].ToString().Trim() == date)
                {
                    if (startCol == -1)
                        startCol = i;
                    else
                        endCol = i;
                }
            }

            return (startCol, endCol);
        }

        private Dictionary<string, int> LoadSubjectMap()
        {
            var map = new Dictionary<string, int>();
            var sheet = GetSheetData("Квалификации");
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

        private Teacher ParseTeacherRow(IList<object> row, Dictionary<string, int> subjectMap, (int startCol, int endCol) dateColumns)
        {
            try
            {
                string name = row[1].ToString().Trim();
                string subjectsInput = row[2].ToString().Trim();
                int priority = row.Count > 3 && int.TryParse(row[3].ToString(), out int p) ? p : 1;
                int maximumAttention = 15;

                // Получаем время начала и конца для выбранной даты
                string startTimeStr = dateColumns.startCol != -1 && row.Count > dateColumns.startCol ?
                    row[dateColumns.startCol].ToString() : "";
                string endTimeStr = dateColumns.endCol != -1 && row.Count > dateColumns.endCol ?
                    row[dateColumns.endCol].ToString() : "";

                if (string.IsNullOrEmpty(startTimeStr) || string.IsNullOrEmpty(endTimeStr))
                    return null; // Пропускаем преподавателей без расписания на выбранную дату

                var subjectIds = subjectsInput
                    .Split(new[] { ',', '.', ';' }, StringSplitOptions.RemoveEmptyEntries)
                    .Select(id => id.Trim())
                    .Where(id => int.TryParse(id, out _))
                    .Select(int.Parse)
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

        private Student ParseStudentRow(IList<object> row, Dictionary<string, int> subjectMap, (int startCol, int endCol) dateColumns)
        {
            try
            {
                string name = row[1].ToString().Trim();
                string subjectId = row[2].ToString().Trim();

                // Получаем время начала и конца для выбранной даты
                string startTimeStr = dateColumns.startCol != -1 && row.Count > dateColumns.startCol ?
                    row[dateColumns.startCol].ToString() : "";
                string endTimeStr = dateColumns.endCol != -1 && row.Count > dateColumns.endCol ?
                    row[dateColumns.endCol].ToString() : "";

                if (string.IsNullOrEmpty(startTimeStr) || string.IsNullOrEmpty(endTimeStr))
                    return null; // Пропускаем студентов без расписания на выбранную дату

                if (row.Count < 4 || !int.TryParse(row[3].ToString(), out int needForAttention))
                {
                    needForAttention = 1; // Значение по умолчанию
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

        // Остальные методы остаются без изменений
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
                    Range = $"{sheetName}!A1"
                };

                // 3. Отправляем данные
                var request = service.Spreadsheets.Values.Update(
                    valueRange,
                    spreadsheetId,
                    $"{sheetName}!A1");

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
    }
}