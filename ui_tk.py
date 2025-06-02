import os
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from utils import db_utils as dbu
from utils import log_utils as lu
from utils import face_utils as fu, voice_utils as vu, signature_utils as su
from utils.indexer import update_index
#from utils.config import BIOMETRIC_CONFIG
from utils.config import THRESHOLD_FACE, THRESHOLD_VOICE, THRESHOLD_SIGNATURE

# Глобальная переменная для текущего пользователя
current_user_id = None
current_user_login = None

BIOMETRIC_CONFIG = {
    'face': {
        'index_file': 'face_ivf_index.pkl',
        'samples_table': 'face_samples',
        'vector_column': 'feature_vector',
        'threshold': THRESHOLD_FACE,
        'save_fn': dbu.save_face_vector,
        'update_query': """
            UPDATE {table} SET {vector_column} = %s 
            WHERE sample_id = %s
        """
    },
    'voice': {
        'index_file': 'voice_ivf_index.pkl',
        'samples_table': 'voice_samples',
        'vector_column': 'audio_vector',
        'threshold': THRESHOLD_VOICE,
        'save_fn': dbu.save_voice_vector,
        'update_query': """
            UPDATE {table} SET {vector_column} = %s 
            WHERE sample_id = %s
        """
    },
    'signature': {
        'index_file': 'signature_ivf_index.pkl',
        'samples_table': 'signature_samples',
        'vector_column': 'signature_vector',
        'threshold': THRESHOLD_SIGNATURE,
        'save_fn': dbu.save_signature_vector,
        'update_query': """
            UPDATE {table} SET {vector_column} = %s 
            WHERE sample_id = %s
        """
    }
}

# Текущий залогиненный пользователь (subject_id и логин)
current_user_id = None
current_user_login = None


# ----------------------------
# Вспомогательные функции
# ----------------------------
def select_file(biometric_type):
    """Диалог выбора файла для указанного типа биометрии."""
    if biometric_type in ('face', 'signature'):
        filetypes = [("Image files", "*.jpg *.jpeg *.png")]
    else:
        filetypes = [("Audio files", "*.wav *.ogg *.mp3")]

    path = filedialog.askopenfilename(title=f"Выберите файл ({biometric_type})", filetypes=filetypes)
    return path or None


def prompt_text(title, prompt):
    """Простой диалог ввода текста."""
    return simpledialog.askstring(title, prompt)


def show_info(message):
    messagebox.showinfo("Информация", message)


def show_error(message):
    messagebox.showerror("Ошибка", message)


# ----------------------------
# Действия (UI → бизнес-логика)
# ----------------------------
def register_biometric_ui(biometric_type):
    """
    Регистрация новой биометрии:
    - Если нет текущего пользователя, сначала создаём нового (логин/пароль и т.д.).
    - Иначе добавляем новый сэмпл текущему пользователю.
    """
    global current_user_id, current_user_login

    config = BIOMETRIC_CONFIG[biometric_type]

    # Если пользователь не залогинен — просим ввести личные данные
    if current_user_id is None:
        full_name = prompt_text("Регистрация", "Введите полное имя:")
        if not full_name:
            return
        gender = prompt_text("Регистрация", "Введите пол (M/F):")
        if not gender:
            return
        login = prompt_text("Регистрация", "Введите логин:")
        if not login:
            return
        password = prompt_text("Регистрация", "Введите пароль:")
        if not password:
            return
    else:
        # Уже залогиненный: не спрашиваем ФИО/логин/пароль
        full_name = None
        gender = None
        login = None
        password = None

    # Выбираем файл
    file_path = select_file(biometric_type)
    if not file_path or not os.path.exists(file_path):
        show_error("Файл не выбран или не существует.")
        return

    # Проверка расширения
    if biometric_type == 'face' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        show_error("Лицо: поддерживаемые форматы — JPG, JPEG, PNG")
        return
    if biometric_type == 'voice' and not file_path.lower().endswith(('.wav', '.ogg', '.mp3')):
        show_error("Голос: поддерживаемые форматы — WAV, OGG, MP3")
        return
    if biometric_type == 'signature' and not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
        show_error("Подпись: поддерживаемые форматы — JPG, JPEG, PNG")
        return

    # Извлечение вектора
    vector = None
    if biometric_type == 'face':
        vector = fu.get_face_vector(file_path)
    elif biometric_type == 'voice':
        vector = vu.extract_audio_vector(file_path)
    else:
        vector = su.extract_signature_vector(file_path)

    if not vector:
        show_error(f"Не удалось извлечь вектор из {biometric_type}.")
        return

    # Если пользователь не авторизован — создаём нового вместе с этим биосэмплом
    if current_user_id is None:
        # register_user возвращает sample_id, а внутри создаёт subject и первый сэмпл
        sample_id = dbu.register_user(full_name, gender, login, password, file_path, biometric_type)
        if not sample_id:
            show_error("Ошибка регистрации пользователя.")
            return

        save_fn = config['save_fn']
        if not save_fn(sample_id, vector):
            show_error(f"Ошибка сохранения {biometric_type}.")
            return

        # Сохраняем информацию о текущем пользователе
        current_user_id = dbu.get_subject_by_login(login)
        current_user_login = login
        show_info(f"Пользователь '{login}' зарегистрирован и авторизован.")

    else:
        # Пользователь уже существует → добавляем новый активный сэмпл
        sample_id = dbu.add_biometric_sample(current_user_id, file_path, biometric_type)
        if not sample_id:
            show_error("Ошибка добавления биометрии.")
            return

        save_fn = config['save_fn']
        if not save_fn(sample_id, vector):
            show_error(f"Ошибка сохранения {biometric_type}.")
            return

        show_info(f"{biometric_type.capitalize()} добавлен для пользователя '{current_user_login}'.")

    # Пересобираем соответствующий индекс
    config = BIOMETRIC_CONFIG[biometric_type]
    update_index(
        config['samples_table'],
        config['vector_column'],
        config['index_file']
    )

