-- ========================================
-- СИСТЕМА КАСКАДНЫХ ОБНОВЛЕНИЙ
-- ========================================

-- 1. ОБНОВЛЕНИЕ ВЕРСИЙ И ХЕШЕЙ
-- ========================================

CREATE OR REPLACE FUNCTION update_subject_version()
RETURNS TRIGGER AS $$
BEGIN
    -- Увеличиваем версию при любом изменении
    NEW.version_number := COALESCE(OLD.version_number, 0) + 1;
    NEW.updated_at := NOW();
    
    -- Вычисляем хеш данных для отслеживания изменений
    NEW.data_hash := md5(
        COALESCE(NEW.full_name, '') || 
        COALESCE(NEW.gender::text, '') || 
        COALESCE(NEW.birth_date::text, '')
    );
    
    -- Сохраняем версию в историю, если данные действительно изменились
    IF OLD.data_hash IS DISTINCT FROM NEW.data_hash THEN
        INSERT INTO subject_versions (
            subject_id, subject_data, valid_from, valid_to, 
            change_reason, changed_by
        ) VALUES (
            NEW.subject_id,
            jsonb_build_object(
                'full_name', OLD.full_name,
                'gender', OLD.gender,
                'birth_date', OLD.birth_date,
                'version', OLD.version_number
            ),
            OLD.updated_at,
            NOW(),
            'Subject data updated',
            current_user
        );
        
        -- Помечаем профиль для переобработки
        UPDATE biometric_profiles 
        SET needs_reprocessing = true,
            processing_status = 'pending'
        WHERE subject_id = NEW.subject_id;
        
        -- Уведомляем о необходимости переобработки
        PERFORM pg_notify('subject_updated', 
            json_build_object(
                'subject_id', NEW.subject_id,
                'change_type', 'profile_data',
                'priority', 'medium'
            )::text
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. КАСКАДНОЕ ОБНОВЛЕНИЕ КАЧЕСТВА ОБРАЗЦОВ
-- ========================================

CREATE OR REPLACE FUNCTION cascade_sample_quality_update()
RETURNS TRIGGER AS $$
DECLARE
    old_best_sample_id INT;
    new_best_sample_id INT;
    profile_needs_update BOOLEAN := false;
BEGIN
    -- Находим текущий лучший образец для этого субъекта и типа
    SELECT sample_id INTO old_best_sample_id
    FROM samples 
    WHERE subject_id = NEW.subject_id 
    AND sample_type = NEW.sample_type 
    AND is_current_best = true;
    
    -- Определяем новый лучший образец
    SELECT sample_id INTO new_best_sample_id
    FROM samples 
    WHERE subject_id = NEW.subject_id 
    AND sample_type = NEW.sample_type 
    AND processing_status = 'completed'
    ORDER BY quality_score DESC, recorded_at DESC 
    LIMIT 1;
    
    -- Обновляем флаги лучших образцов
    IF old_best_sample_id != new_best_sample_id OR old_best_sample_id IS NULL THEN
        -- Снимаем флаг со старого лучшего
        UPDATE samples 
        SET is_current_best = false 
        WHERE sample_id = old_best_sample_id;
        
        -- Устанавливаем флаг на новый лучший
        UPDATE samples 
        SET is_current_best = true 
        WHERE sample_id = new_best_sample_id;
        
        profile_needs_update := true;
    END IF;
    
    -- Обновляем статистику качества в профиле
    IF profile_needs_update THEN
        UPDATE biometric_profiles 
        SET quality_stats = (
            SELECT jsonb_build_object(
                'avg_quality', AVG(quality_score),
                'max_quality', MAX(quality_score),
                'sample_count', COUNT(*),
                'last_best_update', NOW()
            )
            FROM samples 
            WHERE subject_id = NEW.subject_id 
            AND processing_status = 'completed'
        ),
        last_processed = NOW()
        WHERE subject_id = NEW.subject_id;
        
        -- Инвалидируем кеш сходства для этого субъекта
        UPDATE similarity_cache 
        SET is_valid = false 
        WHERE vector1_id IN (
            SELECT vd.vector_id 
            FROM vector_data vd 
            JOIN samples s ON vd.sample_id = s.sample_id 
            WHERE s.subject_id = NEW.subject_id
        ) OR vector2_id IN (
            SELECT vd.vector_id 
            FROM vector_data vd 
            JOIN samples s ON vd.sample_id = s.sample_id 
            WHERE s.subject_id = NEW.subject_id
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. АВТОМАТИЧЕСКОЕ СОЗДАНИЕ ЗАДАНИЙ НА ОБРАБОТКУ
-- ===============================================

CREATE OR REPLACE FUNCTION create_processing_jobs()
RETURNS TRIGGER AS $$
BEGIN
    -- Создаем задание на извлечение векторов
    INSERT INTO processing_jobs (
        sample_id, job_type, status, job_params, priority
    ) VALUES (
        NEW.sample_id,
        'vector_extraction',
        'pending',
        jsonb_build_object(
            'sample_type', NEW.sample_type,
            'model_version', (
                SELECT version FROM model_versions 
                WHERE model_name = NEW.sample_type || '_model' 
                AND is_active = true 
                LIMIT 1
            ),
            'quality_threshold', 0.3
        ),
        CASE 
            WHEN NEW.sample_type = 'face' THEN 1
            WHEN NEW.sample_type = 'voice' THEN 2
            ELSE 3
        END
    );
    
    -- Создаем задание на расчет метрик качества
    INSERT INTO processing_jobs (
        sample_id, job_type, status, job_params, priority
    ) VALUES (
        NEW.sample_id,
        'quality_analysis',
        'pending',
        jsonb_build_object(
            'metrics', ARRAY['sharpness', 'brightness', 'contrast', 'noise_level']
        ),
        2
    );
    
    -- Уведомляем процессор
    PERFORM pg_notify('new_sample', 
        json_build_object(
            'sample_id', NEW.sample_id,
            'sample_type', NEW.sample_type,
            'priority', 'normal'
        )::text
    );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 4. ОБНОВЛЕНИЕ МОДЕЛИ - КАСКАДНАЯ ПЕРЕОБРАБОТКА
-- =============================================

CREATE OR REPLACE FUNCTION handle_model_update()
RETURNS TRIGGER AS $$
BEGIN
    -- При активации новой модели
    IF NEW.is_active = true AND (OLD.is_active = false OR OLD.is_active IS NULL) THEN
        
        -- Деактивируем старые версии той же модели
        UPDATE model_versions 
        SET is_active = false 
        WHERE model_name = NEW.model_name 
        AND model_id != NEW.model_id;
        
        -- Помечаем все векторы старых моделей как устаревшие
        UPDATE vector_data 
        SET is_normalized = false 
        WHERE model_version != NEW.version 
        AND sample_id IN (
            SELECT sample_id FROM samples 
            WHERE sample_type = replace(NEW.model_name, '_model', '')
        );
        
        -- Создаем задания на переобработку для активных субъектов
        INSERT INTO processing_jobs (
            sample_id, job_type, status, job_params, priority
        )
        SELECT 
            s.sample_id,
            'vector_reextraction',
            'pending',
            jsonb_build_object(
                'old_model_version', vd.model_version,
                'new_model_version', NEW.version,
                'reason', 'model_update'
            ),
            1 -- Высокий приоритет
        FROM samples s
        JOIN vector_data vd ON s.sample_id = vd.sample_id
        JOIN subjects sub ON s.subject_id = sub.subject_id
        WHERE s.sample_type = replace(NEW.model_name, '_model', '')
        AND sub.status = 'active'
        AND s.is_current_best = true; -- Только лучшие образцы
        
        -- Уведомляем о массовой переобработке
        PERFORM pg_notify('model_updated', 
            json_build_object(
                'model_name', NEW.model_name,
                'version', NEW.version,
                'samples_to_reprocess', (
                    SELECT COUNT(*) FROM samples s
                    JOIN subjects sub ON s.subject_id = sub.subject_id
                    WHERE s.sample_type = replace(NEW.model_name, '_model', '')
                    AND sub.status = 'active'
                    AND s.is_current_best = true
                )
            )::text
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 5. УМНАЯ ИНВАЛИДАЦИЯ КЕША
-- ========================

CREATE OR REPLACE FUNCTION invalidate_similarity_cache()
RETURNS TRIGGER AS $$
BEGIN
    -- При обновлении вектора инвалидируем связанный кеш
    IF TG_OP = 'UPDATE' AND OLD.feature_vector IS DISTINCT FROM NEW.feature_vector THEN
        
        UPDATE similarity_cache 
        SET is_valid = false 
        WHERE vector1_id = NEW.vector_id OR vector2_id = NEW.vector_id;
        
        -- Удаляем устаревшие записи кеша (старше 7 дней)
        DELETE FROM similarity_cache 
        WHERE is_valid = false 
        AND calculated_at < NOW() - INTERVAL '7 days';
        
    -- При вставке нового вектора создаем задания на предвычисление
    ELSIF TG_OP = 'INSERT' THEN
        
        -- Создаем задание на предвычисление сходства с популярными векторами
        INSERT INTO processing_jobs (
            sample_id, job_type, status, job_params, priority
        ) VALUES (
            (SELECT sample_id FROM samples WHERE sample_id = 
             (SELECT sample_id FROM vector_data WHERE vector_id = NEW.vector_id)),
            'similarity_precompute',
            'pending',
            jsonb_build_object(
                'vector_id', NEW.vector_id,
                'target_count', 100, -- Предвычислить с топ-100 популярными
                'min_quality', 0.7
            ),
            3 -- Низкий приоритет
        );
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- СОЗДАНИЕ ТРИГГЕРОВ
-- ========================================

-- Триггеры на subjects
CREATE TRIGGER tr_subjects_version_update
    BEFORE UPDATE ON subjects
    FOR EACH ROW
    EXECUTE FUNCTION update_subject_version();

-- Триггеры на samples
CREATE TRIGGER tr_samples_create_jobs
    AFTER INSERT ON samples
    FOR EACH ROW
    EXECUTE FUNCTION create_processing_jobs();

CREATE TRIGGER tr_samples_quality_cascade
    AFTER INSERT OR UPDATE OF quality_score, processing_status ON samples
    FOR EACH ROW
    EXECUTE FUNCTION cascade_sample_quality_update();

-- Триггеры на model_versions
CREATE TRIGGER tr_model_versions_cascade
    AFTER UPDATE OF is_active ON model_versions
    FOR EACH ROW
    EXECUTE FUNCTION handle_model_update();

-- Триггеры на vector_data
CREATE TRIGGER tr_vector_data_cache_invalidate
    AFTER INSERT OR UPDATE ON vector_data
    FOR EACH ROW
    EXECUTE FUNCTION invalidate_similarity_cache();

-- ========================================
-- ПРОДВИНУТАЯ ФУНКЦИЯ ПОИСКА
-- ========================================

CREATE OR REPLACE FUNCTION intelligent_biometric_search(
    input_vector FLOAT[],
    search_type VARCHAR,
    subject_filters JSONB DEFAULT '{}',
    search_options JSONB DEFAULT '{}'
)
RETURNS TABLE(
    subject_id INT,
    similarity_score FLOAT,
    confidence_level VARCHAR,
    sample_info JSONB,
    profile_stats JSONB
) AS $$
DECLARE
    quality_threshold FLOAT;
    time_range_days INT;
    max_results INT;
    use_cache BOOLEAN;
    search_id INT;
BEGIN
    -- Извлекаем параметры поиска
    quality_threshold := COALESCE((search_options->>'quality_threshold')::FLOAT, 0.5);
    time_range_days := COALESCE((search_options->>'time_range_days')::INT, 90);
    max_results := COALESCE((search_options->>'max_results')::INT, 20);
    use_cache := COALESCE((search_options->>'use_cache')::BOOLEAN, true);
    
    -- Логируем поиск
    INSERT INTO search_history (subject_id, search_params, search_type, performed_at)
    VALUES (
        NULL, -- Пока неизвестно
        jsonb_build_object(
            'search_type', search_type,
            'quality_threshold', quality_threshold,
            'time_range_days', time_range_days,
            'subject_filters', subject_filters
        ),
        'biometric_search',
        NOW()
    ) RETURNING search_history.search_id INTO search_id;
    
    RETURN QUERY
    WITH filtered_subjects AS (
        -- Фильтруем субъектов по заданным критериям
        SELECT s.*
        FROM subjects s
        JOIN biometric_profiles bp ON s.subject_id = bp.subject_id
        WHERE s.status = 'active'
        AND s.consent = true
        AND (
            subject_filters = '{}' OR
            (
                COALESCE((subject_filters->>'gender')::CHAR, s.gender) = s.gender AND
                COALESCE((subject_filters->>'min_age')::INT, 0) <= 
                    EXTRACT(YEAR FROM AGE(s.birth_date)) AND
                COALESCE((subject_filters->>'max_age')::INT, 150) >= 
                    EXTRACT(YEAR FROM AGE(s.birth_date))
            )
        )
    ),
    
    best_samples AS (
        -- Берем только лучшие образцы каждого субъекта
        SELECT DISTINCT ON (fs.subject_id)
            fs.subject_id,
            sam.sample_id,
            sam.quality_score,
            sam.recorded_at,
            vd.vector_id,
            vd.feature_vector,
            vd.confidence_score,
            bp.quality_stats
        FROM filtered_subjects fs
        JOIN samples sam ON fs.subject_id = sam.subject_id
        JOIN vector_data vd ON sam.sample_id = vd.sample_id
        JOIN biometric_profiles bp ON fs.subject_id = bp.subject_id
        WHERE sam.sample_type = search_type
        AND sam.processing_status = 'completed'
        AND sam.quality_score >= quality_threshold
        AND sam.recorded_at > NOW() - (time_range_days || ' days')::INTERVAL
        AND vd.is_normalized = true
        ORDER BY fs.subject_id, sam.quality_score DESC, sam.recorded_at DESC
    ),
    
    similarity_results AS (
        -- Вычисляем сходство (с использованием кеша если возможно)
        SELECT 
            bs.subject_id,
            bs.sample_id,
            bs.quality_score,
            bs.confidence_score,
            bs.quality_stats,
            COALESCE(
                -- Пытаемся взять из кеша
                (SELECT sc.similarity_score 
                 FROM similarity_cache sc 
                 WHERE sc.vector1_id = bs.vector_id 
                 AND sc.is_valid = true 
                 AND use_cache),
                -- Вычисляем в реальном времени
                1.0 - (bs.feature_vector <-> input_vector)
            ) as similarity,
            bs.recorded_at
        FROM best_samples bs
    ),
    
    ranked_results AS (
        SELECT 
            sr.*,
            -- Комплексная оценка с учетом качества и свежести
            (sr.similarity * 0.7 + 
             sr.quality_score * 0.2 + 
             sr.confidence_score * 0.1 +
             CASE 
                WHEN sr.recorded_at > NOW() - INTERVAL '7 days' THEN 0.05
                WHEN sr.recorded_at > NOW() - INTERVAL '30 days' THEN 0.02
                ELSE 0
             END
            ) as combined_score
        FROM similarity_results sr
        WHERE sr.similarity > 0.3 -- Минимальный порог сходства
    )
    
    SELECT 
        rr.subject_id,
        rr.similarity,
        CASE 
            WHEN rr.combined_score > 0.9 THEN 'very_high'
            WHEN rr.combined_score > 0.7 THEN 'high'
            WHEN rr.combined_score > 0.5 THEN 'medium'
            ELSE 'low'
        END as confidence_level,
        jsonb_build_object(
            'sample_id', rr.sample_id,
            'quality_score', rr.quality_score,
            'confidence_score', rr.confidence_score,
            'recorded_at', rr.recorded_at,
            'combined_score', rr.combined_score
        ) as sample_info,
        rr.quality_stats as profile_stats
    FROM ranked_results rr
    ORDER BY rr.combined_score DESC
    LIMIT max_results;
    
    -- Обновляем историю поиска с результатами
    UPDATE search_history 
    SET results = (
        SELECT jsonb_agg(
            jsonb_build_object(
                'subject_id', t.subject_id,
                'similarity_score', t.similarity_score,
                'confidence_level', t.confidence_level
            )
        )
        FROM (
            SELECT * FROM intelligent_biometric_search(
                input_vector, search_type, subject_filters, search_options
            ) LIMIT 5
        ) t
    )
    WHERE search_history.search_id = search_id;
    
END;
