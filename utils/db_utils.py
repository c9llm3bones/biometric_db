import psycopg2
from utils.config import DB_CONFIG, THRESHOLD_VOICE, THRESHOLD_FACE
from utils import face_utils
from psycopg2.extras import RealDictCursor

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def register_user(full_name, gender, birth_date, consent, file_path, file_type):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Добавляем субъекта
        cursor.execute("""
            INSERT INTO subjects (full_name, gender, birth_date, consent)
            VALUES (%s, %s, %s, %s) RETURNING subject_id
        """, (full_name, gender, birth_date, consent))
        subject_id = cursor.fetchone()[0]

        # Добавляем сенсор (например, веб-камера)
        cursor.execute("""
            INSERT INTO sensors (sensor_name, sensor_type, manufacturer)
            VALUES ('Web Camera', 'webcam', 'Generic') RETURNING sensor_id
        """)
        sensor_id = cursor.fetchone()[0]

        # Хэш файла (упрощённый)
        sample_hash = hash(file_path)

        # Добавляем образец
        cursor.execute("""
            INSERT INTO samples (subject_id, sensor_id, sample_type, sample_hash, file_path)
            VALUES (%s, %s, %s, %s, %s) RETURNING sample_id
        """, (subject_id, sensor_id, file_type, str(sample_hash), file_path))
        sample_id = cursor.fetchone()[0]

        conn.commit()
        cursor.close()
        conn.close()

        return sample_id
    except Exception as e:
        print("Ошибка при регистрации:", e)
        return None

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

def recognize_face(vector):

    if not vector:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT subj.full_name, fs.feature_vector <-> %s AS similarity
        FROM face_samples fs
        JOIN samples s ON fs.sample_id = s.sample_id
        JOIN subjects subj ON s.subject_id = subj.subject_id
        ORDER BY similarity ASC
        LIMIT 5
    """, (str(vector),))

    results = cursor.fetchall()
    conn.close()
    print(*[(name, sim) for name, sim in results])
    return [(name, sim) for name, sim in results if sim < THRESHOLD_FACE]

def get_subject_by_name(full_name):
    """Получить subject_id по имени"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT subject_id FROM subjects WHERE full_name = %s", (full_name,))
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

def update_face_vector(sample_id, image_path):
    """Обновить вектор и путь к изображению"""
    from face_utils import get_face_vector

    vector = get_face_vector(image_path)
    if not vector:
        return False

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Обновляем путь в samples
        cursor.execute("""
            UPDATE samples 
            SET file_path = %s 
            WHERE sample_id = %s
        """, (image_path, sample_id))

        # Обновляем вектор в face_samples
        cursor.execute("""
            UPDATE face_samples 
            SET feature_vector = %s 
            WHERE sample_id = %s
        """, (str(vector), sample_id))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print("Ошибка при обновлении:", e)
        return False
    
def register_signature(subject_id, signature_path):
    """
    Регистрация образца подписи в БД
    :param subject_id: идентификатор пользователя
    :param signature_path: путь к фото подписи
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO sensors (sensor_name, sensor_type, manufacturer)
            VALUES ('', '', '')
            RETURNING sample_id
        """)
        sensor_id = cursor.fetchone()[0]
        sample_hash = hash(signature_path)

        cursor.execute("""
            INSERT INTO samples (
                subject_id, sensor_id, sample_type, sample_hash, file_path
            ) VALUES (%s, %s, 'signature', %s, %s)
            RETURNING sample_id
        """, (subject_id, sensor_id, str(sample_hash), signature_path))
        sample_id = cursor.fetchone()[0]
        
        conn.commit()
        cursor.close()
        conn.close()

        return sample_id
    except Exception as e:
        print("Ошибка при регистрации подписи")
        return None
    
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
    
def recognize_signature(vector, threshold=0.6):
    """
    Поиск по векторам почерка
    :param vector: вектор почерка
    :param threshold: порог схожести
    :return: список совпадений
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT subj.full_name, ss.signature_vector <-> %s AS similarity
            FROM signature_samples ss
            JOIN samples s ON ss.sample_id = s.sample_id
            JOIN subjects subj ON s.subject_id = subj.subject_id
            ORDER BY similarity ASC
            LIMIT 5
        """, (str(vector),))

        results = cursor.fetchall()
        conn.close()

        return [(name, sim) for name, sim in results if sim < threshold]

    except Exception as e:
        print("Ошибка при распознавании почерка:", e)
        return []
    
def update_signature_vector(sample_id, vector):
    """
    Обновляет вектор почерка
    :param sample_id: идентификатор образца
    :param vector: новый вектор
    :return: True/False
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE signature_samples
            SET signature_vector = %s
            WHERE sample_id = %s
        """, (str(vector), sample_id))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print("Ошибка при обновлении вектора почерка:", e)
        return False

def update_signature_file(sample_id, new_file_path):
    """
    Обновляет путь к файлу подписи
    :param sample_id: идентификатор образца
    :param new_file_path: новый путь
    :return: True/False
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE samples
            SET file_path = %s
            WHERE sample_id = %s
        """, (new_file_path, sample_id))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print("Ошибка при обновлении пути к подписи:", e)
        return False

def register_voice(subject_id, voice_path, voice_text):
    """
    Регистрация голосового образца в БД
    :param subject_id: идентификатор пользователя
    :param voice_path: путь к аудиофайлу
    :param voice_text: произнесенный текст
    :return: True/False
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Добавляем сенсор (микрофон)
        cursor.execute("""
            INSERT INTO sensors (sensor_name, sensor_type, manufacturer)
            VALUES ('Generic Microphone', 'mic', 'Generic')
            RETURNING sensor_id
        """)
        sensor_id = cursor.fetchone()[0]

        # Хэшируем файл
        sample_hash = hash(voice_path)

        # Добавляем образец
        cursor.execute("""
            INSERT INTO samples (
                subject_id, sensor_id, sample_type, sample_hash, file_path
            ) VALUES (%s, %s, 'voice', %s, %s)
            RETURNING sample_id
        """, (subject_id, sensor_id, str(sample_hash), voice_path))
        sample_id = cursor.fetchone()[0]

        conn.commit()
        cursor.close()
        conn.close()

        return sample_id

    except Exception as e:
        print("Ошибка при регистрации голоса:", e)
        return None

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

def recognize_voice(vector):
    """
    Поиск по голосовым векторам (192-мерный)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subj.full_name, vs.audio_vector <-> %s AS similarity
            FROM voice_samples vs
            JOIN samples s ON vs.sample_id = s.sample_id
            JOIN subjects subj ON s.subject_id = subj.subject_id
            ORDER BY similarity ASC
            LIMIT 5
        """, (str(vector),))

        results = cursor.fetchall()
        conn.close()
        print([(name, sim) for name, sim in results])
        return [(name, sim) for name, sim in results if sim < THRESHOLD_VOICE]  # порог схожести

    except Exception as e:
        print("❌ Ошибка поиска по голосу:", e)
        return []
    
def update_voice_vector(sample_id, vector):
    """
    Обновляет вектор голоса
    :param sample_id: идентификатор образца
    :param vector: новый вектор
    :return: True/False
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE voice_samples
            SET audio_vector = %s
            WHERE sample_id = %s
        """, (str(vector), sample_id))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print("Ошибка при обновлении голоса:", e)
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
                s.birth_date,
                s.consent,
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
            LEFT JOIN samples samp ON s.subject_id = samp.subject_id
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
                    'birth_date': row['birth_date'],
                    'consent': row['consent'],
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