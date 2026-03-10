import sys
import subprocess
import threading
import random
import toml
import telebot
from flask import Flask

# --- Настройка веб-сервера для Render ---
app = Flask('')

@app.route('/')
def home():
    return "Avito Parser, Telegram Bot & Proxy Manager are running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Глобальная переменная для управления процессом парсера
parser_process = None

# --- Умный запуск парсера с ротацией прокси ---
def start_parser():
    global parser_process
    if parser_process:
        print("Останавливаем старый процесс парсера...")
        parser_process.terminate()
        parser_process.wait()

    print("Подготавливаем прокси и конфиг...")
    try:
        # Читаем список прокси
        with open("proxies.txt", "r", encoding="utf-8") as f:
            proxies = [line.strip() for line in f if line.strip()]
        
        if proxies:
            chosen_proxy = random.choice(proxies)
            # Защита от ошибки: если нет http://, добавляем его
            if not chosen_proxy.startswith("http"):
                chosen_proxy = f"http://{chosen_proxy}"
            
            # Открываем конфиг
            with open("config.toml", "r", encoding="utf-8") as f:
                data = toml.load(f)
            
            # Вписываем выбранный прокси в конфиг
            if "avito" not in data:
                data["avito"] = {}
            data["avito"]["proxy_string"] = chosen_proxy
            
            # Сохраняем конфиг
            with open("config.toml", "w", encoding="utf-8") as f:
                toml.dump(data, f)
            print(f"🚀 Заряжен резидентский прокси: {chosen_proxy.split('@')[-1] if '@' in chosen_proxy else 'скрыт'}")
        else:
            print("⚠ Файл proxies.txt пуст! Парсер запустится без прокси.")
            
    except FileNotFoundError:
        print("⚠ Файл proxies.txt не найден! Создайте его и добавьте прокси.")
    except Exception as e:
        print(f"⚠ Ошибка при загрузке прокси: {e}")

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

    @bot.message_handler(commands=['add'])
    def add_link(message):
        if not check_owner(message): return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Напиши так:\n/add https://avito.ru/...")
            return
        
        new_url = parts[1]
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
            
        if "urls" not in data["avito"]:
            data["avito"]["urls"] = []
        data["avito"]["urls"].append(new_url)
        
        with open("config.toml", "w", encoding="utf-8") as f:
            toml.dump(data, f)
            
        bot.reply_to(message, "✅ Ссылка добавлена! Меняю прокси и перезапускаю парсер...")
        start_parser()

    @bot.message_handler(commands=['del'])
    def del_link(message):
        if not check_owner(message): return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            bot.reply_to(message, "Напиши так:\n/del <номер>")
            return
        
        idx = int(parts[1])
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

    @bot.message_handler(commands=['restart'])
    def restart_bot(message):
        if not check_owner(message): return
        bot.reply_to(message, "🔄 Принудительная смена прокси и перезапуск...")
        start_parser()

    print("Telegram-бот управления успешно запущен!")
    bot.infinity_polling()

# --- Точка входа ---
if __name__ == '__main__':
    # 1. Запускаем сервер Flask (в фоне)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 2. Делаем первый старт парсера
    start_parser()
    
    # 3. Запускаем слушателя Telegram (блокирует основной поток)
    run_tg_bot()
