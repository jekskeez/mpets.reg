import logging
import random
import string
import requests
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from threading import Thread
from pymailtm import MailTm
import asyncio
import nest_asyncio

# Инициализация клиента для работы с Mail.tm
mail_client = MailTm()

# Токен, полученный через BotFather
TOKEN = '7782933862:AAHpwHk04nZVoAu9IlwTEJLxh_ob6pLiKHQ'

# Для хранения состояния (активен ли цикл)
is_running = False

# Применяем nest_asyncio
nest_asyncio.apply()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_username(length=8):
    """Генерация случайного имени пользователя."""
    username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    logger.info(f"Сгенерировано имя пользователя: {username}")
    return username


def get_available_domains():
    """Получение списка доступных доменов с помощью API Mail.tm."""
    try:
        response = requests.get("https://api.mail.tm/domains")
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
    try:
        domains = get_available_domains()
        if not domains:
            logger.error("Список доменов пуст.")
            return None
        
        domain = domains[0]
        username = generate_username()
        address = f"{username}@{domain}"
        password = generate_username(12)

        # Данные для создания аккаунта
        payload = {
            "address": address,
            "password": password
        }

        response = requests.post("https://api.mail.tm/accounts", json=payload)
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


async def start(update: Update, context: CallbackContext):
    """Запуск цикла регистрации"""
    global is_running
    if not is_running:
        is_running = True
        await update.message.reply_text("Цикл регистрации начался!")
        logger.info("Цикл регистрации начался")
        thread = Thread(target=register_cycle, args=(update, context))
        thread.start()
    else:
        await update.message.reply_text("Цикл уже запущен.")


async def stop(update: Update, context: CallbackContext):
    """Остановка цикла регистрации"""
    global is_running
    is_running = False
    await update.message.reply_text("Цикл регистрации остановлен.")
    logger.info("Цикл регистрации остановлен.")


def register_cycle(update: Update, context: CallbackContext):
    """Цикл регистрации аккаунтов"""
    while is_running:
        try:
            # Создаем временную почту
            email_data = create_email()
            if email_data is None:
                logger.warning("Не удалось создать почту, пробую снова...")
                asyncio.run_coroutine_threadsafe(update.message.reply_text("Не удалось создать почту, пробую снова..."), asyncio.get_event_loop())
                time.sleep(5)
                continue

            temp_email, temp_email_password = email_data

            # Переход по ссылке и заполнение формы
            session = requests.Session()

            # Шаг 1: Переход по ссылке mpets.mobi/start
            start_response = session.get('https://mpets.mobi/start')
            logger.info(f"Шаг 1: Переход по ссылке mpets.mobi/start. Статус: {start_response.status_code}")

            # Шаг 2: Переход по ссылке save_gender
            gender_response = session.get('https://mpets.mobi/save_gender?type=12')
            logger.info(f"Шаг 2: Переход по ссылке save_gender. Статус: {gender_response.status_code}")

            # Шаг 3: Переход по ссылке save для ввода данных
            save_data_url = 'https://mpets.mobi/save'
            nickname = generate_username()
            password = generate_username(10)
            data = {
                'name': nickname,
                'password': password,
                'email': temp_email
            }
            save_response = session.post(save_data_url, data=data)
            logger.info(f"Шаг 3: Отправка данных на save. Статус: {save_response.status_code}")

            if save_response.status_code == 200:
                logger.info(f"Шаг 3: Данные успешно отправлены для {nickname}, {temp_email}")
            else:
                logger.error(f"Шаг 3: Ошибка отправки данных на save. Статус: {save_response.status_code}")

            # Шаг 4: Отправка данных в Telegram
            user_data = f"Никнейм: {nickname}\nПароль: {password}\nПочта: {temp_email}\nПароль почты: {temp_email_password}"
            logger.info(f"Шаг 4: Отправка данных в Telegram: {user_data}")
            asyncio.run_coroutine_threadsafe(update.message.reply_text(user_data), asyncio.get_event_loop())

            # Шаг 5: Переход по ссылке enter_club
            club_response = session.get('https://mpets.mobi/enter_club?id=6694')
            logger.info(f"Шаг 5: Переход по ссылке enter_club. Статус: {club_response.status_code}")

            # Пауза между регистрациями (например, 10 секунд)
            time.sleep(10)

        except Exception as e:
            logger.error(f"Ошибка при регистрации: {str(e)}")
            asyncio.run_coroutine_threadsafe(update.message.reply_text(f"Ошибка: {str(e)}"), asyncio.get_event_loop())
            break


async def main():
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))

    # Запуск бота
    await application.run_polling()


# Запускаем основной цикл бота
if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
