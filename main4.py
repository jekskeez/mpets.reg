import logging
import random
import string
import requests
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from threading import Thread
import asyncio
import nest_asyncio
from faker import Faker

# Инициализация логирования
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация клиента для работы с Mail.tm
mail_client = None  # Отсутствует реальная инициализация, но это не влияет на основную логику

# Создаем объект Faker для генерации русских данных
fake = Faker('ru_RU')

# Переменная для отслеживания состояния цикла
is_running = False  # Инициализация переменной

# Функция для получения токена из файла
def get_token_from_file():
    try:
        with open('token.txt', 'r') as file:
            # Чтение первой строки и извлечение токена
            token_line = file.readline().strip()
            if token_line.startswith('token ='):
                token = token_line.split('=')[1].strip()
                return token
            else:
                logger.error("Файл token.txt не содержит правильный формат токена.")
                return None
    except Exception as e:
        logger.error(f"Ошибка при чтении токена из файла: {e}")
        return None

# Получаем токен
TOKEN = get_token_from_file()
if TOKEN is None:
    raise ValueError("Токен не был получен. Проверьте файл token.txt.")

# Применяем nest_asyncio
nest_asyncio.apply()

# Ограничение запросов к API Mail.tm (8 запросов в минуту)
REQUEST_LIMIT = 8
TIME_WINDOW = 60  # Время в секундах (60 секунд = 1 минута)
request_count = 0
last_request_time = time.time()

def generate_mail(length=8):
    """Генерация случайного имени пользователя, которое будет использоваться для никнейма, пароля и пароля почты."""
    username_mail = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    logger.info(f"Сгенерировано имя пользователя: {username_mail}")
    return username_mail

def generate_username():
    """Генерация никнейма с русским именем и 5 случайными цифрами."""
    # Генерация случайного имени
    nickname = fake.first_name()
    
    # Генерация 5 случайных чисел
    random_numbers = ''.join(random.choices('0123456789', k=5))
    
    # Объединение имени с числами
    username = nickname + random_numbers
    
    # Ограничиваем длину до 12 символов (если нужно)
    username = username[:12]
    
    return username

def get_available_domains():
    """Получение списка доступных доменов с помощью API Mail.tm."""
    global request_count, last_request_time
    
    # Проверяем, не превысили ли мы лимит запросов за минуту
    current_time = time.time()
    if current_time - last_request_time < TIME_WINDOW and request_count >= REQUEST_LIMIT:
        # Ждем до конца минуты, чтобы не превышать лимит запросов
        sleep_time = TIME_WINDOW - (current_time - last_request_time)
        logger.info(f"Достигнут лимит запросов, спим {sleep_time:.2f} секунд.")
        time.sleep(sleep_time)

    try:
        response = requests.get("https://api.mail.tm/domains")
        request_count += 1
        last_request_time = time.time()  # Обновляем время последнего запроса
        
        if response.status_code == 200:
            data = response.json()
            domains = [domain['domain'] for domain in data['hydra:member']]
            logger.info(f"Получены домены: {domains}")
            return domains
        else:
            logger.error(f"Не удалось получить список доменов. Код ответа: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Ошибка при получении доменов: {e}")
        return []

