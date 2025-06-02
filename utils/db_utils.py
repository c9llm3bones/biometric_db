import psycopg2
from utils.config import DB_CONFIG, THRESHOLD_VOICE, THRESHOLD_FACE
from utils import face_utils
from psycopg2.extras import RealDictCursor
import bcrypt
import numpy as np
from utils.indexer import load_index_and_search
from utils.config import BIOMETRIC_CONFIG
import os
import time
import json
def hash_password(plain_password: str):
    hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt())
    return hashed.decode()

def verify_password(plain_password: str, hashed_password: str):
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def log_search(subject_id=None, sensor_id=None, sample_id=None, 
              search_type='face', query_vector_type='face',
              candidates_found=0, search_time_ms=0.0,
              threshold_used=0.5, additional_info=None):
    """
    Логирует операцию поиска в таблице search_logs
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO search_logs (
                subject_id, sensor_id, sample_id,
                search_type, query_vector_type,
                candidates_found, search_time_ms,
                threshold_used, additional_info
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            subject_id, sensor_id, sample_id,
            search_type, query_vector_type,
            candidates_found, search_time_ms,
            threshold_used, json.dumps(additional_info) if additional_info else None
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Ошибка при записи лога поиска: {e}")
        return False


def recognize_biometric(vector, biometric_type):
    start_time = time.time()
    
    if not vector:
        log_search(
            search_type=biometric_type,
            query_vector_type=biometric_type,
            candidates_found=0,
            search_time_ms=0,
            threshold_used=0,
            additional_info={"error": "Пустой вектор"}
        )
        return []

    config = BIOMETRIC_CONFIG[biometric_type]
    
    if not os.path.exists(config['index_file']):
        log_search(
            search_type=biometric_type,
            query_vector_type=biometric_type,
            candidates_found=0,
            search_time_ms=0,
            threshold_used=0,
            additional_info={"error": "Индексный файл не найден"}
        )
        return []

    results = load_index_and_search(config['index_file'], np.array(vector))
    search_time_ms = (time.time() - start_time) * 1000
    
    if not results:
        log_search(
            search_type=biometric_type,
            query_vector_type=biometric_type,
            candidates_found=0,
            search_time_ms=search_time_ms,
            threshold_used=config['threshold'],
            additional_info={"note": "Нет совпадений"}
        )
        return []

    conn = get_db_connection()
    cursor = conn.cursor()
    subject_ids = [str(sid) for sid, _ in results]
    placeholders = ','.join(['%s'] * len(subject_ids))
    
    cursor.execute(f"""
        SELECT DISTINCT subj.subject_id, subj.login
        FROM subjects subj
        JOIN samples s ON subj.subject_id = s.subject_id
        WHERE subj.subject_id IN ({placeholders}) AND s.status = 'active'
    """, subject_ids)
    
    login_map = {int(sid): login for sid, login in cursor.fetchall()}
    conn.close()
    
    final_results = []
    for subject_id, distance in results:
        if distance < config['threshold'] and subject_id in login_map:
            final_results.append((
                subject_id,
                login_map[subject_id],
                float(distance)
            ))

    log_search(
        search_type=biometric_type,
        query_vector_type=biometric_type,
        candidates_found=len(final_results),
        search_time_ms=search_time_ms,
        threshold_used=config['threshold'],
        additional_info={
            "raw_results": len(results),
            "threshold": config['threshold'],
            "vector_shape": str(np.array(vector).shape)
        }
    )
    
    return final_results

def check_dublicate_biometric(subject_id, vector, biometric_type):
    print('Проверяем наличие похожих образцов')
    matches = recognize_biometric(vector, biometric_type)
    if matches:
        for match_subject_id, _, _ in matches:
            if match_subject_id != subject_id:
                return True
    return False

def update_biometric_vector(subject_id, vector, file_path, biometric_type):
    try:
        if check_dublicate_biometric(subject_id, vector, biometric_type):
            raise Exception("Похожий биометрический образец уже зарегистрирован другим пользователем")

        config = BIOMETRIC_CONFIG[biometric_type]
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE samples
            SET status = 'inactive'
            WHERE subject_id = %s
              AND sample_type = %s
              AND status != 'inactive'
        """, (subject_id, biometric_type))

        cursor.execute("""
            INSERT INTO sensors (sensor_name, sensor_type, manufacturer)
            VALUES (%s, %s, %s) RETURNING sensor_id
        """, (f'Generic {biometric_type} Sensor', 'camera', 'Generic'))
        sensor_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO samples (subject_id, sensor_id, sample_type, sample_hash, file_path)
            VALUES (%s, %s, %s, %s, %s) RETURNING sample_id
        """, (subject_id, sensor_id, biometric_type, str(hash(file_path)), file_path))
        sample_id = cursor.fetchone()[0]

        insert_query = f"""
            INSERT INTO {config['samples_table']} (sample_id, {config['vector_column']})
            VALUES (%s, %s)
        """
        cursor.execute(insert_query, (sample_id, str(vector)))

        conn.commit()
        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"Ошибка обновления {biometric_type}: {e}")
        return False

def save_biometric_vector(sample_id, vector, biometric_type):
    config = BIOMETRIC_CONFIG[biometric_type]
    return config['save_function'](sample_id, vector)

def update_password(subject_id, new_password):
    hashed = hash_password(new_password)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subjects SET password_hash = %s WHERE subject_id = %s
        """, (hashed, subject_id))
        conn.commit()
        cursor.close()
        conn.close()

        return True
    except Exception as e:
        print("Ошибка обновления пароля:", e)
        return False    

