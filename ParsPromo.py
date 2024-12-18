import asyncio
import re
import os
import time
import random
import sys
import pickle
from collections import deque
from dotenv import load_dotenv
from pyrogram import Client
import aiohttp
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
from selenium.common.exceptions import WebDriverException
from pyrogram.errors import FloodWait

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

# Куки файлы
COOKIE_FILES = ['cookies.pkl']

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
    promo_patterns = [
        r'Промокод[:\s\*`]*([A-Z0-9-]+)',  # Original pattern
        r'Промоко[:\s\*`]*([A-Z0-9-]+)',   # Misspelled "Промокод"
        r'Промо[:\s\*`]*([A-Z0-9-]+)',     # Shortened "Промо"
        r'([A-Z0-9]{4}-[A-Z0-9]{4})',      # Pattern like Y088-GS22
        r'([A-Z0-9]{5}-[A-Z0-9]{5})',      # Pattern like 2Y088-GGS22
    ]
    
    for pattern in promo_patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    
    return None

def get_random_user_agent():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0"
    ]
    return random.choice(user_agents)

def use_promo_code(promo_code):
    max_retries = 3
    all_success = True

    for cookie_file_path in COOKIE_FILES:
        success_for_current_cookie = False  # Успешность для текущего файла куки

        for attempt in range(max_retries):
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"user-agent={get_random_user_agent()}")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            port = 8516 + random.randint(0, 400)  # Используем случайный порт
            chrome_service = ChromeService(port=port)
            
            driver = None
            try:
                driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
                driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                print(f'Using promo code "{promo_code}" for cookie file: {cookie_file_path}')
                time.sleep(1)
                
                with open(cookie_file_path, 'rb') as cookie_file:
                    cookies = pickle.load(cookie_file)
                
                driver.get('https://animestars.org/')
                for cookie in cookies:
                    if 'expiry' in cookie:
                        del cookie['expiry']
                    driver.add_cookie(cookie)
                
                driver.get('https://animestars.org/promo_codes/')
                print('Site opened with cookies')

                input_field = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '#promo_code_input'))
                )
                
                driver.execute_script("arguments[0].value = arguments[1];", input_field, promo_code)
                driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", input_field)

                print(f'Promo code "{promo_code}" entered.')

                button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, '#promo_code_button'))
                )
                
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                driver.execute_script("arguments[0].click();", button)
                print(f'Promo code "{promo_code}" successfully used (button clicked).')

                time.sleep(2)
                
                success_for_current_cookie = True
                break

            except WebDriverException as e:
                print(f"WebDriver error on attempt {attempt + 1} for {cookie_file_path}: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1} for {cookie_file_path}: {e}")
            finally:
                if driver:
                    driver.quit()
                    time.sleep(5)

        if not success_for_current_cookie:
            print(f"Failed to use promo code {promo_code} with cookie file {cookie_file_path}")
            all_success = False

    return all_success

async def process_promo_queue():
    while True:
        if promo_queue:
            promo_code = promo_queue.popleft()
            success = use_promo_code(promo_code)
            if not success:
                print(f"Failed to use promo code {promo_code} with all attempts. Adding back to queue.")
                promo_queue.append(promo_code)
        await asyncio.sleep(5)

async def check_telegram_messages():
    global last_telegram_message_id, is_first_telegram_check
    max_retries = 5
    retry_delay = 5

    while True:
        for attempt in range(max_retries):
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
                break
            except FloodWait as e:
                print(f"Flood wait error. Waiting for {e.x} seconds.")
                await asyncio.sleep(e.x)
            except Exception as e:
                print(f"Telegram error: {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    print("Max retries reached. Continuing to next iteration.")

        await asyncio.sleep(10)

async def check_discord_messages():
    global last_discord_message_id, is_first_discord_check
    max_retries = 5
    retry_delay = 5

    async with aiohttp.ClientSession() as session:
        while True:
            for attempt in range(max_retries):
                try:
                    async with session.get(DISCORD_API_URL, headers=discord_headers, proxy=PROXY_URL if PROXY_ENABLED else None) as response:
                        if response.status == 200:
                            messages = await response.json()
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
                            print(f"Discord API error: {response.status} - {await response.text()}")
                    break
                except aiohttp.ClientError as e:
                    print(f"Discord connection error: {e}")
                    if attempt < max_retries - 1:
                        print(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    else:
                        print("Max retries reached. Continuing to next iteration.")
                except Exception as e:
                    print(f"Unexpected error: {e}")
                    if attempt < max_retries - 1:
                        print(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    else:
                        print("Max retries reached. Continuing to next iteration.")

            await asyncio.sleep(15)

async def main(run_time):
    start = time.time()
    try:
        await app.start()
        
        telegram_task = asyncio.create_task(check_telegram_messages())
        discord_task = asyncio.create_task(check_discord_messages())
        promo_queue_task = asyncio.create_task(process_promo_queue())
        
        await asyncio.sleep(run_time)
        
        telegram_task.cancel()
        discord_task.cancel()
        promo_queue_task.cancel()
        
        await asyncio.gather(telegram_task, discord_task, promo_queue_task, return_exceptions=True)
    except Exception as e:
        print(f"Error in main: {e}")
    finally:
        if app.is_connected:
            await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    while True:
        current_time = datetime.now()
        next_restart_time = (current_time.replace(minute=58, second=0, microsecond=0) 
                             + timedelta(hours=1) if current_time.minute >= 58 else current_time.replace(minute=58, second=0, microsecond=0))
        time_to_wait = (next_restart_time - current_time).total_seconds()
        
        print(f"Starting the script at {current_time.strftime('%H:%M:%S')}...")
        
        try:
            loop.run_until_complete(main(time_to_wait))
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
        finally:
            if app.is_connected:
                print("Stopping Pyrogram client...")
                loop.run_until_complete(app.stop())

        print("Restarting script...")
