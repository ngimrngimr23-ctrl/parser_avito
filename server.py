from flask import Flask
import subprocess

app = Flask('')

@app.route('/')
def home():
    return "Avito Parser is running in the background!"

if __name__ == '__main__':
    # 1. Запускаем "безголовый" парсер (специально для серверов)
    subprocess.Popen(["python", "parser_cls.py"])
    # 2. Поднимаем веб-порт, чтобы Render не ругался и не выключал бота
    app.run(host='0.0.0.0', port=10000)
  
