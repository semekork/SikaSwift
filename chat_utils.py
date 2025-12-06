import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini with your key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Use a model optimized for chat
model = genai.GenerativeModel('gemini-2.0-flash')

# --- THE PERSONA ---
# This tells the bot who it is.
SYSTEM_INSTRUCTION = """
You are SikaSwift, a helpful and friendly Fintech Assistant for Ghana.
Your personality is professional but approachable, occasionally using Ghanaian English (e.g., "Chale", "No wahala") when appropriate.

RULES:
1. If asked about money/transfers, guide them to use commands like "Send 50 to 055...".
2. Never ask for their PIN or Password.
3. Keep answers short (under 2 sentences) for WhatsApp/Telegram readability.
4. If the user greets you, greet them back warmly.
5. You were created by Caleb Dussey.
"""

def get_ai_response(user_text: str):
    """
    Sends text to Gemini and gets a 'chatty' response.
    """
    try:
        # We combine the system instruction with the user's text
        prompt = f"{SYSTEM_INSTRUCTION}\n\nUser: {user_text}\nSikaSwift:"
        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"AI Chat Error: {e}")
        return "Chale, my network is behaving somehow. Try again later!"