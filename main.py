import os
from datetime import datetime
from utils import db_utils as dbu
from utils import log_utils as lu
from utils import voice_utils as vu
from utils import signature_utils as su
from utils import face_utils as fu

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def input_with_prompt(prompt):
    return input(f"{prompt}: ").strip()

def update_photo(name):
    clear_screen()
    print(f"=== Обновление фото для {name} ===\n")
    
    new_image_path = input_with_prompt("Введите путь к новому изображению")
    if not os.path.exists(new_image_path):
        print("❌ Ошибка: Файл не найден.")
        return

    subject_id = dbu.get_subject_by_name(name)
    if not subject_id:
        print("❌ Пользователь не найден.")
        return

    sample_id = dbu.get_sample_id(subject_id)
    if not sample_id:
        print("❌ У пользователя нет записей.")
        return

    print("\nОбновление фото...")
    if dbu.update_face_vector(sample_id, new_image_path):
        print("✅ Фото успешно обновлено!")
    else:
        print("❌ Ошибка при обновлении.")


def view_audit_logs():
    clear_screen()
    print("=== Анализ логов ===\n")
    
    print("1. Показать все логи")
    print("2. Фильтр по таблице")
    print("3. Фильтр по пользователю")
    print("4. Экспорт логов в CSV")
    print("5. Активность пользователей")
    print("6. Изменения по таблицам")
    print("7. Назад\n")
    
    choice = input("Выберите действие (1-7): ").strip()

    if choice == '1':
        logs = lu.fetch_all_logs()
        print_logs(logs)
    elif choice == '2':
        table = input("Введите имя таблицы: ")
        logs = lu.filter_logs_by_table(table)
        print_logs(logs)
    elif choice == '3':
        user = input("Введите имя пользователя: ")
        logs = lu.filter_logs_by_user(user)
        print_logs(logs)
    elif choice == '4':
        logs = lu.fetch_all_logs()
        lu.export_logs_to_csv(logs)
    elif choice == '5':
        activity = lu.analyze_user_activity()
        print("\n📊 Активность пользователей:")
        for user, count in activity:
            print(f"{user}: {count} изменений")
    elif choice == '6':
        changes = lu.analyze_table_changes()
        print("\n📊 Изменения по таблицам:")
        for table, count in changes:
            print(f"{table}: {count} изменений")
    elif choice == '7':
        return
    else:
        print("❌ Неверный выбор.")

def print_logs(logs):
    print("\n📜 Логи:")
    for log in logs:
        print(f"ID: {log[0]}")
        print(f"Таблица: {log[1]}")
        print(f"Операция: {log[2]}")
        print(f"Старые данные: {log[3]}")
        print(f"Новые данные: {log[4]}")
        print(f"Дата: {log[5]}")
        print(f"Пользователь: {log[6]}")
        print("-" * 50)

def register_biometric(biometric_type, extract_func, save_func, sensor_type='webcam'):
    """
    Универсальная функция регистрации биометрии
    :param biometric_type: 'face', 'voice', 'signature'
    :param extract_func: функция извлечения вектора (например, fu.get_face_vector)
    :param save_func: функция сохранения в БД (например, dbu.save_face_vector)
    :param sensor_type: тип сенсора ('webcam', 'mic', 'signature_pad')
    """
    clear_screen()
    print(f"=== Регистрация ({biometric_type}) ===\n")

    full_name = input_with_prompt("Введите имя")
    gender = input_with_prompt("Пол (M/F)").upper()
    birth_date = input_with_prompt("Дата рождения (YYYY-MM-DD)")
    consent = input_with_prompt("Даете согласие на обработку данных? (y/n)").lower() == 'y'
    file_path = input_with_prompt(f"Введите путь к файлу ({biometric_type})")

    if not os.path.exists(file_path):
        print("❌ Файл не найден")
        return

    # Проверка формата файла
    if biometric_type == 'face' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("❌ Лицо: поддерживаемые форматы — JPG, JPEG, PNG")
        return
    elif biometric_type == 'voice' and not file_path.lower().endswith(('.wav', '.ogg', '.mp3')):
        print("❌ Голос: поддерживаемые форматы — WAV, OGG, MP3")
        return
    elif biometric_type == 'signature' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("❌ Подпись: поддерживаемые форматы — JPG, JPEG, PNG")
        return

    print("\nОбработка...")


    # Извлечение вектора
    vector = extract_func(file_path)

    if vector is None or len(vector) == 0:
        print(f"❌ Не удалось извлечь вектор из {biometric_type}")
        return
    print("Вектор извлечён")
    #/home/kostya/biometric_course_work/dataset/faces/Authorize/Ira2.jpg
    
    # Регистрация пользователя
    sample_id = dbu.register_user(full_name, gender, birth_date, consent, file_path, biometric_type)
    if not sample_id:
        print("❌ Ошибка регистрации пользователя")
        return
    # Сохранение биометрии
    if save_func(sample_id, vector):
        print(f"✅ {biometric_type.capitalize()} успешно зарегистрирован")
    else:
        print(f"❌ Ошибка регистрации {biometric_type}")

