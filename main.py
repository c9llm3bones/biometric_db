import os
from datetime import datetime
from utils import db_utils as dbu
from utils import log_utils as lu
from utils import voice_utils as vu
from utils import signature_utils as su
from utils import face_utils as fu
from utils.config import BIOMETRIC_CONFIG
from utils.indexer import update_index
import time
import json

def clear_screen():
    #os.system('cls' if os.name == 'nt' else 'clear')
    pass

def input_with_prompt(prompt):
    return input(f"{prompt}: ").strip()

def view_audit_logs():
    """Интерфейс для просмотра и анализа аудит-логов"""
    while True:
        print("\n=== Анализ логов аудита ===\n")
        print("1. Показать все логи (последние 100)")
        print("2. Фильтр по таблице")
        print("3. Фильтр по пользователю")
        print("4. Фильтр по дате")
        print("5. Экспорт логов в CSV")
        print("6. Активность пользователей")
        print("7. Изменения по таблицам")
        print("8. Назад\n")
        
        choice = input("Выберите действие (1-8): ").strip()

        if choice == '1':
            logs = lu.fetch_all_logs()
            print_audit_logs(logs)
            
        elif choice == '2':
            table = input("Введите имя таблицы: ")
            logs = lu.filter_logs_by_table(table_name=table)
            print_audit_logs(logs)
            
        elif choice == '3':
            user = input("Введите имя пользователя: ")
            logs = lu.filter_logs_by_user(user=user)
            print_audit_logs(logs)
            
        elif choice == '4':
            start = input("Начальная дата (YYYY-MM-DD): ")
            end = input("Конечная дата (YYYY-MM-DD): ")
            logs = lu.filter_logs_by_date(start_date=start, end_date=end)
            print_audit_logs(logs)
            
        elif choice == '5':
            logs = lu.fetch_all_logs()
            lu.export_logs_to_csv(logs)
            
        elif choice == '6':
            stats = lu.analyze_user_activity()
            print("\nАктивность пользователей:")
            for row in stats.get('user_stats', []):
                print(f"{row['changed_by']}: {row['changes_count']} изменений")
                
        elif choice == '7':
            stats = lu.analyze_table_changes()
            print("\nИзменения по таблицам:")
            for row in stats.get('table_stats', []):
                print(f"{row['table_name']}: {row['changes_count']} изменений")
                
        elif choice == '8':
            return
            
        else:
            print("Неверный выбор.")
        input("\nНажмите Enter для продолжения...")

def print_audit_logs(logs):
    if not logs:
        print("\n⚠️ Нет записей для отображения")
        return

    print("\n📜 Логи аудита:")
    for log in logs:
        print("=" * 80)
        print(f"ID: {log[0]}")          # log_id
        print(f"Дата: {log[1]}")         # timestamp
        print(f"Таблица: {log[2]}")      # table_name
        print(f"Операция: {log[3]}")     # operation
        print(f"Пользователь: {log[9]}") # changed_by

        if log[4]:  # subject_id
            print(f"Subject ID: {log[4]}")
        if log[5]:  # sensor_id
            print(f"Sensor ID: {log[5]}")
        if log[6]:  # sample_id
            print(f"Sample ID: {log[6]}")

        print("-" * 40)
        print("Старые данные:")
        print(json.dumps(log[7], indent=2, ensure_ascii=False) if log[7] else "Нет данных")  # old_data
        print("-" * 40)
        print("Новые данные:")
        print(json.dumps(log[8], indent=2, ensure_ascii=False) if log[8] else "Нет данных")  # new_data
        print("=" * 80)

def register_biometric(biometric_type, extract_func, save_func, sensor_type='camera', subject_id=None):
    #clear_screen()
    config = BIOMETRIC_CONFIG[biometric_type]
    print(f"=== Регистрация ({biometric_type}) ===\n")
    if subject_id is None:
        full_name = input_with_prompt("Введите имя")
        gender = input_with_prompt("Пол (M/F)").upper()
        login = input_with_prompt("Введите логин")
        password = input_with_prompt("Введите пароль")
    file_path = input_with_prompt(f"Введите путь к файлу ({biometric_type})")

    if not os.path.exists(file_path):
        print("Файл не найден")
        return

    # Проверка формата файла
    if biometric_type == 'face' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("Лицо: поддерживаемые форматы — JPG, JPEG, PNG")
        return
    elif biometric_type == 'voice' and not file_path.lower().endswith(('.wav', '.ogg', '.mp3')):
        print("Голос: поддерживаемые форматы — WAV, OGG, MP3")
        return
    elif biometric_type == 'signature' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("Подпись: поддерживаемые форматы — JPG, JPEG, PNG")
        return

    print("\nОбработка...")


    # Извлечение вектора
    vector = extract_func(file_path)

    if vector is None or len(vector) == 0:
        print(f"❌ Не удалось извлечь вектор из {biometric_type}")
        return
    print("Вектор извлечён")
    #/home/kostya/biometric_course_work/dataset/faces/Authorize/Ira2.jpg
    
    if subject_id is None:
        # Регистрация нового пользователя
        sample_id = dbu.register_user(full_name, gender, login, password, file_path, biometric_type, vector)
    else:
        # Добавление биометрии существующему пользователю
        sample_id = dbu.add_biometric_sample(subject_id, file_path, biometric_type)
    if not sample_id:
        print("Ошибка регистрации пользователя")
        return
    # Сохранение биометрии
    if save_func(sample_id, vector):
        print(f"{biometric_type.capitalize()} успешно зарегистрирован")
    else:
        print(f"Ошибка регистрации {biometric_type}")
    
    update_index(
        config['samples_table'],
        config['vector_column'],
        config['index_file']
    )

