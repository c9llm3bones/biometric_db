--CREATE EXTENSION vector;
-- Таблица субъектов (людей)

CREATE INDEX idx_face_vector_hnsw ON face_samples USING hnsw(feature_vector);

-- Для голоса
CREATE INDEX idx_voice_vector_hnsw ON voice_samples USING hnsw(audio_vector);

-- Для подписи
CREATE INDEX idx_signature_vector_hnsw ON signature_samples USING hnsw(signature_vector);

DROP TABLE IF EXISTS 
    audit_logs,
    face_samples,
    voice_samples,
    signature_samples,
    samples,
    sensors,
    subjects CASCADE;

CREATE TABLE IF NOT EXISTS subjects (
    subject_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    gender CHAR(1), -- 'M' - мужской, 'F' - женский
    birth_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    consent BOOLEAN NOT NULL DEFAULT FALSE -- Согласие на обработку данных
);

-- Таблица устройств сбора данных (сенсоров)
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id SERIAL PRIMARY KEY,
    sensor_name VARCHAR(100) NOT NULL,
    sensor_type VARCHAR(50) NOT NULL, -- например: 'webcam', 'dslr', 'mic'
    manufacturer VARCHAR(100),
    description TEXT
);

-- Таблица метаданных о биометрических образцах
CREATE TABLE IF NOT EXISTS samples (
    sample_id SERIAL PRIMARY KEY,
    subject_id INT REFERENCES subjects(subject_id),
    sensor_id INT REFERENCES sensors(sensor_id),
    sample_type VARCHAR(20) NOT NULL CHECK (sample_type IN ('face', 'voice', 'signature')),
    sample_hash VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 хэш файла
    file_path TEXT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица для хранения векторов лиц
CREATE TABLE IF NOT EXISTS face_samples (
    sample_id INT PRIMARY KEY REFERENCES samples(sample_id),
    image_width INT,
    image_height INT,
    image_format VARCHAR(10), -- например: jpg, png
    feature_vector VECTOR(128) NOT NULL -- 128-мерный вектор лица
);

-- Таблица для голоса
CREATE TABLE IF NOT EXISTS voice_samples (
    sample_id INT PRIMARY KEY REFERENCES samples(sample_id),
    voice_text TEXT, -- текст, произнесенный пользователем
    sampling_rate INT NOT NULL, -- частота дискретизации
    audio_format VARCHAR(10) NOT NULL, -- например: wav, mp3
    audio_vector VECTOR(192) NOT NULL -- MFCC-вектор
);

-- Таблица для почерка
CREATE TABLE IF NOT EXISTS signature_samples (
    sample_id INT PRIMARY KEY REFERENCES samples(sample_id),
    signature_image_path TEXT NOT NULL, -- путь к изображению подписи
    stroke_speed FLOAT, -- средняя скорость написания
    signature_vector VECTOR(128) NOT NULL -- вектор почерка
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

    RETURN NEW; -- Если всё ок, возвращаем NEW
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_subject
BEFORE INSERT OR UPDATE ON subjects
FOR EACH ROW
EXECUTE FUNCTION validate_subject();

-- Функция для валидации samples
CREATE OR REPLACE FUNCTION validate_sample()
RETURNS TRIGGER AS $$
BEGIN
    -- Проверка: sample_type должен быть 'face', 'voice' или 'signature'
    IF NEW.sample_type NOT IN ('face', 'voice', 'signature') THEN
        RAISE EXCEPTION 'sample_type должен быть face, voice или signature';
    END IF;

    -- Проверка: sample_hash не пустой
    IF NEW.sample_hash IS NULL OR NEW.sample_hash = '' THEN
        RAISE EXCEPTION 'sample_hash не может быть пустым';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для samples
CREATE TRIGGER trg_validate_sample
BEFORE INSERT OR UPDATE ON samples
FOR EACH ROW
EXECUTE FUNCTION validate_sample();

-- Функция для логирования изменений в samples
CREATE OR REPLACE FUNCTION log_sample_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, old_data, new_data)
        VALUES ('samples', 'UPDATE', row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, old_data, new_data)
        VALUES ('samples', 'DELETE', row_to_json(OLD), NULL);
    END IF;
    RETURN NULL; -- для AFTER триггеров
END;
$$ LANGUAGE plpgsql;

-- Триггер для логирования изменений
CREATE TRIGGER trg_log_sample_changes
AFTER UPDATE OR DELETE ON samples
FOR EACH ROW
EXECUTE FUNCTION log_sample_changes();

-- Функция для валидации face_samples
CREATE OR REPLACE FUNCTION validate_face_sample()
RETURNS TRIGGER AS $$
BEGIN
    -- Проверка: размеры изображения положительные
    IF NEW.image_width <= 0 OR NEW.image_height <= 0 THEN
        RAISE EXCEPTION 'image_width и image_height должны быть положительными числами';
    END IF;

    -- Проверка: формат изображения
    IF NEW.image_format NOT IN ('jpg', 'png') THEN
        RAISE EXCEPTION 'image_format должен быть jpg или png';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для face_samples
CREATE TRIGGER trg_validate_face_sample
BEFORE INSERT OR UPDATE ON face_samples
FOR EACH ROW
EXECUTE FUNCTION validate_face_sample();

-- Функция для логирования изменений в face_samples
CREATE OR REPLACE FUNCTION log_face_sample_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, old_data, new_data)
        VALUES ('face_samples', 'UPDATE', row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, old_data, new_data)
        VALUES ('face_samples', 'DELETE', row_to_json(OLD), NULL);
    END IF;
    RETURN NULL; -- для AFTER триггеров
END;
$$ LANGUAGE plpgsql;

-- Триггер для логирования изменений
CREATE TRIGGER trg_log_face_sample_changes
AFTER UPDATE OR DELETE ON face_samples
FOR EACH ROW
EXECUTE FUNCTION log_face_sample_changes();

DROP INDEX IF EXISTS idx_face_vector;
DROP INDEX IF EXISTS idx_voice_vector;
DROP INDEX IF EXISTS idx_signature_vector;

-- Для поиска по косинусному расстоянию
CREATE INDEX idx_face_vector ON face_samples 
USING hnsw (feature_vector vector_cosine_ops);


CREATE INDEX idx_voice_vector ON voice_samples 
USING hnsw (audio_vector vector_l2_ops);

CREATE INDEX idx_signature_vector ON signature_samples 
USING hnsw (signature_vector vector_l2_ops);