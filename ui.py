import streamlit as st
from utils import db_utils as dbu
from utils import face_utils as fu, voice_utils as vu, signature_utils as su

st.title("🔐 Биометрическая регистрация / аутентификация")

mode = st.sidebar.selectbox("Выберите действие", [
    "Регистрация лица", "Аутентификация лица",
    "Регистрация голоса", "Аутентификация голоса",
    "Регистрация подписи", "Аутентификация подписи"
])

def show_register(biotype, extract_fn, save_fn):
    st.header(f"Регистрация по {biotype}")
    name = st.text_input("Полное имя")
    gender = st.selectbox("Пол", ["M", "F"])
    bdate = st.date_input("Дата рождения")
    consent = st.checkbox("Даю согласие на обработку данных")
    file = st.file_uploader(f"Файл ({biotype})", type={"jpg","jpeg","png"} if biotype=="лицу" else {"wav","ogg","mp3"})
    if st.button("Зарегистрировать"):
        if not file:
            st.error("Загрузите файл")
            return
        with open("tmp.bin", "wb") as f:
            f.write(file.getbuffer())
        vec = extract_fn("tmp.bin")
        sample_id = dbu.register_user(name, gender, bdate.strftime("%Y-%m-%d"), consent, "tmp.bin", biotype)
        if save_fn(sample_id, vec):
            st.success(f"{biotype.capitalize()} успешно зарегистрирован")
        else:
            st.error("Ошибка при сохранении вектора")

def show_login(biotype, extract_fn, recognize_fn):
    st.header(f"Аутентификация по {biotype}")
    file = st.file_uploader(f"Файл ({biotype})", type={"jpg","jpeg","png"} if biotype=="лицу" else {"wav","ogg","mp3"})
    if st.button("Войти"):
        if not file:
            st.error("Загрузите файл")
            return
        with open("tmp.bin", "wb") as f:
            f.write(file.getbuffer())
        vec = extract_fn("tmp.bin")
        matches = recognize_fn(vec)
        if matches:
            for name, sim in matches:
                st.write(f"**{name}** — сходство: {1-sim:.2%}")
        else:
            st.error("Не распознано")

if mode == "Регистрация лица":
    show_register("лицу", fu.get_face_vector, dbu.save_face_vector)
elif mode == "Аутентификация лица":
    show_login("лицу", fu.get_face_vector, dbu.recognize_face)
elif mode == "Регистрация голоса":
    show_register("голос", vu.extract_audio_vector, dbu.save_voice_vector)
elif mode == "Аутентификация голоса":
    show_login("голосу", vu.extract_audio_vector, dbu.recognize_voice)
elif mode == "Регистрация подписи":
    show_register("подписи", su.extract_signature_vector, dbu.save_signature_vector)
elif mode == "Аутентификация подписи":
    show_login("подписи", su.extract_signature_vector, dbu.recognize_signature)