def biometric_login(biometric_type, extract_func, recognize_func):
    """
    Универсальная функция аутентификации
    :param biometric_type: 'лицу', 'голосу', 'подписи'
    :param extract_func: функция извлечения вектора
    :param recognize_func: функция поиска в БД
    """
    clear_screen()
    print(f"=== Аутентификация по {biometric_type} ===\n")

    file_path = input_with_prompt(f"Введите путь к файлу ({biometric_type})")
    if not os.path.exists(file_path):
        print("❌ Файл не найден")
        return

    # Проверка формата файла
    if biometric_type == 'лицу' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("❌ Лицо: поддерживаемые форматы — JPG, JPEG, PNG")
        return
    elif biometric_type == 'голосу' and not file_path.lower().endswith(('.wav', '.ogg', '.mp3')):
        print("❌ Голос: поддерживаемые форматы — WAV, OGG, MP3")
        return
    elif biometric_type == 'подписи' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("❌ Подпись: поддерживаемые форматы — JPG, JPEG, PNG")
        return

    print("\nОбработка...")
    print(file_path)
    vector = extract_func(file_path)
    if not vector:
        print(f"❌ Не удалось извлечь вектор из {biometric_type}")
        return
    print("Вектор извлечён")
#/home/kostya/biometric_course_work/dataset/faces/Authorize/Ira2.jpg
    print('vectorized')
    matches = recognize_func(vector)
    if matches:
        print("✅ Найдено совпадение:")
        for name, sim in matches:
            print(f" - {name} (сходство: {1 - sim:.2f}%)")
    else:
        print("❌ Не распознано")


def main():
    
    while True:
        clear_screen()
        users = dbu.get_all_users_with_biometrics()
        
        if users:
            for user in users:
                print(f"Пользователь: {user['full_name']} (ID: {user['subject_id']})")
                print(f"  Пол: {user['gender']}, Дата рождения: {user['birth_date']}")
                print(f"  Согласие на обработку данных: {'Да' if user['consent'] else 'Нет'}")
                print("  Биометрия:")
                
                if user['biometrics']:
                    for bio in user['biometrics']:
                        print(f"    Тип: {bio['sample_type']}, Файл: {bio['file_path']}")
                        if bio['sample_type'] == 'face':
                            print(f"      Вектор лица: {bio['feature_vector']}")
                        elif bio['sample_type'] == 'voice':
                            print(f"      Текст голоса: {bio['voice_text']}")
                            print(f"      Вектор аудио: {bio['audio_vector']}")
                        elif bio['sample_type'] == 'signature':
                            print(f"      Вектор подписи: {bio['signature_vector']}")
                else:
                    print("    Нет биометрических образцов")
                print("-" * 40)
        else:
            print("Не удалось загрузить данные пользователей.")
        print("=== Биометрическая система ===\n")
        print("1. Зарегистрироваться по лицу")
        print("2. Зарегистрироваться по голосу")
        print("3. Зарегистрироваться по подписи")
        print("4. Войти по лицу")
        print("5. Войти по голосу")
        print("6. Войти по подписи")
        print("7. Анализ логов")
        print("8. Выход\n")

        choice = input("Выберите действие (1-8): ").strip()

        if choice == '1':
            register_biometric('face', fu.get_face_vector, dbu.save_face_vector, 'webcam')
        elif choice == '2':
            register_biometric('voice', vu.extract_audio_vector, dbu.save_voice_vector, 'mic')
        elif choice == '3':
            register_biometric('signature', su.extract_signature_vector, dbu.save_signature_vector, 'signature_pad')
        elif choice == '4':
            biometric_login('лицу', fu.get_face_vector, dbu.recognize_face)
        elif choice == '5':
            biometric_login('голосу', vu.extract_audio_vector, dbu.recognize_voice)
        elif choice == '6':
            biometric_login('подписи', su.extract_signature_vector, dbu.recognize_signature)
        elif choice == '7':
            view_audit_logs()
        elif choice == '8':
            print("Выход...")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

        input("\nНажмите Enter, чтобы продолжить...")
    

def register_face():
    register_biometric('face', fu.get_face_vector, dbu.save_face_vector, 'webcam')

def register_voice():
    register_biometric('voice', vu.extract_audio_vector, dbu.save_voice_vector, 'mic')

def register_signature():
    register_biometric('signature', su.extract_signature_vector, dbu.save_signature_vector, 'signature_pad')
 #/home/kostya/biometric_course_work/dataset/voices/Registration/Kostya.ogg
 #/home/kostya/biometric_course_work/dataset/voices/Authorization/Kostya_reg_3.ogg
 #/home/kostya/biometric_course_work/dataset/voices/Authorization/Ira_1.ogg
 #/home/kostya/biometric_course_work/dataset/voices/Authorization/Serega_auth.ogg

 #/home/kostya/biometric_course_work/dataset/faces/Registered/Kostya.png
 #/home/kostya/biometric_course_work/dataset/faces/Registered/Adil_reg.jpg

 #/home/kostya/biometric_course_work/dataset/faces/Authorize/Kostya3.jpg
 #/home/kostya/biometric_course_work/dataset/faces/Authorize/Kostya2.jpg
 #/home/kostya/biometric_course_work/dataset/faces/Authorize/Adil_auth.jpg

def login_face():
    biometric_login('лицу', fu.get_face_vector, dbu.recognize_face)

def login_voice():
    biometric_login('голосу', vu.extract_audio_vector, dbu.recognize_voice)

def login_signature():
    biometric_login('подписи', su.extract_signature_vector, dbu.recognize_signature)

if __name__ == "__main__":
    main()
    

#/home/kostya/biometric_course_work/dataset/faces/Registered/Adil_reg.jpg

#/home/kostya/biometric_course_work/dataset/faces/Authorize/Adil_auth.jpg
