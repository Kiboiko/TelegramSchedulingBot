import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class BackgroundTasks:
    def __init__(self, storage, gsheets, feedback_manager, feedback_teacher_manager):
        self.storage = storage
        self.gsheets = gsheets
        self.feedback_manager = feedback_manager
        self.feedback_teacher_manager = feedback_teacher_manager

    async def cleanup_old_bookings(self):
        """Периодически очищает старые бронирования"""
        while True:
            try:
                bookings = self.storage.load()
                self.storage.save(bookings)  # Это вызовет фильтрацию старых записей
                logger.info("Cleanup of old bookings completed")
                await asyncio.sleep(6 * 60 * 60)  # Каждые 6 часов
            except Exception as e:
                logger.error(f"Error in cleanup_old_bookings: {e}")
                await asyncio.sleep(60)  # Подождать минуту при ошибке

    async def sync_with_gsheets(self):
        """Фоновая синхронизация с Google Sheets"""
        while True:
            try:
                if hasattr(self.storage, 'gsheets') and self.storage.gsheets:
                    bookings = self.storage.load()
                    success = self.storage.gsheets.update_all_sheets(bookings)
                    if success:
                        logger.info("Фоновая синхронизация с Google Sheets выполнена")
                    else:
                        logger.warning("Не удалось выполнить синхронизацию с Google Sheets")
                await asyncio.sleep(60)  # Каждый час
            except Exception as e:
                logger.error(f"Ошибка в фоновой синхронизации: {e}")
                await asyncio.sleep(600)  # Ждем 10 минут при ошибке

    async def sync_from_gsheets_background(self):
        """Фоновая синхронизация из Google Sheets в JSON"""
        while True:
            try:
                if hasattr(self.storage, 'gsheets') and self.storage.gsheets:
                    success = self.storage.gsheets.sync_from_gsheets_to_json(self.storage)
                    if success:
                        logger.info("Фоновая синхронизация из Google Sheets в JSON выполнена")
                    else:
                        logger.warning("Не удалось выполнить синхронизацию из Google Sheets")
                await asyncio.sleep(60)  # Синхронизация каждую минуту
            except Exception as e:
                logger.error(f"Ошибка в фоновой синхронизации из Google Sheets: {e}")
                await asyncio.sleep(300)

    async def check_feedback_background(self):
        """Фоновая задача для проверки и отправки обратной связи"""
        while True:
            try:
                await self.feedback_manager.send_feedback_questions()
                await asyncio.sleep(1800)  # Проверка каждые 30 минут
            except Exception as e:
                logger.error(f"Ошибка в фоновой задаче feedback: {e}")
                await asyncio.sleep(300)  # Ждем 5 минут при ошибке

    async def sync_pending_feedback_background(self):
        """Фоновая задача для синхронизации неотправленных отзывов"""
        while True:
            try:
                # Получаем несинхронизированные отзывы
                pending_feedback = self.feedback_manager.get_pending_feedback_for_gsheets()

                if pending_feedback:
                    logger.info(f"Найдено {len(pending_feedback)} несинхронизированных отзывов")

                    for feedback in pending_feedback:
                        try:
                            # Синхронизируем каждый отзыв
                            self.feedback_manager.sync_feedback_to_gsheets(feedback)

                            # Помечаем как синхронизированный
                            self.feedback_manager.mark_feedback_synced(
                                feedback['user_id'],
                                feedback['date'],
                                feedback['subject']
                            )

                            logger.info(f"Синхронизирован отзыв user_id {feedback['user_id']}")

                        except Exception as e:
                            logger.error(f"Ошибка синхронизации отзыва: {e}")
                            continue

                    logger.info("Синхронизация отзывов завершена")

                await asyncio.sleep(300)  # Проверка каждые 5 минут

            except Exception as e:
                logger.error(f"Ошибка в фоновой задаче синхронизации отзывов: {e}")
                await asyncio.sleep(300)

    async def check_teacher_feedback_background(self):
        """Фоновая задача для проверки и отправки обратной связи преподавателям"""
        while True:
            try:
                await self.feedback_teacher_manager.send_feedback_questions()
                await asyncio.sleep(1800)  # Проверка каждые 30 минут
            except Exception as e:
                logger.error(f"Ошибка в фоновой задаче feedback преподавателей: {e}")
                await asyncio.sleep(300)

    async def sync_pending_teacher_feedback_background(self):
        """Фоновая задача для синхронизации неотправленных отзывов преподавателей"""
        while True:
            try:
                pending_feedback = self.feedback_teacher_manager.get_pending_feedback_for_gsheets()

                if pending_feedback:
                    logger.info(f"Найдено {len(pending_feedback)} несинхронизированных отзывов преподавателей")

                    for feedback in pending_feedback:
                        try:
                            self.feedback_teacher_manager.sync_feedback_to_gsheets(feedback)
                            self.feedback_teacher_manager.mark_feedback_synced(
                                feedback['user_id'],
                                feedback['date']
                            )
                            logger.info(f"Синхронизирован отзыв преподавателя user_id {feedback['user_id']}")
                        except Exception as e:
                            logger.error(f"Ошибка синхронизации отзыва преподавателя: {e}")
                            continue

                await asyncio.sleep(300)  # Проверка каждые 5 минут

            except Exception as e:
                logger.error(f"Ошибка в фоновой задаче синхронизации отзывов преподавателей: {e}")
                await asyncio.sleep(300)

    async def startup_tasks(self):
        """Действия при запуске бота"""
        logger.info("Выполнение startup задач")
        
        # Принудительная синхронизация при старте
        if self.gsheets:
            try:
                worksheet = self.gsheets._get_or_create_users_worksheet()
                records = worksheet.get_all_records()

                # Собираем уникальные user_id
                unique_users = {}
                duplicates = []

                for i, record in enumerate(records, start=2):
                    user_id = str(record.get("user_id"))
                    if user_id in unique_users:
                        duplicates.append(i)
                    else:
                        unique_users[user_id] = record

                # Удаляем дубликаты (с конца, чтобы не сбивались номера строк)
                for row_num in sorted(duplicates, reverse=True):
                    worksheet.delete_rows(row_num)

                logger.info(f"Удалено {len(duplicates)} дубликатов пользователей")
            except Exception as e:
                logger.error(f"Ошибка при очистке дубликатов: {e}")

    def start_all_tasks(self):
        """Запуск всех фоновых задач"""
        tasks = [
            self.cleanup_old_bookings(),
            self.sync_from_gsheets_background(),
            self.check_feedback_background(),
            self.sync_pending_feedback_background(),
            self.check_teacher_feedback_background(),
            self.sync_pending_teacher_feedback_background()
        ]
        return tasks