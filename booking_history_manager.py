# booking_history_manager.py
import json
import logging
from datetime import datetime, time,timedelta
from typing import Dict, Optional, Any
import os

logger = logging.getLogger(__name__)

class BookingHistoryManager:
    def __init__(self, file_path: str = "booking_history.json"):
        self.file_path = file_path
        self.history_data = self._load_history()

    def _load_history(self) -> Dict[str, Any]:
        """Загружает историю бронирований из файла"""
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Создаем файл с базовой структурой
                base_structure = {
                    "user_booking_history": {},
                    "child_booking_history": {}
                }
                self._save_history(base_structure)
                return base_structure
        except Exception as e:
            logger.error(f"Ошибка загрузки истории бронирований: {e}")
            return {"user_booking_history": {}, "child_booking_history": {}}

    def _save_history(self, data: Dict[str, Any] = None):
        """Сохраняет историю бронирований в файл"""
        try:
            if data is None:
                data = self.history_data
            
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения истории бронирований: {e}")

    def get_last_booking_time(self, user_id: int, subject_id: str = None, is_child: bool = False) -> Optional[Dict[str, str]]:
        """Получает последнее время бронирования для пользователя или ребенка"""
        try:
            history_key = "child_booking_history" if is_child else "user_booking_history"
            user_key = str(user_id)
            
            if subject_id:
                user_key = f"{user_key}_{subject_id}"
            
            if user_key in self.history_data[history_key]:
                return self.history_data[history_key][user_key]
            return None
        except Exception as e:
            logger.error(f"Ошибка получения последнего времени бронирования: {e}")
            return None

    def save_booking_time(self, user_id: int, subject_id: str, start_time: str, end_time: str, 
                         is_child: bool = False, date: str = None):
        """Сохраняет время бронирования в историю"""
        try:
            history_key = "child_booking_history" if is_child else "user_booking_history"
            user_key = str(user_id)
            
            if subject_id:
                user_key = f"{user_key}_{subject_id}"
            
            booking_data = {
                "start_time": start_time,
                "end_time": end_time,
                "last_used": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            if date:
                booking_data["date"] = date
            
            self.history_data[history_key][user_key] = booking_data
            self._save_history()
            
            logger.info(f"Сохранено время бронирования для {user_key}: {start_time}-{end_time}")
        except Exception as e:
            logger.error(f"Ошибка сохранения времени бронирования: {e}")

    def get_suggested_time(self, user_id: int, subject_id: str, selected_date, 
                          is_child: bool = False) -> Dict[str, str]:
        """Получает предложенное время с учетом рабочего дня"""
        last_booking = self.get_last_booking_time(user_id, subject_id, is_child)
        
        if not last_booking:
            return {"start_time": None, "end_time": None}
        
        start_time_str = last_booking.get("start_time")
        end_time_str = last_booking.get("end_time")
        
        if not start_time_str or not end_time_str:
            return {"start_time": None, "end_time": None}
        
        # Получаем рабочие часы для выбранной даты
        from time_utils import get_time_range_for_date
        start_time_range, end_time_range, _ = get_time_range_for_date(selected_date)
        
        # Преобразуем строки времени в объекты time
        try:
            start_time_obj = datetime.strptime(start_time_str, "%H:%M").time()
            end_time_obj = datetime.strptime(end_time_str, "%H:%M").time()
            
            # Проверяем, что время начала в пределах рабочего дня
            if start_time_obj < start_time_range:
                start_time_obj = start_time_range
            elif start_time_obj > end_time_range:
                start_time_obj = end_time_range
            
            # Проверяем, что время окончания не выходит за пределы рабочего дня
            if end_time_obj > end_time_range:
                end_time_obj = end_time_range
            
            # Убеждаемся, что окончание после начала
            if end_time_obj <= start_time_obj:
                end_time_obj = self._calculate_end_time(start_time_obj, selected_date)
            
            return {
                "start_time": start_time_obj.strftime("%H:%M"),
                "end_time": end_time_obj.strftime("%H:%M")
            }
            
        except Exception as e:
            logger.error(f"Ошибка обработки предложенного времени: {e}")
            return {"start_time": None, "end_time": None}

    def _calculate_end_time(self, start_time: time, selected_date) -> time:
        """Рассчитывает время окончания на основе времени начала"""
        from time_utils import get_time_range_for_date
        start_time_range, end_time_range, _ = get_time_range_for_date(selected_date)
        
        # По умолчанию 1 час
        start_datetime = datetime.combine(selected_date, start_time)
        end_datetime = start_datetime + timedelta(hours=1)
        end_time_obj = end_datetime.time()
        
        # Обрезаем если выходит за рабочие часы
        if end_time_obj > end_time_range:
            end_time_obj = end_time_range
            
        return end_time_obj