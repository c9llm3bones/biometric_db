import os
import gradio as gr
from utils import db_utils as dbu
from utils import face_utils as fu, voice_utils as vu, signature_utils as su, log_utils as lu

# ------- ФУНКЦИИ РЕГИСТРАЦИИ -------

def register_face(name, gender, birth_date, consent, image_file):
    """
    Регистрирует пользователя по лицу:
    - получает вектор через fu.get_face_vector
    - сохраняет пользователя и вектор в БД
    """
    if not all([name, gender, birth_date, consent, image_file]):
        return "Ошибка: заполните все поля и загрузите изображение."
    # записываем временный файл
    tmp_path = "tmp_face.png"
    with open(tmp_path, "wb") as f:
        f.write(image_file.read())
    # извлечение вектора
    vector = fu.get_face_vector(tmp_path)
    if vector is None:
        os.remove(tmp_path)
        return "Не удалось извлечь вектор из изображения."
    # регистрация пользователя и сохранение вектора
    sample_id = dbu.register_user(name, gender, birth_date.strftime("%Y-%m-%d"), True, tmp_path, "face")
    success = dbu.save_face_vector(sample_id, vector)
    os.remove(tmp_path)
    return "Лицо успешно зарегистрировано!" if success else "Ошибка при сохранении вектора."

def register_voice(name, gender, birth_date, consent, audio_file):
    """
    Регистрирует пользователя по голосу:
    - конвертирует (если нужно), получает вектор через vu.extract_audio_vector
    - сохраняет пользователя и вектор в БД
    """
    if not all([name, gender, birth_date, consent, audio_file]):
        return "Ошибка: заполните все поля и загрузите аудио."
    # сохраняем во временный файл (Gradio даёт file-like объект)
    tmp_path = "tmp_audio.ogg"
    with open(tmp_path, "wb") as f:
        f.write(audio_file.read())
    # извлечение вектора
    vector = vu.extract_audio_vector(tmp_path)
    if vector is None:
        os.remove(tmp_path)
        return "Не удалось извлечь вектор из аудио."
    # регистрация пользователя и сохранение вектора
    sample_id = dbu.register_user(name, gender, birth_date.strftime("%Y-%m-%d"), True, tmp_path, "voice")
    success = dbu.save_voice_vector(sample_id, vector)
    os.remove(tmp_path)
    return "Голос успешно зарегистрирован!" if success else "Ошибка при сохранении вектора."

def register_signature(name, gender, birth_date, consent, sig_file):
    """
    Регистрирует пользователя по подписи:
    - сохраняет файл во временный PNG, получает вектор через su.extract_signature_vector
    - сохраняет пользователя и вектор в БД
    """
    if not all([name, gender, birth_date, consent, sig_file]):
        return "Ошибка: заполните все поля и загрузите подпись."
    tmp_path = "tmp_sign.png"
    with open(tmp_path, "wb") as f:
        f.write(sig_file.read())
    # извлекаем вектор подписи
    vector = su.extract_signature_vector(tmp_path)
    if vector is None:
        os.remove(tmp_path)
        return "Не удалось извлечь вектор из подписи."
    # регистрация пользователя и сохранение
    sample_id = dbu.register_user(name, gender, birth_date.strftime("%Y-%m-%d"), True, tmp_path, "signature")
    success = dbu.save_signature_vector(sample_id, vector)
    os.remove(tmp_path)
    return "Подпись успешно зарегистрирована!" if success else "Ошибка при сохранении вектора."

# ------- ФУНКЦИИ АУТЕНТИФИКАЦИИ -------

def login_face(image_file):
    """
    Аутентификация по лицу:
    - сохраняем во временный файл, получаем вектор
    - вызываем dbu.recognize_face, выводим топ-5 совпадений
    """
    if not image_file:
        return "Ошибка: загрузите изображение лица."
    tmp_path = "tmp_face_login.png"
    with open(tmp_path, "wb") as f:
        f.write(image_file.read())
    vector = fu.get_face_vector(tmp_path)
    os.remove(tmp_path)
    if vector is None:
        return "Не удалось извлечь вектор из изображения."
    matches = dbu.recognize_face(vector)
    if not matches:
        return "Не распознано."
    result = []
    for name, sim in matches:
        result.append(f"{name} — сходство: {round((1 - sim) * 100, 2)}%")
    return "\n".join(result)

def login_voice(audio_file):
    """
    Аутентификация по голосу:
    - сохраняем временный файл, получаем вектор
    - вызываем dbu.recognize_voice, выводим топ-5 совпадений
    """
    if not audio_file:
        return "Ошибка: загрузите аудиофайл."
    tmp_path = "tmp_audio_login.ogg"
    with open(tmp_path, "wb") as f:
        f.write(audio_file.read())
    vector = vu.extract_audio_vector(tmp_path)
    os.remove(tmp_path)
    if vector is None:
        return "Не удалось извлечь вектор из аудио."
    matches = dbu.recognize_voice(vector)
    if not matches:
        return "Не распознано."
    result = []
    for name, sim in matches:
        result.append(f"{name} — сходство: {round((1 - sim) * 100, 2)}%")
    return "\n".join(result)

def login_signature(sig_file):
    """
    Аутентификация по подписи:
    - сохраняем временный файл, получаем вектор
    - вызываем dbu.recognize_signature, выводим топ-5 совпадений
    """
    if not sig_file:
        return "Ошибка: загрузите изображение с подписью."
    tmp_path = "tmp_sign_login.png"
    with open(tmp_path, "wb") as f:
        f.write(sig_file.read())
    vector = su.extract_signature_vector(tmp_path)
    os.remove(tmp_path)
    if vector is None:
        return "Не удалось извлечь вектор из подписи."
    matches = dbu.recognize_signature(vector)
    if not matches:
        return "Не распознано."
    result = []
    for name, sim in matches:
        result.append(f"{name} — сходство: {round((1 - sim) * 100, 2)}%")
    return "\n".join(result)

