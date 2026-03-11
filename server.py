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

# --- Настройка веб-сервера для Render ---
app = Flask('')

@app.route('/')
def home():
    return "Avito Parser & Telegram Bot are running!"

def run_flask():
    # Отключаем reloader, чтобы избежать двойного запуска
    app.run(host='0.0.0.0', port=10000, use_reloader=False)

# Глобальная переменная для управления процессом парсера
parser_process = None

# --- Функция чтения прокси прямо из твоего CSV файла ---
def get_proxy_list():
    proxies = []
    # Если ты залил csv.csv, читаем его
    if os.path.exists("csv.csv"):
        try:
            with open("csv.csv", "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Пропускаем первую строку (заголовки)
                for row in reader:
                    if len(row) >= 4:
                        login, pwd, ip, port = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
                        # Собираем идеальную ссылку для парсера
                        proxies.append(f"http://{login}:{pwd}@{ip}:{port}")
        except Exception as e:
            print(f"Ошибка чтения csv.csv: {e}")
    # Резервный вариант, если csv нет, но есть proxies.txt
    elif os.path.exists("proxies.txt"):
        try:
            with open("proxies.txt", "r", encoding="utf-8") as f:
                proxies = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Ошибка чтения proxies.txt: {e}")
            
    return proxies

# --- Умный запуск парсера с ротацией ---
def start_parser():
    global parser_process
    if parser_process:
        print("Останавливаем старый процесс парсера...")
        parser_process.terminate()
        parser_process.wait()

    print("Подготавливаем прокси и конфиг...")
    proxies = get_proxy_list()
    
    if proxies:
        chosen_proxy = random.choice(proxies)
        # Защита: добавляем http:// если его нет
        if not chosen_proxy.startswith("http"):
            chosen_proxy = f"http://{chosen_proxy}"
            
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            
            if "avito" not in data:
                data["avito"] = {}
            data["avito"]["proxy_string"] = chosen_proxy
            
            with open("config.toml", "w", encoding="utf-8") as f:
                toml.dump(data, f)
                
            hidden_proxy = chosen_proxy.split('@')[-1] if '@' in chosen_proxy else 'скрыт'
            print(f"🚀 Заряжен резидентский прокси из CSV: {hidden_proxy}")
        except Exception as e:
            print(f"⚠ Ошибка записи в конфиг: {e}")
    else:
        print("⚠ Файлы csv.csv или proxies.txt пустые или не найдены! Запуск без прокси.")

    print("Запускаем парсер Авито...")
    parser_process = subprocess.Popen([sys.executable, "parser_cls.py"], stdout=sys.stdout, stderr=sys.stderr)

# --- Telegram Бот для управления ---
def run_tg_bot():
    try:
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
            token = data["avito"].get("tg_token", "")
            chat_ids = data["avito"].get("tg_chat_id", [])
            owner_id = str(chat_ids[0]) if chat_ids else ""
    except Exception as e:
        print(f"Ошибка чтения конфига для бота: {e}")
        return

    if not token or not owner_id:
        print("В config.toml не указан токен или ID! Бот управления не запущен.")
        return

    bot = telebot.TeleBot(token)

    def check_owner(message):
        return str(message.chat.id) == owner_id

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        if not check_owner(message): return
        bot.reply_to(message, "🕹 Управление парсером:\n\n/links - Показать ссылки\n/add <ссылка> - Добавить\n/del <номер> - Удалить\n/restart - Сменить прокси и перезапустить")

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
            msg = "🔗 Текущие ссылки:\n"
            for i, u in enumerate(urls):
                msg += f"[{i}] {u}\n"
            bot.reply_to(message, msg)
        except Exception as e:
            bot.reply_to(message, f"Ошибка чтения ссылок: {e}")

    @bot.message_handler(commands=['add'])
    def add_link(message):
        if not check_owner(message): return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Напиши так:\n/add https://avito.ru/...")
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
                
            bot.reply_to(message, "✅ Ссылка добавлена! Меняю прокси и перезапускаю парсер...")
            start_parser()
        except Exception as e:
            bot.reply_to(message, f"Ошибка при добавлении: {e}")

    @bot.message_handler(commands=['del'])
    def del_link(message):
        if not check_owner(message): return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            bot.reply_to(message, "Напиши так:\n/del <номер>")
            return
        
        idx = int(parts[1])
        try:
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
                
            urls = data["avito"].get("urls", [])
            if 0 <= idx < len(urls):
                removed = urls.pop(idx)
                with open("config.toml", "w", encoding="utf-8") as f:
                    toml.dump(data, f)
                bot.reply_to(message, f"🗑 Удалено:\n{removed}\n\nМеняю прокси и перезапускаю...")
                start_parser()
            else:
                bot.reply_to(message, "❌ Нет такого номера. Посмотри номера через /links")
        except Exception as e:
            bot.reply_to(message, f"Ошибка при удалении: {e}")

    @bot.message_handler(commands=['restart'])
    def restart_bot(message):
        if not check_owner(message): return
        bot.reply_to(message, "🔄 Принудительная смена прокси и перезапуск...")
        start_parser()

    print("Очищаем зависшие запросы Telegram...")
    bot.delete_webhook(drop_pending_updates=True)
    
    print("Telegram-бот управления успешно запущен!")
    bot.infinity_polling(skip_pending=True)

# --- Точка входа ---
if __name__ == '__main__':
    # Защита от двойного запуска (важно для Render/Flask)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print("Главный процесс стартует...")

        # 1. Запускаем веб-сервер (чтобы Render не отключал нас)
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        
        # 2. Первый старт парсера
        start_parser()
        
        # 3. Запускаем Телеграм-бота с автоперезапуском при падении
        while True:
            try:
                run_tg_bot()
            except Exception as e:
                print(f"Критическая ошибка бота: {e}. Перезапуск через 5 секунд...")
                time.sleep(5)
    else:
        print("Вторичный процесс проигнорирован.")    
