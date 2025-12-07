import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

async def send_message(chat_id: str, text: str):
    """
    Async: Sends a standard text message.
    """
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {"remove_keyboard": True}
        })

async def request_phone_number(chat_id: str):
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
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE_URL}/sendMessage", json=payload)

async def send_name_confirmation(chat_id: str, amount: float, phone: str, name: str):
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
    
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown",
            "reply_markup": keyboard
        })

async def delete_message(chat_id: str, message_id: int):
    url = f"{BASE_URL}/deleteMessage"
    payload = {"chat_id": chat_id, "message_id": message_id}
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload)
    except Exception as e:
        print(f"Error deleting message: {e}")

async def delete_message_buttons(chat_id: str, message_id: int):
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE_URL}/editMessageReplyMarkup", json={
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": None 
        })

async def answer_callback(callback_id: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE_URL}/answerCallbackQuery", json={"callback_query_id": callback_id})
    
async def send_photo(chat_id: str, photo_path: str, caption: str = ""):
    url = f"{BASE_URL}/sendPhoto"
    
    # httpx handles files differently than requests
    try:
        async with httpx.AsyncClient() as client:
            with open(photo_path, "rb") as f:
                # We read the file into memory or stream it
                files = {"photo": f}
                data = {"chat_id": chat_id, "caption": caption}
                await client.post(url, data=data, files=files)
    except Exception as e:
        print(f"Failed to send photo: {e}")