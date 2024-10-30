import os
import re
import httpx
import time
import threading
import asyncio
import pickle
import locale
import sys
import random
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telethon import TelegramClient
from telethon.sync import events
from telethon.sessions import StringSession

# Настройка локали и кодировки
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
sys.stdout.reconfigure(encoding='utf-8')

# Загрузка переменных окружения
load_dotenv('config.env')

# Конфигурация
TOKEN = os.getenv('DISCORD_USER_TOKEN')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
API_URL = f'https://discord.com/api/v9/channels/{CHANNEL_ID}/messages'
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')
COOKIE_FILES = ['cookies.pkl', 'cookies1.pkl', 'cookies2.pkl']

# Глобальные переменные
is_first_check = True
last_message_id = None
last_message_id_tg = 0

# Улучшенные заголовки с рандомизацией User-Agent
def get_random_user_agent():
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    ]
    return random.choice(user_agents)

def get_headers():
    return {
        'Authorization': TOKEN,
        'User-Agent': get_random_user_agent(),
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
    }

# Улучшенная функция извлечения промокода
def extract_promo_code(message):
    promo_patterns = [
        r'Промокод[:\s\*`]*([A-Z0-9-]+)',
    ]
    
    for pattern in promo_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

# Улучшенная функция использования промокода
def use_promo_code(promo_code):
    for cookie_file_path in COOKIE_FILES:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={get_random_user_agent()}")
        
        # Добавляем дополнительные опции для обхода обнаружения
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        driver = None
        try:
            driver = webdriver.Chrome(service=ChromeService(), options=chrome_options)
            
            # Подмена navigator.webdriver
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print(f'Использую промокод "{promo_code}" для файла куки: {cookie_file_path}')

            # Добавляем случайную задержку
            time.sleep(random.uniform(1, 3))
            
            driver.get('https://animestars.org/promo_codes/')
            driver.delete_all_cookies()

            # Загрузка куки
            with open(cookie_file_path, 'rb') as cookie_file:
                cookies = pickle.load(cookie_file)
                for cookie in cookies:
                    if 'expiry' in cookie:
                        del cookie['expiry']
                    driver.add_cookie(cookie)

            # Перезагрузка с куки
            driver.get('https://animestars.org/promo_codes/')

            # Ожидание появления поля ввода
            input_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#promo_code_input'))
            )
            
            # Имитация человеческого ввода
            for char in promo_code:
                input_field.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))

            print(f'Промокод "{promo_code}" введен в поле.')

            # Ожидание кнопки и клик
            button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '#promo_code_button'))
            )
            button.click()
            print('Нажата кнопка "Использовать".')

            time.sleep(random.uniform(1, 2))
            
        except Exception as e:
            print(f"Ошибка при использовании промокода с куки {cookie_file_path}: {e}")
        finally:
            if driver:
                driver.quit()

# Улучшенная функция проверки Discord
async def check_new_messages_discord():
    global last_message_id, is_first_check
    
    while True:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(API_URL, headers=get_headers())
                
                if response.status_code == 200:
                    messages = response.json()
                    if messages:
                        latest_message = messages[0]
                        
                        if latest_message['id'] != last_message_id:
                            last_message_id = latest_message['id']
                            
                            if is_first_check:
                                is_first_check = False
                                print("Пропущено первое сообщение для инициализации.")
                                continue

                            promo_code = extract_promo_code(latest_message['content'])
                            if promo_code:
                                print(f"Найден новый промокод из Discord: {promo_code}")
                                use_promo_code(promo_code)
                            else:
                                print("Промокод не найден в новом сообщении.")
                elif response.status_code == 429:  # Rate limit
                    retry_after = response.headers.get('Retry-After', 60)
                    print(f"Достигнут лимит запросов, ожидание {retry_after} секунд")
                    await asyncio.sleep(float(retry_after))
                else:
                    print(f"Ошибка при запросе к API: {response.status_code} - {response.text}")
                    await asyncio.sleep(60)  # Ожидание при ошибке

        except Exception as e:
            print(f"Ошибка в Discord checker: {e}")
            await asyncio.sleep(60)  # Ожидание при ошибке

        await asyncio.sleep(random.uniform(25, 35))  # Случайный интервал

# Улучшенная функция проверки Telegram
async def check_new_messages_telegram():
    global last_message_id_tg
    
    while True:
        try:
            # Используем StringSession для более стабильной работы
            session = StringSession()
            client = TelegramClient(session, API_ID, API_HASH)
            
            async with client:
                print("Telegram клиент запущен успешно")
                
                @client.on(events.NewMessage(chats=CHANNEL_USERNAME))
                async def handler(event):
                    global last_message_id_tg
                    try:
                        if event.id != last_message_id_tg:
                            last_message_id_tg = event.id
                            promo_code = extract_promo_code(event.message.message)
                            if promo_code:
                                print(f"Найден новый промокод из Telegram: {promo_code}")
                                use_promo_code(promo_code)
                            else:
                                print("Промокод не найден в новом сообщении.")
                    except Exception as e:
                        print(f"Ошибка в обработчике Telegram: {e}")

                await client.run_until_disconnected()
                
        except Exception as e:
            print(f"Ошибка в Telegram checker: {e}")
            await asyncio.sleep(60)  # Ожидание при ошибке
            continue

def run_discord_listener():
    while True:
        try:
            asyncio.run(check_new_messages_discord())
        except Exception as e:
            print(f"Ошибка в Discord listener: {e}")
            time.sleep(60)

def run_telegram_listener():
    while True:
        try:
            asyncio.run(check_new_messages_telegram())
        except Exception as e:
            print(f"Ошибка в Telegram listener: {e}")
            time.sleep(60)

if __name__ == "__main__":
    print("Запуск бота...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        executor.submit(run_discord_listener)
        executor.submit(run_telegram_listener)
