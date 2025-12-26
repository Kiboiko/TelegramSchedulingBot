# teacher_reminder.py
from typing import List, Dict
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from database import db
import asyncio

logger = logging.getLogger(__name__)


class TeacherReminderManager:
    def __init__(self, storage, gsheets_manager, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets_manager
        self.bot = bot

    async def get_all_teachers(self) -> List[Dict]:
        """Получает список всех преподавателей из БД с их именами"""
        try:
            async with db.pool.acquire() as conn:
                teachers = await conn.fetch("""
                    SELECT DISTINCT u.user_id, u.user_name
                    FROM users u
                    JOIN teachers t ON u.user_id = t.user_id
                    WHERE u.roles LIKE '%teacher%'
                    AND u.user_name IS NOT NULL
                    AND u.user_name != ''
                """)
                return [dict(teacher) for teacher in teachers]
        except Exception as e:
            logger.error(f"❌ Error getting teachers: {e}")
            return []

    async def has_schedule_for_next_week(self, teacher_id: int) -> bool:
        """Проверяет, есть ли у преподавателя записи на следующую неделю"""
        try:
            # Следующий понедельник
            today = datetime.now()
            days_until_monday = (7 - today.weekday()) % 7
            days_until_monday = 7 if days_until_monday == 0 else days_until_monday  # Если сегодня понедельник, берем следующий
            next_monday = today + timedelta(days=days_until_monday)
            next_friday = next_monday + timedelta(days=4)

            async with db.pool.acquire() as conn:
                bookings = await conn.fetch("""
                    SELECT COUNT(*) as count
                    FROM bookings b
                    WHERE b.user_id = $1
                    AND b.user_role = 'teacher'
                    AND b.date BETWEEN $2 AND $3
                """, teacher_id, next_monday.date(), next_friday.date())

                return bookings[0]['count'] > 0 if bookings else False

        except Exception as e:
            logger.error(f"❌ Error checking schedule for teacher {teacher_id}: {e}")
            return False

    async def send_reminders(self):
        """Отправляет напоминания преподавателям без расписания на следующую неделю"""
        try:
            # Получаем всех преподавателей
            teachers = await self.get_all_teachers()

            if not teachers:
                logger.info("✅ No teachers found")
                return

            success_count = 0
            fail_count = 0
            reminded_count = 0

            for teacher in teachers:
                teacher_id = teacher['user_id']
                user_name = teacher.get('user_name', 'Преподаватель')

                try:
                    # Проверяем, не отправляли ли уже напоминание сегодня
                    sent_today = await self.check_reminder_sent_today(teacher_id)
                    if sent_today:
                        logger.info(f"✅ Reminder already sent today to teacher {teacher_id}")
                        continue

                    # Проверяем, есть ли расписание на след неделю
                    has_schedule = await self.has_schedule_for_next_week(teacher_id)
                    if has_schedule:
                        logger.info(f"✅ Teacher {user_name} has schedule for next week, skipping")
                        continue

                    # Отправляем напоминание
                    await self.bot.send_message(
                        chat_id=teacher_id,
                        text=f"Привет, {user_name}! 👋\n\n"
                             f"НАПОМИНАНИЕ! Проставьте свои возможности на следующую неделю 📅\n\n"
                             f"Если вы уже свободны для занятий, используйте кнопку '📅 Забронировать время' в меню!"
                    )

                    # Сохраняем факт отправки
                    await self.save_reminder_sent(teacher_id)

                    success_count += 1
                    reminded_count += 1
                    logger.info(f"✅ Reminder sent to teacher {teacher_id} ({user_name})")

                    # Небольшая задержка
                    await asyncio.sleep(0.1)

                except Exception as e:
                    fail_count += 1
                    logger.error(f"❌ Failed to send reminder to teacher {teacher_id}: {e}")

            logger.info(
                f"✅ Teacher reminders: sent to {reminded_count} teachers, success {success_count}, failed {fail_count}")

            # Возвращаем статистику
            return {
                'total_teachers': len(teachers),
                'sent_reminders': reminded_count,
                'success': success_count,
                'failed': fail_count
            }

        except Exception as e:
            logger.error(f"❌ Error sending teacher reminders: {e}")
            return {}

    async def check_reminder_sent_today(self, teacher_id: int) -> bool:
        """Проверяет, отправляли ли уже напоминание сегодня"""
        # В Google Sheets не было хранения истории, так что просто возвращаем False
        # Это позволит отправлять напоминания каждый день, если нужно
        return False

        # ЗАКОММЕНТИРУЙТЕ старый код:
        # try:
        #     async with db.pool.acquire() as conn:
        #         reminder = await conn.fetchrow("""
        #             SELECT reminder_id FROM reminders
        #             WHERE user_id = $1
        #             AND reminder_type = 'teacher_schedule_reminder'
        #             AND sent = TRUE
        #             AND DATE(sent_at) = CURRENT_DATE
        #             LIMIT 1
        #         """, teacher_id)
        #         return reminder is not None
        # except Exception as e:
        #     logger.error(f"❌ Error checking reminder sent today: {e}")
        #     return False

    async def save_reminder_sent(self, teacher_id: int):
        """Сохраняет факт отправки напоминания - НЕ НУЖНО В НАШЕМ СЛУЧАЕ"""
        # В Google Sheets не хранили историю напоминаний, так что просто логируем
        logger.info(f"✅ Напоминание отправлено преподавателю {teacher_id}")
        # Ничего не сохраняем в БД

        # ЗАКОММЕНТИРУЙТЕ старый код:
        # try:
        #     async with db.pool.acquire() as conn:
        #         await conn.execute("""
        #             INSERT INTO reminders (user_id, reminder_type, target_date, sent, sent_at)
        #             VALUES ($1, 'teacher_schedule_reminder', CURRENT_DATE, TRUE, CURRENT_TIMESTAMP)
        #             ON CONFLICT (user_id, reminder_type, target_date)
        #             DO UPDATE SET sent = TRUE, sent_at = CURRENT_TIMESTAMP
        #         """, teacher_id)
        # except Exception as e:
        #     logger.error(f"❌ Error saving teacher reminder: {e}")

    def should_send_reminder(self) -> bool:
        """Проверяет, нужно ли отправлять напоминание в текущий момент"""
        from config import REMINDER_CONFIG

        now = datetime.now()

        # Проверяем день недели (3 = четверг)
        if now.weekday() != REMINDER_CONFIG.get("reminder_day", 3):
            return False

        # Проверяем время (18:00)
        if now.hour != REMINDER_CONFIG.get("reminder_hour", 18):
            return False

        if now.minute != REMINDER_CONFIG.get("reminder_minute", 0):
            return False

        return True

    async def check_and_send_weekly_reminders(self):
        """Проверяет и отправляет еженедельные напоминания преподавателям"""
        if self.should_send_reminder():
            logger.info("🎯 It's time to send weekly teacher reminders!")
            return await self.send_reminders()
        return {}

    async def get_teachers_without_next_week_schedule(self) -> List[Dict]:
        """Находит преподавателей без расписания на следующую неделю"""
        try:
            teachers = await self.get_all_teachers()
            teachers_without_schedule = []

            for teacher in teachers:
                has_schedule = await self.has_schedule_for_next_week(teacher['user_id'])
                if not has_schedule:
                    teachers_without_schedule.append(teacher)

            return teachers_without_schedule

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

    async def get_reminder_stats(self) -> Dict:
        """Получает статистику напоминаний"""
        try:
            async with db.pool.acquire() as conn:
                # Общая статистика
                total_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_reminders,
                        SUM(CASE WHEN sent THEN 1 ELSE 0 END) as sent_reminders,
                        SUM(CASE WHEN NOT sent THEN 1 ELSE 0 END) as pending_reminders,
                        COUNT(DISTINCT user_id) as unique_teachers
                    FROM reminders
                    WHERE reminder_type = 'teacher_schedule_reminder'
                """)

                # Статистика за эту неделю
                weekly_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as this_week_reminders,
                        COUNT(DISTINCT user_id) as this_week_teachers
                    FROM reminders
                    WHERE reminder_type = 'teacher_schedule_reminder'
                    AND target_date >= DATE_TRUNC('week', CURRENT_DATE)
                    AND target_date < DATE_TRUNC('week', CURRENT_DATE) + INTERVAL '7 days'
                """)

                # Статистика за сегодня
                today_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as today_reminders,
                        COUNT(DISTINCT user_id) as today_teachers
                    FROM reminders
                    WHERE reminder_type = 'teacher_schedule_reminder'
                    AND DATE(sent_at) = CURRENT_DATE
                """)

                return {
                    'total': dict(total_stats) if total_stats else {},
                    'this_week': dict(weekly_stats) if weekly_stats else {},
                    'today': dict(today_stats) if today_stats else {}
                }
        except Exception as e:
            logger.error(f"❌ Error getting teacher reminder stats: {e}")
            return {}

    async def create_test_reminder(self, teacher_id: int):
        """Создает тестовое напоминание (для отладки)"""
        try:
            await self.bot.send_message(
                chat_id=teacher_id,
                text="🔔 ТЕСТОВОЕ НАПОМИНАНИЕ\n\n"
                     "Это тестовое сообщение для проверки системы напоминаний!"
            )

            await self.save_reminder_sent(teacher_id)
            logger.info(f"✅ Test reminder sent to teacher {teacher_id}")

        except Exception as e:
            logger.error(f"❌ Error sending test reminder: {e}")