def check_current_password(subject_id, plain_password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM subjects WHERE subject_id = %s", (subject_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        hashed_password = row[0]
        return verify_password(plain_password, hashed_password)
    return False

def add_biometric_sample(subject_id, file_path, biometric_type):
    try:
        if check_dublicate_biometric(subject_id, file_path, biometric_type):
            raise Exception("Похожий биометрический образец уже зарегистрирован другим пользователем")
        config = BIOMETRIC_CONFIG[biometric_type]
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO sensors (sensor_name, sensor_type, manufacturer)
            VALUES (%s, %s, %s) RETURNING sensor_id
        """, (f'Generic {biometric_type} Sensor', 'camera', 'Generic'))
        sensor_id = cursor.fetchone()[0]
        
        
        cursor.execute("""
            INSERT INTO samples (subject_id, sensor_id, sample_type, sample_hash, file_path)
            VALUES (%s, %s, %s, %s, %s) RETURNING sample_id
        """, (subject_id, sensor_id, biometric_type, str(hash(file_path)), file_path))
        sample_id = cursor.fetchone()[0]
        
        conn.commit()
        cursor.close()
        conn.close()
        return sample_id
    except Exception as e:
        print("Ошибка при добавлении образца биометрии:", e)
        return None

def register_user(full_name, gender, login, password, file_path, biometric_type, vector):
    try:
        if check_dublicate_biometric(None, vector, biometric_type):
            raise Exception("Похожий биометрический образец уже зарегистрирован другим пользователем")
        config = BIOMETRIC_CONFIG[biometric_type]
        conn = get_db_connection()
        cursor = conn.cursor()

        # Добавляем субъекта
        cursor.execute("""
            INSERT INTO subjects (full_name, gender, login, password_hash)
            VALUES (%s, %s, %s, %s) RETURNING subject_id
        """, (full_name, gender, login, hash_password(password)))
        subject_id = cursor.fetchone()[0]

        # Добавляем сенсор
        cursor.execute("""
            INSERT INTO sensors (sensor_name, sensor_type, manufacturer)
            VALUES (%s, %s, %s) RETURNING sensor_id
        """, (f'Generic {biometric_type} Sensor', 'camera', 'Generic'))
        sensor_id = cursor.fetchone()[0]

        # Добавляем образец
        cursor.execute("""
            INSERT INTO samples (subject_id, sensor_id, sample_type, sample_hash, file_path)
            VALUES (%s, %s, %s, %s, %s) RETURNING sample_id
        """, (subject_id, sensor_id, biometric_type, str(hash(file_path)), file_path))
        sample_id = cursor.fetchone()[0]

        conn.commit()
        cursor.close()
        conn.close()

        return sample_id
    except Exception as e:
        print("Ошибка при регистрации:", e)
        return None

def get_subject_by_login(login):
    """Получить subject_id по имени"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT subject_id FROM subjects WHERE login = %s", (login,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_sample_id(subject_id):
    """Получить sample_id по subject_id"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sample_id FROM samples WHERE subject_id = %s LIMIT 1", (subject_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def save_face_vector(sample_id, vector):
    try:
        if not vector:
            return False

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO face_samples (sample_id, image_width, image_height, image_format, feature_vector)
            VALUES (%s, %s, %s, %s, %s)
        """, (sample_id, 640, 480, 'jpg', str(vector)))

        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print("Ошибка при сохранении вектора:", e)
        return False

def save_signature_vector(sample_id, vector, stroke_speed=None):
    """
    Сохраняет вектор почерка в БД
    :param sample_id: идентификатор образца
    :param vector: вектор почерка
    :param stroke_speed: скорость написания (опционально)
    :return: True/False
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO signature_samples (
                sample_id, signature_image_path, stroke_speed, signature_vector
            ) VALUES (%s, %s, %s, %s)
        """, (sample_id, '', stroke_speed, str(vector)))

        conn.commit()
        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print("Ошибка при сохранении вектора почерка:", e)
        return False