def biometric_login(biometric_type, extract_func):
    """
    Универсальная функция аутентификации
    :param biometric_type: 'лицу', 'голосу', 'подписи'
    :param extract_func: функция извлечения вектора
    """
    #clear_screen()
    print(f"=== Аутентификация по {biometric_type} ===\n")

    file_path = input_with_prompt(f"Введите путь к файлу ({biometric_type})")
    if not os.path.exists(file_path):
        print("Файл не найден")
        return

    # Проверка формата файла
    if biometric_type == 'face' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("Лицо: поддерживаемые форматы — JPG, JPEG, PNG")
        return
    elif biometric_type == 'voice' and not file_path.lower().endswith(('.wav', '.ogg', '.mp3')):
        print("Голос: поддерживаемые форматы — WAV, OGG, MP3")
        return
    elif biometric_type == 'signature' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        print("Подпись: поддерживаемые форматы — JPG, JPEG, PNG")
        return

    print("\nОбработка...")
    print(file_path)
    vector = extract_func(file_path)
    if not vector:
        print(f"❌ Не удалось извлечь вектор из {biometric_type}")
        return
    print("Вектор извлечён")
#/home/kostya/biometric_course_work/dataset/faces/Authorize/Ira2.jpg
    matches = dbu.recognize_biometric(vector, biometric_type)
    print(matches)
    if matches:
        print("Найдено совпадение:")
        for id, name, sim in matches:
            print(f" - {name} (сходство: {1 - sim:.2f}%)")
        current_user_id = matches[0][0] 
        current_user_name = matches[0][1]
        user_menu(current_user_id, current_user_name)
    else:
        print("Не распознано")

def user_menu(current_user_id, current_user_name):
    while True:
        clear_screen()
        print(f"\n=== Меню пользователя: {current_user_name} ===")
        print("1. Изменить пароль")
        print("2. Обновить биометрию лица")
        print("3. Обновить биометрию голоса")
        print("4. Обновить биометрию подписи")
        print("5. Добавить новый тип биометрии")
        print("6. Выйти из аккаунта")
        
        choice = input("Выберите действие (1-6): ").strip()
        
        if choice == '1':
            change_password(current_user_id)
        elif choice == '2':
            update_biometric('face', fu.extract_face_vector, current_user_id)
        elif choice == '3':
            update_biometric('voice', vu.extract_audio_vector, current_user_id)
        elif choice == '4':
            update_biometric('signature', su.extract_signature_vector, current_user_id)
        elif choice == '5':
            add_biometric(current_user_id)
        elif choice == '6':
            current_user_id = None
            current_user_name = None
            print("Вы вышли из аккаунта.")
            return
        else:
            print("Неверный выбор.")
        
        input("\nНажмите Enter, чтобы продолжить...")

def update_biometric(bio_type, extract_func, current_user_id):
    config = BIOMETRIC_CONFIG[bio_type]
    file_path = input_with_prompt(f"Введите путь к новому файлу ({bio_type})")
    print(f"current_user_id: {current_user_id}")
    # Проверка файла
    if not os.path.exists(file_path):
        print("Файл не найден")
        return
    
    print("\nОбработка...")
    vector = extract_func(file_path)
    if not vector:
        print(f"Не удалось извлечь вектор из {bio_type}")
        return
    
    # Обновление в БД
    if dbu.update_biometric_vector(current_user_id, vector, file_path, bio_type):
        print(f"{bio_type.capitalize()} успешно обновлен")
    else:
        print(f"Ошибка обновления {bio_type}")
    
    update_index(
        config['samples_table'],
        config['vector_column'],
        config['index_file']
    )

