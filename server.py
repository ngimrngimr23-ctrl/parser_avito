import sys
import subprocess
import threading
import random
import toml
import telebot
import os
import time
import csv
from flask import Flask

# --- Настройка веб-сервера ---
app = Flask('')

@app.route('/')
def home():
    return "Avito Auto-Pilot & Telegram Bot are running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000, use_reloader=False)

# --- Глобальные переменные ---
parser_process = None
parser_lock = threading.Lock()

# --- Чтение прокси из csv.csv ---
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
                        proxies.append(f"{login}:{pwd}@{ip}:{port}")
        except Exception as e:
            print(f"Ошибка чтения csv.csv: {e}")
    return proxies

# --- Запуск самого парсера ---
def start_parser_internal():
    global parser_process
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

    parser_process = subprocess.Popen(
        [sys.executable, "-u", "parser_cls.py"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True
    )

# --- АВТОПИЛОТ (Фоновый мониторинг логов) ---
def monitor_parser():
    global parser_process
    with parser_lock:
        start_parser_internal()
    
    while True:
        if parser_process and parser_process.poll() is not None:
            with parser_lock:
                start_parser_internal()
        
        try:
            if parser_process and parser_process.stdout:
                line = parser_process.stdout.readline()
                if line:
                    print(line, end='')
                    # Если парсер поймал банку или ошибку - меняем прокси
                    if any(err in line for err in ["плохие: 1шт", "Request error", "Errno -2", "Name or service not known"]):
                        print("\n[АВТОПИЛОТ] Ошибка! Меняем прокси на следующий...\n")
                        with parser_lock:
                            parser_process.terminate()
                            parser_process.wait()
                            start_parser_internal()
                else:
                    time.sleep(0.1)
        except Exception:
            time.sleep(1)

# --- TELEGRAM БОТ (Пульт управления) ---
def run_tg_bot():
    try:
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
            token = data["avito"].get("tg_token", "")
            chat_ids = data["avito"].get("tg_chat_id", [])
            owner_id = str(chat_ids[0]) if chat_ids else ""
    except Exception as e:
        print(f"Ошибка конфига бота: {e}")
        return

    if not token or not owner_id:
        print("Токен не указан! Бот не запущен.")
        return

    bot = telebot.TeleBot(token)

    def check_owner(message):
        return str(message.chat.id) == owner_id

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        if not check_owner(message): return
        bot.reply_to(message, "🕹 **Пульт управления Avito:**\n\n/links - Показать ссылки\n/add <ссылка> - Добавить\n/del <номер> - Удалить\n/restart - Сменить прокси", parse_mode="Markdown")

    @bot.message_handler(commands=['links'])
    def list_links(message):
        if not check_owner(message): return
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            urls = data["avito"].get("urls", [])
            if not urls:
                bot.reply_to(message, "Список ссылок пуст.")
                return
            msg = "🔗 **Текущие ссылки:**\n"
            for i, u in enumerate(urls):
                msg += f"[{i}] {u}\n"
            bot.reply_to(message, msg, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as e:
            bot.reply_to(message, f"Ошибка: {e}")

    @bot.message_handler(commands=['add'])
    def add_link(message):
        if not check_owner(message): return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Используй: `/add https://avito.ru/...`", parse_mode="Markdown")
            return
        new_url = parts[1]
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            if "urls" not in data["avito"]:
                data["avito"]["urls"] = []
            data["avito"]["urls"].append(new_url)
            with open("config.toml", "w", encoding="utf-8") as f:
                toml.dump(data, f)
            
            bot.reply_to(message, "✅ Ссылка добавлена! Перезапускаю парсер...")
            with parser_lock:
                global parser_process
                if parser_process:
                    parser_process.terminate()
                    parser_process.wait()
                start_parser_internal()
        except Exception as e:
            bot.reply_to(message, f"Ошибка: {e}")

    @bot.message_handler(commands=['del'])
    def del_link(message):
        if not check_owner(message): return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            bot.reply_to(message, "Используй: `/del <номер>`", parse_mode="Markdown")
            return
        idx = int(parts[1])
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            urls = data["avito"].get("urls", [])
            if 0 <= idx < len(urls):
                urls.pop(idx)
                with open("config.toml", "w", encoding="utf-8") as f:
                    toml.dump(data, f)
                bot.reply_to(message, "🗑 Ссылка удалена! Перезапускаю...")
                with parser_lock:
                    global parser_process
                    if parser_process:
                        parser_process.terminate()
                        parser_process.wait()
                    start_parser_internal()
            else:
                bot.reply_to(message, "❌ Нет такого номера.")
        except Exception as e:
            bot.reply_to(message, f"Ошибка: {e}")

    @bot.message_handler(commands=['restart'])
    def restart_bot(message):
        if not check_owner(message): return
        bot.reply_to(message, "🔄 Принудительная смена прокси...")
        with parser_lock:
            global parser_process
            if parser_process:
                parser_process.terminate()
                parser_process.wait()
            start_parser_internal()

    print("Очищаем зависшие запросы Telegram...")
    bot.delete_webhook(drop_pending_updates=True)
    print("Telegram-бот управления успешно запущен!")
    bot.infinity_polling(skip_pending=True)

# --- Точка входа ---
if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("Запуск системы...")
        
        # 1. Запускаем веб-сервер
        threading.Thread(target=run_flask, daemon=True).start()
        
        # 2. Запускаем Автопилот парсера
        threading.Thread(target=monitor_parser, daemon=True).start()
        
        # 3. Запускаем Бота в главном потоке
        while True:
            try:
                run_tg_bot()
            except Exception as e:
                print(f"Ошибка бота: {e}. Перезапуск через 5 секунд...")
                time.sleep(5)
    else:
        print("Вторичный процесс проигнорирован.")    
