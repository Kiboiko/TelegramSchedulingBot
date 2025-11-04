import asyncpg
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        # Получаем строку подключения из .env
        self.connection_string = os.getenv("DATABASE_URL")
        if not self.connection_string:
            # Если нет DATABASE_URL, собираем из отдельных параметров
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "")
            db_name = os.getenv("DB_NAME", "ShedullBot")

            self.connection_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

        self.pool = None

    async def connect(self):
        """Установка соединения с базой данных"""
        try:
            self.pool = await asyncpg.create_pool(self.connection_string)
            logger.info("✅ Connected to PostgreSQL database")

            # Проверяем существование таблиц
            await self._check_tables()

        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            raise

    async def _check_tables(self):
        """Проверяет существование таблиц"""
        try:
            async with self.pool.acquire() as conn:
                # Проверяем существование таблиц
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    AND table_name IN ('content_info', 'content_data', 'payments')
                """)

                if len(tables) == 3:
                    logger.info("✅ All tables exist")
                else:
                    logger.warning("⚠️ Some tables are missing")
                    # Создаем таблицы если их нет
                    await self._create_tables(conn)

        except Exception as e:
            logger.error(f"Error checking tables: {e}")
            raise

    async def _create_tables(self, conn):
        """Создает таблицы если они не существуют"""
        try:
            # Таблица информации о контенте
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS content_info (
                    content_id SERIAL PRIMARY KEY,
                    added_by INTEGER NOT NULL,
                    center_id INTEGER DEFAULT 1,
                    added_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица данных контента
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS content_data (
                    id SERIAL PRIMARY KEY,
                    content_id INTEGER REFERENCES content_info(content_id) ON DELETE CASCADE,
                    type VARCHAR(20) NOT NULL,
                    data JSONB NOT NULL
                )
            """)

            # Таблица платежей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id SERIAL PRIMARY KEY,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER,
                    content_id INTEGER REFERENCES content_info(content_id),
                    amount DECIMAL(10, 2) NOT NULL,
                    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) DEFAULT 'pending',
                    subject_id VARCHAR(10),
                    target_user_id INTEGER,
                    teacher_confirmed BOOLEAN DEFAULT FALSE,
                    admin_notified BOOLEAN DEFAULT FALSE
                )
            """)

            # Создаем индексы
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_from_user ON payments(from_user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_to_user ON payments(to_user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_content_info_added_by ON content_info(added_by)")

            logger.info("✅ Tables created successfully")

        except Exception as e:
            logger.error(f"❌ Error creating tables: {e}")
            raise

    async def close(self):
        """Закрытие соединения"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")

    async def save_content(self, added_by: int, content_type: str, file_data: Dict[str, Any]) -> int:
        """Сохранение контента в базу данных"""
        try:
            async with self.pool.acquire() as conn:
                # Создаем запись в content_info
                content_id = await conn.fetchval(
                    "INSERT INTO content_info (added_by, center_id) VALUES ($1, $2) RETURNING content_id",
                    added_by, 1
                )

                # Сохраняем данные контента
                await conn.execute(
                    "INSERT INTO content_data (content_id, type, data) VALUES ($1, $2, $3)",
                    content_id, content_type, json.dumps(file_data)
                )

                logger.info(f"✅ Content saved with ID: {content_id}")
                return content_id

        except Exception as e:
            logger.error(f"❌ Error saving content: {e}")
            raise

    async def save_payment_with_content(self, from_user_id: int, to_user_id: int,
                                        content_id: int, amount: float, subject_id: str,
                                        target_user_id: int) -> int:
        """Сохранение платежа с привязкой к контенту"""
        try:
            async with self.pool.acquire() as conn:
                payment_id = await conn.fetchval(
                    """INSERT INTO payments (from_user_id, to_user_id, content_id, 
                       amount, subject_id, target_user_id) 
                       VALUES ($1, $2, $3, $4, $5, $6) RETURNING payment_id""",
                    from_user_id, to_user_id, content_id, amount, subject_id, target_user_id
                )

                logger.info(f"✅ Payment saved with ID: {payment_id}")
                return payment_id

        except Exception as e:
            logger.error(f"❌ Error saving payment: {e}")
            raise

    async def get_payment_with_content(self, payment_id: int) -> Optional[Dict[str, Any]]:
        """Получение платежа с информацией о контенте"""
        try:
            async with self.pool.acquire() as conn:
                payment = await conn.fetchrow(
                    """SELECT p.*, ci.added_by, ci.added_datetime, cd.type, cd.data
                       FROM payments p
                       JOIN content_info ci ON p.content_id = ci.content_id
                       JOIN content_data cd ON ci.content_id = cd.content_id
                       WHERE p.payment_id = $1""",
                    payment_id
                )

                if payment:
                    return dict(payment)
                return None

        except Exception as e:
            logger.error(f"❌ Error getting payment: {e}")
            return None

    async def update_payment_status(self, payment_id: int, status: str, teacher_confirmed: bool = None):
        """Обновление статуса платежа"""
        try:
            async with self.pool.acquire() as conn:
                if teacher_confirmed is not None:
                    await conn.execute(
                        "UPDATE payments SET status = $1, teacher_confirmed = $2 WHERE payment_id = $3",
                        status, teacher_confirmed, payment_id
                    )
                else:
                    await conn.execute(
                        "UPDATE payments SET status = $1 WHERE payment_id = $2",
                        status, payment_id
                    )

                logger.info(f"✅ Payment {payment_id} status updated to {status}")

        except Exception as e:
            logger.error(f"❌ Error updating payment status: {e}")
            raise

    async def get_user_payments(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение платежей пользователя"""
        try:
            async with self.pool.acquire() as conn:
                payments = await conn.fetch(
                    """SELECT p.*, cd.data->>'file_id' as file_id, cd.type as content_type
                       FROM payments p
                       JOIN content_info ci ON p.content_id = ci.content_id
                       JOIN content_data cd ON ci.content_id = cd.content_id
                       WHERE p.from_user_id = $1 OR p.target_user_id = $1
                       ORDER BY p.payment_date DESC
                       LIMIT $2""",
                    user_id, limit
                )

                return [dict(payment) for payment in payments]

        except Exception as e:
            logger.error(f"❌ Error getting user payments: {e}")
            return []

    async def get_pending_payments(self) -> List[Dict[str, Any]]:
        """Получение ожидающих подтверждения платежей"""
        try:
            async with self.pool.acquire() as conn:
                payments = await conn.fetch(
                    """SELECT p.*, cd.data->>'file_id' as file_id, cd.type as content_type
                       FROM payments p
                       JOIN content_info ci ON p.content_id = ci.content_id
                       JOIN content_data cd ON ci.content_id = cd.content_id
                       WHERE p.status = 'pending'
                       ORDER BY p.payment_date ASC"""
                )

                return [dict(payment) for payment in payments]

        except Exception as e:
            logger.error(f"❌ Error getting pending payments: {e}")
            return []


# Глобальный экземпляр базы данных
db = DatabaseManager()