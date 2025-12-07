import os
import uuid
import httpx
import json
from dotenv import load_dotenv


load_dotenv()

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
BASE_URL = "https://api.paystack.co"

HEADERS = {
    "Authorization": f"Bearer {PAYSTACK_SECRET}",
    "Content-Type": "application/json"
}

NETWORK_CONFIG = {}

def load_network_config():
    """
    Loads network prefixes from networks.json into memory.
    """
    global NETWORK_CONFIG
    try:
        with open("networks.json", "r") as f:
            NETWORK_CONFIG = json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading networks.json: {e}")
        
    load_network_config()

def get_paystack_bank_code(phone: str) -> str:
    """
    Maps phone prefixes to Paystack's Bank Codes using networks.json.
    """
    p = phone.strip().replace("+233", "0")
    
    # Iterate through the loaded config
    for code, prefixes in NETWORK_CONFIG.items():
        if any(p.startswith(prefix) for prefix in prefixes):
            return code
        
    return "MTN"

async def resolve_mobile_money(phone: str):
    bank_code = get_paystack_bank_code(phone)
    url = f"{BASE_URL}/bank/resolve"
    params = {"account_number": phone, "bank_code": bank_code}
    
    try:
        async with httpx.AsyncClient() as client:
            req = await client.get(url, params=params, headers=HEADERS)
        resp = req.json()
        
        if resp.get("status"):
            return {"status": True, "account_name": resp["data"]["account_name"]}
        else:
            return {"status": False, "message": "Could not verify name."}
    except Exception as e:
        return {"status": False, "message": str(e)}

async def initiate_charge(user_phone: str, amount_ghs: float, email: str = "user@sikaswift.com"):
    amount_kobo = int(amount_ghs * 100) 
    network = get_paystack_bank_code(user_phone).lower()

    payload = {
        "email": email,
        "amount": amount_kobo,
        "currency": "GHS",
        "mobile_money": {"phone": user_phone, "provider": network},
        "reference": f"txn_{uuid.uuid4()}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            req = await client.post(f"{BASE_URL}/charge", json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}

async def submit_otp(reference: str, otp_code: str):
    url = f"{BASE_URL}/charge/submit_otp"
    payload = {"otp": otp_code, "reference": reference}
    try:
        async with httpx.AsyncClient() as client:
            req = await client.post(url, json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}

async def create_transfer_recipient(name: str, phone: str):
    bank_code = get_paystack_bank_code(phone)
    payload = {
        "type": "mobile_money",
        "name": name,
        "account_number": phone,
        "bank_code": bank_code, 
        "currency": "GHS"
    }
    try:
        async with httpx.AsyncClient() as client:
            req = await client.post(f"{BASE_URL}/transferrecipient", json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False}

async def initiate_transfer(amount_ghs: float, recipient_code: str):
    amount_kobo = int(amount_ghs * 100)
    payload = {
        "source": "balance", 
        "amount": amount_kobo,
        "recipient": recipient_code,
        "reason": "SikaSwift Transfer"
    }
    try:
        async with httpx.AsyncClient() as client:
            req = await client.post(f"{BASE_URL}/transfer", json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}

async def refund_charge(reference: str):
    """
    Async: Refunds a transaction back to the user.
    """
    url = f"{BASE_URL}/refund"
    payload = {"transaction": reference}
    
    try:
        async with httpx.AsyncClient() as client:
            req = await client.post(url, json=payload, headers=HEADERS)
        return req.json()
    except Exception as e:
        return {"status": False, "message": str(e)}