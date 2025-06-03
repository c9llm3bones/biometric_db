import os
import torch
import torchaudio
from speechbrain.pretrained import EncoderClassifier
import numpy as np
from pydub import AudioSegment

def normalize_vector(vector):
    return vector / np.linalg.norm(vector)

def extract_speechbrain_vector(audio_path):
    try:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Файл не найден: {audio_path}")

        spk_model = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb"
        )

        signal, fs = torchaudio.load(audio_path)

        if signal.shape[0] > 1:
            signal = torch.mean(signal, dim=0, keepdim=True)

        with torch.no_grad():
            embeddings = spk_model.encode_batch(signal)     # [1, time, 192]
            mean_embedding = torch.mean(embeddings, dim=1)  # [1, 192]
            embedding = mean_embedding.squeeze().cpu().numpy()
        return normalize_vector(embedding)

    except Exception as e:
        print(f"Ошибка при обработке голоса: {e}")
        return None


def convert_ogg_to_wav(input_path, output_path):
    try:
        audio = AudioSegment.from_ogg(input_path)
        audio.export(output_path, format="wav")
        return True
    except Exception as e:
        print(f"Ошибка конвертации Ogg: {e}")
        return False
def extract_audio_vector(audio_path):
    ext = os.path.splitext(audio_path)[1].lower()
    temp_wav = None

    if ext == ".ogg":
        temp_wav = audio_path.replace(".ogg", "_temp.wav")
        if not convert_ogg_to_wav(audio_path, temp_wav):
            return None
        audio_path = temp_wav

    elif ext == ".mp3":
        temp_wav = audio_path.replace(".mp3", "_temp.wav")
        try:
            AudioSegment.from_mp3(audio_path).export(temp_wav, format="wav")
            audio_path = temp_wav
        except Exception as e:
            print(f"Ошибка конвертации MP3: {e}")
            return None

    vector = extract_speechbrain_vector(audio_path)

    if temp_wav and os.path.exists(temp_wav):
        os.remove(temp_wav)

    if vector is not None:
        return vector.tolist()  
    else:
        return None


#m1 = extract_audio_vector("dataset/voices/Registration/Kostya_reg_3.wav")
#m2 = extract_audio_vector("dataset/voices/Registration/Kostya_reg_2.wav")
#print(len(m1))
#print(len(m2))
