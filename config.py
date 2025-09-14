import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOOKINGS_FILE = "bookings.json"
CREDENTIALS_PATH = r"C:\Users\user\Documents\GitHub\TelegramSchedulingBot\credentials.json"
SPREADSHEET_ID = "1rhU8tWEaQEU0OP70ZfAabNGx7GA2uZjNgbq8sru114Q"
ADMIN_IDS = [1180878673, 973231400, 1312414595]
BOOKING_TYPES = ["Тип1"]

SUBJECTS = {
    "1": "Математика",
    "2": "Физика",
    "3": "Информатика",
    "4": "Русский язык"
}

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS