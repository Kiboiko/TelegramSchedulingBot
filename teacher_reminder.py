import logging
from datetime import datetime, timedelta
from aiogram import Bot
from typing import List

logger = logging.getLogger(__name__)


class TeacherReminderManager:
    def __init__(self, storage, gsheets_manager, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets_manager
        self.bot = bot

    def get_all_teachers(self) -> List[int]:
        """Получает список всех user_id преподавателей"""
        try:
            if not self.gsheets:
                logger.warning("Google Sheets manager не доступен")
                return []

            worksheet = self.gsheets._get_or_create_users_worksheet()
            records = worksheet.get_all_records()

            teachers = []
            for record in records:
                user_id = record.get('user_id')
                roles_str = record.get('roles', '')

                if user_id and roles_str:
                    roles = [role.strip().lower() for role in roles_str.split(',')]
                    if 'teacher' in roles:
                        teachers.append(int(user_id))

            logger.info(f"Найдено {len(teachers)} преподавателей для напоминаний")
            return teachers

        except Exception as e:
            logger.error(f"Ошибка получения списка преподавателей: {e}")
            return []

    async def send_reminders(self):
        """Отправляет напоминания всем преподавателям"""
        try:
            teachers = self.get_all_teachers()

            if not teachers:
                logger.info("Нет преподавателей для отправки напоминаний")
                return

            success_count = 0
            fail_count = 0

            for teacher_id in teachers:
                try:
                    await self.bot.send_message(
                        chat_id=teacher_id,
                        text="НАПОМИНАНИЕ! Проставьте свои возможности на следующую неделю"
                    )
                    success_count += 1
                    logger.info(f"Напоминание отправлено преподавателю {teacher_id}")

                    # Небольшая задержка чтобы не превысить лимиты Telegram
                    import asyncio
                    await asyncio.sleep(0.1)

                except Exception as e:
                    fail_count += 1
                    logger.error(f"Не удалось отправить напоминание преподавателю {teacher_id}: {e}")

            logger.info(f"Напоминания отправлены: успешно {success_count}, неудачно {fail_count}")

        except Exception as e:
            logger.error(f"Ошибка отправки напоминаний: {e}")

    def should_send_reminder(self) -> bool:
        """Проверяет, нужно ли отправлять напоминание в текущий момент"""
        from config import REMINDER_CONFIG

        now = datetime.now()

        # Проверяем день недели (3 = четверг)
        if now.weekday() != REMINDER_CONFIG["reminder_day"]:
            return False

        # Проверяем время (18:00)
        if now.hour != REMINDER_CONFIG["reminder_hour"]:
            return False

        if now.minute != REMINDER_CONFIG["reminder_minute"]:
            return False

        return True