def save_voice_vector(sample_id, vector, sampling_rate=16000, audio_format='wav'):
    """
    Сохраняет 192-мерный вектор голоса в БД
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO voice_samples (
                sample_id, voice_text, sampling_rate, audio_format, audio_vector
            ) VALUES (%s, %s, %s, %s, %s)
        """, (sample_id, '', sampling_rate, audio_format, str(vector)))

        conn.commit()
        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print("Ошибка при сохранении вектора голоса:", e)
        return False

def get_all_users_with_biometrics():
    try:
        # Подключение к базе данных с использованием RealDictCursor для именованных полей
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        cur = conn.cursor()
        
        # SQL-запрос для получения всех данных о пользователях и их биометрии
        query = """
            SELECT 
                s.subject_id,
                s.full_name,
                s.gender,
                s.login,
                samp.sample_id,
                samp.sample_type,
                samp.file_path,
                samp.recorded_at,
                fs.image_width,
                fs.image_height,
                fs.image_format,
                fs.feature_vector AS face_vector,
                vs.voice_text,
                vs.sampling_rate,
                vs.audio_format,
                vs.audio_vector AS voice_vector,
                ss.signature_image_path,
                ss.stroke_speed,
                ss.signature_vector
            FROM subjects s
            LEFT JOIN samples samp ON s.subject_id = samp.subject_id AND samp.status = 'active'
            LEFT JOIN face_samples fs ON samp.sample_id = fs.sample_id
            LEFT JOIN voice_samples vs ON samp.sample_id = vs.sample_id
            LEFT JOIN signature_samples ss ON samp.sample_id = ss.sample_id
            ORDER BY s.subject_id;
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        # Словарь для хранения пользователей, ключ - subject_id
        users = {}
        
        for row in rows:
            subject_id = row['subject_id']
            
            # Если пользователь еще не добавлен, добавляем его
            if subject_id not in users:
                users[subject_id] = {
                    'subject_id': subject_id,
                    'full_name': row['full_name'],
                    'gender': row['gender'],
                    'login': row['login'],
                    'biometrics': []
                }
            
            # Добавляем биометрию, если она существует (sample_id не null)
            if row['sample_id'] is not None:
                biometric = {
                    'sample_id': row['sample_id'],
                    'sample_type': row['sample_type'],
                    'file_path': row['file_path'],
                    'recorded_at': row['recorded_at']
                }
                
                # Добавляем специфичные поля в зависимости от типа образца
                if row['sample_type'] == 'face':
                    biometric.update({
                        'image_width': row['image_width'],
                        'image_height': row['image_height'],
                        'image_format': row['image_format'],
                        'feature_vector': row['face_vector']
                    })
                elif row['sample_type'] == 'voice':
                    biometric.update({
                        'voice_text': row['voice_text'],
                        'sampling_rate': row['sampling_rate'],
                        'audio_format': row['audio_format'],
                        'audio_vector': row['voice_vector']
                    })
                elif row['sample_type'] == 'signature':
                    biometric.update({
                        'signature_image_path': row['signature_image_path'],
                        'stroke_speed': row['stroke_speed'],
                        'signature_vector': row['signature_vector']
                    })
                
                users[subject_id]['biometrics'].append(biometric)
        
        # Закрытие соединения
        cur.close()
        conn.close()
        
        # Возвращаем список пользователей
        return list(users.values())
    
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None