def biometric_login_ui(biometric_type):
    """
    Аутентификация по биометрии. После успешного поиска запоминаем current_user_id.
    """
    global current_user_id, current_user_login

    if current_user_id is not None:
        show_info("Вы уже авторизованы. Сначала выйдите из аккаунта.")
        return

    file_path = select_file(biometric_type)
    if not file_path:
        return

    if biometric_type == 'face':
        vector = fu.get_face_vector(file_path)
    elif biometric_type == 'voice':
        vector = vu.extract_audio_vector(file_path)
    else:
        vector = su.extract_signature_vector(file_path)

    if not vector:
        show_error(f"Не удалось извлечь вектор из {biometric_type}.")
        return

    results = dbu.recognize_biometric(vector, biometric_type)
    if not results:
        show_error("Не распознано.")
        return

    # Берём ближайшего (с минимальной дистанцией)
    results.sort(key=lambda x: x[2])
    subj_id, login, dist = results[0]
    current_user_id = subj_id
    current_user_login = login
    show_info(f"Авторизация успешна. Добро пожаловать, {login}!")


def update_password_ui():
    """Смена пароля для текущего пользователя."""
    global current_user_id, current_user_login

    if current_user_id is None:
        show_error("Сначала авторизуйтесь.")
        return

    old_pw = prompt_text("Смена пароля", "Введите текущий пароль:")
    if not dbu.check_current_password(current_user_id, old_pw):
        show_error("Неверный текущий пароль.")
        return

    new_pw = prompt_text("Смена пароля", "Введите новый пароль:")
    confirm = prompt_text("Смена пароля", "Повторите новый пароль:")
    if new_pw != confirm:
        show_error("Пароли не совпадают.")
        return

    if dbu.update_password(current_user_id, new_pw):
        show_info("Пароль успешно изменён.")
    else:
        show_error("Ошибка при изменении пароля.")


def update_biometric_ui(biometric_type):
    """Обновление (замена) уже существующего сэмпла для залогиненного пользователя."""
    global current_user_id, current_user_login

    if current_user_id is None:
        show_error("Сначала авторизуйтесь.")
        return

    file_path = select_file(biometric_type)
    if not file_path:
        return

    if biometric_type == 'face':
        vector = fu.get_face_vector(file_path)
    elif biometric_type == 'voice':
        vector = vu.extract_audio_vector(file_path)
    else:
        vector = su.extract_signature_vector(file_path)

    if not vector:
        show_error(f"Не удалось извлечь вектор из {biometric_type}.")
        return

    # Деактивируем старый сэмпл и создаём новый (add_biometric_sample внутри снимает статус)
    if dbu.update_biometric_vector(current_user_id, vector, file_path, biometric_type):
        show_info(f"{biometric_type.capitalize()} успешно обновлён.")
        # Перестраиваем нужный индекс
        config = BIOMETRIC_CONFIG[biometric_type]
        update_index(
        config['samples_table'],
        config['vector_column'],
        config['index_file']
    )
    else:
        show_error(f"Ошибка при обновлении {biometric_type}.")


def add_biometric_ui():
    """Добавление нового типа биометрии для авторизованного пользователя."""
    global current_user_id, current_user_login

    if current_user_id is None:
        show_error("Сначала авторизуйтесь.")
        return

    # Предлагаем список типов, которых у пользователя ещё нет
    existing = dbu.get_user_active_sample_types(current_user_id)  # возвращает список 'face','voice','signature'
    options = [t for t in ('face', 'voice', 'signature') if t not in existing]
    if not options:
        show_info("У вас уже есть все типы биометрии.")
        return

    choice = simpledialog.askstring("Добавить биометрию",
                                    f"Выберите тип для добавления: {', '.join(options)}")
    if choice not in options:
        show_error("Неверный тип.")
        return

    # Повторяем практически ту же логику, что и register_biometric_ui, но без создания нового пользователя
    file_path = select_file(choice)
    if not file_path or not os.path.exists(file_path):
        show_error("Файл не выбран или не существует.")
        return

    if choice == 'face':
        vector = fu.get_face_vector(file_path)
    elif choice == 'voice':
        vector = vu.extract_audio_vector(file_path)
    else:
        vector = su.extract_signature_vector(file_path)

    if not vector:
        show_error(f"Не удалось извлечь вектор из {choice}.")
        return

    sample_id = dbu.add_biometric_sample(current_user_id, file_path, choice)
    if not sample_id:
        show_error("Ошибка добавления биометрии.")
        return

    save_fn = BIOMETRIC_CONFIG[choice]['save_fn']
    if not save_fn(sample_id, vector):
        show_error(f"Ошибка сохранения {choice}.")
        return

    show_info(f"{choice.capitalize()} добавлен.")
    config = BIOMETRIC_CONFIG[choice]
    update_index(
        config['samples_table'],
        config['vector_column'],
        config['index_file']
    )

def logout_ui():
    """Выход из учётной записи."""
    global current_user_id, current_user_login
    current_user_id = None
    current_user_login = None
    show_info("Вы вышли из аккаунта.")


def view_all_users_ui():
    """Показать всех пользователей и их биометрию."""
    users = dbu.get_all_users_with_biometrics()
    if not users:
        show_error("Нет ни одного пользователя.")
        return

    win = tk.Toplevel(root)
    win.title("Все пользователи")
    txt = tk.Text(win, width=80, height=25)
    txt.pack(fill=tk.BOTH, expand=True)

    for user in users:
        txt.insert(tk.END, f"Пользователь: {user['full_name']} (ID: {user['subject_id']})\n")
        txt.insert(tk.END, f"  Логин: {user['login']}, Пол: {user['gender']}\n")
        txt.insert(tk.END, "  Биометрия:\n")
        for bio in user['biometrics']:
            txt.insert(tk.END, f"    - Тип: {bio['sample_type']}, Файл: {bio['file_path']}\n")
            if bio['sample_type'] == 'face':
                txt.insert(tk.END, f"       • Вектор лица (128D)\n")
            elif bio['sample_type'] == 'voice':
                txt.insert(tk.END, f"       • Вектор голоса (192D)\n")
            else:
                txt.insert(tk.END, f"       • Вектор подписи (128D)\n")
        txt.insert(tk.END, "-" * 60 + "\n")
    txt.configure(state=tk.DISABLED)


