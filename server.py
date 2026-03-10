from flask import Flask
import subprocess
import sys
import threading
import telebot
import toml

app = Flask('')

@app.route('/')
def home():
    return "Avito Parser and Telegram Bot are running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Глобальная переменная для управления процессом парсера
parser_process = None

def start_parser():
    global parser_process
    if parser_process:
        print("Останавливаем старый процесс парсера...")
        parser_process.terminate()
        parser_process.wait()
    print("Запускаем парсер с новыми настройками...")
    parser_process = subprocess.Popen([sys.executable, "parser_cls.py"], stdout=sys.stdout, stderr=sys.stderr)

def run_tg_bot():
    # Читаем токен и твой ID прямо из config.toml
    try:
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
            token = data["avito"].get("tg_token", "")
            chat_ids = data["avito"].get("tg_chat_id", [])
            owner_id = str(chat_ids[0]) if chat_ids else ""
    except Exception as e:
        print(f"Ошибка чтения конфига: {e}")
        return

    if not token or not owner_id:
        print("В config.toml не указан токен или ID! Бот управления не запущен.")
        return

    bot = telebot.TeleBot(token)

    # Проверка, чтобы чужие люди не могли управлять твоим ботом
    def check_owner(message):
        return str(message.chat.id) == owner_id

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        if not check_owner(message): return
        bot.reply_to(message, "🕹 Управление парсером:\n\n/links - Показать текущие ссылки\n/add <ссылка> - Добавить новую\n/del <номер> - Удалить по номеру")

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
            bot.reply_to(message, "Напиши команду так:\n/add https://avito.ru/...")
            return
        
        new_url = parts[1]
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
            
        if "urls" not in data["avito"]:
            data["avito"]["urls"] = []
        data["avito"]["urls"].append(new_url)
        
        with open("config.toml", "w", encoding="utf-8") as f:
            toml.dump(data, f)
            
        bot.reply_to(message, "✅ Ссылка добавлена! Перезапускаю парсер...")
        start_parser()

    @bot.message_handler(commands=['del'])
    def del_link(message):
        if not check_owner(message): return
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            bot.reply_to(message, "Напиши команду так:\n/del <номер>")
            return
        
        idx = int(parts[1])
        with open("config.toml", "r", encoding="utf-8") as f:
            data = toml.load(f)
            
        urls = data["avito"].get("urls", [])
        if 0 <= idx < len(urls):
            removed = urls.pop(idx)
            with open("config.toml", "w", encoding="utf-8") as f:
                toml.dump(data, f)
            bot.reply_to(message, f"🗑 Удалено:\n{removed}\n\nПерезапускаю парсер...")
            start_parser()
        else:
            bot.reply_to(message, "❌ Нет такого номера. Посмотри номера через /links")

    print("Бот управления успешно запущен!")
    bot.infinity_polling()

if __name__ == '__main__':
    # 1. Запускаем сам парсер Авито
    start_parser()
    
    # 2. Запускаем веб-сервер Flask (в фоновом потоке, чтобы не блокировал)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 3. Запускаем Telegram-бота (в главном потоке)
    run_tg_bot()
    
