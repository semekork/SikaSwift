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
    # If text contains 'send', 'pay', 'transfer', we assume it's money related.
    if any(word in text for word in ["send", "pay", "transfer", "give"]):
        response["intent"] = "SEND_MONEY"
    
    # 2. EXTRACT AMOUNT (Look for numbers)
    # This regex finds numbers, even if they have decimals (e.g. 50.50)
    # It ignores "GHS" or "cedis"
    amount_match = re.search(r'(\d+(\.\d{2})?)', text)
    if amount_match:
        response["amount"] = float(amount_match.group(1))

    # 3. EXTRACT RECIPIENT (Look for Phone Numbers)
    # This regex looks for 10-digit numbers starting with 0 (Ghana format)
    # e.g., 0551234567 or 024...
    phone_match = re.search(r'(0\d{9})', text)
    if phone_match:
        response["recipient"] = phone_match.group(1)
        
    return response

# --- Quick Test Block (Runs only if you run this file directly) ---
if __name__ == "__main__":
    print(parse_message("Please send 50.50 cedis to 0555111222"))
    # Should print: {'intent': 'SEND_MONEY', 'amount': 50.5, 'recipient': '0555111222'...}