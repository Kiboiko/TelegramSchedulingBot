import logging
from datetime import datetime
from typing import List, Dict, Any
from aiogram import Bot, types
from database import db
from config import SUBJECTS

logger = logging.getLogger(__name__)


class FeedbackTeacherManager:
    def __init__(self, storage, gsheets_manager, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets_manager
        self.bot = bot
        self.good_feedback_delay = 7

    async def save_feedback_response(self, user_id: int, date_str: str,
                                     rating: str, details: str = ""):
        """Сохраняет ответ обратной связи преподавателя в БД"""
        try:
            async with db.pool.acquire() as conn:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

                # Проверяем существующую запись
                existing = await conn.fetchrow("""
                    SELECT feedback_id FROM feedback_teachers 
                    WHERE user_id = $1 AND date = $2
                """, user_id, date_obj)

                if existing:
                    # Обновляем существующую запись
                    await conn.execute("""
                        UPDATE feedback_teachers 
                        SET rating = $1, details = $2, created_at = CURRENT_TIMESTAMP
                        WHERE user_id = $3 AND date = $4
                    """, rating, details, user_id, date_obj)
                else:
                    # Создаем новую запись
                    await conn.execute("""
                        INSERT INTO feedback_teachers 
                        (user_id, date, rating, details)
                        VALUES ($1, $2, $3, $4)
                    """, user_id, date_obj, rating, details)

                logger.info(f"✅ Teacher feedback saved: user_id={user_id}, date={date_str}")

        except Exception as e:
            logger.error(f"❌ Error saving teacher feedback: {e}")

    async def get_todays_finished_lessons(self) -> List[Dict[str, Any]]:
        """Получает список завершенных смен преподавателей на сегодня"""
        try:
            today = datetime.now().date()
            today_str = today.strftime("%Y-%m-%d")

            # Получаем бронирования преподавателей на сегодня
            async with db.pool.acquire() as conn:
                bookings = await conn.fetch("""
                    SELECT b.*, u.user_name
                    FROM bookings b
                    JOIN users u ON b.user_id = u.user_id
                    WHERE b.user_role = 'teacher'
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

                    # Получаем предметы преподавателя
                    subjects = []
                    if b.get('subjects'):
                        subjects = [s.strip() for s in b['subjects'].split(',') if s.strip()]
                    b['subjects'] = subjects

                    # Проверяем, нужно ли отправлять фидбэк
                    if await self.should_send_feedback(b['user_id'], today_str):
                        finished_lessons.append(b)

                return finished_lessons

        except Exception as e:
            logger.error(f"❌ Error getting finished teacher lessons: {e}")
            return []

    async def should_send_feedback(self, user_id: int, date_str: str) -> bool:
        """Определяет, нужно ли отправлять отзыв преподавателю"""
        try:
            # Проверяем, не отправляли ли уже отзыв
            if await self.check_feedback_sent(user_id, date_str):
                return False

            # Получаем количество смен с последнего "Хорошо"
            shift_count = await self.get_shift_count_since_last_good_feedback(user_id)

            # Если было "Хорошо" и прошло меньше смен, чем delay - не отправляем
            if shift_count > 0 and shift_count < self.good_feedback_delay:
                return False

            return True

        except Exception as e:
            logger.error(f"❌ Error checking teacher feedback need: {e}")
            return True

    async def check_feedback_sent(self, user_id: int, date_str: str) -> bool:
        """Проверяет, была ли уже отправлена обратная связь преподавателю"""
        try:
            async with db.pool.acquire() as conn:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                feedback = await conn.fetchrow("""
                    SELECT feedback_id FROM feedback_teachers 
                    WHERE user_id = $1 AND date = $2
                """, user_id, date_obj)
                return feedback is not None
        except Exception as e:
            logger.error(f"❌ Error checking teacher feedback sent: {e}")
            return True

    async def get_shift_count_since_last_good_feedback(self, user_id: int) -> int:
        """Получает количество смен с последнего отзыва 'Хорошо' у преподавателя"""
        try:
            async with db.pool.acquire() as conn:
                # Находим последний отзыв "Хорошо"
                last_good = await conn.fetchrow("""
                    SELECT date FROM feedback_teachers 
                    WHERE user_id = $1 AND rating = 'good'
                    ORDER BY date DESC LIMIT 1
                """, user_id)

                if not last_good:
                    return 0

                # Получаем смены после последнего отзыва "Хорошо"
                shifts = await conn.fetch("""
                    SELECT COUNT(*) as count
                    FROM bookings 
                    WHERE user_id = $1 
                    AND user_role = 'teacher'
                    AND date > $2
                """, user_id, last_good['date'])

                return shifts[0]['count'] if shifts else 0

        except Exception as e:
            logger.error(f"❌ Error getting teacher shift count: {e}")
            return 0

    async def send_feedback_questions(self):
        """Отправляет вопросы обратной связи преподавателям"""
        try:
            finished_lessons = await self.get_todays_finished_lessons()

            for lesson in finished_lessons:
                user_id = lesson.get('user_id')
                date_str = lesson.get('date')
                start_time = lesson.get('start_time', '')
                end_time = lesson.get('end_time', '')
                subjects = lesson.get('subjects', [])

                # Получаем название предметов
                subject_names = []
                for subject_id in subjects:
                    subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")
                    subject_names.append(subject_name)

                subjects_text = ", ".join(subject_names)

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
                            callback_data=f"feedback_teacher_good_{date_str}"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="Могло быть лучше 🤔",
                            callback_data=f"feedback_teacher_better_{date_str}"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="Ужасно 👎",
                            callback_data=f"feedback_teacher_bad_{date_str}"
                        )
                    ]
                ])

                message_text = (
                    f"Привет! Как прошла ваша смена?\n"
                    f"📅 {formatted_date} ({weekday})\n"
                    f"⏰ {start_time}-{end_time}\n"
                    f"📚 {subjects_text}"
                )

                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        reply_markup=keyboard
                    )
                    logger.info(f"✅ Teacher feedback question sent to user {user_id}")

                    # Помечаем как отправленный
                    await self.mark_feedback_sent(user_id, date_str)

                except Exception as e:
                    logger.error(f"❌ Failed to send feedback to teacher {user_id}: {e}")

        except Exception as e:
            logger.error(f"❌ Error in teacher send_feedback_questions: {e}")

    async def mark_feedback_sent(self, user_id: int, date_str: str):
        """Помечает, что запрос обратной связи был отправлен преподавателю"""
        try:
            async with db.pool.acquire() as conn:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                await conn.execute("""
                    INSERT INTO feedback_teachers 
                    (user_id, date, rating, details, sent)
                    VALUES ($1, $2, 'pending', '', TRUE)
                    ON CONFLICT (user_id, date) 
                    DO UPDATE SET sent = TRUE, created_at = CURRENT_TIMESTAMP
                """, user_id, date_obj)
        except Exception as e:
            logger.error(f"❌ Error marking teacher feedback as sent: {e}")

    async def get_pending_feedback_for_sync(self) -> List[Dict[str, Any]]:
        """Получает несинхронизированные отзывы преподавателей"""
        try:
            async with db.pool.acquire() as conn:
                feedbacks = await conn.fetch("""
                    SELECT ft.*, u.user_name
                    FROM feedback_teachers ft
                    JOIN users u ON ft.user_id = u.user_id
                    WHERE ft.synced_to_sheets = FALSE
                    AND ft.rating != 'pending'
                    LIMIT 50
                """)
                return [dict(f) for f in feedbacks]
        except Exception as e:
            logger.error(f"❌ Error getting pending teacher feedback: {e}")
            return []