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
        # 1. Сначала пробуем получить строку подключения из DATABASE_URL
        self.connection_string = os.getenv("DATABASE_URL")

        if self.connection_string:
            logger.info("✅ Используется DATABASE_URL для подключения")
        else:
            # 2. Если DATABASE_URL нет, собираем из отдельных параметров
            # Используем настройки для Docker-базы по умолчанию
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5433")  # ⬅️ ПОРТ 5433 для Docker
            db_user = os.getenv("DB_USER", "shedull_user")
            db_password = os.getenv("DB_PASSWORD", "ShedullBot123!")
            db_name = os.getenv("DB_NAME", "ShedullBot")

            # Формируем строку подключения
            self.connection_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

            logger.info(f"✅ Собрана строка подключения: {db_host}:{db_port}")

        # Выводим отладочную информацию (без пароля)
        safe_connection_string = self.connection_string.replace(
            os.getenv("DB_PASSWORD", ""),
            "***"
        ) if os.getenv("DB_PASSWORD") else self.connection_string
        logger.info(f"📊 Подключение к базе: {safe_connection_string}")

        self.pool = None

    async def connect(self):
        """Установка соединения с базой данных"""
        try:
            self.pool = await asyncpg.create_pool(self.connection_string)
            logger.info("✅ Успешно подключились к PostgreSQL базе данных")

            # Проверяем существование таблиц
            await self.check_tables()  # ⬅️ Изменили с _check_tables на check_tables

        except asyncpg.InvalidPasswordError:
            logger.error("❌ ОШИБКА: Неверный пароль для подключения к базе")
            logger.error("Проверьте DB_PASSWORD в .env файле")
            raise
        except asyncpg.ConnectionDoesNotExistError:
            logger.error("❌ ОШИБКА: Не удалось подключиться к базе")
            logger.error(f"Проверьте: {self.connection_string}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к базе данных: {e}")
            raise

    async def check_tables(self):
        """Проверяет существование таблиц"""
        try:
            async with self.pool.acquire() as conn:
                # Проверяем существование таблиц
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    AND table_name IN ('content_info', 'content_data', 'payments', 
                                      'users', 'subjects', 'students', 'teachers', 
                                      'bookings', 'parent_children')
                """)

                if len(tables) == 9:
                    logger.info("✅ All tables exist")
                else:
                    logger.warning("⚠️ Some tables are missing")
                    # Создаем таблицы если их нет
                    await self.create_tables(conn)

        except Exception as e:
            logger.error(f"Error checking tables: {e}")
            raise

    async def create_tables(self, conn):
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

            # Таблица предметов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS subjects (
                    subject_id VARCHAR(10) PRIMARY KEY,
                    subject_name VARCHAR(100) NOT NULL,
                    material_link TEXT
                )
            """)

            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    user_name VARCHAR(255) NOT NULL,
                    roles TEXT,  -- 'student', 'teacher', 'parent' через запятую
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица студентов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    student_id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                    subject_id VARCHAR(10) REFERENCES subjects(subject_id),
                    class INTEGER,
                    attention_need INTEGER DEFAULT 3,
                    balance DECIMAL(10, 2) DEFAULT 0.0,
                    tariff DECIMAL(10, 2) DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, subject_id)
                )
            """)

            # Таблица преподавателей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS teachers (
                    teacher_id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                    subject_id VARCHAR(10) REFERENCES subjects(subject_id),
                    priority VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, subject_id)
                )
            """)

            # Таблица связи родитель-дети
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS parent_children (
                    id SERIAL PRIMARY KEY,
                    parent_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(parent_id, child_id)
                )
            """)

            # Таблица бронирований
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    user_role VARCHAR(20) NOT NULL,  -- 'student' или 'teacher'
                    booking_type VARCHAR(50) DEFAULT 'Тип1',
                    date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    subject_id VARCHAR(10) REFERENCES subjects(subject_id),  -- для студентов
                    subjects TEXT,  -- для преподавателей (через запятую)
                    parent_id INTEGER REFERENCES users(user_id),  -- если запись от родителя
                    parent_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Создаем индексы
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_from_user ON payments(from_user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_to_user ON payments(to_user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_content_info_added_by ON content_info(added_by)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user_role ON bookings(user_role)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_students_user_id ON students(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_teachers_user_id ON teachers(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_children_parent ON parent_children(parent_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_children_child ON parent_children(child_id)")

            logger.info("✅ Tables created successfully")

        except Exception as e:
            logger.error(f"❌ Error creating tables: {e}")
            raise

    async def close(self):
        """Закрытие соединения"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")

    async def check_parent_child_link(self, parent_id: int, child_id: int) -> bool:
        """Проверяет, есть ли привязка родитель-ребенок"""
        try:
            async with self.pool.acquire() as conn:
                link = await conn.fetchrow(
                    "SELECT id FROM parent_children WHERE parent_id = $1 AND child_id = $2",
                    parent_id, child_id
                )
                return link is not None
        except Exception as e:
            logger.error(f"Error checking parent-child link: {e}")
            return False

    async def link_parent_child(self, parent_id: int, child_id: int) -> bool:
        """Привязывает ребенка к родителю"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO parent_children (parent_id, child_id)
                    VALUES ($1, $2)
                    ON CONFLICT (parent_id, child_id) DO NOTHING
                """, parent_id, child_id)
                return True
        except Exception as e:
            logger.error(f"Error linking parent-child: {e}")
            return False

    async def unlink_parent_child(self, parent_id: int, child_id: int) -> bool:
        """Отвязывает ребенка от родителя"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM parent_children WHERE parent_id = $1 AND child_id = $2",
                    parent_id, child_id
                )
                return True
        except Exception as e:
            logger.error(f"Error unlinking parent-child: {e}")
            return False

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

    async def save_user_roles(self, user_id: int, roles: List[str]) -> bool:
        """Сохраняет несколько ролей пользователя"""
        try:
            async with self.pool.acquire() as conn:
                roles_str = ','.join(roles)
                await conn.execute("""
                    UPDATE users 
                    SET roles = $1, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = $2
                """, roles_str, user_id)
                logger.info(f"✅ User {user_id} roles saved: {roles_str}")
                return True
        except Exception as e:
            logger.error(f"❌ Error saving user roles: {e}")
            return False

    async def add_user_role(self, user_id: int, role: str) -> bool:
        """Добавляет роль пользователю (если ее еще нет)"""
        try:
            current_roles = await self.get_user_roles(user_id)
            if role in current_roles:
                return True  # Роль уже есть

            new_roles = current_roles + [role]
            roles_str = ','.join(new_roles)

            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users 
                    SET roles = $1, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = $2
                """, roles_str, user_id)
                logger.info(f"✅ Added role {role} to user {user_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Error adding user role: {e}")
            return False

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

    # ========== Методы для работы с пользователями ==========
    
    async def save_or_update_user(self, user_id: int, user_name: str, roles: str = None) -> bool:
        """Сохраняет или обновляет пользователя"""
        try:
            async with self.pool.acquire() as conn:
                # Проверяем, существует ли пользователь
                existing = await conn.fetchrow(
                    "SELECT user_id FROM users WHERE user_id = $1", user_id
                )
                
                if existing:
                    # Обновляем существующего пользователя
                    if roles:
                        await conn.execute(
                            "UPDATE users SET user_name = $1, roles = $2, updated_at = CURRENT_TIMESTAMP WHERE user_id = $3",
                            user_name, roles, user_id
                        )
                    else:
                        await conn.execute(
                            "UPDATE users SET user_name = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2",
                            user_name, user_id
                        )
                else:
                    # Создаем нового пользователя
                    await conn.execute(
                        "INSERT INTO users (user_id, user_name, roles) VALUES ($1, $2, $3)",
                        user_id, user_name, roles or ""
                    )
                
                logger.info(f"✅ User {user_id} saved/updated")
                return True
        except Exception as e:
            logger.error(f"❌ Error saving user: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает пользователя по ID"""
        try:
            async with self.pool.acquire() as conn:
                user = await conn.fetchrow(
                    "SELECT * FROM users WHERE user_id = $1", user_id
                )
                return dict(user) if user else None
        except Exception as e:
            logger.error(f"❌ Error getting user: {e}")
            return None

    async def get_user_roles(self, user_id: int) -> List[str]:
        """Получает роли пользователя"""
        try:
            user = await self.get_user(user_id)
            if user and user.get('roles'):
                return [r.strip() for r in user['roles'].split(',') if r.strip()]
            return []
        except Exception as e:
            logger.error(f"❌ Error getting user roles: {e}")
            return []

    # ========== Методы для работы с предметами ==========
    
    async def save_subject(self, subject_id: str, subject_name: str, material_link: str = None) -> bool:
        """Сохраняет предмет"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO subjects (subject_id, subject_name, material_link)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (subject_id) 
                    DO UPDATE SET subject_name = $2, material_link = $3
                """, subject_id, subject_name, material_link)
                return True
        except Exception as e:
            logger.error(f"❌ Error saving subject: {e}")
            return False

    # ========== Методы для работы со студентами ==========
    
    async def save_student(self, user_id: int, subject_id: str, class_num: int = None, 
                          attention_need: int = 3, balance: float = 0.0, tariff: float = 0.0) -> bool:
        """Сохраняет или обновляет студента"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO students (user_id, subject_id, class, attention_need, balance, tariff)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (user_id, subject_id)
                    DO UPDATE SET 
                        class = COALESCE($3, students.class),
                        attention_need = COALESCE($4, students.attention_need),
                        balance = COALESCE($5, students.balance),
                        tariff = COALESCE($6, students.tariff),
                        updated_at = CURRENT_TIMESTAMP
                """, user_id, subject_id, class_num, attention_need, balance, tariff)
                return True
        except Exception as e:
            logger.error(f"❌ Error saving student: {e}")
            return False

    async def get_student(self, user_id: int, subject_id: str = None) -> Optional[Dict[str, Any]]:
        """Получает данные студента"""
        try:
            async with self.pool.acquire() as conn:
                if subject_id:
                    student = await conn.fetchrow(
                        "SELECT * FROM students WHERE user_id = $1 AND subject_id = $2",
                        user_id, subject_id
                    )
                else:
                    # Возвращаем первого студента (если несколько предметов)
                    student = await conn.fetchrow(
                        "SELECT * FROM students WHERE user_id = $1 LIMIT 1",
                        user_id
                    )
                return dict(student) if student else None
        except Exception as e:
            logger.error(f"❌ Error getting student: {e}")
            return None

    # ========== Методы для работы с преподавателями ==========
    
    async def save_teacher(self, user_id: int, subject_id: str, priority: str = None) -> bool:
        """Сохраняет или обновляет преподавателя"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO teachers (user_id, subject_id, priority)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, subject_id)
                    DO UPDATE SET 
                        priority = COALESCE($3, teachers.priority),
                        updated_at = CURRENT_TIMESTAMP
                """, user_id, subject_id, priority)
                return True
        except Exception as e:
            logger.error(f"❌ Error saving teacher: {e}")
            return False

    async def get_teacher_subjects(self, user_id: int) -> List[str]:
        """Получает список предметов преподавателя"""
        try:
            async with self.pool.acquire() as conn:
                subjects = await conn.fetch(
                    "SELECT subject_id FROM teachers WHERE user_id = $1", user_id
                )
                return [s['subject_id'] for s in subjects]
        except Exception as e:
            logger.error(f"❌ Error getting teacher subjects: {e}")
            return []

    # ========== Методы для работы с бронированиями ==========
    
    async def add_booking(self, booking_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Добавляет новое бронирование"""
        try:
            async with self.pool.acquire() as conn:
                # Подготавливаем данные
                user_id = booking_data.get('user_id')
                user_role = booking_data.get('user_role')
                date = booking_data.get('date')
                start_time = booking_data.get('start_time')
                end_time = booking_data.get('end_time')
                subject_id = booking_data.get('subject') if user_role == 'student' else None
                subjects = ','.join(booking_data.get('subjects', [])) if user_role == 'teacher' else None
                parent_id = booking_data.get('parent_id')
                parent_name = booking_data.get('parent_name')
                booking_type = booking_data.get('booking_type', 'Тип1')
                
                # Преобразуем дату и время
                if isinstance(date, str):
                    date_obj = datetime.strptime(date, "%Y-%m-%d").date()
                else:
                    date_obj = date
                
                if isinstance(start_time, str):
                    start_time_obj = datetime.strptime(start_time, "%H:%M").time()
                else:
                    start_time_obj = start_time
                    
                if isinstance(end_time, str):
                    end_time_obj = datetime.strptime(end_time, "%H:%M").time()
                else:
                    end_time_obj = end_time
                
                # Вставляем бронирование (SERIAL автоматически генерирует ID)
                booking_id = await conn.fetchval("""
                    INSERT INTO bookings (
                        user_id, user_role, booking_type, date, 
                        start_time, end_time, subject_id, subjects, 
                        parent_id, parent_name
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING booking_id
                """, user_id, user_role, booking_type, date_obj, 
                    start_time_obj, end_time_obj, subject_id, subjects, parent_id, parent_name)
                
                # Формируем результат
                result = booking_data.copy()
                result['id'] = booking_id
                result['booking_id'] = booking_id
                
                logger.info(f"✅ Booking {booking_id} saved")
                return result
        except Exception as e:
            logger.error(f"❌ Error adding booking: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def get_user_bookings(self, user_id: int, date: str = None) -> List[Dict[str, Any]]:
        """Получает бронирования пользователя"""
        try:
            async with self.pool.acquire() as conn:
                if date:
                    bookings = await conn.fetch("""
                        SELECT b.*, u.user_name
                        FROM bookings b
                        JOIN users u ON b.user_id = u.user_id
                        WHERE b.user_id = $1 AND b.date = $2
                        ORDER BY b.date, b.start_time
                    """, user_id, date)
                else:
                    bookings = await conn.fetch("""
                        SELECT b.*, u.user_name
                        FROM bookings b
                        JOIN users u ON b.user_id = u.user_id
                        WHERE b.user_id = $1
                        ORDER BY b.date, b.start_time
                    """, user_id)
                
                result = []
                for booking in bookings:
                    b = dict(booking)
                    # Преобразуем время обратно в строки
                    if b.get('start_time'):
                        b['start_time'] = b['start_time'].strftime("%H:%M")
                    if b.get('end_time'):
                        b['end_time'] = b['end_time'].strftime("%H:%M")
                    if b.get('date'):
                        b['date'] = b['date'].strftime("%Y-%m-%d")
                    # Преобразуем subjects обратно в список
                    if b.get('subjects'):
                        b['subjects'] = [s.strip() for s in b['subjects'].split(',') if s.strip()]
                    result.append(b)
                
                return result
        except Exception as e:
            logger.error(f"❌ Error getting user bookings: {e}")
            return []

    async def cancel_booking(self, booking_id: int) -> bool:
        """Отменяет бронирование"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM bookings WHERE booking_id = $1", booking_id
                )
                return result == "DELETE 1"
        except Exception as e:
            logger.error(f"❌ Error canceling booking: {e}")
            return False

    async def has_booking_conflict(self, user_id: int, date: str, start_time: str, 
                                   end_time: str, exclude_booking_id: int = None) -> bool:
        """Проверяет конфликт временных интервалов"""
        try:
            async with self.pool.acquire() as conn:
                date_obj = datetime.strptime(date, "%Y-%m-%d").date()
                start_time_obj = datetime.strptime(start_time, "%H:%M").time()
                end_time_obj = datetime.strptime(end_time, "%H:%M").time()
                
                query = """
                    SELECT booking_id FROM bookings
                    WHERE user_id = $1 AND date = $2
                    AND (
                        (start_time < $4 AND end_time > $3)
                    )
                """
                params = [user_id, date_obj, start_time_obj, end_time_obj]
                
                if exclude_booking_id:
                    query += " AND booking_id != $5"
                    params.append(exclude_booking_id)
                
                conflict = await conn.fetchrow(query, *params)
                return conflict is not None
        except Exception as e:
            logger.error(f"❌ Error checking booking conflict: {e}")
            return False

    # ========== Дополнительные методы для замены функционала Google Sheets ==========
    
    async def get_user_name_sync(self, user_id: int) -> str:
        """Синхронная обертка для получения имени пользователя"""
        try:
            user = await self.get_user(user_id)
            return user.get('user_name', '') if user else ''
        except Exception as e:
            logger.error(f"❌ Error getting user name: {e}")
            return ''

    async def get_user_roles_sync(self, user_id: int) -> List[str]:
        """Синхронная обертка для получения ролей пользователя"""
        return await self.get_user_roles(user_id)

    async def has_user_roles_sync(self, user_id: int) -> bool:
        """Синхронная обертка для проверки наличия ролей"""
        roles = await self.get_user_roles(user_id)
        return len(roles) > 0

    async def save_user_info_sync(self, user_id: int, user_name: str) -> bool:
        """Синхронная обертка для сохранения информации о пользователе"""
        return await self.save_or_update_user(user_id, user_name)

    async def get_user_data_sync(self, user_id: int) -> Dict[str, Any]:
        """Получает все данные пользователя (включая студентов и преподавателей)"""
        try:
            user = await self.get_user(user_id)
            if not user:
                return {}
            
            result = {
                'user_id': user.get('user_id'),
                'user_name': user.get('user_name', ''),
                'roles': user.get('roles', '')
            }
            
            # Получаем данные студента
            async with self.pool.acquire() as conn:
                students = await conn.fetch(
                    "SELECT * FROM students WHERE user_id = $1", user_id
                )
                if students:
                    student_data = dict(students[0])
                    result['class'] = student_data.get('class')
                    result['attention_need'] = student_data.get('attention_need')
                    result['balance'] = float(student_data.get('balance', 0))
                    result['tariff'] = float(student_data.get('tariff', 0))
                    result['subject_id'] = student_data.get('subject_id')
            
            # Получаем предметы преподавателя
            teacher_subjects = await self.get_teacher_subjects(user_id)
            if teacher_subjects:
                result['teacher_subjects'] = ','.join(teacher_subjects)
                result['subjects'] = teacher_subjects
            
            return result
        except Exception as e:
            logger.error(f"❌ Error getting user data: {e}")
            return {}

    async def save_user_data_sync(self, user_data: dict) -> bool:
        """Сохраняет данные пользователя"""
        try:
            user_id = user_data.get('user_id')
            user_name = user_data.get('user_name', '')
            roles = user_data.get('roles', '')
            
            if not user_id:
                return False
            
            # Сохраняем пользователя
            await self.save_or_update_user(user_id, user_name, roles)
            
            # Сохраняем данные студента, если есть
            if 'subject_id' in user_data:
                class_num = user_data.get('class')
                attention_need = user_data.get('attention_need', 3)
                balance = user_data.get('balance', 0.0)
                tariff = user_data.get('tariff', 0.0)
                await self.save_student(user_id, user_data['subject_id'], class_num, 
                                      attention_need, balance, tariff)
            
            # Сохраняем предметы преподавателя, если есть
            if 'subjects' in user_data or 'teacher_subjects' in user_data:
                subjects = user_data.get('subjects', [])
                if not subjects and 'teacher_subjects' in user_data:
                    subjects = [s.strip() for s in user_data['teacher_subjects'].split(',') if s.strip()]
                
                for subject_id in subjects:
                    priority = user_data.get('priority', '')
                    await self.save_teacher(user_id, subject_id, priority)
            
            return True
        except Exception as e:
            logger.error(f"❌ Error saving user data: {e}")
            return False

    async def get_available_subjects_for_student_sync(self, user_id: int) -> List[str]:
        """Получает доступные предметы для ученика"""
        try:
            async with self.pool.acquire() as conn:
                subjects = await conn.fetch(
                    "SELECT DISTINCT subject_id FROM students WHERE user_id = $1", user_id
                )
                return [s['subject_id'] for s in subjects]
        except Exception as e:
            logger.error(f"❌ Error getting available subjects: {e}")
            return []

    async def get_student_balance_sync(self, student_id: int) -> float:
        """Получает общий баланс студента (сумма по всем предметам)"""
        try:
            async with self.pool.acquire() as conn:
                balances = await conn.fetch(
                    "SELECT balance FROM students WHERE user_id = $1", student_id
                )
                total = sum(float(b['balance']) for b in balances)
                return total
        except Exception as e:
            logger.error(f"❌ Error getting student balance: {e}")
            return 0.0

    async def get_student_balance_by_subjects_sync(self, student_id: int) -> Dict[str, float]:
        """Получает баланс студента разбитый по предметам"""
        try:
            async with self.pool.acquire() as conn:
                students = await conn.fetch(
                    "SELECT subject_id, balance FROM students WHERE user_id = $1", student_id
                )
                return {s['subject_id']: float(s['balance']) for s in students}
        except Exception as e:
            logger.error(f"❌ Error getting student balance by subjects: {e}")
            return {}

    async def update_student_balance_sync(self, student_id: int, amount: float, subject_id: str = None):
        """Обновляет баланс студента"""
        try:
            async with self.pool.acquire() as conn:
                if subject_id:
                    # Обновляем баланс для конкретного предмета
                    await conn.execute("""
                        UPDATE students 
                        SET balance = balance + $1, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $2 AND subject_id = $3
                    """, amount, student_id, subject_id)
                else:
                    # Обновляем баланс для всех предметов
                    await conn.execute("""
                        UPDATE students 
                        SET balance = balance + $1, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = $2
                    """, amount, student_id)
        except Exception as e:
            logger.error(f"❌ Error updating student balance: {e}")

    async def get_parent_children_sync(self, parent_id: int) -> List[int]:
        """Получает список ID детей родителя"""
        try:
            async with self.pool.acquire() as conn:
                children = await conn.fetch(
                    "SELECT child_id FROM parent_children WHERE parent_id = $1",
                    parent_id
                )
                return [c['child_id'] for c in children]
        except Exception as e:
            logger.error(f"❌ Error getting parent children: {e}")
            return []

    async def get_child_info_sync(self, child_id: int) -> dict:
        """Получает информацию о ребенке (ученике)"""
        try:
            user = await self.get_user(child_id)
            if not user:
                return {}
            
            student = await self.get_student(child_id)
            if not student:
                return {}
            
            return {
                'user_id': child_id,
                'user_name': user.get('user_name', ''),
                'subject_id': student.get('subject_id'),
                'class': student.get('class'),
                'attention_need': student.get('attention_need'),
                'balance': float(student.get('balance', 0)),
                'tariff': float(student.get('tariff', 0))
            }
        except Exception as e:
            logger.error(f"❌ Error getting child info: {e}")
            return {}

    async def save_parent_info_sync(self, parent_id: int, parent_name: str, children_ids: List[int] = None) -> bool:
        """Сохраняет информацию о родителе"""
        try:
            # Сохраняем пользователя с ролью parent
            current_roles = await self.get_user_roles(parent_id)
            new_roles = set(current_roles)
            new_roles.add('parent')
            await self.save_or_update_user(parent_id, parent_name, ",".join(new_roles))
            
            # Сохраняем связи родитель-дети
            if children_ids:
                async with self.pool.acquire() as conn:
                    # Удаляем старые связи
                    await conn.execute(
                        "DELETE FROM parent_children WHERE parent_id = $1",
                        parent_id
                    )
                    # Добавляем новые связи
                    for child_id in children_ids:
                        await conn.execute("""
                            INSERT INTO parent_children (parent_id, child_id)
                            VALUES ($1, $2)
                            ON CONFLICT (parent_id, child_id) DO NOTHING
                        """, parent_id, child_id)
            
            return True
        except Exception as e:
            logger.error(f"❌ Error saving parent info: {e}")
            return False


# Глобальный экземпляр базы данных
db = DatabaseManager()