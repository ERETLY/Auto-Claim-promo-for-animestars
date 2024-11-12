import asyncio
import re
import os
import time
import random
import pickle
from collections import deque
from dotenv import load_dotenv
from pyrogram import Client
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Load environment variables
load_dotenv('config.env')

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')
TELEGRAM_CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

DISCORD_TOKEN = os.getenv('DISCORD_USER_TOKEN')
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
DISCORD_API_URL = f'https://discord.com/api/v9/channels/{DISCORD_CHANNEL_ID}/messages'

PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'false').lower() == 'true'
PROXY_URL = os.getenv('PROXY_URL')

# Cookie files
COOKIE_FILES = ['cookies.pkl', 'cookies1.pkl', 'cookies2.pkl']

app = Client("my_account", api_id=API_ID, api_hash=API_HASH, phone_number=PHONE_NUMBER)

last_telegram_message_id = 0
last_discord_message_id = None
is_first_telegram_check = True
is_first_discord_check = True

promo_queue = deque()

discord_headers = {
    'Authorization': DISCORD_TOKEN,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
    'Content-Type': 'application/json',
}

def extract_promo_code(message):
    promo_pattern = r'Промокод[:\s\*`]*([A-Z0-9-]+)'
    match = re.search(promo_pattern, message)
    return match.group(1) if match else None

def get_random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
    ]
    return random.choice(user_agents)

def use_promo_code(promo_code):
    for cookie_file_path in COOKIE_FILES:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"user-agent={get_random_user_agent()}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
         # Use a different port for ChromeDriver
        chrome_service = ChromeService(port=9516)  # You can change this port if needed
        
        driver = None
        try:
            driver = webdriver.Chrome(service=ChromeService(), options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print(f'Using promo code "{promo_code}" for cookie file: {cookie_file_path}')
            time.sleep(random.uniform(1, 3))
            
            driver.get('https://animestars.org/promo_codes/')
            driver.delete_all_cookies()

            with open(cookie_file_path, 'rb') as cookie_file:
                cookies = pickle.load(cookie_file)
                for cookie in cookies:
                    if 'expiry' in cookie:
                        del cookie['expiry']
                    driver.add_cookie(cookie)

            driver.get('https://animestars.org/promo_codes/')

            input_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#promo_code_input'))
            )
            
            for char in promo_code:
                input_field.send_keys(char)
                time.sleep(random.uniform(0.1, 0.3))

            print(f'Promo code "{promo_code}" entered.')

            button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '#promo_code_button'))
            )
            button.click()
            print('Clicked "Use" button.')

            time.sleep(random.uniform(1, 2))

        except Exception as e:
            print(f"Error using promo code with cookie {cookie_file_path}: {e}")
        finally:
            if driver:
                driver.quit()

async def process_promo_queue():
    while True:
        if promo_queue:
            promo_code = promo_queue.popleft()
            use_promo_code(promo_code)
        await asyncio.sleep(5)

async def check_telegram_messages():
    global last_telegram_message_id, is_first_telegram_check
    while True:
        try:
            async for message in app.get_chat_history(TELEGRAM_CHANNEL_USERNAME, limit=1):
                if message.id != last_telegram_message_id:
                    last_telegram_message_id = message.id

                    if is_first_telegram_check:
                        is_first_telegram_check = False
                        print("Skipped first Telegram message.")
                        continue

                    message_text = message.text or message.caption
                    if message_text:
                        promo_code = extract_promo_code(message_text)
                        if promo_code:
                            print(f"New Telegram promo code found: {promo_code}")
                            promo_queue.append(promo_code)
                        else:
                            print("No promo code found in new Telegram message.")
                    else:
                        print("No text found in Telegram message.")
        except Exception as e:
            print(f"Telegram error: {e}")

        await asyncio.sleep(10)

def check_discord_messages():
    global last_discord_message_id, is_first_discord_check
    
    proxies = None
    if PROXY_ENABLED and PROXY_URL:
        proxies = {'http': PROXY_URL, 'https': PROXY_URL}
    
    while True:
        try:
            response = requests.get(DISCORD_API_URL, headers=discord_headers, proxies=proxies)
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    latest_message = messages[0]
                    
                    if latest_message['id'] != last_discord_message_id:
                        last_discord_message_id = latest_message['id']

                        if is_first_discord_check:
                            is_first_discord_check = False
                            print("Skipped first Discord message.")
                            continue

                        promo_code = extract_promo_code(latest_message['content'])
                        if promo_code:
                            print(f"New Discord promo code found: {promo_code}")
                            promo_queue.append(promo_code)
                        else:
                            print("No promo code found in new Discord message.")
                else:
                    print("Failed to get Discord messages.")
            else:
                print(f"Discord API error: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"Discord error: {e}")

        time.sleep(10)

async def main():
    await app.start()
    print("Telegram client started")
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        telegram_task = asyncio.create_task(check_telegram_messages())
        discord_task = executor.submit(check_discord_messages)
        promo_queue_task = asyncio.create_task(process_promo_queue())
        
        await asyncio.gather(telegram_task, promo_queue_task)
        discord_task.result()

    await app.stop()

if __name__ == "__main__":
    app.run(main())
