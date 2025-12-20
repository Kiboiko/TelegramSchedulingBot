# migrate_to_db.py
import asyncio
import json
import logging
from datetime import datetime
from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_feedback_data():
    """Переносит данные фидбэков из JSON файлов в БД"""
    try:
        # Миграция студенческих фидбэков
        try:
            with open("feedback.json", 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)

            migrated_count = 0
            for feedback in feedbacks:
                try:
                    if feedback.get('status') == 'completed':
                        async with db.pool.acquire() as conn:
                            date_obj = datetime.fromisoformat(
                                feedback['responded_at']
                            ).date() if 'responded_at' in feedback else datetime.now().date()

                            await conn.execute("""
                                INSERT INTO feedback_students 
                                (user_id, subject_id, date, rating, details, sent, synced_to_sheets)
                                VALUES ($1, $2, $3, $4, $5, TRUE, TRUE)
                                ON CONFLICT (user_id, subject_id, date) DO NOTHING
                            """,
                                               feedback['user_id'],
                                               feedback.get('subject'),
                                               date_obj,
                                               feedback.get('rating', 'good'),
                                               feedback.get('details', ''))

                            migrated_count += 1

                except Exception as e:
                    logger.error(f"Error migrating feedback {feedback}: {e}")

            logger.info(f"✅ Migrated {migrated_count} student feedbacks")

        except FileNotFoundError:
            logger.info("Student feedback file not found, skipping")

        # Миграция преподавательских фидбэков
        try:
            with open("feedback_teachers.json", 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)

            migrated_count = 0
            for feedback in feedbacks:
                try:
                    if feedback.get('status') == 'completed':
                        async with db.pool.acquire() as conn:
                            date_obj = datetime.fromisoformat(
                                feedback['responded_at']
                            ).date() if 'responded_at' in feedback else datetime.now().date()

                            await conn.execute("""
                                INSERT INTO feedback_teachers 
                                (user_id, date, rating, details, sent, synced_to_sheets)
                                VALUES ($1, $2, $3, $4, TRUE, TRUE)
                                ON CONFLICT (user_id, date) DO NOTHING
                            """,
                                               feedback['user_id'],
                                               date_obj,
                                               feedback.get('rating', 'good'),
                                               feedback.get('details', ''))

                            migrated_count += 1

                except Exception as e:
                    logger.error(f"Error migrating teacher feedback {feedback}: {e}")

            logger.info(f"✅ Migrated {migrated_count} teacher feedbacks")

        except FileNotFoundError:
            logger.info("Teacher feedback file not found, skipping")

        logger.info("✅ Feedback migration completed")

    except Exception as e:
        logger.error(f"❌ Error migrating feedback data: {e}")


async def main():
    await db.connect()
    await migrate_feedback_data()


if __name__ == "__main__":
    asyncio.run(main())