def add_biometric(current_user_id):
    print("\nДоступные типы биометрии:")
    print("1. Лицо")
    print("2. Голос")
    print("3. Подпись")
    choice = input("Выберите тип (1-3): ").strip()
    
    if choice == '1':
        register_biometric('face', fu.extract_face_vector, dbu.save_face_vector, 'camera', current_user_id)
        config = BIOMETRIC_CONFIG['face']
    elif choice == '2':
        register_biometric('voice', vu.extract_audio_vector, dbu.save_voice_vector, 'mic', current_user_id)
        config = BIOMETRIC_CONFIG['voice']
    elif choice == '3':
        register_biometric('signature', su.extract_signature_vector, dbu.save_signature_vector, 'signature_pad', current_user_id)
        config = BIOMETRIC_CONFIG['signature']
    else:
        print("Неверный выбор")
    update_index(
        config['samples_table'],
        config['vector_column'],
        config['index_file']
    )

def change_password(current_user_id):
    current_pass = input_with_prompt("Введите текущий пароль")
    if not dbu.check_current_password(current_user_id, current_pass):
        print("Неверный текущий пароль")
        return
    
    new_pass = input_with_prompt("Введите новый пароль")
    confirm_pass = input_with_prompt("Повторите новый пароль")
    
    if new_pass != confirm_pass:
        print("Пароли не совпадают")
        return
    
    if dbu.update_password(current_user_id, new_pass):
        print("Пароль успешно изменен")
    else:
        print("Ошибка при изменении пароля")

#TODO: implement index search and abillity to update biometry after login
#TODO: add a simple registration and login with password

def main():
    while True:
        #clear_screen()
        print("Загружаем пользователей...")
        users = dbu.get_all_users_with_biometrics()
        
        if users:
            print("Пользователи загружены!")
            for user in users:
                print(f"Пользователь: {user['full_name']} (ID: {user['subject_id']})")
                print(f"  Пол: {user['gender']}")
                print("   Биометрия:")
                
                if user['biometrics']:
                    for bio in user['biometrics']:
                        print(f"    Тип: {bio['sample_type']}, Файл: {bio['file_path']}")
                        #if bio['sample_type'] == 'face':
                        #    print(f"      Вектор лица: {bio['feature_vector']}")
                        #elif bio['sample_type'] == 'voice':
                        #    print(f"      Текст голоса: {bio['voice_text']}")
                        #    print(f"      Вектор аудио: {bio['audio_vector']}")
                        #elif bio['sample_type'] == 'signature':
                        #    print(f"      Вектор подписи: {bio['signature_vector']}")
                else:
                    print("    Нет биометрических образцов")
                print("-" * 40)
        else:
            print("Не удалось загрузить данные пользователей.(База данных пуста)")
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
            register_biometric('face', fu.extract_face_vector, dbu.save_face_vector, 'camera')
        elif choice == '2':
            register_biometric('voice', vu.extract_audio_vector, dbu.save_voice_vector, 'mic')
        elif choice == '3':
            register_biometric('signature', su.extract_signature_vector, dbu.save_signature_vector, 'signature_pad')
        elif choice == '4':
            biometric_login('face', fu.extract_face_vector)
        elif choice == '5':
            biometric_login('voice', vu.extract_audio_vector)
        elif choice == '6':
            biometric_login('signature', su.extract_signature_vector)
        elif choice == '7':
            view_audit_logs()
        elif choice == '8':
            print("Выход...")
            break
        else:
            print("Неверный выбор. Попробуйте снова.")

        input("\nНажмите Enter, чтобы продолжить...")
    

 #/home/kostya/biometric_course_work/dataset/voices/Registration/Kostya.ogg
 #/home/kostya/biometric_course_work/dataset/voices/Authorization/Kostya_reg_3.ogg
 #/home/kostya/biometric_course_work/dataset/voices/Authorization/Ira_1.ogg
 #/home/kostya/biometric_course_work/dataset/voices/Authorization/Serega_auth.ogg

 #/home/kostya/biometric_course_work/dataset/faces/Registered/Kostya.png
 #/home/kostya/biometric_course_work/dataset/faces/Registered/Adil_reg.jpg

 #/home/kostya/biometric_course_work/dataset/faces/Authorize/Kostya3.jpg
 #/home/kostya/biometric_course_work/dataset/faces/Authorize/Kostya2.jpg
 #/home/kostya/biometric_course_work/dataset/faces/Authorize/Adil_auth.jpg

if __name__ == "__main__":
    main()
    

#/home/kostya/biometric_course_work/dataset/faces/Registered/Adil_reg.jpg

#/home/kostya/biometric_course_work/dataset/faces/Authorize/Adil_auth.jpg
