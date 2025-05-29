-- Создание расширения для работы с векторами
CREATE EXTENSION IF NOT EXISTS vector;

-- Удаление существующих таблиц (если есть)
DROP TABLE IF EXISTS 
    audit_logs,
    face_samples,
    voice_samples,
    signature_samples,
    samples,
    sensors,
    subjects CASCADE;

-- Таблица субъектов (людей)
CREATE TABLE IF NOT EXISTS subjects (
    subject_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    gender CHAR(1), -- 'M' - мужской, 'F' - женский
    birth_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    consent BOOLEAN NOT NULL DEFAULT FALSE, -- Согласие на обработку данных
    is_active BOOLEAN DEFAULT TRUE -- для быстрой фильтрации активных пользователей
);

-- Таблица устройств сбора данных (сенсоров)
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id SERIAL PRIMARY KEY,
    sensor_name VARCHAR(100) NOT NULL,
    sensor_type VARCHAR(50) NOT NULL, -- например: 'webcam', 'dslr', 'mic'
    manufacturer VARCHAR(100),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

-- Таблица метаданных о биометрических образцах
CREATE TABLE IF NOT EXISTS samples (
    sample_id SERIAL PRIMARY KEY,
    subject_id INT REFERENCES subjects(subject_id),
    sensor_id INT REFERENCES sensors(sensor_id),
    sample_type VARCHAR(20) NOT NULL CHECK (sample_type IN ('face', 'voice', 'signature')),
    sample_hash VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 хэш файла
    file_path TEXT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    quality_score FLOAT DEFAULT 0.0 CHECK (quality_score >= 0.0 AND quality_score <= 1.0),
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'deleted', 'processed'))
);

-- Таблица для хранения векторов лиц
CREATE TABLE IF NOT EXISTS face_samples (
    sample_id INT PRIMARY KEY REFERENCES samples(sample_id),
    image_width INT,
    image_height INT,
    image_format VARCHAR(10), -- например: jpg, png
    feature_vector VECTOR(128) NOT NULL, -- 128-мерный вектор лица
    confidence_score FLOAT DEFAULT 0.0
);

-- Таблица для голоса
CREATE TABLE IF NOT EXISTS voice_samples (
    sample_id INT PRIMARY KEY REFERENCES samples(sample_id),
    voice_text TEXT, -- текст, произнесенный пользователем
    sampling_rate INT NOT NULL, -- частота дискретизации
    audio_format VARCHAR(10) NOT NULL, -- например: wav, mp3
    audio_vector VECTOR(192) NOT NULL, -- MFCC-вектор
    duration_seconds FLOAT
);

-- Таблица для почерка
CREATE TABLE IF NOT EXISTS signature_samples (
    sample_id INT PRIMARY KEY REFERENCES samples(sample_id),
    signature_image_path TEXT NOT NULL, -- путь к изображению подписи
    stroke_speed FLOAT, -- средняя скорость написания
    signature_vector VECTOR(128) NOT NULL, -- вектор почерка
    stroke_count INT
);

-- Таблица для логирования изменений
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id SERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL, -- 'INSERT', 'UPDATE', 'DELETE'
    old_data JSONB,
    new_data JSONB,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT DEFAULT CURRENT_USER
);

