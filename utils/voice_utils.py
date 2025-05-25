import os
import torch
import torchaudio
from speechbrain.pretrained import EncoderClassifier
import numpy as np

def normalize_vector(vector):
    """Нормализация вектора до единичной длины"""
    return vector / np.linalg.norm(vector)

def extract_speechbrain_vector(audio_path):
    """
    Извлекает 192-мерный вектор голоса через SpeechBrain (spkrec-ecapa-voxceleb)
    :param audio_path: путь к аудиофайлу
    :return: вектор (list) или None
    """
    try:
        # Проверка существования файла
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"❌ Файл не найден: {audio_path}")

        # Загрузка модели (в первый раз скачает ~300MB)
        spk_model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb"
        )

        # Загрузка аудио
        signal, fs = torchaudio.load(audio_path)

        # Моно-аудио
        if signal.shape[0] > 1:
            signal = torch.mean(signal, dim=0, keepdim=True)

        # Извлечение вектора
        with torch.no_grad():
            embedding = spk_model.encode_batch(signal).squeeze().tolist()

        return normalize_vector(embedding)

    except Exception as e:
        print(f"❌ Ошибка при обработке голоса: {e}")
        return None

def convert_ogg_to_wav(input_path, output_path):
    """
    Конвертирует Ogg в WAV с помощью pydub
    """
    from pydub import AudioSegment
    try:
        audio = AudioSegment.from_ogg(input_path)
        audio.export(output_path, format="wav")
        return True
    except Exception as e:
        print(f"❌ Ошибка конвертации Ogg: {e}")
        return False

def extract_audio_vector(audio_path):
    """
    Универсальная функция извлечения вектора голоса
    Поддерживает OGG, MP3, WAV
    :return: вектор в формате [x1,x2,...x192] или None
    """
    ext = os.path.splitext(audio_path)[1].lower()
    temp_wav = None

    # Конвертация в WAV, если нужно
    if ext == ".ogg":
        temp_wav = audio_path.replace(".ogg", "_temp.wav")
        if not convert_ogg_to_wav(audio_path, temp_wav):
            return None
        audio_path = temp_wav

    elif ext == ".mp3":
        temp_wav = audio_path.replace(".mp3", "_temp.wav")
        from pydub import AudioSegment
        try:
            AudioSegment.from_mp3(audio_path).export(temp_wav, format="wav")
            audio_path = temp_wav
        except Exception as e:
            print(f"❌ Ошибка конвертации MP3: {e}")
            return None

    # Извлечение вектора
    vector = extract_speechbrain_vector(audio_path)

    # Удаление временного файла
    if temp_wav and os.path.exists(temp_wav):
        os.remove(temp_wav)

    # Форматирование вектора в строку [x1,x2,...x192]
    if vector is not None:
        return "[" + ",".join(f"{x:.10f}" for x in vector) + "]"
    else:
        return None