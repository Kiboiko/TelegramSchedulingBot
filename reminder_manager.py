import logging
from datetime import datetime, timedelta
from typing import List, Dict
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class StudentReminderManager:
    def __init__(self, storage, gsheets, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets
        self.bot = bot
        self.sent_reminders = set()  # Чтобы не отправлять повторные напоминания

    def has_bookings_in_current_month(self, user_id: int) -> bool:
        """Проверяет, есть ли у ученика записи в текущем месяце"""
        try:
            # Получаем текущий месяц
            now = datetime.now()
            current_month_start = datetime(now.year, now.month, 1)
            if now.month == 12:
                current_month_end = datetime(now.year + 1, 1, 1) - timedelta(days=1)
            else:
                current_month_end = datetime(now.year, now.month + 1, 1) - timedelta(days=1)

            # Загружаем все бронирования
            bookings = self.storage.load_all_bookings()

            for booking in bookings:
                if (booking.get('user_id') == user_id and
                        booking.get('user_role') == 'student'):

                    try:
                        booking_date = datetime.strptime(booking['date'], "%Y-%m-%d")

                        # Проверяем, попадает ли бронь в текущий месяц
                        if current_month_start <= booking_date <= current_month_end:
                            return True

                    except (ValueError, KeyError):
                        continue

            return False

        except Exception as e:
            logger.error(f"Error checking bookings for user {user_id}: {e}")
            return True  # В случае ошибки считаем, что записи есть (не отправляем напоминание)

    def get_all_students(self) -> List[Dict]:
        """Получает всех учеников из Google Sheets с проверкой ФИО"""
        try:
            if not self.gsheets:
                return []

            worksheet = self.gsheets._get_or_create_users_worksheet()
            records = self.gsheets._get_worksheet_records(worksheet)

            students = []
            for record in records:
                roles_str = record.get('roles', '')
                user_name = record.get('user_name', '').strip()

                # Проверяем, что пользователь имеет роль студента И имеет ФИО
                if (roles_str and 'student' in roles_str.lower() and user_name):
                    students.append({
                        'user_id': int(record.get('user_id', 0)),
                        'user_name': user_name,
                        'roles': [role.strip().lower() for role in roles_str.split(',')]
                    })
                else:
                    logger.warning(f"Student {record.get('user_id')} skipped: no name or roles")

            return students

        except Exception as e:
            logger.error(f"Error getting students: {e}")
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
            if user_id in self.sent_reminders:
                return

            keyboard = self.generate_reminder_keyboard()

            await self.bot.send_message(
                chat_id=user_id,
                text=f"Привет, {user_name}! 👋\n\n"
                     f"Тебя давно не было на занятии, давай запишемся!\n"
                     f"Выбери удобное время и предмет для занятия 📚",
                reply_markup=keyboard
            )

            self.sent_reminders.add(user_id)
            logger.info(f"Reminder sent to user {user_id} ({user_name})")

        except Exception as e:
            logger.error(f"Error sending reminder to user {user_id}: {e}")

    async def check_and_send_reminders(self):
        """Основная функция проверки и отправки напоминаний"""
        try:
            logger.info("Starting student reminder check for current month...")

            students = self.get_all_students()
            logger.info(f"Found {len(students)} students to check")

            reminders_sent = 0

            for student in students:
                user_id = student['user_id']
                user_name = student['user_name']

                # Проверяем, есть ли записи в текущем месяце
                has_bookings = self.has_bookings_in_current_month(user_id)

                if not has_bookings:
                    logger.info(f"Student {user_name} ({user_id}) has no bookings this month, sending reminder")
                    await self.send_reminder(user_id, user_name)
                    reminders_sent += 1
                    # Небольшая задержка между отправками
                    import asyncio
                    await asyncio.sleep(0.1)
                else:
                    logger.info(f"Student {user_name} ({user_id}) has bookings this month, skipping")

            logger.info(f"Student reminder check completed. Sent {reminders_sent} reminders")

        except Exception as e:
            logger.error(f"Error in student reminder check: {e}")

    def should_run_check(self) -> bool:
        """Проверяет, нужно ли запускать проверку (15 число каждого месяца)"""
        now = datetime.now()
        # Запускаем 15 числа каждого месяца
        return now.day == 15

    def clear_sent_reminders(self):
        """Очищает список отправленных напоминаний (в начале месяца)"""
        now = datetime.now()
        if now.day == 1:  # В первый день месяца очищаем
            self.sent_reminders.clear()
            logger.info("Cleared sent reminders list for new month")