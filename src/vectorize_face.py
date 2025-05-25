import face_recognition
import psycopg2

conn = psycopg2.connect(
    dbname="biometrics_db",
    user="c9llm3bones",
    password="zizitt123",
    host="localhost"
)
cursor = conn.cursor()

# Путь к изображению
image_path = "/data/faces/ivan_new.jpg"

# Загрузка изображения
image = face_recognition.load_image_file(image_path)
face_vector = face_recognition.face_encodings(image)[0].tolist()  # 128-мерный вектор

# Вставка в БД
cursor.execute("""
    INSERT INTO samples (subject_id, sensor_id, sample_type, sample_hash, file_path)
    VALUES (%s, %s, %s, %s, %s) RETURNING sample_id
""", (1, 1, 'face', 'new_hash_123', image_path))

sample_id = cursor.fetchone()[0]

cursor.execute("""
    INSERT INTO face_samples (sample_id, image_width, image_height, image_format, feature_vector)
    VALUES (%s, %s, %s, %s, %s)
""", (sample_id, 640, 480, 'jpg', face_vector))

conn.commit()
cursor.close()
conn.close()