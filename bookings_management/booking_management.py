# booking_management.py
import logging
from datetime import datetime, time
from typing import List, Dict, Optional
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import json, os

logger = logging.getLogger(__name__)

class BookingManager:
    def __init__(self, storage, gsheets=None):
        self.storage = storage
        self.gsheets = gsheets
    
    def _feedback_exists(self, user_id: int, date_str: str, subject: str) -> bool:
        """Проверяет, оставлен ли уже отзыв для user/date/subject в локальном файле feedback.json"""
        try:
            feedback_file = os.path.join(os.getcwd(), 'feedback.json')
            if not os.path.exists(feedback_file):
                return False
            with open(feedback_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for rec in data:
                if (str(rec.get('user_id')) == str(user_id) and
                        rec.get('date') == date_str and
                        str(rec.get('subject')) == str(subject) and
                        rec.get('status') == 'completed'):
                    return True
        except Exception as e:
            logger.error(f"Ошибка проверки существующего отзыва: {e}")
        return False
    def load_bookings(self) -> List[Dict]:
        """Загружает бронирования из файла и удаляет прошедшие"""
        data = self.storage.load()
        valid_bookings = []
        current_time = datetime.now()

        for booking in data:
            if 'date' not in booking:
                continue

            try:
                if isinstance(booking['date'], str):
                    booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                else:
                    continue

                time_end = datetime.strptime(booking.get('end_time', "00:00"), "%H:%M").time()
                booking_datetime = datetime.combine(booking_date, time_end)

                if booking_datetime < current_time:
                    continue
                
                booking['date'] = booking_date
                valid_bookings.append(booking)

            except ValueError:
                continue

        return valid_bookings
    
    def load_past_bookings(self) -> List[Dict]:
        """Загружает прошедшие бронирования"""
        try:
            data = self.storage.load()
            past_bookings = []
            current_time = datetime.now()

            for booking in data:
                if 'date' not in booking or 'end_time' not in booking:
                    continue

                try:
                    if isinstance(booking['date'], str):
                        booking_date = datetime.strptime(booking['date'], "%Y-%m-%d").date()
                    else:
                        continue

                    time_end = datetime.strptime(booking.get('end_time', "00:00"), "%H:%M").time()
                    booking_datetime = datetime.combine(booking_date, time_end)

                    # Добавляем только прошедшие бронирования
                    if booking_datetime < current_time:
                        booking['date'] = booking_date
                        past_bookings.append(booking)

                except ValueError:
                    continue

            return past_bookings
        except Exception as e:
            logger.error(f"Ошибка загрузки прошедших бронирований: {e}")
            return []
    
    def generate_booking_list(self, user_id: int) -> Optional[InlineKeyboardBuilder]:
        """Генерирует клавиатуру с активными бронированиями"""
        bookings = self.load_bookings()
        user_roles = self.storage.get_user_roles(user_id)

        # Для родителя показываем бронирования всех его детей
        children_ids = []
        if 'parent' in user_roles:
            children_ids = self.storage.get_parent_children(user_id)

        # Разделяем бронирования по категориям
        teacher_bookings = []
        student_bookings = []
        children_bookings = []

        for booking in bookings:
            if booking.get('user_id') == user_id:
                if booking.get('user_role') == 'teacher':
                    teacher_bookings.append(booking)
                else:
                    student_bookings.append(booking)
            elif booking.get('user_id') in children_ids:
                children_bookings.append(booking)

        if not any([teacher_bookings, student_bookings, children_bookings]):
            return None

        builder = InlineKeyboardBuilder()

        # Бронирования преподавателя
        if teacher_bookings:
            builder.row(types.InlineKeyboardButton(
                text="👨‍🏫 МОИ БРОНИРОВАНИЯ (ПРЕПОДАВАТЕЛЬ)",
                callback_data="ignore"
            ))

            for booking in sorted(teacher_bookings, key=lambda x: (x.get("date"), x.get("start_time"))):
                date_str = self._format_booking_date(booking.get('date', ''))
                
                button_text = (
                    f"📅 {date_str} "
                    f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')}"
                )

                builder.row(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"booking_info_{booking.get('id')}"
                ))

        # Бронирования ученика
        if student_bookings:
            builder.row(types.InlineKeyboardButton(
                text="👨‍🎓 МОИ БРОНИРОВАНИЯ (УЧЕНИК)",
                callback_data="ignore"
            ))

            for booking in sorted(student_bookings, key=lambda x: (x.get("date"), x.get("start_time"))):
                date_str = self._format_booking_date(booking.get('date', ''))
                subject = booking.get('subject', '')
                subject_short = self._get_subject_short_name(subject)

                button_text = (
                    f"📅 {date_str} "
                    f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')} "
                    f"📚 {subject_short}"
                )

                builder.row(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"booking_info_{booking.get('id')}"
                ))

        # Бронирования детей (для родителей)
        if children_bookings:
            builder.row(types.InlineKeyboardButton(
                text="👶 БРОНИРОВАНИЯ МОИХ ДЕТЕЙ",
                callback_data="ignore"
            ))

            # Группируем по детям
            children_bookings_by_child = {}
            for booking in children_bookings:
                child_id = booking.get('user_id')
                if child_id not in children_bookings_by_child:
                    children_bookings_by_child[child_id] = []
                children_bookings_by_child[child_id].append(booking)

            for child_id, child_bookings in children_bookings_by_child.items():
                child_info = self.storage.get_child_info(child_id)
                child_name = child_info.get('user_name', f'Ребенок {child_id}')

                builder.row(types.InlineKeyboardButton(
                    text=f"👶 {child_name}",
                    callback_data="ignore"
                ))

                for booking in sorted(child_bookings, key=lambda x: (x.get("date"), x.get("start_time"))):
                    date_str = self._format_booking_date(booking.get('date', ''))
                    subject = booking.get('subject', '')
                    subject_short = self._get_subject_short_name(subject)

                    button_text = (
                        f"   📅 {date_str} "
                        f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')} "
                        f"📚 {subject_short}"
                    )

                    builder.row(types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"booking_info_{booking.get('id')}"
                    ))

        builder.row(types.InlineKeyboardButton(
            text="🔙 Назад в меню",
            callback_data="back_to_menu"
        ))

        return builder
    
    def generate_past_bookings_list(self, user_id: int) -> Optional[InlineKeyboardBuilder]:
        """Генерирует клавиатуру с прошедшими бронированиями"""
        bookings = self.load_past_bookings()
        user_roles = self.storage.get_user_roles(user_id)

        # Для родителя показываем бронирования всех его детей
        children_ids = []
        if 'parent' in user_roles:
            children_ids = self.storage.get_parent_children(user_id)

        # Разделяем бронирования по категориям
        teacher_bookings = []
        student_bookings = []
        children_bookings = []

        for booking in bookings:
            if booking.get('user_id') == user_id:
                if booking.get('user_role') == 'teacher':
                    teacher_bookings.append(booking)
                else:
                    student_bookings.append(booking)
            elif booking.get('user_id') in children_ids:
                children_bookings.append(booking)

        if not any([teacher_bookings, student_bookings, children_bookings]):
            return None

        builder = InlineKeyboardBuilder()

        # Бронирования преподавателя
        if teacher_bookings:
            builder.row(types.InlineKeyboardButton(
                text="👨‍🏫 ПРОШЕДШИЕ БРОНИРОВАНИЯ (ПРЕПОДАВАТЕЛЬ)",
                callback_data="ignore"
            ))

            for booking in sorted(teacher_bookings, key=lambda x: (x.get("date"), x.get("start_time")), reverse=True):
                date_str = self._format_booking_date(booking.get('date', ''), full_year=True)
                
                button_text = (
                    f"📅 {date_str} "
                    f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')}"
                )

                builder.row(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"past_booking_info_{booking.get('id')}"
                ))

        # Бронирования ученика
        if student_bookings:
            builder.row(types.InlineKeyboardButton(
                text="👨‍🎓 ПРОШЕДШИЕ БРОНИРОВАНИЯ (УЧЕНИК)",
                callback_data="ignore"
            ))

            for booking in sorted(student_bookings, key=lambda x: (x.get("date"), x.get("start_time")), reverse=True):
                date_str = self._format_booking_date(booking.get('date', ''), full_year=True)
                subject = booking.get('subject', '')
                subject_short = self._get_subject_short_name(subject)

                button_text = (
                    f"📅 {date_str} "
                    f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')} "
                    f"📚 {subject_short}"
                )

                builder.row(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"past_booking_info_{booking.get('id')}"
                ))

        # Бронирования детей (для родителей)
        if children_bookings:
            builder.row(types.InlineKeyboardButton(
                text="👶 ПРОШЕДШИЕ БРОНИРОВАНИЯ ДЕТЕЙ",
                callback_data="ignore"
            ))

            # Группируем по детям
            children_bookings_by_child = {}
            for booking in children_bookings:
                child_id = booking.get('user_id')
                if child_id not in children_bookings_by_child:
                    children_bookings_by_child[child_id] = []
                children_bookings_by_child[child_id].append(booking)

            for child_id, child_bookings in children_bookings_by_child.items():
                child_info = self.storage.get_child_info(child_id)
                child_name = child_info.get('user_name', f'Ребенок {child_id}')

                builder.row(types.InlineKeyboardButton(
                    text=f"👶 {child_name}",
                    callback_data="ignore"
                ))

                for booking in sorted(child_bookings, key=lambda x: (x.get("date"), x.get("start_time")), reverse=True):
                    date_str = self._format_booking_date(booking.get('date', ''), full_year=True)
                    subject = booking.get('subject', '')
                    subject_short = self._get_subject_short_name(subject)

                    button_text = (
                        f"   📅 {date_str} "
                        f"⏰ {booking.get('start_time', '?')}-{booking.get('end_time', '?')} "
                        f"📚 {subject_short}"
                    )

                    builder.row(types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"past_booking_info_{booking.get('id')}"
                    ))

        builder.row(types.InlineKeyboardButton(
            text="🔙 Назад в меню",
            callback_data="back_to_menu_from_past"
        ))

        return builder
    
    def _format_booking_date(self, date_str: str, full_year: bool = False) -> str:
        """Форматирует дату бронирования"""
        if isinstance(date_str, str) and len(date_str) == 10:  # YYYY-MM-DD format
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if full_year:
                    return date_obj.strftime("%d.%m.%Y")
                else:
                    return date_obj.strftime("%d.%m")
            except ValueError:
                return date_str
        else:
            return date_str
    
    def _get_subject_short_name(self, subject: str) -> str:
        """Возвращает короткое название предмета"""
        from config import SUBJECTS
        return SUBJECTS.get(subject, subject)[:10]  # Ограничиваем длину
    
    def get_booking_info_text(self, booking: Dict) -> str:
        """Формирует текст информации о бронировании"""
        role_text = "👨🎓 Ученик" if booking.get('user_role') == 'student' else "👨🏫 Преподаватель"

        # Обрабатываем дату
        booking_date = booking.get('date')
        if isinstance(booking_date, str):
            try:
                booking_date = datetime.strptime(booking_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            except ValueError:
                booking_date = "Неизвестно"

        message_text = (
            f"📋 Информация о бронировании:\n\n"
            f"🔹 {role_text}\n"
        )

        # Добавляем информацию о ребенке, если это бронь ребенка
        if booking.get('parent_id'):
            parent_name = booking.get('parent_name', 'Родитель')
            message_text += f"👨‍👩‍👧‍👦 Записано родителем: {parent_name}\n"

        message_text += (
            f"👤 Имя: {booking.get('user_name', 'Неизвестно')}\n"
            f"📅 Дата: {booking_date}\n"
            f"⏰ Время: {booking.get('start_time', '?')} - {booking.get('end_time', '?')}\n"
        )

        # Добавляем информацию о предметах
        if booking.get('user_role') == 'teacher':
            subjects = booking.get('subjects', [])
            from config import SUBJECTS
            subjects_text = ", ".join([SUBJECTS.get(subj, subj) for subj in subjects])
            message_text += f"📚 Предметы: {subjects_text}\n"
        else:
            subject = booking.get('subject', 'Неизвестно')
            from config import SUBJECTS
            message_text += f"📚 Предмет: {SUBJECTS.get(subject, subject)}\n"

        # Добавляем тип бронирования
        message_text += f"🏷 Тип: {booking.get('booking_type', 'Тип1')}\n"

        return message_text
    
    def get_past_booking_info_text(self, booking: Dict) -> str:
        """Формирует текст информации о прошедшем бронировании"""
        text = self.get_booking_info_text(booking)
        text += f"\n✅ Занятие завершено"
        return text
    
    def cancel_booking_by_id(self, booking_id: int) -> bool:
        """Отменяет бронирование по ID"""
        return self.storage.cancel_booking(booking_id)
    
    def find_booking_by_id(self, booking_id: int) -> Optional[Dict]:
        """Находит бронирование по ID"""
        bookings = self.load_bookings()
        return next((b for b in bookings if b.get("id") == booking_id), None)
    
    def find_past_booking_by_id(self, booking_id: int) -> Optional[Dict]:
        """Находит прошедшее бронирование по ID"""
        bookings = self.load_past_bookings()
        return next((b for b in bookings if b.get("id") == booking_id), None)
    
    def get_subject_short_name(subject: str) -> str:
        """Возвращает короткое название предмета"""
        from config import SUBJECTS
        return SUBJECTS.get(subject, subject)[:10]

    def is_admin(user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором"""
        from config import ADMIN_IDS
        return user_id in ADMIN_IDS