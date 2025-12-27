# db_to_gsheets_sync.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import traceback
from config import SUBJECTS

logger = logging.getLogger(__name__)


class DBToGSheetsSyncer:
    def __init__(self, db, gsheets_manager, bot):
        """
        Инициализация синхронизатора БД → Google Sheets

        Args:
            db: DatabaseManager instance
            gsheets_manager: GoogleSheetsManager instance
            bot: Bot instance
        """
        self.db = db
        self.gsheets = gsheets_manager
        self.bot = bot
        self.last_sync_time = None

    async def sync_all_data_to_gsheets(self):
        """Основной метод синхронизации всех данных из БД в Google Sheets"""
        try:
            logger.info("🔄 Начинаю синхронизацию БД → Google Sheets...")
            start_time = datetime.now()

            # 1. Синхронизация пользователей (лист "Пользователи бот")
            await self.sync_users_to_gsheets()

            # 2. Синхронизация студентов (лист "Ученики бот")
            await self.sync_students_to_gsheets()

            # 3. Синхронизация преподавателей (лист "Преподаватели бот")
            await self.sync_teachers_to_gsheets()

            # 4. Синхронизация бронирований
            await self.sync_bookings_to_gsheets()

            # 5. Синхронизация родителей (лист "Родители бот")
            await self.sync_parents_to_gsheets()

            duration = datetime.now() - start_time
            logger.info(f"✅ Синхронизация завершена за {duration.total_seconds():.2f} секунд")

            self.last_sync_time = datetime.now()
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации: {e}")
            logger.error(traceback.format_exc())
            return False

    async def sync_users_to_gsheets(self):
        """Синхронизация пользователей в лист 'Пользователи бот'"""
        try:
            logger.info("🔄 Синхронизация пользователей...")

            if not self.gsheets or not hasattr(self.gsheets, 'client') or not self.gsheets.client:
                logger.debug("Google Sheets не подключен, пропускаем синхронизацию пользователей")
                return

            async with self.db.pool.acquire() as conn:
                # Получаем всех пользователей из БД
                users = await conn.fetch("""
                    SELECT user_id, user_name, roles, created_at, updated_at 
                    FROM users 
                    ORDER BY user_id
                """)

                if not users:
                    logger.info("Нет пользователей для синхронизации")
                    return

                # Получаем или создаем лист
                worksheet = self.gsheets._get_or_create_users_worksheet()

                # Очищаем лист (оставляем только заголовки)
                worksheet.clear()

                # Заголовки
                headers = ["user_id", "user_name", "roles", "teacher_subjects", "student_subjects", "parent_children"]
                worksheet.append_row(headers)

                # Подготавливаем данные
                rows = []
                for user in users:
                    user_id = user['user_id']
                    user_name = user['user_name'] or ""
                    roles = user['roles'] or ""

                    # Получаем предметы преподавателя
                    teacher_subjects = []
                    if 'teacher' in roles:
                        teacher_subjects = await self.db.get_teacher_subjects(user_id)

                    # Получаем предметы студента
                    student_subjects = []
                    if 'student' in roles:
                        async with conn:
                            student_records = await conn.fetch(
                                "SELECT subject_id FROM students WHERE user_id = $1",
                                user_id
                            )
                            student_subjects = [record['subject_id'] for record in student_records]

                    # Получаем детей родителя
                    parent_children = []
                    if 'parent' in roles:
                        parent_children = await self.db.get_parent_children_sync(user_id)

                    rows.append([
                        str(user_id),
                        user_name,
                        roles,
                        ','.join(teacher_subjects),
                        ','.join(student_subjects),
                        ','.join(map(str, parent_children))
                    ])

                # Добавляем данные
                if rows:
                    worksheet.append_rows(rows)

                logger.info(f"✅ Синхронизировано {len(users)} пользователей")

        except Exception as e:
            logger.error(f"Ошибка синхронизации пользователей: {e}")

    async def sync_students_to_gsheets(self):
        """Синхронизация студентов в лист 'Ученики бот' (основная таблица)"""
        try:
            logger.info("🔄 Синхронизация студентов...")

            if not self.gsheets:
                logger.warning("Google Sheets не подключен")
                return

            async with self.db.pool.acquire() as conn:
                # Получаем всех студентов с их данными
                students = await conn.fetch("""
                    SELECT 
                        s.user_id,
                        u.user_name,
                        s.subject_id,
                        subj.subject_name,
                        s.class,
                        s.attention_need,
                        s.balance,
                        s.tariff,
                        s.created_at,
                        s.updated_at
                    FROM students s
                    JOIN users u ON s.user_id = u.user_id
                    LEFT JOIN subjects subj ON s.subject_id = subj.subject_id
                    ORDER BY s.user_id, s.subject_id
                """)

                if not students:
                    logger.info("Нет студентов для синхронизации")
                    return

                # Получаем или создаем лист
                worksheet = self.gsheets._get_or_create_worksheet("Ученики бот")

                # Очищаем лист
                worksheet.clear()

                # Создаем заголовки для таблицы
                # Структура: ID, Имя, Предмет ID, Предмет, Класс, Потребность во внимании, Баланс, Тариф
                headers = [
                    "ID", "Имя", "Предмет ID", "Предмет", "Класс",
                    "Потребность во внимании (мин)", "Баланс", "Тариф"
                ]

                # Добавляем даты для расписания (текущая неделя + 2 недели вперед)
                from datetime import datetime, timedelta
                today = datetime.now().date()

                date_headers = []
                for i in range(0, 21):  # 3 недели
                    current_date = today + timedelta(days=i)
                    if current_date.weekday() < 5:  # Только будни
                        date_str = current_date.strftime("%d.%m.%Y")
                        date_headers.extend([f"{date_str} начало", f"{date_str} конец"])

                headers.extend(date_headers)
                worksheet.append_row(headers)

                # Подготавливаем данные
                rows = []
                for student in students:
                    row = [
                        str(student['user_id']),
                        student['user_name'] or "",
                        student['subject_id'] or "",
                        student['subject_name'] or "",
                        student['class'] or "",
                        student['attention_need'] or "",
                        float(student['balance'] or 0),
                        float(student['tariff'] or 0)
                    ]

                    # Добавляем пустые ячейки для дат (будут заполнены бронированиями позже)
                    row.extend([''] * len(date_headers))

                    rows.append(row)

                # Добавляем данные
                if rows:
                    worksheet.append_rows(rows)

                logger.info(f"✅ Синхронизировано {len(students)} записей студентов")

        except Exception as e:
            logger.error(f"Ошибка синхронизации студентов: {e}")
            logger.error(traceback.format_exc())

    async def sync_teachers_to_gsheets(self):
        """Синхронизация преподавателей в лист 'Преподаватели бот'"""
        try:
            logger.info("🔄 Синхронизация преподавателей...")

            if not self.gsheets:
                logger.warning("Google Sheets не подключен")
                return

            async with self.db.pool.acquire() as conn:
                # Получаем всех преподавателей
                teachers = await conn.fetch("""
                    SELECT DISTINCT 
                        t.user_id,
                        u.user_name,
                        STRING_AGG(t.subject_id, ',') as subjects_ids,
                        t.priority
                    FROM teachers t
                    JOIN users u ON t.user_id = u.user_id
                    GROUP BY t.user_id, u.user_name, t.priority
                    ORDER BY t.user_id
                """)

                if not teachers:
                    logger.info("Нет преподавателей для синхронизации")
                    return

                # Получаем или создаем лист
                worksheet = self.gsheets._get_or_create_worksheet("Преподаватели бот")

                # Очищаем лист
                worksheet.clear()

                # Создаем заголовки
                headers = ["ID", "Имя", "Предметы ID", "Приоритет"]

                # Добавляем даты для расписания
                from datetime import datetime, timedelta
                today = datetime.now().date()

                date_headers = []
                for i in range(0, 21):  # 3 недели
                    current_date = today + timedelta(days=i)
                    if current_date.weekday() < 5:  # Только будни
                        date_str = current_date.strftime("%d.%m.%Y")
                        date_headers.extend([f"{date_str} начало", f"{date_str} конец"])

                headers.extend(date_headers)
                worksheet.append_row(headers)

                # Подготавливаем данные
                rows = []
                for teacher in teachers:
                    row = [
                        str(teacher['user_id']),
                        teacher['user_name'] or "",
                        teacher['subjects_ids'] or "",
                        teacher['priority'] or ""
                    ]

                    # Добавляем пустые ячейки для дат
                    row.extend([''] * len(date_headers))

                    rows.append(row)

                # Добавляем данные
                if rows:
                    worksheet.append_rows(rows)

                logger.info(f"✅ Синхронизировано {len(teachers)} преподавателей")

        except Exception as e:
            logger.error(f"Ошибка синхронизации преподавателей: {e}")

    async def sync_bookings_to_gsheets(self):
        """Синхронизация бронирований в Google Sheets"""
        try:
            logger.info("🔄 Синхронизация бронирований...")

            if not self.gsheets:
                logger.warning("Google Sheets не подключен")
                return

            async with self.db.pool.acquire() as conn:
                # Получаем все активные бронирования
                bookings = await conn.fetch("""
                    SELECT 
                        b.booking_id,
                        b.user_id,
                        b.user_role,
                        b.date,
                        b.start_time,
                        b.end_time,
                        b.subject_id,
                        b.subjects,
                        u.user_name,
                        s.subject_name
                    FROM bookings b
                    JOIN users u ON b.user_id = u.user_id
                    LEFT JOIN subjects s ON b.subject_id = s.subject_id
                    WHERE b.date >= CURRENT_DATE
                    ORDER BY b.date, b.start_time
                """)

                if not bookings:
                    logger.info("Нет активных бронирований для синхронизации")
                    return

                # Сначала загружаем существующие данные из листов
                await self._update_bookings_in_sheet("Ученики бот", bookings, is_teacher=False)
                await self._update_bookings_in_sheet("Преподаватели бот", bookings, is_teacher=True)

                logger.info(f"✅ Синхронизировано {len(bookings)} бронирований")

        except Exception as e:
            logger.error(f"Ошибка синхронизации бронирований: {e}")
            logger.error(traceback.format_exc())

    async def _update_bookings_in_sheet(self, sheet_name: str, bookings: List[Dict[str, Any]], is_teacher: bool):
        """Обновляет бронирования в указанном листе"""
        try:
            worksheet = self.gsheets._get_or_create_worksheet(sheet_name)
            data = worksheet.get_all_values()

            if len(data) < 2:  # Только заголовки
                logger.warning(f"Лист '{sheet_name}' пустой или содержит только заголовки")
                return

            # Получаем заголовки
            headers = [str(h).strip().lower() for h in data[0]]

            # Создаем карту дат для быстрого поиска колонок
            date_columns = {}
            for i, header in enumerate(headers):
                if 'начало' in header:
                    # Извлекаем дату из заголовка
                    date_part = header.replace('начало', '').strip()
                    date_columns[date_part] = {
                        'start_col': i,
                        'end_col': i + 1 if 'конец' in headers[i + 1].lower() else i + 1
                    }

            # Фильтруем бронирования по типу пользователя
            filtered_bookings = [b for b in bookings if
                                 (is_teacher and b['user_role'] == 'teacher') or
                                 (not is_teacher and b['user_role'] == 'student')]

            if not filtered_bookings:
                logger.info(f"Нет бронирований для листа '{sheet_name}'")
                return

            # Для каждого бронирования находим строку и обновляем ячейки
            for booking in filtered_bookings:
                user_id = str(booking['user_id'])
                date_obj = booking['date']
                date_str = date_obj.strftime("%d.%m.%Y")

                # Находим строку пользователя
                row_index = -1
                for i, row in enumerate(data[1:], start=2):  # Пропускаем заголовок
                    if row and len(row) > 0 and str(row[0]).strip() == user_id:
                        # Для студентов проверяем еще предмет
                        if not is_teacher:
                            subject_id = booking['subject_id']
                            if len(row) > 2 and str(row[2]).strip() == str(subject_id):
                                row_index = i
                                break
                        else:
                            row_index = i
                            break

                if row_index == -1:
                    logger.warning(f"Не найдена строка для user_id {user_id} в листе '{sheet_name}'")
                    continue

                # Находим колонку для даты
                if date_str in date_columns:
                    start_col = date_columns[date_str]['start_col']
                    end_col = date_columns[date_str]['end_col']

                    # Обновляем время
                    start_time = booking['start_time'].strftime("%H:%M") if booking['start_time'] else ""
                    end_time = booking['end_time'].strftime("%H:%M") if booking['end_time'] else ""

                    try:
                        worksheet.update_cell(row_index, start_col + 1, start_time)
                        worksheet.update_cell(row_index, end_col + 1, end_time)
                        logger.debug(f"Обновлено бронирование: {user_id} {date_str} {start_time}-{end_time}")
                    except Exception as e:
                        logger.error(f"Ошибка обновления ячейки: {e}")
                else:
                    logger.warning(f"Дата {date_str} не найдена в заголовках листа '{sheet_name}'")

        except Exception as e:
            logger.error(f"Ошибка обновления бронирований в листе '{sheet_name}': {e}")
            logger.error(traceback.format_exc())

    async def sync_parents_to_gsheets(self):
        """Синхронизация родителей в лист 'Родители бот'"""
        try:
            logger.info("🔄 Синхронизация родителей...")

            if not self.gsheets:
                logger.warning("Google Sheets не подключен")
                return

            async with self.db.pool.acquire() as conn:
                # Получаем всех родителей с их детьми
                parents = await conn.fetch("""
                    SELECT DISTINCT 
                        p.user_id as parent_id,
                        pu.user_name as parent_name,
                        STRING_AGG(CAST(pc.child_id AS TEXT), ',') as children_ids
                    FROM parent_children pc
                    JOIN users p ON pc.parent_id = p.user_id
                    JOIN users pu ON p.user_id = pu.user_id
                    WHERE 'parent' IN (SELECT unnest(string_to_array(p.roles, ',')))
                    GROUP BY p.user_id, pu.user_name
                    ORDER BY p.user_id
                """)

                if not parents:
                    logger.info("Нет родителей для синхронизации")
                    return

                # Получаем или создаем лист
                worksheet = self.gsheets._get_or_create_parents_worksheet()

                # Очищаем лист
                worksheet.clear()

                # Заголовки
                headers = ["user_id", "user_name", "children_ids"]
                worksheet.append_row(headers)

                # Подготавливаем данные
                rows = []
                for parent in parents:
                    rows.append([
                        str(parent['parent_id']),
                        parent['parent_name'] or "",
                        parent['children_ids'] or ""
                    ])

                # Добавляем данные
                if rows:
                    worksheet.append_rows(rows)

                logger.info(f"✅ Синхронизировано {len(parents)} родителей")

        except Exception as e:
            logger.error(f"Ошибка синхронизации родителей: {e}")

    async def sync_incremental_changes(self):
        """Инкрементальная синхронизация только измененных данных"""
        try:
            if not self.last_sync_time:
                # Первая синхронизация - синхронизируем все
                logger.info("Первая синхронизация, загружаем все данные...")
                return await self.sync_all_data_to_gsheets()

            logger.info(f"🔄 Инкрементальная синхронизация с {self.last_sync_time}...")

            async with self.db.pool.acquire() as conn:
                # Получаем измененных пользователей
                changed_users = await conn.fetch("""
                    SELECT user_id FROM users 
                    WHERE updated_at > $1 OR created_at > $1
                """, self.last_sync_time)

                # Получаем новые/измененные бронирования
                changed_bookings = await conn.fetch("""
                    SELECT booking_id FROM bookings
                    WHERE updated_at > $1 OR created_at > $1
                """, self.last_sync_time)

                # Получаем измененных студентов
                changed_students = await conn.fetch("""
                    SELECT user_id FROM students
                    WHERE updated_at > $1 OR created_at > $1
                """, self.last_sync_time)

                # Получаем измененных преподавателей
                changed_teachers = await conn.fetch("""
                    SELECT user_id FROM teachers
                    WHERE updated_at > $1 OR created_at > $1
                """, self.last_sync_time)

                if not any([changed_users, changed_bookings, changed_students, changed_teachers]):
                    logger.info("Нет изменений для инкрементальной синхронизации")
                    return False

                # Обновляем все данные, так как изменения могут быть в любом месте
                logger.info(f"Обнаружены изменения: "
                            f"пользователей={len(changed_users)}, "
                            f"бронирований={len(changed_bookings)}, "
                            f"студентов={len(changed_students)}, "
                            f"преподавателей={len(changed_teachers)}")

                await self.sync_all_data_to_gsheets()

                self.last_sync_time = datetime.now()
                return True

        except Exception as e:
            logger.error(f"Ошибка инкрементальной синхронизации: {e}")
            return False

    async def debug_gsheets_structure(self):
        """Отладочный метод для проверки структуры Google Sheets"""
        try:
            logger.info("=== ОТЛАДКА СТРУКТУРЫ GOOGLE SHEETS ===")

            if not self.gsheets:
                logger.warning("Google Sheets не подключен")
                return

            # Проверяем листы
            sheet_names = [ws.title for ws in self.gsheets.spreadsheet.worksheets()]
            logger.info(f"Доступные листы: {sheet_names}")

            for sheet_name in ['Ученики бот', 'Преподаватели бот', 'Пользователи бот', 'Родители бот']:
                try:
                    worksheet = self.gsheets.spreadsheet.worksheet(sheet_name)
                    data = worksheet.get_all_values()
                    logger.info(f"Лист '{sheet_name}': {len(data)} строк, {len(data[0]) if data else 0} столбцов")

                    if data and len(data) > 0:
                        logger.info(f"  Заголовки: {data[0]}")
                        if len(data) > 1:
                            logger.info(f"  Первая строка данных: {data[1]}")
                except Exception as e:
                    logger.warning(f"Лист '{sheet_name}' не найден или ошибка: {e}")

        except Exception as e:
            logger.error(f"Ошибка при отладке структуры: {e}")