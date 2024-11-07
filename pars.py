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
from pyrogram import Client, filters

locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables from config.env file
load_dotenv('config.env')

# Configuration variables
TOKEN = os.getenv('DISCORD_USER_TOKEN')  # Personal Discord token
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
API_URL = f'https://discord.com/api/v9/channels/{CHANNEL_ID}/messages'

# Telegram API authentication data
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')

# Array of cookie files for accounts
COOKIE_FILES = ['cookies.pkl', 'cookies1.pkl', 'cookies2.pkl']

# Flag to skip the first message
is_first_check = True
last_message_id = None
last_message_id_tg = 0

headers = {
    'Authorization': TOKEN,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
    'Content-Type': 'application/json',
}

# Function to extract promo code from message
def extract_promo_code(message):
    promo_pattern = r'Промокод[:\s\*`]*([A-Z0-9-]+)'
    match = re.search(promo_pattern, message)
    if match:
        return match.group(1)
    return None

# Function to use promo code
def use_promo_code(promo_code):
    for cookie_file_path in COOKIE_FILES:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        # Create web driver
        driver = webdriver.Chrome(service=ChromeService(), options=chrome_options)

        try:
            print(f'Using a promocode "{promo_code}" for cookie file: {cookie_file_path}')

            driver.get('https://animestars.org/promo_codes/')
            driver.delete_all_cookies()

            # Load cookies from file
            with open(cookie_file_path, 'rb') as cookie_file:
                cookies = pickle.load(cookie_file)
                for cookie in cookies:
                    if 'expiry' in cookie:
                        del cookie['expiry']
                    driver.add_cookie(cookie)

            # Reload page with set cookies
            driver.get('https://animestars.org/promo_codes/')

            # Enter promo code
            driver.find_element(By.CSS_SELECTOR, '#promo_code_input').send_keys(promo_code)
            print(f'Promocode "{promo_code}" inserted into the field.')

            # Click "Use" button
            driver.find_element(By.CSS_SELECTOR, '#promo_code_button').click()
            print('Clicked on the "Use" button".')

            # Wait 1 second before taking screenshot
            time.sleep(1)

            # Save screenshot
            screenshot_filename = f'screenshot_{promo_code}.png'
            driver.save_screenshot(screenshot_filename)
            print(f'Screenshot saved as {screenshot_filename}.')
            
        except Exception as e:
            print(f"Error when using a promoode with cookies {cookie_file_path}: {e}")
        finally:
            driver.quit()

# Main function to check for new messages in Discord
async def check_new_messages_discord():
    global last_message_id, is_first_check
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Get the latest message from the channel
                response = await client.get(API_URL, headers=headers)
                if response.status_code == 200:
                    messages = response.json()
                    if messages:
                        latest_message = messages[0]  # Most recent message

                        # Check if we've already processed this message
                        if latest_message['id'] != last_message_id:
                            last_message_id = latest_message['id']  # Update last message ID

                            # Skip the first message
                            if is_first_check:
                                is_first_check = False
                                print("The first message for initialization was missed.")
                                continue

                            # Extract promo code
                            promo_code = extract_promo_code(latest_message['content'])
                            if promo_code:
                                print(f"Found a new promocode from Discord: {promo_code}")
                                # Use promo code
                                use_promo_code(promo_code)
                            else:
                                print("Promocode not found in new message.")
                else:
                    print(f"Error when requesting to API: {response.status_code} - {response.text}")

            except Exception as e:
                print(f"Error in Discord listener: {e}")

            # Wait before next request
            await asyncio.sleep(30)  # 30 seconds

# Main function to check for new messages in Telegram
async def check_new_messages_telegram():
    global last_message_id_tg
    app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

    @app.on_message(filters.chat(CHANNEL_USERNAME))
    async def handle_message(client, message):
        global last_message_id_tg
        # Check if we've already processed this message
        if message.id != last_message_id_tg:
            last_message_id_tg = message.id  # Update last message ID
            # Try to extract promo code
            promo_code = extract_promo_code(message.text)
            if promo_code:
                print(f"Found a new promocode from Telegram: {promo_code}")
                # Use promo code
                use_promo_code(promo_code)
            else:
                print("Promocode not found in new message.")

    await app.start()
    print("Telegram listener started")
    await app.idle()

def run_discord_listener():
    asyncio.run(check_new_messages_discord())

def run_telegram_listener():
    asyncio.run(check_new_messages_telegram())

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as executor:
        executor.submit(run_discord_listener)
        executor.submit(run_telegram_listener)
