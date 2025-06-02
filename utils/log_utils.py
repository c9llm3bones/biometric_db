import psycopg2
from utils.config import DB_CONFIG
import json
from datetime import datetime

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def fetch_all_logs():
    """Получить все логи"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC")
    logs = cursor.fetchall()
    conn.close()
    return logs

def filter_logs_by_date(start_date: str, end_date: str):
    """Фильтр по дате (YYYY-MM-DD)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM audit_logs
        WHERE timestamp BETWEEN %s AND %s
        ORDER BY timestamp DESC
    """, (start_date, end_date))
    logs = cursor.fetchall()
    conn.close()
    return logs

def filter_logs_by_table(table_name: str):
    """Фильтр по таблице"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM audit_logs
        WHERE table_name = %s
        ORDER BY timestamp DESC
    """, (table_name,))
    logs = cursor.fetchall()
    conn.close()
    return logs

def filter_logs_by_user(user: str):
    """Фильтр по пользователю"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM audit_logs
        WHERE changed_by = %s
        ORDER BY timestamp DESC
    """, (user,))
    logs = cursor.fetchall()
    conn.close()
    return logs

def export_logs_to_csv(logs, filename="audit_export.csv"):
    """Экспорт логов в CSV"""
    import csv
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "Таблица", "Операция", "Старые данные", 
            "Новые данные", "Дата изменения", "Пользователь"
        ])
        for log in logs:
            writer.writerow([
                log[0], log[1], log[2], 
                json.dumps(log[3], ensure_ascii=False), 
                json.dumps(log[4], ensure_ascii=False),
                log[5], log[6]
            ])
    print(f"Логи экспортированы в {filename}")

def analyze_user_activity():
    """Анализ активности пользователей"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT changed_by, COUNT(*) as changes_count
        FROM audit_logs
        GROUP BY changed_by
        ORDER BY changes_count DESC
    """)
    result = cursor.fetchall()
    conn.close()
    return result

def analyze_table_changes():
    """Анализ изменений по таблицам"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_name, COUNT(*) as changes_count
        FROM audit_logs
        GROUP BY table_name
        ORDER BY changes_count DESC
    """)
    result = cursor.fetchall()
    conn.close()
    return result