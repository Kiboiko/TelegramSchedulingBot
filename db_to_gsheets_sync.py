# db_to_gsheets_sync.py (исправленная версия)
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import traceback
from config import SUBJECTS

logger = logging.getLogger(__name__)


class DBToGSheetsSyncer:
    def __init__(self, db, gsheets_manager, bot):
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
        """Синхронизация пользователей в лист 'Пользователи бот' - СОХРАНЯЕМ СТРУКТУРУ"""
        try:
            logger.info("🔄 Синхронизация пользователей...")

            if not self.gsheets:
                logger.warning("Google Sheets не подключен")
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

                # Получаем лист БЕЗ очистки
                worksheet = self.gsheets._get_or_create_users_worksheet()
                data = worksheet.get_all_values()

                # Если лист пустой, создаем базовую структуру
                if not data or len(data) == 0:
                    headers = ["user_id", "user_name", "roles", "teacher_subjects", "student_subjects",
                               "parent_children"]
                    worksheet.append_row(headers)
                    data = [headers]

                # Создаем карту существующих пользователей по user_id
                existing_users = {}
                header_row = data[0]

                # Находим индексы колонок
                user_id_col = self._find_column_index(header_row, "user_id")
                user_name_col = self._find_column_index(header_row, "user_name")
                roles_col = self._find_column_index(header_row, "roles")
                teacher_subjects_col = self._find_column_index(header_row, "teacher_subjects")
                student_subjects_col = self._find_column_index(header_row, "student_subjects")
                parent_children_col = self._find_column_index(header_row, "parent_children")

                if user_id_col == -1:
                    logger.error("Столбец user_id не найден в листе пользователей")
                    return

                # Собираем существующих пользователей
                for i, row in enumerate(data[1:], start=2):
                    if len(row) > user_id_col and row[user_id_col]:
                        existing_users[row[user_id_col]] = {
                            'row_index': i,
                            'row_data': row
                        }

                # Обновляем или добавляем пользователей
                for user in users:
                    user_id = str(user['user_id'])
                    user_name = user['user_name'] or ""
                    roles = user['roles'] or ""

                    # Получаем дополнительные данные
                    teacher_subjects = []
                    if 'teacher' in roles:
                        teacher_subjects = await self.db.get_teacher_subjects(user['user_id'])

                    student_subjects = []
                    if 'student' in roles:
                        async with conn:
                            student_records = await conn.fetch(
                                "SELECT subject_id FROM students WHERE user_id = $1",
                                user['user_id']
                            )
                            student_subjects = [record['subject_id'] for record in student_records]

                    parent_children = []
                    if 'parent' in roles:
                        parent_children = await self.db.get_parent_children_sync(user['user_id'])

                    # Подготавливаем строку
                    row_data = [''] * len(header_row)
                    if user_id_col != -1:
                        row_data[user_id_col] = user_id
                    if user_name_col != -1:
                        row_data[user_name_col] = user_name
                    if roles_col != -1:
                        row_data[roles_col] = roles
                    if teacher_subjects_col != -1:
                        row_data[teacher_subjects_col] = ','.join(teacher_subjects)
                    if student_subjects_col != -1:
                        row_data[student_subjects_col] = ','.join(student_subjects)
                    if parent_children_col != -1:
                        row_data[parent_children_col] = ','.join(map(str, parent_children))

                    # Обновляем существующую строку или добавляем новую
                    if user_id in existing_users:
                        # Обновляем существующую строку
                        row_index = existing_users[user_id]['row_index']
                        worksheet.update(f'A{row_index}', [row_data])
                        logger.debug(f"Обновлен пользователь: {user_id} - {user_name}")
                    else:
                        # Добавляем новую строку
                        worksheet.append_row(row_data)
                        logger.debug(f"Добавлен пользователь: {user_id} - {user_name}")

                logger.info(f"✅ Синхронизировано {len(users)} пользователей")

        except Exception as e:
            logger.error(f"Ошибка синхронизации пользователей: {e}")
            logger.error(traceback.format_exc())

    async def sync_students_to_gsheets(self):
        """Синхронизация студентов в лист 'Ученики бот' - ТОЛЬКО ОБНОВЛЕНИЕ ДАННЫХ"""
        try:
            logger.info("🔄 Синхронизация студентов (обновление данных)...")

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

                # Получаем лист БЕЗ очистки
                worksheet = self.gsheets._get_or_create_worksheet("Ученики бот")
                data = worksheet.get_all_values()

                if len(data) < 2:  # Только заголовки или пусто
                    logger.warning("Лист 'Ученики бот' почти пустой, пропускаем синхронизацию")
                    return

                # Получаем заголовки
                headers = [str(h).strip() for h in data[0]]

                # Находим индексы нужных колонок
                col_indices = {
                    'id': self._find_column_index(headers, "ID"),
                    'name': self._find_column_index(headers, "Имя"),
                    'subject_id': self._find_column_index(headers, "Предмет ID"),
                    'subject': self._find_column_index(headers, "Предмет"),
                    'class': self._find_column_index(headers, "Класс"),
                    'attention': self._find_column_index(headers, "Потребность во внимании"),
                    'balance': self._find_column_index(headers, "Баланс"),
                    'tariff': self._find_column_index(headers, "Тариф")
                }

                # Создаем карту студентов по ID+Subject для быстрого поиска
                student_map = {}
                for i, row in enumerate(data[1:], start=2):
                    if len(row) > col_indices['id'] and len(row) > col_indices['subject_id']:
                        student_id = str(row[col_indices['id']]).strip()
                        subject_id = str(row[col_indices['subject_id']]).strip() if col_indices[
                                                                                        'subject_id'] != -1 else ""
                        if student_id and subject_id:
                            key = f"{student_id}_{subject_id}"
                            student_map[key] = {
                                'row_index': i,
                                'row_data': row
                            }

                # Обновляем или добавляем студентов
                updated_count = 0
                added_count = 0

                for student in students:
                    user_id = str(student['user_id'])
                    subject_id = student['subject_id'] or ""
                    key = f"{user_id}_{subject_id}"

                    # Подготавливаем обновленные значения
                    updates = {}

                    # Только обновляем базовые данные, если колонки существуют
                    if col_indices['id'] != -1:
                        # ID обычно уже есть, но на всякий случай
                        pass

                    if col_indices['name'] != -1:
                        updates[col_indices['name']] = student['user_name'] or ""

                    if col_indices['subject'] != -1:
                        updates[col_indices['subject']] = student['subject_name'] or ""

                    if col_indices['class'] != -1 and student['class']:
                        updates[col_indices['class']] = str(student['class'])

                    if col_indices['attention'] != -1 and student['attention_need']:
                        updates[col_indices['attention']] = str(student['attention_need'])

                    if col_indices['balance'] != -1 and student['balance']:
                        updates[col_indices['balance']] = str(float(student['balance'] or 0))

                    if col_indices['tariff'] != -1 and student['tariff']:
                        updates[col_indices['tariff']] = str(float(student['tariff'] or 0))

                    # Если студент уже есть в таблице - обновляем
                    if key in student_map:
                        row_index = student_map[key]['row_index']
                        existing_row = student_map[key]['row_data']

                        # Создаем обновленную строку
                        updated_row = existing_row.copy()
                        for col_idx, value in updates.items():
                            if col_idx < len(updated_row):
                                updated_row[col_idx] = value

                        # Обновляем только изменившиеся ячейки
                        if updated_row != existing_row:
                            # Преобразуем в диапазон A1
                            start_col = chr(65)  # 'A'
                            end_col = chr(65 + len(updated_row) - 1)  # Последняя колонка
                            range_str = f"{start_col}{row_index}:{end_col}{row_index}"
                            worksheet.update(range_str, [updated_row])
                            updated_count += 1
                            logger.debug(f"Обновлен студент: {user_id} предмет {subject_id}")

                    # Иначе - добавляем новую строку (редкий случай)
                    else:
                        # Создаем новую строку
                        new_row = [''] * len(headers)

                        # Заполняем обязательные поля
                        if col_indices['id'] != -1:
                            new_row[col_indices['id']] = user_id
                        if col_indices['subject_id'] != -1:
                            new_row[col_indices['subject_id']] = subject_id

                        # Заполняем остальные поля
                        for col_idx, value in updates.items():
                            if col_idx < len(new_row):
                                new_row[col_idx] = value

                        worksheet.append_row(new_row)
                        added_count += 1
                        logger.debug(f"Добавлен студент: {user_id} предмет {subject_id}")

                logger.info(f"✅ Обновлено студентов: {updated_count}, добавлено: {added_count}")

        except Exception as e:
            logger.error(f"Ошибка синхронизации студентов: {e}")
            logger.error(traceback.format_exc())

    async def sync_teachers_to_gsheets(self):
        """Синхронизация преподавателей в лист 'Преподаватели бот' - ТОЛЬКО ОБНОВЛЕНИЕ"""
        try:
            logger.info("🔄 Синхронизация преподавателей (обновление данных)...")

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

                # Получаем лист БЕЗ очистки
                worksheet = self.gsheets._get_or_create_worksheet("Преподаватели бот")
                data = worksheet.get_all_values()

                if len(data) < 2:
                    logger.warning("Лист 'Преподаватели бот' почти пустой, пропускаем синхронизацию")
                    return

                # Получаем заголовки
                headers = [str(h).strip() for h in data[0]]

                # Находим индексы нужных колонок
                col_indices = {
                    'id': self._find_column_index(headers, "ID"),
                    'name': self._find_column_index(headers, "Имя"),
                    'subjects': self._find_column_index(headers, "Предметы ID"),
                    'priority': self._find_column_index(headers, "Приоритет")
                }

                # Создаем карту преподавателей по ID
                teacher_map = {}
                for i, row in enumerate(data[1:], start=2):
                    if len(row) > col_indices['id']:
                        teacher_id = str(row[col_indices['id']]).strip()
                        if teacher_id:
                            teacher_map[teacher_id] = {
                                'row_index': i,
                                'row_data': row
                            }

                # Обновляем преподавателей
                updated_count = 0

                for teacher in teachers:
                    teacher_id = str(teacher['user_id'])

                    # Подготавливаем обновления
                    updates = {}

                    if col_indices['name'] != -1:
                        updates[col_indices['name']] = teacher['user_name'] or ""

                    if col_indices['subjects'] != -1:
                        updates[col_indices['subjects']] = teacher['subjects_ids'] or ""

                    if col_indices['priority'] != -1:
                        updates[col_indices['priority']] = teacher['priority'] or ""

                    # Если преподаватель уже есть - обновляем
                    if teacher_id in teacher_map:
                        row_index = teacher_map[teacher_id]['row_index']
                        existing_row = teacher_map[teacher_id]['row_data']

                        # Создаем обновленную строку
                        updated_row = existing_row.copy()
                        for col_idx, value in updates.items():
                            if col_idx < len(updated_row):
                                updated_row[col_idx] = value

                        # Обновляем только изменившиеся ячейки
                        if updated_row != existing_row:
                            # Преобразуем в диапазон A1
                            start_col = chr(65)  # 'A'
                            end_col = chr(65 + len(updated_row) - 1)
                            range_str = f"{start_col}{row_index}:{end_col}{row_index}"
                            worksheet.update(range_str, [updated_row])
                            updated_count += 1
                            logger.debug(f"Обновлен преподаватель: {teacher_id}")

                    # Иначе - добавляем новую строку
                    else:
                        new_row = [''] * len(headers)

                        # Заполняем обязательные поля
                        if col_indices['id'] != -1:
                            new_row[col_indices['id']] = teacher_id

                        # Заполняем остальные поля
                        for col_idx, value in updates.items():
                            if col_idx < len(new_row):
                                new_row[col_idx] = value

                        worksheet.append_row(new_row)
                        logger.debug(f"Добавлен преподаватель: {teacher_id}")

                logger.info(f"✅ Обновлено преподавателей: {updated_count}")

        except Exception as e:
            logger.error(f"Ошибка синхронизации преподавателей: {e}")
            logger.error(traceback.format_exc())

    async def sync_bookings_to_gsheets(self):
        """Синхронизация бронирований - ТОЛЬКО ВРЕМЯ В РАСПИСАНИИ"""
        try:
            logger.info("🔄 Синхронизация бронирований (только время)...")

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

                # Синхронизируем в оба листа
                await self._update_bookings_in_sheet_safe("Ученики бот", bookings, is_teacher=False)
                await self._update_bookings_in_sheet_safe("Преподаватели бот", bookings, is_teacher=True)

                logger.info(f"✅ Синхронизировано {len(bookings)} бронирований")

        except Exception as e:
            logger.error(f"Ошибка синхронизации бронирований: {e}")
            logger.error(traceback.format_exc())

    async def _update_bookings_in_sheet_safe(self, sheet_name: str, bookings: List[Dict[str, Any]], is_teacher: bool):
        """Безопасное обновление бронирований (только время, не трогаем структуру)"""
        try:
            worksheet = self.gsheets._get_or_create_worksheet(sheet_name)
            data = worksheet.get_all_values()

            if len(data) < 2:
                logger.warning(f"Лист '{sheet_name}' почти пустой, пропускаем обновление бронирований")
                return

            # Получаем заголовки
            headers = [str(h).strip().lower() for h in data[0]]

            # Находим индекс колонки ID
            id_col_name = "id" if is_teacher else "id"
            id_col_idx = self._find_column_index(headers, id_col_name, case_sensitive=False)

            if id_col_idx == -1:
                logger.error(f"Столбец '{id_col_name}' не найден в листе '{sheet_name}'")
                return

            # Для студентов также нужен столбец предмета
            subject_col_idx = -1
            if not is_teacher:
                subject_col_idx = self._find_column_index(headers, "предмет id", case_sensitive=False)
                if subject_col_idx == -1:
                    logger.warning(f"Столбец 'предмет id' не найден для студентов")

            # Создаем карту строк для быстрого поиска
            row_map = {}
            for i, row in enumerate(data[1:], start=2):
                if len(row) > id_col_idx and row[id_col_idx]:
                    user_id = str(row[id_col_idx]).strip()

                    if not is_teacher and subject_col_idx != -1 and len(row) > subject_col_idx:
                        # Для студентов: ключ = user_id + subject_id
                        subject_id = str(row[subject_col_idx]).strip()
                        key = f"{user_id}_{subject_id}"
                    else:
                        # Для преподавателей: ключ = user_id
                        key = user_id

                    row_map[key] = {
                        'row_index': i,
                        'row_data': row
                    }

            # Находим колонки с датами для обновления времени
            date_columns = self._find_date_columns(headers)

            # Фильтруем бронирования по типу пользователя
            filtered_bookings = [b for b in bookings if
                                 (is_teacher and b['user_role'] == 'teacher') or
                                 (not is_teacher and b['user_role'] == 'student')]

            if not filtered_bookings:
                logger.info(f"Нет бронирований для листа '{sheet_name}'")
                return

            # Обновляем время бронирований
            updated_count = 0

            for booking in filtered_bookings:
                user_id = str(booking['user_id'])
                date_obj = booking['date']
                date_str = date_obj.strftime("%d.%m.%Y")

                # Определяем ключ для поиска строки
                if not is_teacher:
                    subject_id = booking['subject_id'] or ""
                    key = f"{user_id}_{subject_id}"
                else:
                    key = user_id

                # Находим строку
                if key not in row_map:
                    logger.debug(f"Не найдена строка для {key} в листе '{sheet_name}'")
                    continue

                row_info = row_map[key]
                row_index = row_info['row_index']

                # Находим колонки для этой даты
                date_cols = date_columns.get(date_str)
                if not date_cols:
                    logger.debug(f"Не найдены колонки для даты {date_str}")
                    continue

                # Обновляем время
                start_time = booking['start_time'].strftime("%H:%M") if booking['start_time'] else ""
                end_time = booking['end_time'].strftime("%H:%M") if booking['end_time'] else ""

                try:
                    # Обновляем только ячейки времени
                    worksheet.update_cell(row_index, date_cols['start_col'] + 1, start_time)
                    worksheet.update_cell(row_index, date_cols['end_col'] + 1, end_time)
                    updated_count += 1
                    logger.debug(f"Обновлено время: {key} {date_str} {start_time}-{end_time}")
                except Exception as e:
                    logger.error(f"Ошибка обновления ячейки: {e}")

            logger.info(f"✅ Обновлено {updated_count} бронирований в листе '{sheet_name}'")

        except Exception as e:
            logger.error(f"Ошибка обновления бронирований в листе '{sheet_name}': {e}")
            logger.error(traceback.format_exc())

    def _find_date_columns(self, headers: List[str]) -> Dict[str, Dict[str, int]]:
        """Находит колонки с датами в заголовках"""
        date_columns = {}

        for i, header in enumerate(headers):
            header_lower = header.lower()

            # Ищем даты в формате DD.MM.YYYY
            import re
            date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', header)
            if date_match:
                date_str = date_match.group(1)

                # Определяем, это колонка "начало" или "конец"
                if 'начало' in header_lower or 'нач' in header_lower:
                    # Ищем соответствующую колонку "конец"
                    end_col = -1
                    for j in range(i + 1, min(i + 3, len(headers))):  # Ищем в следующих 2 колонках
                        if 'конец' in headers[j].lower() or 'кон' in headers[j].lower():
                            end_col = j
                            break

                    if end_col != -1:
                        date_columns[date_str] = {
                            'start_col': i,
                            'end_col': end_col
                        }
                elif 'конец' in header_lower or 'кон' in header_lower:
                    # Пропускаем, т.к. обработаем как часть пары
                    continue

        return date_columns

    async def sync_parents_to_gsheets(self):
        """Синхронизация родителей в лист 'Родители бот' - СОХРАНЯЕМ СТРУКТУРУ"""
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

                # Получаем лист БЕЗ очистки
                worksheet = self.gsheets._get_or_create_parents_worksheet()
                data = worksheet.get_all_values()

                # Если лист пустой, создаем базовую структуру
                if not data or len(data) == 0:
                    headers = ["user_id", "user_name", "children_ids"]
                    worksheet.append_row(headers)
                    data = [headers]

                # Находим индексы колонок
                headers = data[0]
                user_id_col = self._find_column_index(headers, "user_id")
                user_name_col = self._find_column_index(headers, "user_name")
                children_col = self._find_column_index(headers, "children_ids")

                if user_id_col == -1:
                    logger.error("Столбец user_id не найден в листе родителей")
                    return

                # Создаем карту существующих родителей
                parent_map = {}
                for i, row in enumerate(data[1:], start=2):
                    if len(row) > user_id_col and row[user_id_col]:
                        parent_map[row[user_id_col]] = {
                            'row_index': i,
                            'row_data': row
                        }

                # Обновляем или добавляем родителей
                for parent in parents:
                    parent_id = str(parent['parent_id'])

                    # Подготавливаем строку
                    row_data = [''] * len(headers)
                    if user_id_col != -1:
                        row_data[user_id_col] = parent_id
                    if user_name_col != -1:
                        row_data[user_name_col] = parent['parent_name'] or ""
                    if children_col != -1:
                        row_data[children_col] = parent['children_ids'] or ""

                    # Обновляем или добавляем
                    if parent_id in parent_map:
                        row_index = parent_map[parent_id]['row_index']
                        worksheet.update(f'A{row_index}', [row_data])
                    else:
                        worksheet.append_row(row_data)

                logger.info(f"✅ Синхронизировано {len(parents)} родителей")

        except Exception as e:
            logger.error(f"Ошибка синхронизации родителей: {e}")

    def _find_column_index(self, headers: List[str], column_name: str, case_sensitive: bool = False) -> int:
        """Находит индекс колонки по имени"""
        search_name = column_name if case_sensitive else column_name.lower()

        for i, header in enumerate(headers):
            header_to_check = header if case_sensitive else header.lower()
            if search_name in header_to_check:
                return i

        return -1

    async def sync_incremental_changes(self):
        """Инкрементальная синхронизация только измененных данных"""
        try:
            if not self.last_sync_time:
                # Первая синхронизация
                return await self.sync_all_data_to_gsheets()

            # Для простоты - всегда синхронизируем все
            # В будущем можно оптимизировать
            return await self.sync_all_data_to_gsheets()

        except Exception as e:
            logger.error(f"Ошибка инкрементальной синхронизации: {e}")
            return False