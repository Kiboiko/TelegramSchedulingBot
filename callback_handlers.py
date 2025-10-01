# callback_handlers.py
from aiogram import types, F
from aiogram.fsm.context import FSMContext
import logging
from datetime import datetime, time
from typing import Dict, List
from main import booking_manager
logger = logging.getLogger(__name__)
from bookings_management.booking_management import BookingManager
from bookings_management.booking_keyboards import *
class CallbackHandlers:
    """Централизованная обработка callback'ов"""
    
    CALLBACK_HANDLERS = {
        # Бронирования
        "calendar_change": "handle_calendar_change",
        "calendar_day": "handle_calendar_day",
        "time_point": "handle_time_point",
        "confirm_time_range": "handle_confirm_time_range",
        "booking_confirm": "handle_booking_confirm",
        "booking_cancel": "handle_booking_cancel",
        "cancel_time_selection": "handle_cancel_time_selection",
        
        # Роли
        "role_": "handle_role_selection",
        "subject_": "handle_subject_selection",
        "select_child_": "handle_child_selection",
        
        # Бронирования (управление)
        "booking_info_": "handle_booking_info",
        "cancel_booking_": "handle_cancel_booking",
        "past_booking_info_": "handle_past_booking_info",
        
        # Навигация
        "back_to_menu": "handle_back_to_menu",
        "back_to_bookings": "handle_back_to_bookings",
        "back_to_past_bookings": "handle_back_to_past_bookings",
        
        # Время
        "select_start_mode": "handle_select_start_mode",
        "select_end_mode": "handle_select_end_mode",
        "time_slot_unavailable": "handle_time_slot_unavailable",
        "availability_info": "handle_availability_info",
        "interval_contains_unavailable": "handle_interval_unavailable",
        
        # Feedback
        "feedback_": "handle_feedback",
        "feedback_submit_details": "handle_feedback_submit",
        "feedback_teacher_": "handle_teacher_feedback",
        "feedback_teacher_submit_details": "handle_teacher_feedback_submit",
        
        # Расписание
        "confirm_schedule": "handle_confirm_schedule",
        "cancel_schedule": "handle_cancel_schedule"
    }
    
    @staticmethod
    async def process_callback(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает callback и направляет в соответствующий обработчик"""
        try:
            callback_data = callback.data
            
            # Ищем подходящий обработчик
            for pattern, handler_name in CallbackHandlers.CALLBACK_HANDLERS.items():
                if callback_data.startswith(pattern):
                    handler = getattr(CallbackHandlers, handler_name)
                    await handler(callback, state)
                    return
            
            # Если не нашли обработчик
            await callback.answer("❌ Действие не распознано", show_alert=True)
            logger.warning(f"Неизвестный callback: {callback_data}")
            
        except Exception as e:
            logger.error(f"Ошибка обработки callback: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    # === ОБРАБОТЧИКИ БРОНИРОВАНИЙ ===
    
    @staticmethod
    async def handle_calendar_change(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает изменение месяца в календаре"""
        try:
            date_str = callback.data.replace("calendar_change_", "")
            year, month = map(int, date_str.split("-"))
            
            from main import generate_calendar
            await callback.message.edit_reply_markup(
                reply_markup=generate_calendar(year, month)
            )
            await callback.answer()
        except Exception as e:
            logger.error(f"Error changing calendar month: {e}")
            await callback.answer("Не удалось изменить месяц", show_alert=True)

    @staticmethod
    async def handle_calendar_day(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор даты в календаре"""
        from main import process_calendar
        await process_calendar(callback, state)

    @staticmethod
    async def handle_time_point(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор временной точки"""
        from main import process_time_point
        await process_time_point(callback, state)

    @staticmethod
    async def handle_confirm_time_range(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает подтверждение временного диапазона"""
        from main import confirm_time_range
        await confirm_time_range(callback, state)

    @staticmethod
    async def handle_booking_confirm(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает подтверждение бронирования"""
        from main import process_confirmation
        await process_confirmation(callback, state)

    @staticmethod
    async def handle_booking_cancel(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает отмену бронирования"""
        from main import process_cancellation
        await process_cancellation(callback, state)

    # === ОБРАБОТЧИКИ РОЛЕЙ И ПРЕДМЕТОВ ===
    
    @staticmethod
    async def handle_role_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор роли"""
        from main import process_role_selection
        await process_role_selection(callback, state)

    @staticmethod
    async def handle_subject_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор предмета"""
        from main import process_student_subject
        await process_student_subject(callback, state)

    @staticmethod
    async def handle_child_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор ребенка для родителя"""
        from main import process_child_selection
        await process_child_selection(callback, state)

    # === ОБРАБОТЧИКИ УПРАВЛЕНИЯ БРОНИРОВАНИЯМИ ===
    
    @staticmethod
    async def handle_booking_info(callback: types.CallbackQuery, state: FSMContext):
        """Показывает информацию о бронировании"""
        try:
            booking_id_str = callback.data.replace("booking_info_", "")
            booking_id = int(booking_id_str)
            booking = booking_manager.find_booking_by_id(booking_id)

            if not booking:
                await callback.answer("Бронирование не найдено", show_alert=True)
                return

            message_text = booking_manager.get_booking_info_text(booking)
            from bookings_management.booking_keyboards import generate_booking_actions
            
            await callback.message.edit_text(
                message_text,
                reply_markup=generate_booking_actions(booking_id)
            )
            await callback.answer()
        except Exception as e:
            logger.error(f"Ошибка в handle_booking_info: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_cancel_booking(callback: types.CallbackQuery, state: FSMContext):
        """Отменяет бронирование"""
        booking_id = int(callback.data.replace("cancel_booking_", ""))
        if booking_manager.cancel_booking_by_id(booking_id):
            await callback.message.edit_text(f"✅ Бронирование ID {booking_id} успешно отменено")
        else:
            await callback.message.edit_text("❌ Не удалось отменить бронирование")
        await callback.answer()

    @staticmethod
    async def handle_past_booking_info(callback: types.CallbackQuery, state: FSMContext):
        """Показывает информацию о прошедшем бронировании"""
        try:
            booking_id_str = callback.data.replace("past_booking_info_", "")
            booking_id = int(booking_id_str)
            booking = booking_manager.find_past_booking_by_id(booking_id)

            if not booking:
                await callback.answer("Бронирование не найдено", show_alert=True)
                return

            message_text = booking_manager.get_past_booking_info_text(booking)
            from bookings_management.booking_keyboards import generate_past_booking_info
            
            await callback.message.edit_text(
                message_text,
                reply_markup=generate_past_booking_info(booking_id)
            )
            await callback.answer()
        except Exception as e:
            logger.error(f"Ошибка в handle_past_booking_info: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    # === ОБРАБОТЧИКИ НАВИГАЦИИ ===
    
    @staticmethod
    async def handle_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
        """Возвращает в главное меню"""
        from main import back_handler
        await back_handler(callback)

    @staticmethod
    async def handle_back_to_bookings(callback: types.CallbackQuery, state: FSMContext):
        """Возвращает к списку бронирований"""
        from main import back_handler
        await back_handler(callback)

    @staticmethod
    async def handle_back_to_past_bookings(callback: types.CallbackQuery, state: FSMContext):
        """Возвращает к списку прошедших бронирований"""
        from main import back_to_past_bookings
        await back_to_past_bookings(callback)

    # === ОБРАБОТЧИКИ ВРЕМЕНИ ===
    
    @staticmethod
    async def handle_select_start_mode(callback: types.CallbackQuery, state: FSMContext):
        """Переключает в режим выбора начала времени"""
        from main import switch_selection_mode
        await switch_selection_mode(callback, state)

    @staticmethod
    async def handle_select_end_mode(callback: types.CallbackQuery, state: FSMContext):
        """Переключает в режим выбора окончания времени"""
        from main import switch_selection_mode
        await switch_selection_mode(callback, state)

    @staticmethod
    async def handle_time_slot_unavailable(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает нажатие на недоступный слот"""
        from main import handle_unavailable_slot
        await handle_unavailable_slot(callback)

    @staticmethod
    async def handle_availability_info(callback: types.CallbackQuery, state: FSMContext):
        """Показывает информацию о доступности"""
        from main import show_availability_info
        await show_availability_info(callback, state)

    @staticmethod
    async def handle_interval_unavailable(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает недоступный интервал"""
        from main import handle_interval_contains_unavailable
        await handle_interval_contains_unavailable(callback, state)

    # === ОБРАБОТЧИКИ FEEDBACK ===
    
    @staticmethod
    async def handle_feedback(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает feedback от учеников"""
        from main import handle_feedback_rating
        await handle_feedback_rating(callback, state)

    @staticmethod
    async def handle_feedback_submit(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает отправку feedback"""
        from main import handle_feedback_submit
        await handle_feedback_submit(callback, state)

    @staticmethod
    async def handle_teacher_feedback(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает feedback от преподавателей"""
        from main import handle_teacher_feedback_rating
        await handle_teacher_feedback_rating(callback, state)

    @staticmethod
    async def handle_teacher_feedback_submit(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает отправку feedback преподавателей"""
        from main import handle_teacher_feedback_submit
        await handle_teacher_feedback_submit(callback, state)

    # === ОБРАБОТЧИКИ РАСПИСАНИЯ ===
    
    @staticmethod
    async def handle_confirm_schedule(callback: types.CallbackQuery, state: FSMContext):
        """Подтверждает составление расписания"""
        from main import process_schedule_confirmation
        await process_schedule_confirmation(callback, state)

    @staticmethod
    async def handle_cancel_schedule(callback: types.CallbackQuery, state: FSMContext):
        """Отменяет составление расписания"""
        from main import cancel_schedule_generation
        await cancel_schedule_generation(callback, state)

    @staticmethod
    async def handle_cancel_time_selection(callback: types.CallbackQuery, state: FSMContext):
        """Отменяет выбор времени"""
        from main import cancel_time_selection_handler
        await cancel_time_selection_handler(callback, state)