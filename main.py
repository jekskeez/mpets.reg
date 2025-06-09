import logging
import random
import string
import requests
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import asyncio
import nest_asyncio

# ==== Марков-генератор слов (3-грам) ====

from collections import defaultdict, Counter

class MarkovWordGenerator:
    def __init__(self, seeds, n=3):
        """
        seeds: список стартовых слов (строк)
        n: длина n-грам (по умолчанию 3)
        """
        self.n = n
        self.model = defaultdict(Counter)
        self._build_model(seeds)

    def _build_model(self, seeds):
        start = "^" * (self.n - 1)
        end = "$"
        for w in seeds:
            w = start + w.lower() + end
            for i in range(len(w) - (self.n - 1)):
                gram = w[i:i + (self.n - 1)]
                nxt = w[i + (self.n - 1)]
                self.model[gram][nxt] += 1

    def generate(self, max_length=8):
        gram = "^" * (self.n - 1)
        result = []
        while True:
            choices, weights = zip(*self.model[gram].items())
            nxt = random.choices(choices, weights=weights)[0]
            if nxt == "$" or len(result) >= max_length:
                break
            result.append(nxt)
            gram = gram[1:] + nxt
        # капитализуем первый символ
        return "".join(result).capitalize()

# Список seed-слов (взяли из вашего примера)
SEEDS = [
    "Азирис", "Тутовка", "Тогол", "Баррель", "Всемирность", "Глиптодонт",
    "Минори", "Омежник", "Полевица", "Пирамидальный", "Светский",
    "Феокрит", "Лаконичный", "Кечкара", "Кельнер", "Бегин", "Канифас",
    "Сераинг", "Фанфарный", "Мишино", "Мутул", "Ивинг", "Беляк",
    "Мазелла", "Казеин", "Буффон", "Лаксум", "Водоотлив", "Адряс",
    "Вытва", "Шугурово", "Регтайм", "Завражье", "Трихалк", "Скочилов",
    "Кольяда", "Мутаген"
]

# Создаём генератор
markov_gen = MarkovWordGenerator(SEEDS, n=3)

# ==== Конфиг и инициализация ====

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)
nest_asyncio.apply()

# Чтение Telegram-токена из файла
def get_token_from_file():
    try:
        with open('token.txt', 'r') as f:
            line = f.readline().strip()
            if line.startswith('token ='):
                return line.split('=',1)[1].strip()
    except Exception as e:
        logger.error(f"Не смогли прочитать token.txt: {e}")
    return None

TOKEN = get_token_from_file()
if not TOKEN:
    raise RuntimeError("Токен не найден в token.txt")

# Параметры Mail.tm (упрощённо)
REQUEST_LIMIT = 8
TIME_WINDOW = 60
request_count = 0
last_req = time.time()

def generate_mail(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_available_domains():
    global request_count, last_req
    now = time.time()
    if now - last_req < TIME_WINDOW and request_count >= REQUEST_LIMIT:
        time.sleep(TIME_WINDOW - (now - last_req))
    try:
        r = requests.get("https://api.mail.tm/domains")
        request_count += 1
        last_req = time.time()
        data = r.json().get('hydra:member', [])
        return [d['domain'] for d in data]
    except:
        return []

def create_email():
    domains = get_available_domains()
    if not domains:
        return None
    domain = domains[0]
    user = generate_mail()
    addr = f"{user}@{domain}"
    pwd = generate_mail(12)
    try:
        resp = requests.post("https://api.mail.tm/accounts", json={"address": addr, "password": pwd})
        global request_count, last_req
        request_count += 1
        last_req = time.time()
        if resp.status_code == 201:
            return addr, pwd
    except Exception as e:
        logger.error(f"Mail.tm error: {e}")
    return None

is_running = False

# ==== Основная логика бота ====

async def start(update: Update, context: CallbackContext):
    global is_running
    is_running = True
    await update.message.reply_text("Старт регистрации!")
    await register_cycle(update, context)

async def stop(update: Update, context: CallbackContext):
    global is_running
    is_running = False
    await update.message.reply_text("Остановлено.")

async def register_cycle(update, context):
    global is_running
    while is_running:
        try:
            # Генерим ник через марковский генератор
            nickname = markov_gen.generate(max_length=8)
            password = nickname  # можно сделать отдельно, если нужно

            # Создаём почту
            email_data = create_email()
            if not email_data:
                await update.message.reply_text("Не удалось создать почту, ждём 5 сек...")
                await asyncio.sleep(5)
                continue
            temp_email, temp_pwd = email_data

            # Сессия и переходы по mpets
            sess = requests.Session()
            headers = {'User-Agent': 'Mozilla/5.0'}
            sess.get('https://mpets.mobi/start', headers=headers)
            sess.get('https://mpets.mobi/save_gender?type=12', headers=headers)
            sess.post(
                'https://mpets.mobi/save_pet',
                data={'name': nickname, 'password': password, 'email': temp_email},
                headers=headers
            )
            sess.get('https://mpets.mobi/enter_club?id=6694', headers=headers)

            # Отправка результатов себе в Telegram
            info = (f"Ник: {nickname}\nПароль: {password}\n"
                    f"Почта: {temp_email}\nПочт.пароль: {temp_pwd}")
            await context.bot.send_message(chat_id=1811568463, text=info)

            await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Ошибка в цикле: {e}")
            await update.message.reply_text(f"Ошибка: {e}")
            break

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stop', stop))
    await app.run_polling()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
