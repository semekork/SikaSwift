import re

def parse_message(text: str):
    """
    Extracts intent, amount, and recipient from natural language.
    Example: "Send 50 to 0555123456"
    """
    text = text.lower().strip()
    
    response = {
        "intent": "UNKNOWN",
        "amount": None,
        "recipient": None,
        "raw_text": text
    }

    # 1. DETECT INTENT
    if any(word in text for word in ["send", "pay", "transfer", "give"]):
        response["intent"] = "SEND_MONEY"
    
    # 2. EXTRACT AMOUNT
    amount_match = re.search(r'(\d+(\.\d{2})?)', text)
    if amount_match:
        response["amount"] = float(amount_match.group(1))

    # 3. EXTRACT RECIPIENT
    # Looks for 10-digit numbers starting with 0
    phone_match = re.search(r'(0\d{9})', text)
    if phone_match:
        response["recipient"] = phone_match.group(1)
        
    return response