import logging
from datetime import datetime
from aiogram import Bot
from typing import List
from database import db

logger = logging.getLogger(__name__)


class TeacherReminderManager:
    def __init__(self, storage, gsheets_manager, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets_manager
        self.bot = bot

    async def get_all_teachers(self) -> List[int]:
        """Получает список всех user_id преподавателей из БД"""
        try:
            async with db.pool.acquire() as conn:
                teachers = await conn.fetch("""
                    SELECT DISTINCT u.user_id
                    FROM users u
                    JOIN teachers t ON u.user_id = t.user_id
                    WHERE u.roles LIKE '%teacher%'
                """)
                return [t['user_id'] for t in teachers]
        except Exception as e:
            logger.error(f"❌ Error getting teachers: {e}")
            return []

    async def send_reminders(self):
        """Отправляет напоминания всем преподавателям"""
        try:
            teachers = await self.get_all_teachers()

            if not teachers:
                logger.info("✅ No teachers found for reminders")
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
                    logger.info(f"✅ Reminder sent to teacher {teacher_id}")

                    # Сохраняем факт отправки
                    await self.save_teacher_reminder_sent(teacher_id)

                    await asyncio.sleep(0.1)  # Задержка

                except Exception as e:
                    fail_count += 1
                    logger.error(f"❌ Failed to send reminder to teacher {teacher_id}: {e}")

            logger.info(f"✅ Reminders sent: success {success_count}, failed {fail_count}")

        except Exception as e:
            logger.error(f"❌ Error sending teacher reminders: {e}")

    async def save_teacher_reminder_sent(self, teacher_id: int):
        """Сохраняет факт отправки напоминания преподавателю"""
        try:
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO reminders (user_id, reminder_type, target_date, sent)
                    VALUES ($1, 'teacher_schedule_reminder', CURRENT_DATE, TRUE)
                    ON CONFLICT (user_id, reminder_type, target_date) DO NOTHING
                """, teacher_id)
        except Exception as e:
            logger.error(f"❌ Error saving teacher reminder: {e}")

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

    async def check_and_send_weekly_reminders(self):
        """Проверяет и отправляет еженедельные напоминания преподавателям"""
        if self.should_send_reminder():
            await self.send_reminders()

    async def get_teachers_without_next_week_schedule(self) -> List[int]:
        """Находит преподавателей без расписания на следующую неделю"""
        try:
            next_monday = datetime.now() + timedelta(days=(7 - datetime.now().weekday()))
            next_friday = next_monday + timedelta(days=4)

            async with db.pool.acquire() as conn:
                teachers = await conn.fetch("""
                    SELECT DISTINCT u.user_id
                    FROM users u
                    JOIN teachers t ON u.user_id = t.user_id
                    WHERE u.roles LIKE '%teacher%'
                    AND NOT EXISTS (
                        SELECT 1 FROM bookings b
                        WHERE b.user_id = u.user_id
                        AND b.user_role = 'teacher'
                        AND b.date BETWEEN $1 AND $2
                    )
                """, next_monday.date(), next_friday.date())

                return [t['user_id'] for t in teachers]

        except Exception as e:
            logger.error(f"❌ Error finding teachers without schedule: {e}")
            return []

    async def send_specific_reminders(self, teacher_ids: List[int], message: str):
        """Отправляет специфические напоминания выбранным преподавателям"""
        try:
            for teacher_id in teacher_ids:
                try:
                    await self.bot.send_message(
                        chat_id=teacher_id,
                        text=message
                    )
                    logger.info(f"✅ Specific reminder sent to teacher {teacher_id}")
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"❌ Failed to send specific reminder to {teacher_id}: {e}")

        except Exception as e:
            logger.error(f"❌ Error in send_specific_reminders: {e}")