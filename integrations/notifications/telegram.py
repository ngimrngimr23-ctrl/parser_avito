import requests
import datetime
import re

from integrations.notifications.base import Notifier
from integrations.notifications.transport import send_with_retries
from integrations.notifications.utils import get_first_image
from models import Item

# Функция для защиты от капризов Telegram MarkdownV2
def escape_md(text: str) -> str:
    if not text:
        return ""
    # Экранируем все опасные символы, чтобы бот не выдавал ошибку 400
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", str(text))

def format_price(price) -> str:
    try:
        # Делаем красивые пробелы в цене: 1 500 000 ₽
        return "{:,}".format(int(price)).replace(",", " ") + " ₽"
    except:
        return str(price)

def format_date(ts) -> str:
    try:
        # Авито может отдавать время в миллисекундах, переводим в секунды
        if ts > 2e10:
            ts = ts / 1000
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m.%Y в %H:%M")
    except:
        return "Неизвестно"

class TelegramNotifier(Notifier):
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def notify_message(self, message: str):
        def _send():
            return requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "MarkdownV2",
                },
                timeout=10,
            )

        send_with_retries(_send)

    # ПЕРЕКРЫВАЕМ стандартный формат нашим красивым шаблоном
    def format(self, ad: Item) -> str:
        # Достаем данные
        url = f"https://www.avito.ru{ad.urlPath}" if hasattr(ad, 'urlPath') else ""
        title = getattr(ad, 'title', 'Объявление')
        
        price = "Не указана"
        if hasattr(ad, 'priceDetailed') and ad.priceDetailed and hasattr(ad.priceDetailed, 'value'):
            price = format_price(ad.priceDetailed.value)
        elif hasattr(ad, 'price'):
            price = format_price(ad.price)

        pub_date = "Неизвестно"
        if hasattr(ad, 'time'):
            pub_date = format_date(ad.time)
            
        description = ""
        if hasattr(ad, 'description') and ad.description:
            # Обрезаем описание до 300 символов, чтобы сообщение не было огромным
            desc_text = ad.description
            description = desc_text[:300] + "..." if len(desc_text) > 300 else desc_text

        # Собираем красивое сообщение
        msg = f"🚗 *{escape_md(title)}*\n\n"
        msg += f"💰 *Цена:* {escape_md(price)}\n"
        msg += f"📅 *Опубликовано:* {escape_md(pub_date)}\n\n"
        
        if description:
            msg += f"📝 *Описание:*\n_{escape_md(description)}_\n\n"
            
        msg += f"🔗 [Перейти к объявлению]({escape_md(url)})"
        
        return msg


    def notify_ad(self, ad: Item):
        def _send():
            message = self.format(ad)
            return requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendPhoto",
                json={
                    "chat_id": self.chat_id,
                    "caption": message,
                    "photo": get_first_image(ad=ad),
                    "parse_mode": "MarkdownV2",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )

        send_with_retries(_send)


    def notify(self, ad: Item = None, message: str = None):
        if ad:
            return self.notify_ad(ad=ad)
        return self.notify_message(message=message)