def create_email():
    """Создание почты с помощью API Mail.tm."""
    global request_count, last_request_time
    
    # Проверяем, не превысили ли мы лимит запросов за минуту
    current_time = time.time()
    if current_time - last_request_time < TIME_WINDOW and request_count >= REQUEST_LIMIT:
        # Ждем до конца минуты, чтобы не превышать лимит запросов
        sleep_time = TIME_WINDOW - (current_time - last_request_time)
        logger.info(f"Достигнут лимит запросов, спим {sleep_time:.2f} секунд.")
        time.sleep(sleep_time)

    try:
        domains = get_available_domains()
        if not domains:
            logger.error("Список доменов пуст.")
            return None
        
        domain = domains[0]
        username_mail = generate_mail()
        address = f"{username_mail}@{domain}"
        password = generate_mail(12)

        # Данные для создания аккаунта
        payload = {
            "address": address,
            "password": password
        }

        response = requests.post("https://api.mail.tm/accounts", json=payload)
        request_count += 1
        last_request_time = time.time()  # Обновляем время последнего запроса
        
        if response.status_code == 201:
            logger.info(f"Почта успешно создана: {address}")
            return address, password
        elif response.status_code == 422:
            logger.error("Ошибка 422: Некорректные данные (например, имя пользователя или домен).")
        else:
            logger.error(f"Не удалось создать почту. Код ответа: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при создании почты: {e}")
        return None

async def start(update, context):
    """Обработчик команды /start.""" 
    global is_running
    is_running = True  # Запускаем цикл регистрации
    await update.message.reply_text("Регистрация началась!")
    await register_cycle(update, context)  # Передаем и update, и context

async def stop(update: Update, context: CallbackContext):
    """Остановка цикла регистрации"""
    global is_running
    is_running = False
    await update.message.reply_text("Цикл регистрации остановлен.")
    logger.info("Цикл регистрации остановлен.")

async def register_cycle(update, context):
    """Цикл регистрации аккаунтов"""
    global is_running
    while is_running:
        try:
            # Генерация одной строки для никнейма, пароля и пароля почты
            username = generate_username()

            # Создаем почту с тем же username
            email_data = create_email()
            if email_data is None:
                logger.warning("Не удалось создать почту, пробую снова...")
                await update.message.reply_text("Не удалось создать почту, пробую снова...")
                await asyncio.sleep(5)  # Используем асинхронный sleep вместо time.sleep
                continue

            temp_email, temp_email_password = email_data

            # Переход по ссылке и заполнение формы
            session = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            # Шаг 1: Переход по ссылке mpets.mobi/start
            start_response = session.get('https://mpets.mobi/start', headers=headers)
            logger.info(f"Шаг 1: Переход по ссылке mpets.mobi/start. Статус: {start_response.status_code}")

            # Шаг 2: Переход по ссылке save_gender
            gender_response = session.get('https://mpets.mobi/save_gender?type=12', headers=headers)
            logger.info(f"Шаг 2: Переход по ссылке save_gender. Статус: {gender_response.status_code}")

            # Шаг 3: Переход по ссылке save для ввода данных с параметрами в URL
            nickname = username
            password = username  # Пароль такой же как и никнейм

            save_url = f'https://mpets.mobi/save_pet'

            save_data = {
                'name': nickname,  # Переменная nickname
                'password': password,  # Переменная password
                'email': temp_email  # Переменная temp_email
            }
            
            saving_response = session.post(save_url, data=save_data, headers=headers)
            logger.info(f"Шаг 3: Переход по ссылке save_pet. Статус: {saving_response.status_code}")

            # Шаг 4: Отправка данных в Telegram по user_id
            user_data = f"Никнейм: {nickname}\nПароль: {password}\nПочта: {temp_email}\nПароль почты: {temp_email_password}"
            logger.info(f"Шаг 4: Отправка данных в Telegram: {user_data}")
            await context.bot.send_message(chat_id=1811568463, text=user_data)

            # Шаг 5: Переход по ссылке enter_club
            club_response = session.get('https://mpets.mobi/enter_club?id=6694', headers=headers)
            logger.info(f"Шаг 5: Переход по ссылке enter_club. Статус: {club_response.status_code}")

            # Пауза между регистрациями (например, 10 секунд)
            await asyncio.sleep(10)  # Используем асинхронный sleep

        except Exception as e:
            logger.error(f"Ошибка при регистрации: {str(e)}")
            await update.message.reply_text(f"Ошибка: {str(e)}")
            break

async def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))

    # Запуск бота
    await application.run_polling()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
