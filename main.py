import logging
import random
import string
import requests
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
import asyncio
import nest_asyncio
import os

# ==== Марков-генератор слов (3-грам) ====
from collections import defaultdict, Counter

class MarkovWordGenerator:
    def __init__(self, seeds, n=3):
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
        return "".join(result).capitalize()

# Список seed-слов
SEEDS = [
    "Азирис", "Тутовка", "Тогол", "Баррель", "Всемирность", "Глиптодонт",
    "Минори", "Омежник", "Полевица", "Пирамидальный", "Светский",
    "Феокрит", "Лаконичный", "Кечкара", "Кельнер", "Бегин", "Канифас",
    "Сераинг", "Фанфарный", "Мишино", "Мутул", "Ивинг", "Беляк",
    "Мазелла", "Казеин", "Буффон", "Лаксум", "Водоотлив", "Адряс",
    "Вытва", "Шугурово", "Регтайм", "Завражье", "Трихалк", "Скочилов",
    "Кольяда", "Мутаген"
]
markov_gen = MarkovWordGenerator(SEEDS, n=3)

# ==== Конфиг и инициализация ====
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)
nest_asyncio.apply()

# Файл для хранения использованных ников
USED_FILE = 'used_nicks.txt'
if not os.path.exists(USED_FILE):
    open(USED_FILE, 'w', encoding='utf-8').close()

# Загружаем уже использованные ники в set
with open(USED_FILE, 'r', encoding='utf-8') as f:
    used_nicks = set(line.strip() for line in f if line.strip())

# Функция сохранения нового ника
def save_nick(nick):
    with open(USED_FILE, 'a', encoding='utf-8') as f:
        f.write(nick + '\n')
    used_nicks.add(nick)

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

# ==== Mail.tm лимиты ====
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
        return [d['domain'] for d in r.json().get('hydra:member', [])]
    except Exception as e:
        logger.error(f"Ошибка domains API: {e}")
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
        resp = requests.post(
            "https://api.mail.tm/accounts",
            json={"address": addr, "password": pwd}
        )
        global request_count, last_req
        request_count += 1
        last_req = time.time()
        if resp.status_code == 201:
            return addr, pwd
        else:
            logger.error(f"Mail.tm создаёт ошибку: {resp.status_code}")
    except Exception as e:
        logger.error(f"Mail.tm exception: {e}")
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
    chat_id = update.effective_chat.id

    while is_running:
        try:
            # 1) Генерим уникальный ник
            nickname = None
            for _ in range(10):  # до 10 попыток
                cand = markov_gen.generate(max_length=8)
                if len(cand) >= 4 and cand.isalpha() and cand not in used_nicks:
                    nickname = cand
                    break
            if not nickname:
                nickname = random.choice(SEEDS)
                if nickname in used_nicks:
                    await context.bot.send_message(chat_id=chat_id, text="Все seed-ники уже использованы!")
                    break
            save_nick(nickname)
            logger.info(f"Используем ник: {nickname}")
            password = "kaidomaks"

            # 2) Создаём временную почту
            email_data = create_email()
            if not email_data:
                await context.bot.send_message(chat_id=chat_id, text="Не удалось создать почту, ждём 10 сек...")
                await asyncio.sleep(10)
                continue
            temp_email, temp_pwd = email_data

            # 3) Регистрация на mpets
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

            # 4) Отправляем инфо в Telegram
            info = (
                f"Ник: {nickname}\nПароль: {password}\n"
                f"Почта: {temp_email}\nПочт.пароль: {temp_pwd}"
            )
            await context.bot.send_message(chat_id=chat_id, text=info)

            # 5) Пауза, чтобы не превысить лимит Mail.tm
            await asyncio.sleep(12)

        except Exception as e:
            logger.error(f"Ошибка в цикле регистрации: {e}")
            await context.bot.send_message(chat_id=chat_id, text=f"Ошибка: {e}")
            break

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('stop', stop))
    await app.run_polling()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
