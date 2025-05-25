# test_speechbrain.py

import torchaudio
from speechbrain.pretrained import EncoderClassifier
import numpy as np
import os
import torch

def extract_speaker_embedding(audio_path):
    """
    Извлекает 192-мерный вектор голоса с помощью SpeechBrain
    :param audio_path: путь к аудиофайлу
    :return: вектор (list) или None
    """
    try:
        # Загрузка модели (в первый раз скачает ~300 МБ)
        spk_model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb"
        )

        # Загрузка аудиофайла
        if not os.path.exists(audio_path):
            print(f"❌ Файл не найден: {audio_path}")
            return None

        signal, fs = torchaudio.load(audio_path)
        if signal.shape[0] > 1:
            signal = signal[0].unsqueeze(0)  # моно
        print(f"✅ Аудиофайл загружен (частота: {fs} Гц)")

        # Извлечение вектора
        with torch.no_grad():
            embedding = spk_model.encode_batch(signal).squeeze().tolist()
        print(f"✅ Вектор извлечен: {len(embedding)} измерений")
        return embedding

    except Exception as e:
        print("❌ Ошибка:", e)
        return None

if __name__ == "__main__":
    # Пример использования
    audio_path = "/home/kostya/biometric_course_work/dataset/voices/Registration/Kostya.ogg"
    #vector = extract_speaker_embedding(audio_path)

    #if vector:
    #    print("\n📊 Первые 10 компонент вектора:")
    #    print(vector[:10])
    
    # test_comparison.py
    import numpy as np
    from utils.voice_utils import extract_speechbrain_vector, normalize_vector

    # Вектор из регистрации
    vec1 = extract_speechbrain_vector("/home/kostya/biometric_course_work/dataset/voices/Registration/Kostya.ogg")
    vec1 = normalize_vector(vec1)

    # Вектор из аутентификации
    vec2 = extract_speechbrain_vector("/home/kostya/biometric_course_work/dataset/voices/Authorization/Ira_1.ogg")
    vec2 = normalize_vector(vec2)

    # L2-расстояние
    l2_distance = np.linalg.norm(np.array(vec1) - np.array(vec2))
    print("L2-расстояние:", l2_distance)

    # Косинусное сходство
    cos_sim = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    print("Косинусное сходство:", cos_sim)