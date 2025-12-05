import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id: str, text: str):
    """
    Sends a standard text message and removes any previous keyboards.
    """
    requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"remove_keyboard": True}
    })

def request_phone_number(chat_id: str):
    """
    Asks the user to share their contact. 
    Used for Registration AND Password Reset (Identity Proof).
    """
    payload = {
        "chat_id": chat_id,
        "text": "To proceed, I need to verify your identity.\n\nPlease tap the **'📱 Share Phone Number'** button below.",
        "parse_mode": "Markdown",
        "reply_markup": {
            "keyboard": [[{"text": "📱 Share Phone Number", "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True
        }
    }
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

def send_name_confirmation(chat_id: str, amount: float, phone: str, name: str):
    """
    Shows the verified name with [Pay] and [Cancel] buttons.
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
        f"Do you want to proceed?"
    )
    
    requests.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    })

def delete_message(chat_id: str, message_id: int):
    """
    Deletes a specific message.
    CRITICAL for Security: Used to hide the PIN immediately after the user types it.
    """
    url = f"{BASE_URL}/deleteMessage"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error deleting message: {e}")

def delete_message_buttons(chat_id: str, message_id: int):
    """
    Removes the inline buttons (Pay/Cancel) so they can't be clicked twice.
    """
    requests.post(f"{BASE_URL}/editMessageReplyMarkup", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": None 
    })

def answer_callback(callback_id: str):
    """
    Tells Telegram the button click was received (stops the loading spinner).
    """
    requests.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": callback_id})
    
def send_photo(chat_id: str, photo_path: str, caption: str = ""):
    """
    Uploads a local image file to Telegram.
    """
    url = f"{BASE_URL}/sendPhoto"
    
    # Open the file in binary mode
    with open(photo_path, "rb") as image_file:
        files = {"photo": image_file}
        data = {"chat_id": chat_id, "caption": caption}
        
        try:
            requests.post(url, data=data, files=files)
        except Exception as e:
            print(f"Failed to send photo: {e}")