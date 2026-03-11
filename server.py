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

app = Flask('')

@app.route('/')
def home():
    return "Avito Auto-Pilot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000, use_reloader=False)

parser_process = None
parser_lock = threading.Lock()

def get_proxy_list():
    proxies = []
    if os.path.exists("csv.csv"):
        try:
            with open("csv.csv", "r", encoding="utf-8") as f:
                for line in f:
                    # Пропускаем строку с заголовками и пустые строки
                    if "login" in line.lower() or not line.strip(): 
                        continue
                    parts = line.strip().split(",")
                    if len(parts) >= 4:
                        login, pwd, ip, port = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
                        proxies.append(f"{login}:{pwd}@{ip}:{port}")
        except Exception as e:
            print(f"Ошибка чтения csv.csv: {e}", flush=True)
    elif os.path.exists("proxies.txt"):
        try:
            with open("proxies.txt", "r", encoding="utf-8") as f:
                for line in f:
                    p = line.strip().replace("http://", "").replace("https://", "")
                    if len(p) > 5:
                        proxies.append(p)
        except Exception:
            pass
    return proxies

def start_parser_internal():
    global parser_process
    proxies = get_proxy_list()
    
    if not proxies:
        print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Прокси не найдены в csv.csv! Парсер остановлен.", flush=True)
        return False
        
    chosen_proxy = random.choice(proxies)
    config_saved = False
    
    # Пытаемся сохранить конфиг 5 раз (защита от гонки процессов)
    for _ in range(5):
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            if "avito" not in data:
                data["avito"] = {}
                
            data["avito"]["proxy_string"] = chosen_proxy
            
            with open("config.toml", "w", encoding="utf-8") as f:
                toml.dump(data, f)
            config_saved = True
            break
        except Exception:
            time.sleep(1)
            
    if not config_saved:
        print("\n❌ Файл config.toml заблокирован! Запуск отменен, чтобы не идти без прокси.", flush=True)
        return False

    hidden = chosen_proxy.split('@')[-1] if '@' in chosen_proxy else 'скрыт'
    print(f"\n🚀 ПРОКСИ УСПЕШНО ЗАРЯЖЕН: {hidden}", flush=True)

    parser_process = subprocess.Popen(
        [sys.executable, "-u", "parser_cls.py"], 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True
    )
    return True

def monitor_parser():
    global parser_process
    with parser_lock:
        is_running = start_parser_internal()
    
    while True:
        if not is_running:
            time.sleep(10)
            with parser_lock:
                is_running = start_parser_internal()
            continue

        if parser_process and parser_process.poll() is not None:
            with parser_lock:
                is_running = start_parser_internal()
        
        try:
            if parser_process and parser_process.stdout:
                line = parser_process.stdout.readline()
                if line:
                    print(line, end='', flush=True)
                    triggers = ["плохие: 1шт", "Request error", "Errno -2", "Name or service not known", "validation error", "HTTP request failed"]
                    if any(err in line for err in triggers):
                        print("\n[АВТОПИЛОТ] Ошибка или капча! Срочно меняем прокси...\n", flush=True)
                        with parser_lock:
                            parser_process.terminate()
                            parser_process.wait()
                            is_running = start_parser_internal()
                else:
                    time.sleep(0.1)
        except Exception:
            time.sleep(1)

def run_tg_bot():
    try:
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
            token = data["avito"].get("tg_token", "")
            chat_ids = data["avito"].get("tg_chat_id", [])
            owner_id = str(chat_ids[0]) if chat_ids else ""
    except Exception as e:
        print(f"Ошибка конфига бота: {e}", flush=True)
        return

    if not token or not owner_id:
        print("Токен не указан! Бот не запущен.", flush=True)
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

    print("Очищаем зависшие запросы Telegram...", flush=True)
    bot.delete_webhook(drop_pending_updates=True)
    print("Telegram-бот управления успешно запущен!", flush=True)
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("Запуск системы...", flush=True)
        
        threading.Thread(target=run_flask, daemon=True).start()
        threading.Thread(target=monitor_parser, daemon=True).start()
        
        while True:
            try:
                run_tg_bot()
            except Exception as e:
                print(f"Ошибка бота: {e}. Перезапуск через 5 секунд...", flush=True)
                time.sleep(5)
    else:
        print("Вторичный процесс проигнорирован.", flush=True) 
