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

def initiate_charge(user_phone: str, amount_ghs: float, email: str = "user@sikaswift.com"):
    """
    Triggers the USSD prompt on the User's phone.
    """
    amount_kobo = int(amount_ghs * 100) 

    # Simple network detection
    network = "mtn" 
    if user_phone.startswith("020") or user_phone.startswith("050"):
        network = "vod"
    elif user_phone.startswith("027") or user_phone.startswith("057"):
        network = "tgo"

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
    """
    If Paystack asks for an OTP, we send it back here.
    """
    url = f"{BASE_URL}/charge/submit_otp"
    payload = {
        "otp": otp_code,
        "reference": reference
    }
    try:
        req = requests.post(url, json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}