# ------- ФУНКЦИЯ ДЛЯ ПРОСМОТРА ЛОГОВ -------

def show_logs(filter_table=None, filter_user=None):
    """
    Просмотр audit_logs:
    - если filter_table задана, показывает только по таблице
    - если filter_user задан (имя пользователя), показывает только по пользователю
    - иначе выводит все логи
    """
    logs = []
    if filter_table:
        logs = lu.filter_logs_by_table(filter_table)
    elif filter_user:
        logs = lu.filter_logs_by_user(filter_user)
    else:
        logs = lu.fetch_all_logs()

    if not logs:
        return "Логи не найдены."
    lines = []
    for log in logs:
        log_id, table_name, operation, old_data, new_data, changed_at, changed_by = log
        lines.append(f"ID: {log_id}; Таблица: {table_name}; Операция: {operation}; Дата: {changed_at}; Пользователь: {changed_by}\n")
    return "\n".join(lines)

# ------- СОЗДАЁМ Gradio-интерфейс -------

with gr.Blocks() as demo:
    gr.Markdown("# 🔐 Биометрическая регистрация / аутентификация")

    with gr.Tab("Регистрация лица"):
        name_face = gr.Textbox(label="Полное имя")
        gender_face = gr.Radio(["M", "F"], label="Пол")
        bdate_face = gr.Textbox(label="Дата рождения (в формате ГГГГ-ММ-ДД)")
        consent_face = gr.Checkbox(label="Даю согласие на обработку данных")
        img_face = gr.File(label="Загрузите фото (jpg/png)", file_types=[".jpg", ".jpeg", ".png"])
        btn_reg_face = gr.Button("Зарегистрировать")
        out_reg_face = gr.Textbox(label="Результат")
        btn_reg_face.click(
            fn=register_face,
            inputs=[name_face, gender_face, bdate_face, consent_face, img_face],
            outputs=out_reg_face
        )

    with gr.Tab("Регистрация голоса"):
        name_voice = gr.Textbox(label="Полное имя")
        gender_voice = gr.Radio(["M", "F"], label="Пол")
        bdate_voice = gr.Textbox(label="Дата рождения (в формате ГГГГ-ММ-ДД)")
        consent_voice = gr.Checkbox(label="Даю согласие на обработку данных")
        audio_voice = gr.File(label="Загрузите аудио (wav/ogg/mp3)", file_types=[".wav", ".ogg", ".mp3"])
        btn_reg_voice = gr.Button("Зарегистрировать")
        out_reg_voice = gr.Textbox(label="Результат")
        btn_reg_voice.click(
            fn=register_voice,
            inputs=[name_voice, gender_voice, bdate_voice, consent_voice, audio_voice],
            outputs=out_reg_voice
        )

    with gr.Tab("Регистрация подписи"):
        name_sign = gr.Textbox(label="Полное имя")
        gender_sign = gr.Radio(["M", "F"], label="Пол")
        bdate_sign = gr.Textbox(label="Дата рождения (в формате ГГГГ-ММ-ДД)")
        consent_sign = gr.Checkbox(label="Даю согласие на обработку данных")
        img_sign = gr.File(label="Загрузите изображение подписи (jpg/png)", file_types=[".jpg", ".jpeg", ".png"])
        btn_reg_sign = gr.Button("Зарегистрировать")
        out_reg_sign = gr.Textbox(label="Результат")
        btn_reg_sign.click(
            fn=register_signature,
            inputs=[name_sign, gender_sign, bdate_sign, consent_sign, img_sign],
            outputs=out_reg_sign
        )

    with gr.Tab("Аутентификация лица"):
        img_face_log = gr.File(label="Загрузите фото (jpg/png)", file_types=[".jpg", ".jpeg", ".png"])
        btn_log_face = gr.Button("Войти")
        out_log_face = gr.Textbox(label="Результат")
        btn_log_face.click(
            fn=login_face,
            inputs=[img_face_log],
            outputs=out_log_face
        )

    with gr.Tab("Аутентификация голоса"):
        audio_voice_log = gr.File(label="Загрузите аудио (wav/ogg/mp3)", file_types=[".wav", ".ogg", ".mp3"])
        btn_log_voice = gr.Button("Войти")
        out_log_voice = gr.Textbox(label="Результат")
        btn_log_voice.click(
            fn=login_voice,
            inputs=[audio_voice_log],
            outputs=out_log_voice
        )

    with gr.Tab("Аутентификация подписи"):
        img_sign_log = gr.File(label="Загрузите изображение подписи (jpg/png)", file_types=[".jpg", ".jpeg", ".png"])
        btn_log_sign = gr.Button("Войти")
        out_log_sign = gr.Textbox(label="Результат")
        btn_log_sign.click(
            fn=login_signature,
            inputs=[img_sign_log],
            outputs=out_log_sign
        )

    with gr.Tab("Просмотр логов"):
        table_filter = gr.Textbox(label="Фильтр по таблице (опционально)")
        user_filter = gr.Textbox(label="Фильтр по пользователю (имя, опционально)")
        btn_show_logs = gr.Button("Показать логи")
        out_logs = gr.Textbox(label="Логи")
        btn_show_logs.click(
            fn=show_logs,
            inputs=[table_filter, user_filter],
            outputs=out_logs
        )

demo.launch()
