import cv2
import numpy as np

def extract_signature_vector(image_path):
    try:
        # Загрузка изображения
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Не удалось загрузить изображение")

        # Предобработка: resize + бинаризация
        resized = cv2.resize(image, (128, 128))
        _, binary = cv2.threshold(resized, 127, 255, cv2.THRESH_BINARY)

        # Извлекаем простой вектор (например, суммы строк и столбцов)
        row_sums = np.sum(binary, axis=1).tolist()
        col_sums = np.sum(binary, axis=0).tolist()
        vector = row_sums + col_sums  # 256-мерный вектор

        return vector[:128]  # ограничиваем до 128-мерного
    except Exception as e:
        print("Ошибка при обработке почерка:", e)
        return None