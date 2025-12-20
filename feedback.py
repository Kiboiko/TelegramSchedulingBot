import logging
from datetime import datetime
from typing import List, Dict, Any
from aiogram import Bot, types
from database import db
from config import SUBJECTS, ADMIN_IDS
import asyncio

logger = logging.getLogger(__name__)


class FeedbackManager:
    def __init__(self, storage, gsheets_manager, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets_manager
        self.bot = bot
        self.good_feedback_delay = 7

    async def save_feedback_response(self, user_id: int, date_str: str, subject_id: str,
                                     rating: str, details: str = ""):
        """Сохраняет ответ обратной связи в БД"""
        try:
            async with db.pool.acquire() as conn:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

                # Проверяем существующую запись
                existing = await conn.fetchrow("""
                    SELECT id FROM feedback_students 
                    WHERE user_id = $1 AND date = $2 AND subject_id = $3
                """, user_id, date_obj, subject_id)

                if existing:
                    # Обновляем существующую запись
                    await conn.execute("""
                        UPDATE feedback_students 
                        SET rating = $1, details = $2, created_at = CURRENT_TIMESTAMP
                        WHERE user_id = $3 AND date = $4 AND subject_id = $5
                    """, rating, details, user_id, date_obj, subject_id)
                else:
                    # Создаем новую запись
                    await conn.execute("""
                        INSERT INTO feedback_students 
                        (user_id, subject_id, date, rating, details)
                        VALUES ($1, $2, $3, $4, $5)
                    """, user_id, subject_id, date_obj, rating, details)

                logger.info(f"✅ Student feedback saved: user_id={user_id}, date={date_str}")

                # Отправляем уведомление админам для негативных отзывов
                if rating in ['better', 'bad']:
                    await self.send_admin_notification(user_id, date_str, subject_id, rating, details)

        except Exception as e:
            logger.error(f"❌ Error saving student feedback: {e}")

    async def send_admin_notification(self, user_id: int, date_str: str, subject_id: str,
                                      rating: str, details: str = ""):
        """Отправляет уведомление администраторам о негативной обратной связи"""
        try:
            user_name = await db.get_user_name_sync(user_id)
            if not user_name:
                user_name = f"User_{user_id}"

            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")
            rating_text = {
                'better': 'Могло быть лучше',
                'bad': 'Ужасно'
            }.get(rating, rating)

            message_text = (
                "⚠️ *ВНИМАНИЕ! Негативная обратная связь!*\n\n"
                f"👤 *От:* {user_name}\n"
                f"📅 *Дата занятия:* {date_str}\n"
                f"📚 *Предмет:* {subject_name}\n"
                f"⭐ *Оценка:* {rating_text}\n"
            )

            if details:
                message_text += f"📝 *Комментарий:* {details}"

            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message_text,
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ Notification sent to admin {admin_id}")
                except Exception as e:
                    logger.error(f"❌ Failed to notify admin {admin_id}: {e}")

        except Exception as e:
            logger.error(f"❌ Error sending admin notification: {e}")

    async def get_todays_finished_lessons(self) -> List[Dict[str, Any]]:
        """Получает список завершенных занятий на сегодня с учетом счетчика"""
        try:
            today = datetime.now().date()
            today_str = today.strftime("%Y-%m-%d")

            # Получаем бронирования студентов на сегодня
            async with db.pool.acquire() as conn:
                bookings = await conn.fetch("""
                    SELECT b.*, u.user_name
                    FROM bookings b
                    JOIN users u ON b.user_id = u.user_id
                    WHERE b.user_role = 'student'
                    AND b.date = $1
                    AND b.end_time::time < CURRENT_TIME
                """, today)

                finished_lessons = []
                for booking in bookings:
                    b = dict(booking)

                    # Преобразуем время
                    if b.get('start_time'):
                        b['start_time'] = b['start_time'].strftime("%H:%M")
                    if b.get('end_time'):
                        b['end_time'] = b['end_time'].strftime("%H:%M")
                    if b.get('date'):
                        b['date'] = b['date'].strftime("%Y-%m-%d")

                    # Проверяем, нужно ли отправлять фидбэк
                    if await self.should_send_feedback(
                            b['user_id'], today_str, b.get('subject_id')
                    ):
                        finished_lessons.append(b)

                return finished_lessons

        except Exception as e:
            logger.error(f"❌ Error getting finished lessons: {e}")
            return []

    async def should_send_feedback(self, user_id: int, date_str: str, subject_id: str) -> bool:
        """Определяет, нужно ли отправлять отзыв для этого занятия"""
        try:
            # Проверяем, не отправляли ли уже отзыв для этого занятия
            if await self.check_feedback_sent(user_id, date_str, subject_id):
                return False

            # Получаем количество занятий с последнего "Хорошо"
            lesson_count = await self.get_lesson_count_since_last_good_feedback(user_id, subject_id)

            # Если было "Хорошо" и прошло меньше занятий, чем delay - не отправляем
            if lesson_count > 0 and lesson_count < self.good_feedback_delay:
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Error checking feedback need: {e}")
            return True  # При ошибке отправляем фидбэк

    async def check_feedback_sent(self, user_id: int, date_str: str, subject_id: str) -> bool:
        """Проверяет, была ли уже отправлена обратная связь"""
        try:
            async with db.pool.acquire() as conn:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                feedback = await conn.fetchrow("""
                    SELECT feedback_id FROM feedback_students 
                    WHERE user_id = $1 AND date = $2 AND subject_id = $3
                """, user_id, date_obj, subject_id)
                return feedback is not None
        except Exception as e:
            logger.error(f"❌ Error checking feedback sent: {e}")
            return True  # При ошибке считаем, что уже отправлено

    async def get_lesson_count_since_last_good_feedback(self, user_id: int, subject_id: str) -> int:
        """Получает количество занятий с последнего отзыва 'Хорошо'"""
        try:
            async with db.pool.acquire() as conn:
                # Находим последний отзыв "Хорошо"
                last_good = await conn.fetchrow("""
                    SELECT date FROM feedback_students 
                    WHERE user_id = $1 AND subject_id = $2 AND rating = 'good'
                    ORDER BY date DESC LIMIT 1
                """, user_id, subject_id)

                if not last_good:
                    return 0

                # Получаем занятия после последнего отзыва "Хорошо"
                lessons = await conn.fetch("""
                    SELECT COUNT(*) as count
                    FROM bookings 
                    WHERE user_id = $1 
                    AND subject_id = $2
                    AND user_role = 'student'
                    AND date > $3
                """, user_id, subject_id, last_good['date'])

                return lessons[0]['count'] if lessons else 0

        except Exception as e:
            logger.error(f"❌ Error getting lesson count: {e}")
            return 0

    async def send_feedback_questions(self):
        """Отправляет вопросы обратной связи для завершенных занятий"""
        try:
            finished_lessons = await self.get_todays_finished_lessons()

            for lesson in finished_lessons:
                user_id = lesson.get('user_id')
                subject_id = lesson.get('subject_id')
                date_str = lesson.get('date')
                start_time = lesson.get('start_time', '')
                end_time = lesson.get('end_time', '')

                if not all([user_id, subject_id, date_str]):
                    continue

                subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

                # Форматируем дату
                lesson_date = datetime.strptime(date_str, "%Y-%m-%d")
                weekdays_ru = ["Понедельник", "Вторник", "Среда", "Четверг",
                               "Пятница", "Суббота", "Воскресенье"]
                weekday = weekdays_ru[lesson_date.weekday()]
                formatted_date = lesson_date.strftime("%d.%m.%Y")

                # Создаем клавиатуру
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text="Хорошо 👍",
                            callback_data=f"feedback_good_{subject_id}_{date_str}"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="Могло быть лучше 🤔",
                            callback_data=f"feedback_better_{subject_id}_{date_str}"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="Ужасно 👎",
                            callback_data=f"feedback_bad_{subject_id}_{date_str}"
                        )
                    ]
                ])

                message_text = (
                    f"Привет! Как прошло занятие по {subject_name}?\n"
                    f"📅 {formatted_date} ({weekday})\n"
                    f"⏰ {start_time}-{end_time}"
                )

                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        reply_markup=keyboard
                    )
                    logger.info(f"✅ Feedback question sent to user {user_id}")

                    # Помечаем как отправленный
                    await self.mark_feedback_sent(user_id, date_str, subject_id)

                except Exception as e:
                    logger.error(f"❌ Failed to send feedback to user {user_id}: {e}")

        except Exception as e:
            logger.error(f"❌ Error in send_feedback_questions: {e}")

    async def mark_feedback_sent(self, user_id: int, date_str: str, subject_id: str):
        """Помечает, что запрос обратной связи был отправлен"""
        try:
            async with db.pool.acquire() as conn:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                await conn.execute("""
                    INSERT INTO feedback_students 
                    (user_id, subject_id, date, rating, details, sent)
                    VALUES ($1, $2, $3, 'pending', '', TRUE)
                    ON CONFLICT (user_id, subject_id, date) 
                    DO UPDATE SET sent = TRUE, created_at = CURRENT_TIMESTAMP
                """, user_id, subject_id, date_obj)
        except Exception as e:
            logger.error(f"❌ Error marking feedback as sent: {e}")

    async def get_pending_feedback_for_sync(self) -> List[Dict[str, Any]]:
        """Получает несинхронизированные отзывы (для обратной совместимости с Google Sheets)"""
        try:
            async with db.pool.acquire() as conn:
                feedbacks = await conn.fetch("""
                    SELECT fs.*, u.user_name, s.subject_name
                    FROM feedback_students fs
                    JOIN users u ON fs.user_id = u.user_id
                    LEFT JOIN subjects s ON fs.subject_id = s.subject_id
                    WHERE fs.synced_to_sheets = FALSE
                    AND fs.rating != 'pending'
                    LIMIT 50
                """)
                return [dict(f) for f in feedbacks]
        except Exception as e:
            logger.error(f"❌ Error getting pending feedback: {e}")
            return []