import os
import uuid
import requests
from dotenv import load_dotenv

load_dotenv()

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
BASE_URL = "https://api.paystack.co"

HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET}",
    "Content-Type": "application/json"
}

def get_paystack_bank_code(phone: str):
    """
    Maps phone prefixes to Paystack's specific Bank Codes for Ghana MoMo.
   
    """
    p = phone.strip()
    if p.startswith(("024", "054", "055", "059", "025", "053")):
        return "MTN"
    elif p.startswith(("020", "050")):
        return "VOD" # Vodafone/Telecel
    elif p.startswith(("027", "057", "026", "056")):
        return "ATL" # AirtelTigo
    return "MTN" # Default fallback

def resolve_mobile_money(phone: str):
    """
    Verifies the name on a Mobile Money number.
   
    """
    bank_code = get_paystack_bank_code(phone)
    url = f"{BASE_URL}/bank/resolve"
    
    params = {
        "account_number": phone,
        "bank_code": bank_code
    }
    
    try:
        req = requests.get(url, params=params, headers=HEADERS)
        resp = req.json()
        
        if resp.get("status"):
            return {
                "status": True, 
                "account_name": resp["data"]["account_name"]
            }
        else:
            return {"status": False, "message": "Could not verify name."}
    except Exception as e:
        return {"status": False, "message": str(e)}

def initiate_charge(user_phone: str, amount_ghs: float, email: str = "user@sikaswift.com"):
    """
    Step 1: Charge the Sender
    """
    amount_kobo = int(amount_ghs * 100) 
    network = get_paystack_bank_code(user_phone).lower() # charge api uses lowercase codes (mtn, vod)

    payload = {
        "email": email,
        "amount": amount_kobo,
        "currency": "GHS",
        "mobile_money": {
            "phone": user_phone,
            "provider": network
        },
        "reference": f"txn_{uuid.uuid4()}"
    }
    
    try:
        req = requests.post(f"{BASE_URL}/charge", json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}

def submit_otp(reference: str, otp_code: str):
    url = f"{BASE_URL}/charge/submit_otp"
    payload = {"otp": otp_code, "reference": reference}
    try:
        req = requests.post(url, json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}

def create_transfer_recipient(name: str, phone: str):
    """
    Step 2: Create a recipient code
    """
    bank_code = get_paystack_bank_code(phone)
    payload = {
        "type": "mobile_money",
        "name": name,
        "account_number": phone,
        "bank_code": bank_code, 
        "currency": "GHS"
    }
    try:
        req = requests.post(f"{BASE_URL}/transferrecipient", json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False}

def initiate_transfer(amount_ghs: float, recipient_code: str):
    """
    Step 3: Send money to recipient
    """
    amount_kobo = int(amount_ghs * 100)
    payload = {
        "source": "balance", 
        "amount": amount_kobo,
        "recipient": recipient_code,
        "reason": "SikaSwift Transfer"
    }
    try:
        req = requests.post(f"{BASE_URL}/transfer", json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}