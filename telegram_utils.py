import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id: str, text: str):
    requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"remove_keyboard": True}
    })

def request_phone_number(chat_id: str):
    payload = {
        "chat_id": chat_id,
        "text": "To send money, I need your phone number. Click below to share it.",
        "reply_markup": {
            "keyboard": [[{"text": "📱 Share Phone Number", "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True
        }
    }
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_name_confirmation(chat_id: str, amount: float, phone: str, name: str):
    """
    Shows verified name to user.
    """
    keyboard = {
        "inline_keyboard": [
            [
                {"text": f"✅ Pay {name}", "callback_data": f"pay_{amount}_{phone}"},
                {"text": "❌ Cancel", "callback_data": "cancel"}
            ]
        ]
    }
    
    msg = (
        f"👤 **Recipient Found**\n\n"
        f"Name: **{name}**\n"
        f"Number: `{phone}`\n"
        f"Amount: **{amount} GHS**\n\n"
        f"Proceed?"
    )
    
    requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    })

def delete_message_buttons(chat_id: str, message_id: int):
    requests.post(f"{BASE_URL}/editMessageReplyMarkup", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": None 
    })

def answer_callback(callback_id: str):
    requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": callback_id})