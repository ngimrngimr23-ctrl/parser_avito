import sys
import subprocess
import threading
import random
import toml
import os
import time
import csv
from flask import Flask

# --- Настройка веб-сервера для Render (чтобы не засыпал) ---
app = Flask('')

@app.route('/')
def home():
    return "Avito Parser Auto-Pilot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000, use_reloader=False)

# --- Чтение прокси строго без http:// (Решает ошибку Errno -2) ---
def get_proxy_list():
    proxies = []
    if os.path.exists("csv.csv"):
        try:
            with open("csv.csv", "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Пропускаем заголовки
                for row in reader:
                    if len(row) >= 4:
                        login, pwd = row[0].strip(), row[1].strip()
                        ip, port = row[2].strip(), row[3].strip()
                        # Чистый формат: логин:пароль@IP:порт
                        proxies.append(f"{login}:{pwd}@{ip}:{port}")
        except Exception as e:
            print(f"Ошибка чтения csv.csv: {e}")
            
    elif os.path.exists("proxies.txt"):
        try:
            with open("proxies.txt", "r", encoding="utf-8") as f:
                proxies = [line.strip().replace("http://", "").replace("https://", "") for line in f if line.strip()]
        except Exception as e:
            pass
            
    return proxies

# --- Подготовка и запуск парсера ---
def start_parser():
    proxies = get_proxy_list()
    if proxies:
        chosen_proxy = random.choice(proxies)
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            if "avito" not in data:
                data["avito"] = {}
                
            data["avito"]["proxy_string"] = chosen_proxy
            
            with open("config.toml", "w", encoding="utf-8") as f:
                toml.dump(data, f)
            
            hidden = chosen_proxy.split('@')[-1] if '@' in chosen_proxy else 'скрыт'
            print(f"\n🚀 Заряжен прокси: {hidden}")
        except Exception as e:
            print(f"Ошибка записи конфига: {e}")

    # Запускаем парсер и перехватываем его вывод
    return subprocess.Popen(
        [sys.executable, "-u", "parser_cls.py"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True
    )

# --- УМНЫЙ АВТОПИЛОТ (Вместо ручного Telegram-бота) ---
def monitor_parser():
    parser_process = start_parser()
    
    while True:
        if parser_process.poll() is not None:
            # Если парсер случайно закрылся сам - перезапускаем
            parser_process = start_parser()
        
        try:
            # Читаем лог парсера строчка за строчкой
            line = parser_process.stdout.readline()
            if line:
                print(line, end='') # Выводим в панель Render
                
                # ИЩЕМ ОШИБКИ И МОМЕНТАЛЬНО РЕАГИРУЕМ
                if any(err in line for err in ["плохие: 1шт", "Request error", "Errno -2", "Name or service not known"]):
                    print("\n[АВТОПИЛОТ] Прокси не пробил защиту или выдал ошибку! Меняем на следующий...\n")
                    parser_process.terminate()
                    parser_process.wait()
                    parser_process = start_parser()
            else:
                time.sleep(0.1)
        except Exception as e:
            time.sleep(1)

# --- Точка входа ---
if __name__ == '__main__':
    # Защита от двойного запуска потоков
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("Запуск системы Автопилота (Telegram-пульт отключен для избежания конфликта 409)...")
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        monitor_parser()
    else:
        print("Вторичный процесс Flask проигнорирован.")        
