import cv2
import numpy as np

def normalize_vector(vector):
    return vector / np.linalg.norm(vector)

def extract_signature_vector(image_path):
    try:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Не удалось загрузить изображение")

        resized = cv2.resize(image, (128, 128))
        _, binary = cv2.threshold(resized, 127, 255, cv2.THRESH_BINARY)
        row_sums = np.sum(binary, axis=1).tolist()
        col_sums = np.sum(binary, axis=0).tolist()
        vector = row_sums + col_sums 
        print(normalize_vector(vector))
        return normalize_vector(vector).tolist()
    except Exception as e:
        print("Ошибка при обработке подписи:", e)
        return None


#path1 = "dataset/signatures/Registered/kostya_sign.jpg"
"""
path2 = "dataset/signatures/Authorized/kostya_sign.jpg"
#path2 = "dataset/signatures/Authorized/ira_sign.jpg"
vector2 = extract_signature_vector(path2)

if vector1 is not None:
    print("Успешно извлечён вектор подписи!")
    print("Размер вектора:", len(vector1))
    print("Первые 10 значений:", vector1[:10])
else:
    print("Не удалось извлечь вектор.")

if vector2 is not None:
    print("Успешно извлечён вектор подписи!")
    print("Размер вектора:", len(vector2))
    print("Первые 10 значений:", vector2[:10])
else:
    print("Не удалось извлечь вектор.")

from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

similarity = cosine_similarity(
    np.array(vector1).reshape(1, -1),
    np.array(vector2).reshape(1, -1)
)[0][0]

print(f"Сходство подписей: {similarity:.3f}")
if similarity > 0.9:  # или другой порог
    print("✅ Авторизация прошла")
else:
    print("❌ Подпись не совпадает")
"""