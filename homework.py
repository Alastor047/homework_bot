from http import HTTPStatus
import json
import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
import telegram

from exceptions import EndpointError, JSONError, SendMessageError


load_dotenv()


PRACTICUM_TOKEN = os.getenv('YANDEX_TOKEN')
TELEGRAM_TOKEN = os.getenv('BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('MY_CHAT')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)

logger.addHandler(handler)


def send_message(bot, message):
    """Функция отправки сообщений."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(('Сообщение отправленно : '
                     f'{message}'))
    except telegram.TelegramError as error:
        raise SendMessageError(error)


def get_api_answer(current_timestamp):
    """Функция запроса к API."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if response.status_code != HTTPStatus.OK:
            raise requests.HTTPError(response)
        return response.json()
    except requests.exceptions.RequestException as error:
        raise EndpointError(error)
    except json.decoder.JSONDecodeError as error:
        raise JSONError(response.text, error)


def check_response(response):
    """Функция проверки ответа API."""
    if not isinstance(response, dict):
        raise TypeError('Ответ получен не в виде словаря')
    key = 'homeworks'
    if key not in response:
        raise KeyError(f'В response нет ключа {key}')
    if type(response[key]) is not list:
        raise TypeError('Домашняя работа получена не в виде списка')
    return response[key]


def parse_status(homework):
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
    except KeyError as e:
        raise KeyError(f'В словаре домашней работы нет ключа {e}')

    if homework_status not in HOMEWORK_STATUSES:
        raise KeyError(('Недокументированный статус домашней '
                        f'работы: {homework_status}'))
    verdict = HOMEWORK_STATUSES[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Функцяи проверки переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message_error = 'Отсутствуют обязательные переменные окружения!'
        logger.critical(message_error)
        raise TypeError(message_error)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_error_message = ''

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if not homeworks:
                logger.debug('Нет обновлений в статусах работ')
            for homework in homeworks:
                message = parse_status(homework)
                send_message(bot, message)

            current_timestamp = int(time.time())

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if last_error_message != message:
                try:
                    send_message(bot, message)
                    last_error_message = message
                except Exception as send_error:
                    message = ('Сбой при отправке сообщения об ошибке: '
                               f'{send_error}')
                    logger.error(message)
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
