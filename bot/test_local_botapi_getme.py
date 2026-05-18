import requests
import os

TOKEN = os.environ.get("BOT_TOKEN", "7069544338:AAFdAzmBTXbHDyOMTpdw3eciantmEwLbaMk")
API_URL = os.environ.get("LOCAL_BOT_API_URL", "http://telegram-bot-api:8081")

url = f"{API_URL}/bot{TOKEN}/getMe"
try:
    resp = requests.get(url, timeout=10)
    print(f"Status: {resp.status_code}")
    print(resp.text)
except Exception as e:
    print(f"Error: {e}")
