import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
API_KEY = os.getenv("GOOGLE_API_KEY")
USE_AI = False

if API_KEY:
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
        USE_AI = True
    except:
        pass

SYSTEM_PROMPT = """
You are a financial parsing engine. Extract transaction details.
The user may speak English, Pidgin, or Twi. You can respond with Pidgin or Twi if needed.
The user can request to send money using phrases like "Send", "Pay", "Transfer", "Dash", "Fa", "Tua", "Koma", etc.
The user cannot send coins.
Handle suffixes like 'k' (thousand) and 'm' (million).

Return ONLY raw JSON. Keys: 
- "intent": "SEND_MONEY", "UNKNOWN"
- "amount": Float or null
- "recipient": String (10 digit phone) or null

Examples:
- "Send 1k to 0555111222" -> {"intent": "SEND_MONEY", "amount": 1000.0, "recipient": "0555111222"}
- "Have 2.5m for 0244..." -> {"intent": "SEND_MONEY", "amount": 2500000.0, "recipient": "0244..."}
"""

def parse_message(text: str):
    if USE_AI:
        try:
            return parse_message_ai(text)
        except Exception as e:
            print(f"AI Error: {e}, using offline mode.")
            return parse_message_offline(text)
    else:
        return parse_message_offline(text)

def parse_message_ai(text: str):
    response = model.generate_content(f"{SYSTEM_PROMPT}\nInput: {text}")
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean_text)

def parse_message_offline(text: str):
    """
    Robust parser that handles '1k', '1m' and implicit commands.
    """
    text = text.lower().strip()
    
    response = {
        "intent": "UNKNOWN",
        "amount": None,
        "recipient": None,
        "raw_text": text
    }

    # 1. EXTRACT RECIPIENT (Phone Number)
    # 10 digits starting with 0
    phone_match = re.search(r'\b(0\d{9})\b', text)
    if phone_match:
        response["recipient"] = phone_match.group(1)
        # Remove phone from text so it doesn't look like an amount
        text = text.replace(response["recipient"], "")

    # 2. EXTRACT AMOUNT (Handles 1k, 1.5m, 500)
    # Regex explanation:
    # (\d+(\.\d+)?)  -> Captures the number (integer or decimal)
    # \s* -> Allows optional space (e.g., "1 k")
    # ([kmb])?       -> Optional suffix (k=thousand, m=million, b=billion)
    # \b             -> Word boundary to avoid matching "1km" (distance) if needed, 
    #                   but for fintech "1k" is usually money.
    
    amount_match = re.search(r'(\d+(\.\d+)?)\s*([kmb])?\b', text)
    
    if amount_match:
        val = float(amount_match.group(1))
        suffix = amount_match.group(3) # This will be 'k', 'm', 'b', or None
        
        if suffix == 'k':
            val *= 1_000
        elif suffix == 'm':
            val *= 1_000_000
        elif suffix == 'b':
            val *= 1_000_000_000
            
        if val > 0:
            response["amount"] = val

    # 3. DETERMINE INTENT
    keywords = [
        "send", "pay", "transfer", "give", "dash", "fa", "tua", "koma", 
        "have", "take", "for"
    ]
    
    if any(w in text for w in keywords):
        response["intent"] = "SEND_MONEY"
    
    # Smart Fallback: Amount + Recipient = Send
    if response["amount"] and response["recipient"] and response["intent"] == "UNKNOWN":
        response["intent"] = "SEND_MONEY"
    
    if response["intent"] == "UNKNOWN":
        response["intent"] = "CHAT"

    return response


    print(parse_message("Send 1.5k to 0555111222"))
    # Output: {'intent': 'SEND_MONEY', 'amount': 1500.0, ...}