def view_audit_logs_ui():
    """Окно с функционалом просмотра логов."""
    win = tk.Toplevel(root)
    win.title("Логи изменений")
    frame = ttk.Frame(win)
    frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    btn_all = ttk.Button(frame, text="Показать все логи", command=lambda: _show_logs("all", txt))
    btn_all.grid(row=0, column=0, padx=5, pady=5)
    btn_by_table = ttk.Button(frame, text="Фильтр по таблице", command=lambda: _show_logs("by_table", txt))
    btn_by_table.grid(row=0, column=1, padx=5, pady=5)
    btn_by_user = ttk.Button(frame, text="Фильтр по пользователю", command=lambda: _show_logs("by_user", txt))
    btn_by_user.grid(row=0, column=2, padx=5, pady=5)
    btn_export = ttk.Button(frame, text="Экспорт в CSV", command=lambda: _show_logs("export", txt))
    btn_export.grid(row=0, column=3, padx=5, pady=5)
    btn_close = ttk.Button(frame, text="Закрыть", command=win.destroy)
    btn_close.grid(row=0, column=4, padx=5, pady=5)

    txt = tk.Text(win, width=100, height=30)
    txt.pack(fill=tk.BOTH, expand=True)

    def _show_logs(mode, text_widget):
        text_widget.delete("1.0", tk.END)
        if mode == "all":
            logs = lu.fetch_all_logs()
            for log in logs:
                text_widget.insert(tk.END, f"ID: {log[0]}, Таблица: {log[1]}, Операция: {log[2]}, Дата: {log[5]}, Пользователь: {log[6]}\n")
                text_widget.insert(tk.END, f"Старые: {log[3]}\nНовые: {log[4]}\n" + "-"*60 + "\n")

        elif mode == "by_table":
            tbl = prompt_text("Фильтр по таблице", "Введите имя таблицы:")
            if not tbl:
                return
            logs = lu.filter_logs_by_table(tbl)
            for log in logs:
                text_widget.insert(tk.END, f"ID: {log[0]}, Таблица: {log[1]}, Операция: {log[2]}, Дата: {log[5]}, Пользователь: {log[6]}\n")
                text_widget.insert(tk.END, f"Старые: {log[3]}\nНовые: {log[4]}\n" + "-"*60 + "\n")

        elif mode == "by_user":
            usr = prompt_text("Фильтр по пользователю", "Введите логин пользователя:")
            if not usr:
                return
            logs = lu.filter_logs_by_user(usr)
            for log in logs:
                text_widget.insert(tk.END, f"ID: {log[0]}, Таблица: {log[1]}, Операция: {log[2]}, Дата: {log[5]}, Пользователь: {log[6]}\n")
                text_widget.insert(tk.END, f"Старые: {log[3]}\nНовые: {log[4]}\n" + "-"*60 + "\n")

        else:  # export
            all_logs = lu.fetch_all_logs()
            lu.export_logs_to_csv(all_logs)
            show_info("Логи экспортированы в CSV.")


# ----------------------------
# Построение главного окна
# ----------------------------
root = tk.Tk()
root.title("🔐 Биометрическая Система")
root.geometry("450x500")

frm = ttk.Frame(root, padding=20)
frm.pack(fill=tk.BOTH, expand=True)

lbl = ttk.Label(frm, text="Биометрическая система", font=("Arial", 16))
lbl.pack(pady=10)

# 1) Регистрация
btn_register_face = ttk.Button(frm, text="1. Зарегистрироваться по лицу", 
                               command=lambda: register_biometric_ui('face'))
btn_register_voice = ttk.Button(frm, text="2. Зарегистрироваться по голосу", 
                                command=lambda: register_biometric_ui('voice'))
btn_register_sig = ttk.Button(frm, text="3. Зарегистрироваться по подписи", 
                              command=lambda: register_biometric_ui('signature'))

# 2) Аутентификация
btn_login_face = ttk.Button(frm, text="4. Войти по лицу", 
                            command=lambda: biometric_login_ui('face'))
btn_login_voice = ttk.Button(frm, text="5. Войти по голосу", 
                             command=lambda: biometric_login_ui('voice'))
btn_login_sig = ttk.Button(frm, text="6. Войти по подписи", 
                           command=lambda: biometric_login_ui('signature'))

# 3) Просмотр пользователей и логов
btn_view_users = ttk.Button(frm, text="7. Просмотр пользователей", command=view_all_users_ui)
btn_view_logs = ttk.Button(frm, text="8. Анализ логов", command=view_audit_logs_ui)

# 4) Выйти из аккаунта
btn_logout = ttk.Button(frm, text="9. Выйти из аккаунта", command=logout_ui)

# Упакуем основные кнопки
for w in (btn_register_face, btn_register_voice, btn_register_sig,
          btn_login_face, btn_login_voice, btn_login_sig,
          btn_view_users, btn_view_logs, btn_logout):
    w.pack(fill=tk.X, pady=3)

# 5) Секция личных действий (появляется только после авторизации)
sep = ttk.Separator(frm, orient='horizontal')
sep.pack(fill=tk.X, pady=10)
lbl_user_actions = ttk.Label(frm, text="Личные действия (после входа)", font=("Arial", 14))
lbl_user_actions.pack(pady=5)

btn_change_password = ttk.Button(frm, text="Сменить пароль", command=update_password_ui)
btn_update_face = ttk.Button(frm, text="Обновить фото", command=lambda: update_biometric_ui('face'))
btn_update_voice = ttk.Button(frm, text="Обновить голос", command=lambda: update_biometric_ui('voice'))
btn_update_sig = ttk.Button(frm, text="Обновить подпись", command=lambda: update_biometric_ui('signature'))
btn_add_bio = ttk.Button(frm, text="Добавить новую биометрию", command=add_biometric_ui)

for w in (btn_change_password, btn_update_face, btn_update_voice, btn_update_sig, btn_add_bio):
    w.pack(fill=tk.X, pady=3)

root.mainloop()
