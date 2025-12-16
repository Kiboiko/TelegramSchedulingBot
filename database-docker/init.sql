-- Создание всех таблиц ShedullBot
-- Выполняется автоматически при первом запуске

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    user_name VARCHAR(255) NOT NULL,
    roles TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица предметов
CREATE TABLE IF NOT EXISTS subjects (
    subject_id VARCHAR(10) PRIMARY KEY,
    subject_name VARCHAR(100) NOT NULL,
    material_link TEXT
);

-- Таблица студентов
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
);

-- Таблица преподавателей
CREATE TABLE IF NOT EXISTS teachers (
    teacher_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    subject_id VARCHAR(10) REFERENCES subjects(subject_id),
    priority VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, subject_id)
);

-- Таблица связи родитель-дети
CREATE TABLE IF NOT EXISTS parent_children (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    child_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_id, child_id)
);

-- Таблица бронирований
CREATE TABLE IF NOT EXISTS bookings (
    booking_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    user_role VARCHAR(20) NOT NULL,
    booking_type VARCHAR(50) DEFAULT 'Тип1',
    date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    subject_id VARCHAR(10) REFERENCES subjects(subject_id),
    subjects TEXT,
    parent_id INTEGER REFERENCES users(user_id),
    parent_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица информации о контенте
CREATE TABLE IF NOT EXISTS content_info (
    content_id SERIAL PRIMARY KEY,
    added_by INTEGER NOT NULL,
    center_id INTEGER DEFAULT 1,
    added_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица данных контента
CREATE TABLE IF NOT EXISTS content_data (
    id SERIAL PRIMARY KEY,
    content_id INTEGER REFERENCES content_info(content_id) ON DELETE CASCADE,
    type VARCHAR(20) NOT NULL,
    data JSONB NOT NULL
);

-- Таблица платежей
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
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date);
CREATE INDEX IF NOT EXISTS idx_students_user_id ON students(user_id);
CREATE INDEX IF NOT EXISTS idx_teachers_user_id ON teachers(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_from_user ON payments(from_user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

-- Добавляем тестовые предметы
INSERT INTO subjects (subject_id, subject_name) VALUES
('1', 'Математика'),
('2', 'Физика'),
('3', 'Химия'),
('4', 'Информатика'),
('5', 'Русский язык'),
('6', 'Литература'),
('7', 'История'),
('8', 'Обществознание'),
('9', 'Биология'),
('10', 'География'),
('11', 'Английский язык')
ON CONFLICT (subject_id) DO NOTHING;

-- Создаем тестового администратора
INSERT INTO users (user_id, user_name, roles) VALUES
(1, 'Администратор Системы', 'admin')
ON CONFLICT (user_id) DO NOTHING;