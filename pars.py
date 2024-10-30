import os
import re
import httpx
import time
import threading
import asyncio
import pickle
import locale
import sys
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from telethon import TelegramClient
from telethon.sync import events

locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
sys.stdout.reconfigure(encoding='utf-8')

# Загрузка переменных окружения из файла config.env
load_dotenv('config.env')

# Переменные конфигурации
TOKEN = os.getenv('DISCORD_USER_TOKEN')  # Личный токен Discord
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
API_URL = f'https://discord.com/api/v9/channels/{CHANNEL_ID}/messages'

# Данные для аутентификации в Telegram API
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

# Массив файлов куки для аккаунтов
COOKIE_FILES = ['cookies.pkl', 'cookies1.pkl', 'cookies2.pkl']

# Флаг для пропуска первого сообщения
is_first_check = True
last_message_id = None
last_message_id_tg = 0

headers = {
    'Authorization': TOKEN,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
    'Content-Type': 'application/json',
}

# Функция для извлечения промокода из сообщения
def extract_promo_code(message):
    promo_pattern = r'Промокод[:\s\*`]*([A-Z0-9-]+)'
    match = re.search(promo_pattern, message)
    if match:
        return match.group(1)
    return None

# Функция для использования промокода
def use_promo_code(promo_code):
    for cookie_file_path in COOKIE_FILES:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Создание веб-драйвера
        driver = webdriver.Chrome(service=ChromeService(), options=chrome_options)

        try:
            print(f'Using a promocode "{promo_code}" for cookie file: {cookie_file_path}')

            driver.get('https://animestars.org/promo_codes/')
            driver.delete_all_cookies()

            # Загрузка куки из файла
            with open(cookie_file_path, 'rb') as cookie_file:
                cookies = pickle.load(cookie_file)
                for cookie in cookies:
                    if 'expiry' in cookie:
                        del cookie['expiry']
                    driver.add_cookie(cookie)

            # Перезагрузка страницы с установленными куками
            driver.get('https://animestars.org/promo_codes/')

            # Ввод промокода
            driver.find_element(By.CSS_SELECTOR, '#promo_code_input').send_keys(promo_code)
            print(f'Promocode "{promo_code}" inserted into the field.')

            # Нажимаем кнопку "Использовать"
            driver.find_element(By.CSS_SELECTOR, '#promo_code_button').click()
            print('Clicked on the "Use" button".')

            # Ждем 1 секунду перед созданием скриншота
            time.sleep(1)

            # Сохранение скриншота
            screenshot_filename = f'screenshot_{promo_code}.png'
            driver.save_screenshot(screenshot_filename)
            print(f'Screenshot saved as {screenshot_filename}.')
            
        except Exception as e:
            print(f"Error when using a promoode with cookies {cookie_file_path}: {e}")
        finally:
            driver.quit()

# Основная функция для проверки новых сообщений в Discord
async def check_new_messages_discord():
    global last_message_id, is_first_check
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Получаем последнее сообщение из канала
                response = await client.get(API_URL, headers=headers)
                if response.status_code == 200:
                    messages = response.json()
                    if messages:
                        latest_message = messages[0]  # Самое новое сообщение

                        # Проверка, не обрабатывали ли мы это сообщение
                        if latest_message['id'] != last_message_id:
                            last_message_id = latest_message['id']  # Обновляем ID последнего сообщения

                            # Пропускаем первое сообщение
                            if is_first_check:
                                is_first_check = False
                                print("The first message for initialization was missed.")
                                continue

                            # Извлечение промокода
                            promo_code = extract_promo_code(latest_message['content'])
                            if promo_code:
                                print(f"Found a new promocode from Discord: {promo_code}")
                                # Используем промокод
                                use_promo_code(promo_code)
                            else:
                                print("Promocode not found in new message.")
                else:
                    print(f"Error when requesting to API: {response.status_code} - {response.text}")

            except Exception:
                  pass

            # Ожидание перед следующим запросом
            await asyncio.sleep(30)  # 30 секунд

# Основная функция для проверки новых сообщений в Telegram
async def check_new_messages_telegram():
    global last_message_id_tg
    client = TelegramClient('session', API_ID, API_HASH)

    async with client:
        @client.on(events.NewMessage(chats=CHANNEL_USERNAME))
        async def handler(event):
            global last_message_id_tg
            # Проверяем, не обрабатывали ли мы уже это сообщение
            if event.id != last_message_id_tg:
                last_message_id_tg = event.id # Обновляем ID последнего сообщения
                # Попытка извлечь промокод
                promo_code = extract_promo_code(event.message.message)
                if promo_code:
                    print(f"Found a new promocode from Telegram: {promo_code}")
                    # Используем промокод
                    use_promo_code(promo_code)
                else:
                    print("Promocode not found in new message.")

        await client.run_until_disconnected()

def run_discord_listener():
    asyncio.run(check_new_messages_discord())

def run_telegram_listener():
    asyncio.run(check_new_messages_telegram())

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as executor:
        executor.submit(run_discord_listener)
        executor.submit(run_telegram_listener)
