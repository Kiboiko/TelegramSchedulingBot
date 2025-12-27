import logging
from datetime import datetime, timedelta
from typing import List, Dict
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database import db
import asyncio  # Добавлен импорт

logger = logging.getLogger(__name__)


class StudentReminderManager:
    def __init__(self, storage, gsheets, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets
        self.bot = bot

    async def has_bookings_in_current_month(self, user_id: int) -> bool:
        """Проверяет, есть ли у ученика записи в текущем месяце через БД"""
        try:
            now = datetime.now()
            current_month_start = datetime(now.year, now.month, 1).date()
            current_month_end = (datetime(now.year, now.month, 1) + timedelta(days=31)).date()

            async with db.pool.acquire() as conn:
                bookings = await conn.fetch("""
                    SELECT COUNT(*) as count
                    FROM bookings 
                    WHERE user_id = $1 
                    AND user_role = 'student'
                    AND date >= $2
                    AND date < $3
                """, user_id, current_month_start, current_month_end)

                return bookings[0]['count'] > 0 if bookings else False

        except Exception as e:
            logger.error(f"❌ Error checking bookings for user {user_id}: {e}")
            return True  # В случае ошибки считаем, что записи есть

    async def get_all_students(self) -> List[Dict]:
        """Получает всех учеников из БД"""
        try:
            async with db.pool.acquire() as conn:
                students = await conn.fetch("""
                    SELECT u.user_id, u.user_name, u.roles
                    FROM users u
                    JOIN students s ON u.user_id = s.user_id
                    WHERE u.roles LIKE '%student%'
                    AND u.user_name IS NOT NULL
                    AND u.user_name != ''
                    GROUP BY u.user_id, u.user_name, u.roles
                """)

                result = []
                for student in students:
                    roles_list = [r.strip() for r in student['roles'].split(',') if r.strip()] if student['roles'] else []
                    result.append({
                        'user_id': student['user_id'],
                        'user_name': student['user_name'],
                        'roles': roles_list
                    })

                logger.info(f"✅ Found {len(result)} students")
                return result

        except Exception as e:
            logger.error(f"❌ Error getting students: {e}")
            return []

    def generate_reminder_keyboard(self):
        """Генерирует клавиатуру для напоминания"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 Давайте запишемся!", callback_data="reminder_book_now")]
        ])
        return keyboard

    async def send_reminder(self, user_id: int, user_name: str):
        """Отправляет напоминание ученику"""
        try:
            # Проверяем, не отправляли ли уже напоминание в этом месяце
            if await self.check_reminder_sent(user_id, 'student_no_booking'):
                logger.info(f"✅ Reminder already sent to {user_id} this month")
                return

            keyboard = self.generate_reminder_keyboard()

            await self.bot.send_message(
                chat_id=user_id,
                text=f"Привет, {user_name}! 👋\n\n"
                     f"Тебя давно не было на занятии, давай запишемся!\n"
                     f"Выбери удобное время и предмет для занятия 📚",
                reply_markup=keyboard
            )

            # Сохраняем факт отправки напоминания
            await self.save_reminder_sent(user_id, 'student_no_booking')
            logger.info(f"✅ Reminder sent to user {user_id} ({user_name})")

        except Exception as e:
            logger.error(f"❌ Error sending reminder to user {user_id}: {e}")

    async def check_reminder_sent(self, user_id: int, reminder_type: str) -> bool:
        """Проверяет, отправляли ли уже напоминание в этом месяце"""
        try:
            async with db.pool.acquire() as conn:
                this_month_start = datetime.now().replace(day=1).date()
                reminder = await conn.fetchrow("""
                    SELECT reminder_id FROM reminders 
                    WHERE user_id = $1 
                    AND reminder_type = $2
                    AND target_date >= $3
                    AND sent = TRUE
                """, user_id, reminder_type, this_month_start)
                return reminder is not None
        except Exception as e:
            logger.error(f"❌ Error checking reminder sent: {e}")
            return False

    async def save_reminder_sent(self, user_id: int, reminder_type: str):
        """Сохраняет факт отправки напоминания"""
        try:
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO reminders (user_id, reminder_type, target_date, sent, sent_at)
                    VALUES ($1, $2, $3, TRUE, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, reminder_type, target_date) 
                    DO UPDATE SET sent = TRUE, sent_at = CURRENT_TIMESTAMP
                """, user_id, reminder_type, datetime.now().date())
        except Exception as e:
            logger.error(f"❌ Error saving reminder: {e}")

    async def check_and_send_reminders(self):
        """Основная функция проверки и отправки напоминаний"""
        try:
            logger.info("✅ Starting student reminder check for current month...")

            # Проверяем, нужно ли запускать проверку (15 число каждого месяца)
            if not self.should_run_check():
                logger.info("✅ Not the 15th of the month, skipping reminder check")
                return

            students = await self.get_all_students()
            logger.info(f"✅ Found {len(students)} students to check")

            reminders_sent = 0

            for student in students:
                user_id = student['user_id']
                user_name = student['user_name']

                # Проверяем, есть ли записи в текущем месяце
                has_bookings = await self.has_bookings_in_current_month(user_id)

                if not has_bookings:
                    logger.info(f"✅ Student {user_name} ({user_id}) has no bookings this month, sending reminder")
                    await self.send_reminder(user_id, user_name)
                    reminders_sent += 1
                    await asyncio.sleep(0.1)  # Небольшая задержка
                else:
                    logger.info(f"✅ Student {user_name} ({user_id}) has bookings this month, skipping")

            logger.info(f"✅ Student reminder check completed. Sent {reminders_sent} reminders")

        except Exception as e:
            logger.error(f"❌ Error in student reminder check: {e}")

    def should_run_check(self) -> bool:
        """Проверяет, нужно ли запускать проверку (15 число каждого месяца)"""
        now = datetime.now()
        return now.day == 15

    async def create_reminders_for_no_bookings(self):
        """Создает напоминания для студентов без записей на следующую неделю"""
        try:
            # Находим студентов без записей на следующую неделю
            next_week_start = datetime.now() + timedelta(days=7)
            next_week_end = next_week_start + timedelta(days=7)

            async with db.pool.acquire() as conn:
                students = await conn.fetch("""
                    SELECT u.user_id, u.user_name
                    FROM users u
                    JOIN students s ON u.user_id = s.user_id
                    WHERE u.roles LIKE '%student%'
                    AND NOT EXISTS (
                        SELECT 1 FROM bookings b
                        WHERE b.user_id = u.user_id
                        AND b.user_role = 'student'
                        AND b.date BETWEEN $1 AND $2
                    )
                """, next_week_start.date(), next_week_end.date())

                for student in students:
                    await self.create_reminder(
                        student['user_id'],
                        'student_no_booking_next_week',
                        next_week_start.strftime("%Y-%m-%d")
                    )

                logger.info(f"✅ Created reminders for {len(students)} students without bookings")

        except Exception as e:
            logger.error(f"❌ Error creating reminders: {e}")

    async def create_reminder(self, user_id: int, reminder_type: str, target_date: str):
        """Создает напоминание в БД"""
        try:
            async with db.pool.acquire() as conn:
                date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
                await conn.execute("""
                    INSERT INTO reminders (user_id, reminder_type, target_date, sent)
                    VALUES ($1, $2, $3, FALSE)
                    ON CONFLICT (user_id, reminder_type, target_date) DO NOTHING
                """, user_id, reminder_type, date_obj)
        except Exception as e:
            logger.error(f"❌ Error creating reminder: {e}")

    async def clear_sent_reminders(self):
        """Очищает список отправленных напоминаний в начале месяца"""
        try:
            # В начале месяца можно очистить старые напоминания
            now = datetime.now()
            if now.day == 1:  # Первое число месяца
                async with db.pool.acquire() as conn:
                    # Можно удалить напоминания старше 3 месяцев
                    three_months_ago = (now - timedelta(days=90)).date()
                    await conn.execute("""
                        DELETE FROM reminders 
                        WHERE target_date < $1
                        AND reminder_type LIKE 'student_%'
                    """, three_months_ago)
                    logger.info("✅ Old student reminders cleared")
        except Exception as e:
            logger.error(f"❌ Error clearing sent reminders: {e}")

    async def get_reminder_stats(self) -> Dict:
        """Получает статистику напоминаний для учеников"""
        try:
            async with db.pool.acquire() as conn:
                # Общая статистика
                total_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_reminders,
                        SUM(CASE WHEN sent THEN 1 ELSE 0 END) as sent_reminders,
                        SUM(CASE WHEN NOT sent THEN 1 ELSE 0 END) as pending_reminders,
                        COUNT(DISTINCT user_id) as unique_students
                    FROM reminders
                    WHERE reminder_type LIKE 'student_%'
                """)

                # Статистика за этот месяц
                monthly_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as this_month_reminders,
                        COUNT(DISTINCT user_id) as this_month_students
                    FROM reminders
                    WHERE reminder_type LIKE 'student_%'
                    AND target_date >= DATE_TRUNC('month', CURRENT_DATE)
                    AND target_date < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
                """)

                return {
                    'total': dict(total_stats) if total_stats else {},
                    'this_month': dict(monthly_stats) if monthly_stats else {}
                }
        except Exception as e:
            logger.error(f"❌ Error getting student reminder stats: {e}")
            return {}