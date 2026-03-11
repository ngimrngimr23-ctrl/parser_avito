import sys
import subprocess
import threading
import random
import toml
import telebot
import os
import time
from flask import Flask, request

# Твоя ссылка на Render (используется для связи с Телеграмом)
WEBHOOK_URL = "https://parser-avito-ltzi.onrender.com/webhook"

# --- ДОСТАЕМ ТОКЕН ---
try:
    with open("config.toml", "r", encoding="utf-8") as f:
        data = toml.load(f)
        TOKEN = data.get("avito", {}).get("tg_token", "")
        chat_ids = data.get("avito", {}).get("tg_chat_id", [])
        OWNER_ID = str(chat_ids[0]) if chat_ids else ""
except Exception:
    TOKEN = ""
    OWNER_ID = ""

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- ВЕБ-СЕРВЕР И ПРИЕМ КОМАНД ОТ ТЕЛЕГРАМА ---
@app.route('/')
def home():
    return "Avito Auto-Pilot & Telegram Webhook are running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    # Сюда Телеграм сам будет присылать твои команды!
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'error', 403

def check_owner(message):
    return str(message.chat.id) == OWNER_ID

# --- КОМАНДЫ ТЕЛЕГРАМ ---
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not check_owner(message): return
    bot.reply_to(message, "🕹 **Пульт управления Avito (Webhook):**\n\n/links - Показать ссылки\n/add <ссылка> - Добавить\n/del <номер> - Удалить\n/restart - Сменить прокси", parse_mode="Markdown")

@bot.message_handler(commands=['links'])
def list_links(message):
    if not check_owner(message): return
    try:
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
        urls = data.get("avito", {}).get("urls", [])
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
        if "avito" not in data: data["avito"] = {}
        if "urls" not in data["avito"]: data["avito"]["urls"] = []
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
        urls = data.get("avito", {}).get("urls", [])
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

# --- ЛОГИКА ПАРСЕРА И ПРОКСИ ---
parser_process = None
parser_lock = threading.Lock()

def get_proxy_list():
    proxies = []
    if os.path.exists("csv.csv"):
        try:
            with open("csv.csv", "r", encoding="utf-8") as f:
                for line in f:
                    clean_line = line.strip()
                    if not clean_line or "login" in clean_line.lower():
                        continue
                    delimiter = ";" if ";" in clean_line else ","
                    parts = clean_line.split(delimiter)
                    if len(parts) >= 4:
                        login, pwd, ip, port = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
                        if port.isdigit():
                            proxies.append(f"{login}:{pwd}@{ip}:{port}")
        except Exception as e:
            print(f"Ошибка чтения csv.csv: {e}", flush=True)
    return proxies

def start_parser_internal():
    global parser_process
    proxies = get_proxy_list()
    
    if not proxies:
        print("\n❌ КРИТИЧЕСКАЯ ОШИБКА: Прокси не загружены!", flush=True)
        return False
        
    print(f"✅ Успешно загружено прокси из CSV: {len(proxies)} шт.", flush=True)
    chosen_proxy = random.choice(proxies)
    
    for _ in range(5):
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            if "avito" not in data: data["avito"] = {}
            data["avito"]["proxy_string"] = chosen_proxy
            with open("config.toml", "w", encoding="utf-8") as f:
                toml.dump(data, f)
            break
        except Exception:
            time.sleep(1)

    hidden = chosen_proxy.split('@')[-1] if '@' in chosen_proxy else 'скрыт'
    print(f"🚀 ПРОКСИ ЗАРЯЖЕН: {hidden}", flush=True)

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
                    triggers = ["плохие: 1шт", "Request error", "Errno -2", "Name or service not known", "validation error", "HTTP request failed", "429", "Blocked request"]
                    if any(err in line for err in triggers):
                        print("\n[АВТОПИЛОТ] Смена прокси...\n", flush=True)
                        with parser_lock:
                            parser_process.terminate()
                            parser_process.wait()
                            is_running = start_parser_internal()
                else:
                    time.sleep(0.1)
        except Exception:
            time.sleep(1)

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("Запуск системы...", flush=True)
        
        # Настраиваем Webhook вместо Polling!
        if TOKEN:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=WEBHOOK_URL)
            print(f"✅ Webhook успешно установлен на {WEBHOOK_URL}", flush=True)
        
        # Запускаем автопилот парсера
        threading.Thread(target=monitor_parser, daemon=True).start()
    
    # Запускаем Flask-сервер. Он и страницы держит, и команды от ТГ принимает
    app.run(host='0.0.0.0', port=10000, use_reloader=False)
