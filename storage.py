import json
from typing import List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JSONStorage:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.gsheets = None

    def set_gsheets_manager(self, gsheets_manager):
        self.gsheets = gsheets_manager

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
        bookings = self.load()
        booking_id = max([b.get('id', 0) for b in bookings] or [0]) + 1
        booking_data['id'] = booking_id

        # ДЕБАГ: Логируем данные перед сохранением
        logger.info(f"Adding booking: {json.dumps(booking_data, ensure_ascii=False)}")

        bookings.append(booking_data)
        self.save(bookings)
        return booking_data

    def cancel_booking(self, booking_id: int) -> bool:
        """Отменяет бронирование"""
        bookings = self.load()
        initial_count = len(bookings)
        bookings = [b for b in bookings if b.get('id') != booking_id]

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

                if booking_datetime >= current_time:
                    valid_bookings.append(booking)
            except Exception:
                continue

        return valid_bookings

    def _sync_with_gsheets(self):
        """Синхронизирует с Google Sheets"""
        if self.gsheets:
            try:
                bookings = self.load()
                # ДЕБАГ: Логируем что отправляем в Google Sheets
                logger.info(f"Syncing {len(bookings)} bookings to Google Sheets")
                for booking in bookings:
                    if booking.get('user_role') == 'teacher':
                        logger.info(f"Teacher booking subjects: {booking.get('subjects')}")

                self.gsheets.update_all_sheets(bookings)
            except Exception as e:
                logger.error(f"Ошибка синхронизации с Google Sheets: {e}")

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
        """Получает ФИО с гарантией отсутствия дубликатов"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return ""
        
        # Двойная проверка через API и кеширование
        name = self.gsheets.get_user_name(user_id)
        return name if name else ""

    def get_user_roles(self, user_id: int) -> List[str]:
        """Получает роли пользователя из Google Sheets"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return []
        return self.gsheets.get_user_roles(user_id)

    def has_user_roles(self, user_id: int) -> bool:
        """Проверяет, есть ли у пользователя назначенные роли"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return False
        return self.gsheets.has_user_roles(user_id)

    def save_user_name(self, user_id: int, user_name: str) -> bool:
        """Сохраняет ФИО пользователя"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return False
        return self.gsheets.save_user_info(user_id, user_name)

    def save_user_data(self, user_data: dict) -> bool:
        """Сохраняет данные пользователя в Google Sheets"""
        if hasattr(self, 'gsheets') and self.gsheets:
            return self.gsheets.save_user_data(user_data)
        return False
    
    def save_user_info(self, user_id: int, user_name: str = None, role: str = None) -> bool:
        """Сохраняет информацию о пользователе в Google Sheets"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return False
        
        try:
            # Получаем текущие данные пользователя
            current_data = self.gsheets.get_user_data(user_id)
            
            # Обновляем только переданные поля
            if user_name is not None:
                current_data['user_name'] = user_name
            if role is not None:
                current_data['role'] = role
            
            # Сохраняем обновленные данные
            return self.gsheets.save_user_data(current_data)
        except Exception as e:
            logger.error(f"Error saving user info: {e}")
            return False

    def get_user_data(self, user_id: int) -> dict:
        """Получает все данные пользователя по ID"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return {}
        
        try:
            worksheet = self.gsheets._get_or_create_users_worksheet()
            records = worksheet.get_all_records()

            for record in records:
                # Преобразуем user_id к строке для сравнения
                record_user_id = str(record.get("user_id", ""))
                if record_user_id == str(user_id):
                    # Преобразуем все значения в строки и обрабатываем предметы
                    result = {}
                    for key, value in record.items():
                        if value is None:
                            result[key] = ""
                        else:
                            result[key] = str(value)
                    
                    # Обрабатываем предметы преподавателя
                    if 'teacher_subjects' in result and result['teacher_subjects']:
                        result['subjects'] = [subj.strip() for subj in result['teacher_subjects'].split(',') if subj.strip()]
                    return result
            return {}
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
        """Получает предметы преподавателя из Google Sheets"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return []
        return self.gsheets.get_teacher_subjects(user_id)
    
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
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return []
        return self.gsheets.get_parent_children(parent_id)

    def get_child_info(self, child_id: int) -> dict:
        """Получает информацию о ребенке (ученике)"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return {}
        return self.gsheets.get_child_info(child_id)

    def save_parent_info(self, parent_id: int, parent_name: str, children_ids: List[int] = None) -> bool:
        """Сохраняет информацию о родителе"""
        if not hasattr(self, 'gsheets') or not self.gsheets:
            return False
        return self.gsheets.save_parent_info(parent_id, parent_name, children_ids)