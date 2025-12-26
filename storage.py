import json
from typing import List, Dict, Any
from datetime import datetime
import logging
import asyncio

logger = logging.getLogger(__name__)


class JSONStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.gsheets = None
        self.db = None  # DatabaseManager

    def set_gsheets_manager(self, gsheets_manager):
        self.gsheets = gsheets_manager

    def set_database_manager(self, db_manager):
        """Устанавливает менеджер базы данных"""
        self.db = db_manager

    def load(self) -> List[Dict[str, Any]]:
        """Загружает данные из JSON файла"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return self._filter_old_bookings(data)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных: {e}")
            return []

    def save(self, data: List[Dict[str, Any]], sync_to_gsheets: bool = True):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if sync_to_gsheets and self.gsheets:
                self._sync_with_gsheets()
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")

    def add_booking(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        """Добавляет новое бронирование"""
        # Сначала сохраняем в БД (если доступна)
        if self.db and self.db.pool:
            try:
                # Используем asyncio для вызова асинхронного метода
                try:
                    loop = asyncio.get_running_loop()
                    # Если цикл уже запущен, создаем задачу (не ждем завершения)
                    loop.create_task(self._add_booking_to_db(booking_data))
                    logger.info("Booking queued for database save")
                except RuntimeError:
                    # Если нет запущенного цикла, создаем новый
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(self._add_booking_to_db(booking_data))
                        if result:
                            booking_data = result
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error saving booking to database: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # Также сохраняем в JSON для обратной совместимости
        bookings = self.load()
        booking_id = booking_data.get('id') or max([b.get('id', 0) for b in bookings] or [0]) + 1
        booking_data['id'] = booking_id

        logger.info(f"Adding booking: {json.dumps(booking_data, ensure_ascii=False)}")

        # Добавляем в локальное хранилище (если еще нет)
        if not any(b.get('id') == booking_id for b in bookings):
            bookings.append(booking_data)
        
        user_id = booking_data.get('user_id')
        date = booking_data.get('date')
        start_time = booking_data.get('start_time')
        end_time = booking_data.get('end_time')
        
        # Для студентов и преподавателей пытаемся обновить Google Sheets (опционально)
        if (hasattr(self, 'gsheets') and self.gsheets and 
            all([user_id, date, start_time, end_time])):
            
            user_role = booking_data.get('user_role')
            
            if user_role == 'student':
                subject_id = booking_data.get('subject')
                if subject_id:
                    # Обновляем ячейку для студента
                    self.update_student_booking_cell(user_id, subject_id, date, start_time, end_time)
            
            elif user_role == 'teacher':
                subjects = booking_data.get('subjects', [])
                if subjects:
                    # Обновляем ячейку для преподавателя
                    self.update_teacher_booking_cell(user_id, subjects, date, start_time, end_time)
        
        # Сохраняем в JSON
        self.save(bookings, sync_to_gsheets=False)  # Не синхронизируем с Google Sheets, т.к. используем БД
        return booking_data

    async def _add_booking_to_db(self, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        """Асинхронный метод для сохранения бронирования в БД"""
        try:
            # Сохраняем пользователя, если его еще нет
            user_id = booking_data.get('user_id')
            user_name = booking_data.get('user_name', '')
            user_role = booking_data.get('user_role', '')
            
            if user_id and user_name:
                # Получаем текущие роли или создаем новую роль
                user = await self.db.get_user(user_id)
                if user:
                    roles = user.get('roles', '')
                    if user_role and user_role not in roles:
                        roles = f"{roles},{user_role}" if roles else user_role
                else:
                    roles = user_role
                
                await self.db.save_or_update_user(user_id, user_name, roles)
            
            # Сохраняем бронирование
            result = await self.db.add_booking(booking_data)
            if result:
                logger.info(f"✅ Booking saved to database: {result.get('id')}")
                return result
            else:
                logger.error("Failed to save booking to database")
                return booking_data
        except Exception as e:
            logger.error(f"Error in _add_booking_to_db: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return booking_data
    
    def update_teacher_booking_cell(self, user_id: int, subjects: List[str], date: str, 
                              start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для преподавателя"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return False
        return self.gsheets.update_teacher_booking_cell(user_id, subjects, date, start_time, end_time)
    
    def _save_bookings(self, bookings: List[Dict[str, Any]], sync_to_gsheets: bool = True):
        """Внутренний метод сохранения"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(bookings, f, ensure_ascii=False, indent=2)
            
            # Всегда синхронизируем, если указано
            if sync_to_gsheets and self.gsheets:
                self._sync_with_gsheets()
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")

    def cancel_booking(self, booking_id: int) -> bool:
        """Отменяет бронирование"""
        bookings = self.load()
        
        booking_to_cancel = None
        for booking in bookings:
            if booking.get('id') == booking_id:
                booking_to_cancel = booking
                break

        if not booking_to_cancel:
            return False
        initial_count = len(bookings)
        bookings = [b for b in bookings if b.get('id') != booking_id]

        if (hasattr(self, 'gsheets') and self.gsheets and booking_to_cancel):
            user_id = booking_to_cancel.get('user_id')
            date = booking_to_cancel.get('date')
            user_role = booking_to_cancel.get('user_role')
            
            if all([user_id, date]):
                if user_role == 'student':
                    subject_id = booking_to_cancel.get('subject')
                    if subject_id:
                        # Очищаем ячейки для студента
                        success = self.gsheets.update_student_booking_cell(
                            user_id, subject_id, date, "", ""
                        )
                elif user_role == 'teacher':
                    subjects = booking_to_cancel.get('subjects', [])
                    if subjects:
                        # Очищаем ячейки для преподавателя
                        success = self.gsheets.update_teacher_booking_cell(
                            user_id, subjects, date, "", ""
                        )

        if len(bookings) < initial_count:
            self.save(bookings)
            return True
        
        return False

    def _filter_old_bookings(self, bookings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Фильтрует старые бронирования"""
        current_time = datetime.now()
        valid_bookings = []

        for booking in bookings:
            try:
                if 'date' not in booking:
                    continue

                if isinstance(booking['date'], str):
                    booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                else:
                    continue

                time_end = datetime.strptime(booking.get('end_time', "00:00"), "%H:%M").time()
                booking_datetime = datetime.combine(booking_date, time_end)

                valid_bookings.append(booking)
            except Exception:
                continue

        return valid_bookings

    def _sync_with_gsheets(self):
        """Синхронизирует с Google Sheets - ЗАКОММЕНТИРОВАНО: Переход на БД"""
        # ЗАКОММЕНТИРОВАНО: Больше не синхронизируем с Google Sheets
        pass
        # if self.gsheets:
        #     try:
        #         bookings = self.load()
        #         logger.info(f"Syncing {len(bookings)} bookings to Google Sheets")
        #         # self.gsheets.update_all_sheets(bookings)
        #     except Exception as e:
        #         logger.error(f"Ошибка синхронизации с Google Sheets: {e}")

    def _get_all_users_with_roles(self) -> List[Dict[str, Any]]:
        """Получает всех пользователей с назначенными ролями"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return []
        
        try:
            worksheet = self.gsheets._get_or_create_users_worksheet()
            records = worksheet.get_all_records()
            
            users_with_roles = []
            for record in records:
                user_id = record.get('user_id')
                user_name = record.get('user_name', '')
                roles_str = record.get('roles', '')
                
                if roles_str and user_id and user_name:
                    roles = [role.strip().lower() for role in roles_str.split(',') if role.strip()]
                    if roles:
                        users_with_roles.append({
                            'user_id': user_id,
                            'user_name': user_name,
                            'roles': roles
                        })
            
            return users_with_roles
        except Exception as e:
            logger.error(f"Error getting users with roles: {e}")
            return []

    def get_user_role(self, user_id: int) -> str:
        """Возвращает роль пользователя"""
        bookings = self.load()
        for booking in bookings:
            if booking.get('user_id') == user_id:
                return booking.get('user_role')
        return None

    def update_user_subjects(self, user_id: int, subjects: List[str]):
        """Обновляет предметы преподавателя"""
        bookings = self.load()
        updated = False

        for booking in bookings:
            if booking.get('user_id') == user_id and booking.get('user_role') == 'teacher':
                booking['subjects'] = subjects
                updated = True

        if updated:
            self.save(bookings)

    def replace_all_bookings(self, new_bookings: List[Dict[str, Any]]):
        valid_bookings = self._filter_old_bookings(new_bookings)
        used_ids = set()

        for booking in valid_bookings:
            if 'id' not in booking or booking['id'] <= 0:
                booking['id'] = max(used_ids or [0]) + 1
            while booking['id'] in used_ids:
                booking['id'] += 1
            used_ids.add(booking['id'])

            # Сохраняем приоритет только для преподавателей
            if booking.get('user_role') == 'teacher' and 'priority' not in booking:
                booking['priority'] = ''

        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(valid_bookings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка при сохранении данных: {e}")

    def get_user_name(self, user_id: int) -> str:
        """Получает ФИО с гарантией отсутствия дубликатов (поддерживает sync вызовы)."""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    import threading
                    result = {}
                    def _runner():
                        try:
                            result['name'] = asyncio.run(self.db.get_user_name_sync(user_id))
                        except Exception as e:
                            logger.error(f"Error running get_user_name in background thread: {e}")
                            result['name'] = ""
                    t = threading.Thread(target=_runner)
                    t.start()
                    t.join()
                    return result.get('name', "")
                except RuntimeError:
                    # Если нет запущенного цикла, создаем новый
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_user_name_sync(user_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting user name from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            name = self.gsheets.get_user_name(user_id)
            return name if name else ""
        return ""

    def get_user_roles(self, user_id: int) -> List[str]:
        """Получает роли пользователя из БД (работает и в sync контексте).

        Если текущий поток уже запускает event loop, мы выполняем корутину в
        отдельном фоновом потоке с помощью asyncio.run, чтобы не возвращать
        пустой список сразу.
        """
        if self.db and self.db.pool:
            try:
                try:
                    # Если цикл уже запущен в текущем потоке, запускаем корутину в новом потоке
                    loop = asyncio.get_running_loop()
                    import threading
                    result = {}
                    def _runner():
                        try:
                            result['roles'] = asyncio.run(self.db.get_user_roles_sync(user_id))
                        except Exception as e:
                            logger.error(f"Error running get_user_roles in background thread: {e}")
                            result['roles'] = []
                    t = threading.Thread(target=_runner)
                    t.start()
                    t.join()
                    return result.get('roles', [])
                except RuntimeError:
                    # Нет запущенного цикла — можно выполнить синхронно
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_user_roles_sync(user_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting user roles from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.get_user_roles(user_id)
        return []

    def has_user_roles(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя назначенные роли (работает и в sync контексте)."""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    import threading
                    result = {}
                    def _runner():
                        try:
                            result['val'] = asyncio.run(self.db.has_user_roles_sync(user_id))
                        except Exception as e:
                            logger.error(f"Error running has_user_roles in background thread: {e}")
                            result['val'] = False
                    t = threading.Thread(target=_runner)
                    t.start()
                    t.join()
                    return bool(result.get('val', False))
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.has_user_roles_sync(user_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error checking user roles from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.has_user_roles(user_id)
        return False

    def save_user_name(self, user_id: int, user_name: str) -> bool:
        """Сохраняет ФИО пользователя"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.db.save_user_info_sync(user_id, user_name))
                    return True
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.save_user_info_sync(user_id, user_name))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error saving user name to DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.save_user_info(user_id, user_name)
        return False

    def save_user_data(self, user_data: dict) -> bool:
        """Сохраняет данные пользователя в БД"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.db.save_user_data_sync(user_data))
                    return True
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.save_user_data_sync(user_data))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error saving user data to DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.save_user_data(user_data)
        return False
    
    def save_user_info(self, user_id: int, user_name: str = None, role: str = None) -> bool:
        """Сохраняет информацию о пользователе в БД"""
        if self.db and self.db.pool:
            try:
                async def _save():
                    # Получаем текущие данные пользователя
                    current_data = await self.db.get_user_data_sync(user_id)
                    
                    # Обновляем только переданные поля
                    if user_name is not None:
                        current_data['user_name'] = user_name
                    if role is not None:
                        roles = current_data.get('roles', '')
                        if role not in roles:
                            roles = f"{roles},{role}" if roles else role
                        current_data['roles'] = roles
                    
                    # Сохраняем обновленные данные
                    return await self.db.save_user_data_sync(current_data)
                
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(_save())
                    return True
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(_save())
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error saving user info to DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            try:
                current_data = self.gsheets.get_user_data(user_id)
                if user_name is not None:
                    current_data['user_name'] = user_name
                if role is not None:
                    current_data['role'] = role
                return self.gsheets.save_user_data(current_data)
            except Exception as e:
                logger.error(f"Error saving user info: {e}")
        return False

    def get_user_data(self, user_id: int) -> dict:
        """Получает все данные пользователя по ID"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    return {}  # Не можем ждать
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        data = loop.run_until_complete(self.db.get_user_data_sync(user_id))
                        # Преобразуем в строки для совместимости
                        result = {}
                        for key, value in data.items():
                            if value is None:
                                result[key] = ""
                            else:
                                result[key] = str(value)
                        return result
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting user data from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            try:
                worksheet = self.gsheets._get_or_create_users_worksheet()
                records = worksheet.get_all_records()

                for record in records:
                    record_user_id = str(record.get("user_id", ""))
                    if record_user_id == str(user_id):
                        result = {}
                        for key, value in record.items():
                            if value is None:
                                result[key] = ""
                            else:
                                result[key] = str(value)
                        
                        if 'teacher_subjects' in result and result['teacher_subjects']:
                            result['subjects'] = [subj.strip() for subj in result['teacher_subjects'].split(',') if subj.strip()]
                        return result
            except Exception as e:
                logger.error(f"Ошибка при получении данных пользователя: {e}")
        return {}
        
    def has_booking_on_date(self, user_id: int, date: str, role: str, subject: str = None) -> bool:
        """Проверяет, есть ли у пользователя бронь на указанную дату в указанной роли и предмете"""
        try:
            bookings = self.load()
            for booking in bookings:
                if (booking.get('user_id') == user_id and 
                    booking.get('date') == date and 
                    booking.get('user_role') == role):
                    
                    # Для учеников проверяем еще и предмет
                    if role == 'student' and subject:
                        if booking.get('subject') == subject:
                            return True
                    else:
                        # Для преподавателей или без указания предмета
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking bookings: {e}")
            return False
        
    def get_teacher_subjects(self, user_id: int) -> List[str]:
        """Получает предметы преподавателя из БД"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    return []  # Не можем ждать
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_teacher_subjects(user_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting teacher subjects from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.get_teacher_subjects(user_id)
        return []
    
    def has_time_conflict(self, user_id: int, date: str, time_start: str, time_end: str, exclude_id: int = None) -> bool:
        """Проверяет пересечение временных интервалов для пользователя"""
        bookings = self.load()
        
        def time_to_minutes(t):
            h, m = map(int, t.split(':'))
            return h * 60 + m

        new_start = time_to_minutes(time_start)
        new_end = time_to_minutes(time_end)

        for booking in bookings:
            if (booking.get('user_id') == user_id and
                booking.get('date') == date and
                booking.get('user_role') == 'student'):
                
                if exclude_id and booking.get('id') == exclude_id:
                    continue

                existing_start = time_to_minutes(booking.get('start_time', '00:00'))
                existing_end = time_to_minutes(booking.get('end_time', '00:00'))

                # Проверяем пересечение временных интервалов
                if not (new_end <= existing_start or new_start >= existing_end):
                    return True
                    
        return False
    
    def get_parent_children(self, parent_id: int) -> List[int]:
        """Получает список ID детей родителя"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    return []  # Не можем ждать
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_parent_children_sync(parent_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting parent children from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.get_parent_children(parent_id)
        return []

    def get_child_info(self, child_id: int) -> dict:
        """Получает информацию о ребенке (ученике)"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    return {}  # Не можем ждать
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_child_info_sync(child_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting child info from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.get_child_info(child_id)
        return {}

    def save_parent_info(self, parent_id: int, parent_name: str, children_ids: List[int] = None) -> bool:
        """Сохраняет информацию о родителе"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.db.save_parent_info_sync(parent_id, parent_name, children_ids))
                    return True
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.save_parent_info_sync(parent_id, parent_name, children_ids))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error saving parent info to DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.save_parent_info(parent_id, parent_name, children_ids)
        return False
    
    def get_available_subjects_for_student(self, user_id: int) -> List[str]:
        """Получает доступные предметы для ученика"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    return []  # Не можем ждать
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_available_subjects_for_student_sync(user_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting available subjects from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.get_available_subjects_for_student(user_id)
        return []

    def update_student_booking_cell(self, user_id: int, subject_id: str, date: str, 
                                start_time: str, end_time: str) -> bool:
        """Обновляет только конкретную ячейку для ученика"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return False
        return self.gsheets.update_student_booking_cell(user_id, subject_id, date, start_time, end_time)
    
    def load_all_bookings(self) -> List[Dict[str, Any]]:
        """Загружает все бронирования без фильтрации по дате"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        except Exception as e:
            logger.error(f"Ошибка при загрузке всех данных: {e}")
            return []
    def get_student_balance(self, student_id: int) -> float:
        """Получает текущий баланс студента"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    return 0.0  # Не можем ждать
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_student_balance_sync(student_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting balance from DB: {e}")
        
        # Fallback на Google Sheets
        try:
            if hasattr(self, 'gsheets') and self.gsheets:
                return self.gsheets.get_student_balance(student_id)
        except Exception as e:
            logger.error(f"Error getting balance for student {student_id}: {e}")
        return 0.0

    def update_student_balance(self, student_id: int, amount: float):
        """Обновляет баланс студента"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.db.update_student_balance_sync(student_id, amount))
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self.db.update_student_balance_sync(student_id, amount))
                    finally:
                        loop.close()
                return
            except Exception as e:
                logger.error(f"Error updating balance in DB: {e}")
        
        # Fallback на Google Sheets
        try:
            if hasattr(self, 'gsheets') and self.gsheets:
                self.gsheets.update_student_balance(student_id, amount)
        except Exception as e:
            logger.error(f"Error updating balance for student {student_id}: {e}")

    def get_student_balance_by_subjects(self, student_id: int) -> Dict[str, float]:
        """Получает баланс студента разбитый по предметам"""
        if self.db and self.db.pool:
            try:
                try:
                    loop = asyncio.get_running_loop()
                    return {}  # Не можем ждать
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.db.get_student_balance_by_subjects_sync(student_id))
                    finally:
                        loop.close()
            except Exception as e:
                logger.error(f"Error getting balance by subjects from DB: {e}")
        
        # Fallback на Google Sheets
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.get_student_balance_by_subjects(student_id)
        return {}