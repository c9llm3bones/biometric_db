DROP TABLE IF EXISTS 
    audit_logs,
    face_samples,
    voice_samples,
    signature_samples,
    samples,
    sensors,
    subjects CASCADE;

DROP TABLE IF EXISTS search_logs CASCADE;
DROP TABLE IF EXISTS audit_logs CASCADE;

DROP TABLE IF EXISTS signature_samples CASCADE;
DROP TABLE IF EXISTS voice_samples CASCADE;
DROP TABLE IF EXISTS face_samples CASCADE;

DROP TABLE IF EXISTS samples CASCADE;

DROP TABLE IF EXISTS signature_pads CASCADE;
DROP TABLE IF EXISTS microphones CASCADE;
DROP TABLE IF EXISTS cameras CASCADE;

DROP TABLE IF EXISTS sensors CASCADE;

DROP TABLE IF EXISTS subjects CASCADE;

-- 1) Таблица SUBECTS
CREATE TABLE IF NOT EXISTS subjects (
    subject_id   SERIAL PRIMARY KEY,
    full_name    VARCHAR(100) NOT NULL,
    gender       CHAR(1)       CHECK (gender IN ('M','F')),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active    BOOLEAN DEFAULT TRUE,
    login        VARCHAR UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

-- 2) Таблица SENSORS
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id    SERIAL PRIMARY KEY,
    sensor_name  VARCHAR(100) NOT NULL,
    sensor_type  VARCHAR(50)  NOT NULL CHECK (sensor_type IN ('camera','microphone','signature_pad')),
    manufacturer VARCHAR(100),
    description  TEXT,
    is_active    BOOLEAN DEFAULT TRUE
);

-- 3) CAMERAS (только для sensor_type='camera')
CREATE TABLE IF NOT EXISTS cameras (
    sensor_id     INT PRIMARY KEY REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    resolution    VARCHAR(20),
    fps           INT,
    color_depth   INT,
    interface     VARCHAR(50)
);

-- 4) MICROPHONES (только для sensor_type='microphone')
CREATE TABLE IF NOT EXISTS microphones (
    sensor_id         INT PRIMARY KEY REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    sensitivity       VARCHAR(20),
    frequency_response VARCHAR(30),
    diaphragm_size    VARCHAR(20),
    connector_type    VARCHAR(20)
);

-- 5) SIGNATURE_PADS (только для sensor_type='signature_pad')
CREATE TABLE IF NOT EXISTS signature_pads (
    sensor_id      INT PRIMARY KEY REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    active_area    VARCHAR(30),
    pressure_levels INT,
    sampling_rate  INT,
    interface      VARCHAR(50)
);

-- 6) Таблица SAMPLES
CREATE TABLE IF NOT EXISTS samples (
    sample_id      SERIAL PRIMARY KEY,
    subject_id     INT REFERENCES subjects(subject_id) ON DELETE CASCADE,
    sensor_id      INT REFERENCES sensors(sensor_id) ON DELETE SET NULL,
    sample_type    VARCHAR(20) NOT NULL CHECK (sample_type IN ('face','voice','signature')),
    sample_hash    VARCHAR(64) NOT NULL UNIQUE,
    file_path      TEXT       NOT NULL,
    recorded_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status         VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive'))
);

-- 7) FACE_SAMPLES
CREATE TABLE IF NOT EXISTS face_samples (
    sample_id        INT PRIMARY KEY REFERENCES samples(sample_id) ON DELETE CASCADE,
    image_width      INT,
    image_height     INT,
    image_format     VARCHAR(10),
    feature_vector   JSONB,      -- или ARRAY(128)
    confidence_score FLOAT DEFAULT 0.0
);

-- 8) VOICE_SAMPLES
CREATE TABLE IF NOT EXISTS voice_samples (
    sample_id        INT PRIMARY KEY REFERENCES samples(sample_id) ON DELETE CASCADE,
    voice_text       TEXT,
    sampling_rate    INT NOT NULL,
    audio_format     VARCHAR(10) NOT NULL,
    audio_vector     JSONB,      -- или ARRAY(192)
    duration_seconds FLOAT
);

-- 9) SIGNATURE_SAMPLES
CREATE TABLE IF NOT EXISTS signature_samples (
    sample_id             INT PRIMARY KEY REFERENCES samples(sample_id) ON DELETE CASCADE,
    signature_image_path  TEXT NOT NULL,
    stroke_speed         FLOAT,
    signature_vector     JSONB,   -- или ARRAY(128)
    stroke_count         INT
);

-- 10) AUDIT_LOG
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id       SERIAL PRIMARY KEY,
    timestamp    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subject_id   INT          REFERENCES subjects(subject_id) ON DELETE SET NULL,
    sensor_id    INT          REFERENCES sensors(sensor_id) ON DELETE SET NULL,
    sample_id    INT          REFERENCES samples(sample_id) ON DELETE SET NULL,
    table_name   TEXT         NOT NULL,              
    operation    VARCHAR(10)  NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    old_data     JSONB,                              
    new_data     JSONB,                              
    changed_by   TEXT         NOT NULL DEFAULT CURRENT_USER
);


