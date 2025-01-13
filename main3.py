import time
import random
import string
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from telegram import Bot
from telegram.ext import Updater, CommandHandler
from webdriver_manager.chrome import ChromeDriverManager

# Константы для ограничения запросов
TIME_WINDOW = 60  # в секундах
REQUEST_LIMIT = 10  # максимальное количество запросов за минуту
request_count = 0
last_request_time = 0

# Логгер
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Функции для работы с временной почтой
def get_available_domains():
    global request_count, last_request_time
    
    current_time = time.time()
    if current_time - last_request_time < TIME_WINDOW and request_count >= REQUEST_LIMIT:
        sleep_time = TIME_WINDOW - (current_time - last_request_time)
        logger.info(f"Достигнут лимит запросов, спим {sleep_time:.2f} секунд.")
        time.sleep(sleep_time)

    try:
        response = requests.get("https://api.mail.tm/domains")
        request_count += 1
        last_request_time = time.time()
        
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

def generate_username(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def create_email():
    global request_count, last_request_time
    
    current_time = time.time()
    if current_time - last_request_time < TIME_WINDOW and request_count >= REQUEST_LIMIT:
        sleep_time = TIME_WINDOW - (current_time - last_request_time)
        logger.info(f"Достигнут лимит запросов, спим {sleep_time:.2f} секунд.")
        time.sleep(sleep_time)

    try:
        domains = get_available_domains()
        if not domains:
            logger.error("Список доменов пуст.")
            return None
        
        domain = domains[0]
        username = generate_username()
        address = f"{username}@{domain}"
        password = generate_username(12)

        payload = {
            "address": address,
            "password": password
        }

        response = requests.post("https://api.mail.tm/accounts", json=payload)
        request_count += 1
        last_request_time = time.time()
        
        if response.status_code == 201:
            logger.info(f"Почта успешно создана: {address}")
            return address, password
        elif response.status_code == 422:
            logger.error("Ошибка 422: Некорректные данные.")
        else:
            logger.error(f"Не удалось создать почту. Код ответа: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при создании почты: {e}")
        return None

# Функция для регистрации аккаунта через Selenium
def register_account():
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Работает в фоновом режиме
    chrome_options.add_argument('--no-sandbox')  # Для работы в Docker/Colab
    chrome_options.add_argument('--disable-dev-shm-usage')  # Для Colab
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)

    try:
        # Переход по ссылке регистрации
        driver.get('https://mpets.mobi/start')
        time.sleep(2)
        
        driver.get('https://mpets.mobi/save_gender?type=12')
        time.sleep(2)
        
        # Генерация случайных данных
        nickname = generate_username()
        password = generate_username()
        temp_email, temp_email_password = create_email()

        if not temp_email:
            return None

        # Переход к форме регистрации
        driver.get(f'https://mpets.mobi/save?name={nickname}&password={password}&email={temp_email}')
        time.sleep(2)

        # Заполнение формы регистрации
        name_field = driver.find_element(By.NAME, 'name')
        password_field = driver.find_element(By.NAME, 'password')
        email_field = driver.find_element(By.NAME, 'email')

        name_field.send_keys(nickname)
        password_field.send_keys(password)
        email_field.send_keys(temp_email)
        
        # Нажатие на кнопку сохранить
        save_button = driver.find_element(By.XPATH, '//button[text()="Сохранить"]')
        save_button.click()
        time.sleep(2)

        # Возвращаем данные
        return nickname, password, temp_email, temp_email_password
    finally:
        driver.quit()

# Функция для отправки сообщения в Telegram
def send_telegram_message(chat_id, nickname, password, temp_email, temp_email_password):
    message = f"Никнейм: {nickname}\nПароль: {password}\nПочта: {temp_email}\nПароль от почты: {temp_email_password}"
    bot.send_message(chat_id=chat_id, text=message)

# Функция для чтения токена из файла
def read_token_from_file():
    try:
        with open("token.txt", "r") as file:
            # Читаем строку и извлекаем токен
            line = file.readline().strip()
            if line.startswith("token="):
                return line.split("=")[1]
            else:
                logger.error("Неверный формат токена в файле token.txt.")
                return None
    except Exception as e:
        logger.error(f"Ошибка при чтении токена из файла: {e}")
        return None

# Команда /start для начала регистрации
def start(update, context):
    chat_id = update.message.chat_id

    # Начинаем процесс регистрации
    result = register_account()

    if result:
        nickname, password, temp_email, temp_email_password = result

        # Отправляем данные в Telegram
        send_telegram_message(chat_id, nickname, password, temp_email, temp_email_password)

        # Переход по следующей ссылке
        requests.get('https://mpets.mobi/enter_club?id=6694')

        # Сообщение о завершении
        update.message.reply_text('Регистрация прошла успешно!')
    else:
        update.message.reply_text('Не удалось создать аккаунт.')

# Команда /stop для остановки работы
def stop(update, context):
    update.message.reply_text('Цикл регистрации остановлен.')

# Основная функция
def main():
    token = read_token_from_file()  # Читаем токен из файла

    if not token:
        logger.error("Токен не найден. Остановка работы бота.")
        return

    global bot
    bot = Bot(token=token)

    updater = Updater(token=token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('stop', stop))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
