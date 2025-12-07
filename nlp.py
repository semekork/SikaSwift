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

# --- UPDATED SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are a smart financial parsing engine. Extract transaction details from the 'Current Input'.
Use 'Chat History' to resolve missing details (e.g., if History has "Send 50" and Input is "To Mom", combine them).

The user may speak English, Pidgin, or Twi.
Handle suffixes: 'k' (thousand), 'm' (million).
Handle currencies: '$' or 'dollars' -> USD, '£' -> GBP, '€' -> EUR. Default to 'GHS' if unspecified.

Return ONLY raw JSON with these keys: 
- "intent": "SEND_MONEY", "SPLIT_BILL", "UNKNOWN"
- "amount": Float or null
- "currency": "GHS", "USD", "GBP", "EUR" (Default: "GHS")
- "recipient": String (Phone/Name) OR List of Strings (if intent is SPLIT_BILL) OR null

Examples:
1. Input: "Send $50 to Mom" 
   -> {"intent": "SEND_MONEY", "amount": 50.0, "currency": "USD", "recipient": "Mom"}

2. Input: "Split 100 cedis between Kofi and Ama" 
   -> {"intent": "SPLIT_BILL", "amount": 100.0, "currency": "GHS", "recipient": ["Kofi", "Ama"]}

3. History: ["User: Send 50", "Bot: To whom?"] -> Input: "To Mom" 
   -> {"intent": "SEND_MONEY", "amount": 50.0, "currency": "GHS", "recipient": "Mom"}
"""

def parse_message(text: str, history: list = []):
    """
    Parses user text. Now accepts 'history' (list of strings) for context.
    Example history: ["User: Send 50", "Bot: To whom?"]
    """
    if USE_AI:
        try:
            return parse_message_ai(text, history)
        except Exception as e:
            print(f"AI Error: {e}, using offline mode.")
            return parse_message_offline(text)
    else:
        return parse_message_offline(text)

def parse_message_ai(text: str, history: list):
    # Format history for the prompt
    context_str = "\n".join(history[-3:]) if history else "None"
    
    full_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Chat History:\n{context_str}\n\n"
        f"Current Input: {text}"
    )
    
    response = model.generate_content(full_prompt)
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(clean_text)
    except:
        return {"intent": "UNKNOWN", "amount": None, "currency": "GHS", "recipient": None}

def parse_message_offline(text: str):
    """
    Robust offline parser. Now detects basic currency.
    """
    text = text.lower().strip()
    
    response = {
        "intent": "UNKNOWN",
        "amount": None,
        "currency": "GHS",
        "recipient": None,
        "raw_text": text
    }

    # 1. EXTRACT RECIPIENT
    # A. Check for Phone Number (055...)
    phone_match = re.search(r'\b(0\d{9})\b', text)
    if phone_match:
        response["recipient"] = phone_match.group(1)
        text = text.replace(response["recipient"], "")
    
    # B. Check for Name (if no phone found)
    elif not response["recipient"]:
        name_match = re.search(r'(?:to|give|for|pay)\s+([a-zA-Z]+)', text)
        if name_match:
            response["recipient"] = name_match.group(1)

    # 2. EXTRACT AMOUNT & CURRENCY
    # Matches: $50, 50usd, 50ghs, 50 cedis
    amount_match = re.search(r'([$£€])?\s*(\d+(\.\d+)?)\s*([kmb])?\s*(usd|ghs|cedis|dollars)?', text)
    
    if amount_match:
        prefix_sym = amount_match.group(1)
        val = float(amount_match.group(2))
        suffix_kmb = amount_match.group(4)
        suffix_cur = amount_match.group(5)
        
        # Handle Multipliers
        if suffix_kmb == 'k': val *= 1_000
        elif suffix_kmb == 'm': val *= 1_000_000
        elif suffix_kmb == 'b': val *= 1_000_000_000
        
        # Handle Currency
        if prefix_sym == '$' or suffix_cur in ['usd', 'dollars']:
            response["currency"] = "USD"
        elif prefix_sym == '£':
            response["currency"] = "GBP"
        elif prefix_sym == '€':
            response["currency"] = "EUR"
        else:
            response["currency"] = "GHS"
            
        if val > 0:
            response["amount"] = val

    # 3. DETERMINE INTENT
    keywords = ["send", "pay", "transfer", "give", "dash", "fa", "tua", "koma", "have", "take", "for"]
    split_keywords = ["split", "divide", "share"]

    if any(w in text for w in split_keywords):
        response["intent"] = "SPLIT_BILL"
    elif any(w in text for w in keywords):
        response["intent"] = "SEND_MONEY"
    
    # Smart Fallback
    if response["amount"] and response["recipient"] and response["intent"] == "UNKNOWN":
        response["intent"] = "SEND_MONEY"

    return response