-- 11) SEARCH_LOGS
CREATE TABLE IF NOT EXISTS search_logs (
    search_id          SERIAL PRIMARY KEY,
    timestamp          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subject_id         INT          REFERENCES subjects(subject_id) ON DELETE SET NULL,
    sensor_id          INT          REFERENCES sensors(sensor_id)  ON DELETE SET NULL,
    sample_id          INT          REFERENCES samples(sample_id)  ON DELETE SET NULL,
    search_type        VARCHAR(20)  NOT NULL CHECK (search_type IN ('face','voice','signature')),
    query_vector_type  VARCHAR(20)  NOT NULL CHECK (query_vector_type IN ('face','audio','signature')),
    candidates_found   INT          NOT NULL,
    search_time_ms     FLOAT        NOT NULL,
    threshold_used     FLOAT        NOT NULL,
    additional_info    JSONB,       
    searched_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION log_subjects_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, subject_id, new_data)
        VALUES ('subjects', 'INSERT', NEW.subject_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, subject_id, old_data, new_data)
        VALUES ('subjects', 'UPDATE', OLD.subject_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, subject_id, old_data)
        VALUES ('subjects', 'DELETE', OLD.subject_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER subjects_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON subjects
FOR EACH ROW EXECUTE FUNCTION log_subjects_change();

CREATE OR REPLACE FUNCTION log_samples_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, new_data)
        VALUES ('samples', 'INSERT', row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, old_data, new_data)
        VALUES ('samples', 'UPDATE', row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, old_data)
        VALUES ('samples', 'DELETE', row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER samples_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON samples
FOR EACH ROW EXECUTE FUNCTION log_samples_change();
CREATE OR REPLACE FUNCTION log_sensors_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, new_data)
        VALUES ('sensors', 'INSERT', NEW.sensor_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data, new_data)
        VALUES ('sensors', 'UPDATE', OLD.sensor_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data)
        VALUES ('sensors', 'DELETE', OLD.sensor_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sensors_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON sensors
FOR EACH ROW EXECUTE FUNCTION log_sensors_change();

CREATE OR REPLACE FUNCTION log_face_samples_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, new_data)
        VALUES ('face_samples', 'INSERT', NEW.sample_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, old_data, new_data)
        VALUES ('face_samples', 'UPDATE', OLD.sample_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, old_data)
        VALUES ('face_samples', 'DELETE', OLD.sample_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER face_samples_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON face_samples
FOR EACH ROW EXECUTE FUNCTION log_face_samples_change();

CREATE OR REPLACE FUNCTION log_voice_samples_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, new_data)
        VALUES ('voice_samples', 'INSERT', NEW.sample_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, old_data, new_data)
        VALUES ('voice_samples', 'UPDATE', OLD.sample_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, old_data)
        VALUES ('voice_samples', 'DELETE', OLD.sample_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER voice_samples_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON voice_samples
FOR EACH ROW EXECUTE FUNCTION log_voice_samples_change();

CREATE OR REPLACE FUNCTION log_signature_samples_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, new_data)
        VALUES ('signature_samples', 'INSERT', NEW.sample_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, old_data, new_data)
        VALUES ('signature_samples', 'UPDATE', OLD.sample_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, sample_id, old_data)
        VALUES ('signature_samples', 'DELETE', OLD.sample_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER signature_samples_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON signature_samples
FOR EACH ROW EXECUTE FUNCTION log_signature_samples_change();

CREATE OR REPLACE FUNCTION log_cameras_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, new_data)
        VALUES ('cameras', 'INSERT', NEW.sensor_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data, new_data)
        VALUES ('cameras', 'UPDATE', OLD.sensor_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data)
        VALUES ('cameras', 'DELETE', OLD.sensor_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER cameras_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON cameras
FOR EACH ROW EXECUTE FUNCTION log_cameras_change();

CREATE OR REPLACE FUNCTION log_microphones_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, new_data)
        VALUES ('microphones', 'INSERT', NEW.sensor_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data, new_data)
        VALUES ('microphones', 'UPDATE', OLD.sensor_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data)
        VALUES ('microphones', 'DELETE', OLD.sensor_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER microphones_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON microphones
FOR EACH ROW EXECUTE FUNCTION log_microphones_change();

CREATE OR REPLACE FUNCTION log_signature_pads_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, new_data)
        VALUES ('signature_pads', 'INSERT', NEW.sensor_id, row_to_json(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data, new_data)
        VALUES ('signature_pads', 'UPDATE', OLD.sensor_id, row_to_json(OLD), row_to_json(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (table_name, operation, sensor_id, old_data)
        VALUES ('signature_pads', 'DELETE', OLD.sensor_id, row_to_json(OLD));
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER signature_pads_audit_trigger
AFTER INSERT OR UPDATE OR DELETE ON signature_pads
FOR EACH ROW EXECUTE FUNCTION log_signature_pads_change();

CREATE INDEX idx_audit_logs_table ON audit_logs(table_name);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_logs_user ON audit_logs(changed_by);

-- ============= ИНДЕКСЫ ДЛЯ МНОГОУРОВНЕВОГО ПОИСКА =============

-- 1. Быстрые индексы для предфильтрации
CREATE INDEX idx_samples_type_status ON samples(sample_type, status);
CREATE INDEX idx_subjects_active ON subjects(subject_id) WHERE is_active = TRUE;

-- 2. Составные индексы для первого уровня фильтрации
CREATE INDEX idx_samples_composite ON samples(sample_type, status) 
    WHERE status = 'active';