-- Таблица для логов поиска (для анализа производительности)
CREATE TABLE IF NOT EXISTS search_logs (
    search_id SERIAL PRIMARY KEY,
    search_type VARCHAR(20) NOT NULL,
    query_vector_type VARCHAR(20) NOT NULL,
    candidates_found INT,
    search_time_ms FLOAT,
    threshold_used FLOAT,
    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============= ИНДЕКСЫ ДЛЯ МНОГОУРОВНЕВОГО ПОИСКА =============

-- 1. Быстрые индексы для предфильтрации
CREATE INDEX idx_samples_type_status ON samples(sample_type, status);
CREATE INDEX idx_samples_quality ON samples(quality_score) WHERE status = 'active';
CREATE INDEX idx_subjects_active ON subjects(subject_id) WHERE is_active = TRUE;

-- 2. Составные индексы для первого уровня фильтрации
CREATE INDEX idx_samples_composite ON samples(sample_type, status, quality_score) 
    WHERE status = 'active';

-- 3. Векторные индексы для быстрого поиска (IVFFlat - менее точный, но быстрый)
CREATE INDEX idx_face_vector_ivf ON face_samples USING ivfflat(feature_vector) 
    WITH (lists = 100);

CREATE INDEX idx_voice_vector_ivf ON voice_samples USING ivfflat(audio_vector) 
    WITH (lists = 100);

CREATE INDEX idx_signature_vector_ivf ON signature_samples USING ivfflat(signature_vector) 
    WITH (lists = 100);

-- ============= ФУНКЦИИ ДЛЯ ДВУХУРОВНЕВОГО ПОИСКА =============

-- Функция предварительной фильтрации для лиц
CREATE OR REPLACE FUNCTION get_face_candidates(
    query_vector VECTOR(128),
    rough_threshold FLOAT DEFAULT 0.5,  -- широкий порог для предотбора
    quality_threshold FLOAT DEFAULT 0.5,
    max_candidates INT DEFAULT 50  -- больше кандидатов для Python-обработки
)
RETURNS TABLE(
    subject_id INT,
    sample_id INT,
    feature_vector VECTOR(128),
    full_name VARCHAR,
    rough_distance FLOAT
) AS $
BEGIN
    RETURN QUERY
    SELECT subj.subject_id, fs.sample_id, fs.feature_vector, subj.full_name,
           fs.feature_vector <-> query_vector AS rough_distance
    FROM face_samples fs
    JOIN samples s ON fs.sample_id = s.sample_id
    JOIN subjects subj ON s.subject_id = subj.subject_id
    WHERE s.sample_type = 'face'
      AND s.status = 'active'
      AND s.quality_score >= quality_threshold
      AND subj.is_active = TRUE
      AND fs.feature_vector <-> query_vector < rough_threshold  -- быстрый отбор
    ORDER BY rough_distance
    LIMIT max_candidates;
END;
$ LANGUAGE plpgsql;

-- Аналогичная функция для голоса
CREATE OR REPLACE FUNCTION get_voice_candidates(
    query_vector VECTOR(192),
    rough_threshold FLOAT DEFAULT 0.6,
    quality_threshold FLOAT DEFAULT 0.5,
    max_candidates INT DEFAULT 50
)
RETURNS TABLE(
    subject_id INT,
    sample_id INT,
    audio_vector VECTOR(192),
    full_name VARCHAR,
    rough_distance FLOAT
) AS $
BEGIN
    RETURN QUERY
    SELECT subj.subject_id, vs.sample_id, vs.audio_vector, subj.full_name,
           vs.audio_vector <-> query_vector AS rough_distance
    FROM voice_samples vs
    JOIN samples s ON vs.sample_id = s.sample_id
    JOIN subjects subj ON s.subject_id = subj.subject_id
    WHERE s.sample_type = 'voice'
      AND s.status = 'active'
      AND s.quality_score >= quality_threshold
      AND subj.is_active = TRUE
      AND vs.audio_vector <-> query_vector < rough_threshold
    ORDER BY rough_distance
    LIMIT max_candidates;
END;
$ LANGUAGE plpgsql;

-- Функция для подписей
CREATE OR REPLACE FUNCTION get_signature_candidates(
    query_vector VECTOR(128),
    rough_threshold FLOAT DEFAULT 0.5,
    quality_threshold FLOAT DEFAULT 0.5,
    max_candidates INT DEFAULT 50
)
RETURNS TABLE(
    subject_id INT,
    sample_id INT,
    signature_vector VECTOR(128),
    full_name VARCHAR,
    rough_distance FLOAT
) AS $
BEGIN
    RETURN QUERY
    SELECT subj.subject_id, ss.sample_id, ss.signature_vector, subj.full_name,
           ss.signature_vector <-> query_vector AS rough_distance
    FROM signature_samples ss
    JOIN samples s ON ss.sample_id = s.sample_id
    JOIN subjects subj ON s.subject_id = subj.subject_id
    WHERE s.sample_type = 'signature'
      AND s.status = 'active'
      AND s.quality_score >= quality_threshold
      AND subj.is_active = TRUE
      AND ss.signature_vector <-> query_vector < rough_threshold
    ORDER BY rough_distance
    LIMIT max_candidates;
END;
$ LANGUAGE plpgsql;

-- Валидация субъектов
CREATE OR REPLACE FUNCTION validate_subject()
RETURNS TRIGGER AS $$
BEGIN
    -- Проверка: дата рождения не в будущем
    IF NEW.birth_date > CURRENT_DATE THEN
        RAISE EXCEPTION 'Дата рождения не может быть в будущем';
    END IF;

    -- Проверка: пол должен быть 'M' или 'F'
    IF NEW.gender IS NOT NULL AND NEW.gender NOT IN ('M', 'F') THEN
        RAISE EXCEPTION 'Пол должен быть M (мужской) или F (женский)';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Применение триггера
CREATE TRIGGER trigger_validate_subject
    BEFORE INSERT OR UPDATE ON subjects
    FOR EACH ROW EXECUTE FUNCTION validate_subject();

-- Функция для логирования поисков (для анализа производительности)
CREATE OR REPLACE FUNCTION log_search_performance(
    search_type VARCHAR,
    vector_type VARCHAR,
    candidates_count INT,
    search_time FLOAT,
    threshold FLOAT
) RETURNS VOID AS $$
BEGIN
    INSERT INTO search_logs (search_type, query_vector_type, candidates_found, search_time_ms, threshold_used)
    VALUES (search_type, vector_type, candidates_count, search_time, threshold);
END;
$$ LANGUAGE plpgsql;