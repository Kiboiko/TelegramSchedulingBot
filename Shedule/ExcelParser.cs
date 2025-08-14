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
        private readonly SheetsService _service;
        private readonly string _spreadsheetId;
        private readonly Dictionary<int, DateTime> _dateColumns = new Dictionary<int, DateTime>();

        public GoogleSheetsDataLoader(string credentialsPath, string spreadsheetId)
        {
            _spreadsheetId = spreadsheetId;

            GoogleCredential credential;
            using (var stream = new FileStream(credentialsPath, FileMode.Open, FileAccess.Read))
            {
                credential = GoogleCredential.FromStream(stream)
                    .CreateScoped(SheetsService.Scope.Spreadsheets);
            }

            _service = new SheetsService(new BaseClientService.Initializer()
            {
                HttpClientInitializer = credential,
                ApplicationName = "Schedule App",
            });
        }

        public (List<Teacher> teachers, List<Student> students) LoadData(DateTime targetDate)
        {
            var teachers = new List<Teacher>();
            var students = new List<Student>();

            try
            {
                // Загрузка преподавателей
                var teacherSheet = GetSheetData("преподы");
                if (teacherSheet != null && teacherSheet.Count > 0)
                {
                    ParseDateColumns(teacherSheet[0]);

                    foreach (var row in teacherSheet.Skip(1))
                    {
                        if (row == null || row.Count < 2) continue;

                        var teacher = ParseTeacherRow(row, targetDate);
                        if (teacher != null) teachers.Add(teacher);
                    }
                }

                // Загрузка студентов
                var studentSheet = GetSheetData("ученики");
                if (studentSheet != null && studentSheet.Count > 0)
                {
                    ParseDateColumns(studentSheet[0]);

                    foreach (var row in studentSheet.Skip(1))
                    {
                        if (row == null || row.Count < 2) continue;

                        var student = ParseStudentRow(row, targetDate);
                        if (student != null) students.Add(student);
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка при загрузке данных: {ex.Message}");
            }

            return (teachers, students);
        }

        private void ParseDateColumns(IList<object> headerRow)
        {
            _dateColumns.Clear();
            if (headerRow == null) return;

            for (int i = 2; i < headerRow.Count; i++)
            {
                if (DateTime.TryParse(headerRow[i]?.ToString(), out DateTime date))
                {
                    _dateColumns[i] = date;
                }
            }
        }

        private IList<IList<object>>? GetSheetData(string sheetName)
        {
            try
            {
                var range = $"{sheetName}!A:Z";
                var request = _service.Spreadsheets.Values.Get(_spreadsheetId, range);
                var response = request.Execute();
                return response.Values;
            }
            catch
            {
                return null;
            }
        }

        private Teacher? ParseTeacherRow(IList<object> row, DateTime targetDate)
        {
            try
            {
                string name = row[0]?.ToString()?.Trim() ?? "";
                if (string.IsNullOrEmpty(name)) return null;

                string subjectsStr = row[1]?.ToString()?.Trim() ?? "";
                if (string.IsNullOrEmpty(subjectsStr)) return null;

                var subjectIds = new List<int>();
                foreach (var subject in subjectsStr.Split(new[] { ',', ' ', '.' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    if (int.TryParse(subject.Trim(), out int subjectId))
                    {
                        subjectIds.Add(subjectId);
                    }
                }

                if (subjectIds.Count == 0) return null;

                var timeSlots = new List<TimeSpan>();
                foreach (var col in _dateColumns)
                {
                    if (col.Value.Date == targetDate.Date && row.Count > col.Key)
                    {
                        if (TimeSpan.TryParse(row[col.Key]?.ToString(), out TimeSpan time))
                        {
                            timeSlots.Add(time);
                        }
                    }
                }

                if (timeSlots.Count == 0) return null;

                var startTime = timeSlots.Min();
                var endTime = timeSlots.Max().Add(TimeSpan.FromHours(1.5));

                int priority = row.Count > 6 && int.TryParse(row[6]?.ToString(), out int p) ? p : 1;

                return new Teacher(
                    name: name,
                    startOfStudyTime: startTime.ToString(@"hh\:mm"),
                    endOfStudyTime: endTime.ToString(@"hh\:mm"),
                    _lessons: subjectIds,
                    priority: priority,
                    _MaximumAttention: 15
                );
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка парсинга преподавателя: {ex.Message}");
                return null;
            }
        }

        private Student? ParseStudentRow(IList<object> row, DateTime targetDate)
        {
            try
            {
                string name = row[0]?.ToString()?.Trim() ?? "";
                if (string.IsNullOrEmpty(name)) return null;

                string subjectStr = row[1]?.ToString()?.Trim() ?? "";
                if (!int.TryParse(subjectStr, out int subjectId)) return null;

                var timeSlots = new List<TimeSpan>();
                foreach (var col in _dateColumns)
                {
                    if (col.Value.Date == targetDate.Date && row.Count > col.Key)
                    {
                        if (TimeSpan.TryParse(row[col.Key]?.ToString(), out TimeSpan time))
                        {
                            timeSlots.Add(time);
                        }
                    }
                }

                if (timeSlots.Count == 0) return null;

                var startTime = timeSlots.Min();
                var endTime = timeSlots.Max().Add(TimeSpan.FromHours(1.5));

                int needForAttention = row.Count > 5 && int.TryParse(row[5]?.ToString(), out int n) ? n : 1;

                return new Student(
                    name: name,
                    startOfStudyTime: startTime.ToString(@"hh\:mm"),
                    endOfStudyTime: endTime.ToString(@"hh\:mm"),
                    subjectId: subjectId,
                    _NeedForAttention: needForAttention
                );
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Ошибка парсинга студента: {ex.Message}");
                return null;
            }
        }

        public void ExportScheduleToGoogleSheets(object[,] matrix, List<List<Teacher>> combinations)
        {
            try
            {
                string sheetName = "Расписание_" + DateTime.Now.ToString("yyyyMMdd_HHmmss");

                var addRequest = new Request
                {
                    AddSheet = new AddSheetRequest { Properties = new SheetProperties { Title = sheetName } }
                };

                var batchUpdateRequest = new BatchUpdateSpreadsheetRequest
                {
                    Requests = new List<Request> { addRequest }
                };

                _service.Spreadsheets.BatchUpdate(batchUpdateRequest, _spreadsheetId).Execute();

                var valueRange = new ValueRange
                {
                    Values = ConvertToValueList(matrix)
                };

                var updateRequest = _service.Spreadsheets.Values.Update(
                    valueRange,
                    _spreadsheetId,
                    $"{sheetName}!A1");

                updateRequest.ValueInputOption = SpreadsheetsResource.ValuesResource.UpdateRequest.ValueInputOptionEnum.RAW;
                updateRequest.Execute();
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
                    row.Add(matrix[i, j]?.ToString() ?? "");
                }
                values.Add(row);
            }
            return values;
        }
    }
}