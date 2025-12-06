import os
import hmac
import hashlib
import asyncio
import requests # Needed for chat action (typing status)
from fastapi import FastAPI, Request, Depends, HTTPException
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from dotenv import load_dotenv

# --- LOCAL IMPORTS ---
from database import init_db, get_session
from models import Transaction, User
from nlp import parse_message
from telegram_utils import (
    BASE_URL, # Imported for chat actions
    send_message, 
    send_photo, 
    send_name_confirmation, 
    request_phone_number, 
    delete_message_buttons,
    delete_message, 
    answer_callback
)
from paystack_utils import (
    initiate_charge, 
    submit_otp, 
    create_transfer_recipient, 
    initiate_transfer,
    resolve_mobile_money
)
from security_utils import hash_pin, verify_pin
from receipt_utils import generate_receipt
from qr_utils import generate_payment_qr
from chat_utils import get_ai_response  # <--- NEW IMPORT FOR CHAT

# --- CONFIG ---
load_dotenv()
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = "YOUR_ADMIN_ID_HERE" 

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan, title="SikaSwift Bot 🤖")

# =============================================================================
# 1. TELEGRAM WEBHOOK
# =============================================================================

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, session: Session = Depends(get_session)):
    data = await request.json()
    
    # --- A. HANDLE BUTTON CLICKS ---
    if "callback_query" in data:
        await handle_callback(data["callback_query"], session)
        return {"status": "ok"}
    
    # --- B. HANDLE MESSAGES ---
    if "message" in data:
        msg = data["message"]
        chat_id = str(msg["chat"]["id"])
        message_id = msg.get("message_id")
        
        # 1. CONTACT SHARING
        if "contact" in msg:
            phone = msg["contact"]["phone_number"].replace("+", "")
            user = session.get(User, chat_id)
            
            # Identity Verification (Reset PIN)
            if user and user.state == "AWAITING_RESET_AUTH":
                if user.phone_number == phone:
                    user.pin_hash = None
                    user.state = "AWAITING_NEW_PIN"
                    session.add(user)
                    session.commit()
                    send_message(chat_id, "✅ **Identity Verified!**\nEnter your **NEW 4-digit PIN**:")
                else:
                    user.state = "IDLE"
                    session.add(user)
                    session.commit()
                    send_message(chat_id, "❌ Number mismatch. Verification Failed.")
                return {"status": "ok"}
            
            # New Registration
            if not user:
                user = User(telegram_id=chat_id, phone_number=phone, state="IDLE")
                session.merge(user)
                session.commit()
                send_message(chat_id, "✅ Phone saved! **Type /setpin to secure your account.**")
                return {"status": "ok"}
            
        # 2. TEXT PROCESSING
        if "text" in msg:
            text = msg["text"].strip()
            user = session.get(User, chat_id)
            
            if user:
                # --- SECURITY: AUTO-DELETE PIN ---
                if user.state in ["AWAITING_NEW_PIN", "AWAITING_PIN_AUTH"] and len(text) == 4 and text.isdigit():
                    delete_message(chat_id, message_id)

                # --- STATE MACHINE ---
                
                # 1. SETTING PIN
                if user.state == "AWAITING_NEW_PIN":
                    if len(text) == 4 and text.isdigit():
                        user.pin_hash = hash_pin(text)
                        user.state = "IDLE"
                        session.add(user)
                        session.commit()
                        send_message(chat_id, "🔐 **PIN Set Successfully!**")
                    else:
                        send_message(chat_id, "❌ PIN must be 4 digits.")
                    return {"status": "ok"}

                # 2. VERIFYING PIN (PAYMENT)
                if user.state == "AWAITING_PIN_AUTH":
                    if verify_pin(text, user.pin_hash):
                        try:
                            amount, recipient = user.temp_data.split("|")
                            amount = float(amount)
                            user.state = "IDLE"
                            user.temp_data = None
                            session.add(user)
                            session.commit()
                            
                            send_message(chat_id, "🔓 **PIN Verified.** Processing payment...")
                            await execute_charge(chat_id, user, amount, recipient, session)
                        except:
                            send_message(chat_id, "❌ Error. Try again.")
                            user.state = "IDLE"
                            session.add(user)
                            session.commit()
                    else:
                        send_message(chat_id, "❌ **Wrong PIN.** Cancelled.")
                        user.state = "IDLE"
                        user.temp_data = None
                        session.add(user)
                        session.commit()
                    return {"status": "ok"}

                # 3. QR CODE: AMOUNT ENTRY
                if user.state == "AWAITING_QR_AMOUNT":
                    if text.replace('.', '', 1).isdigit():
                        amount = float(text)
                        recipient = user.temp_data
                        
                        user.state = "IDLE"
                        user.temp_data = None
                        session.add(user)
                        session.commit()
                        
                        verification = resolve_mobile_money(recipient)
                        name = verification["account_name"] if verification["status"] else "Unknown"
                        send_name_confirmation(chat_id, amount, recipient, name)
                    else:
                        send_message(chat_id, "❌ Invalid amount.")
                    return {"status": "ok"}

                # 4. WAITING FOR OTP (Legacy)
                statement = select(Transaction).where(
                    Transaction.sender_phone == user.phone_number,
                    Transaction.status == "WAITING_FOR_OTP"
                )
                pending_txn = session.exec(statement).first()
                if pending_txn:
                    await handle_otp_entry(chat_id, text, pending_txn, session)
                    return {"status": "ok"}

            # --- COMMANDS ---

            if text.startswith("/support"):
                complaint = text.replace("/support", "").strip()
                if not complaint:
                    send_message(chat_id, "⚠️ Usage: `/support My issue here`")
                else:
                    # Notify Admin
                    if ADMIN_ID != "YOUR_ADMIN_ID_HERE":
                        try: send_message(ADMIN_ID, f"🆘 **Ticket**\nUser: {chat_id}\nMsg: {complaint}")
                        except: pass
                    send_message(chat_id, "✅ Support request received.")
                return {"status": "ok"}

            if text == "/myqr":
                if not user:
                    send_message(chat_id, "Register first: /start")
                    return {"status": "ok"}
                qr_file = generate_payment_qr(user.phone_number)
                send_photo(chat_id, qr_file, caption=f"Scan to pay **{user.phone_number}**")
                try: os.remove(qr_file) 
                except: pass
                return {"status": "ok"}

            if text.startswith("/start pay_"):
                try:
                    target = text.split("pay_")[1]
                    if not user:
                        request_phone_number(chat_id)
                        return {"status": "ok"}
                    
                    verification = resolve_mobile_money(target)
                    name = verification["account_name"] if verification["status"] else "Unknown"
                    
                    user.state = "AWAITING_QR_AMOUNT"
                    user.temp_data = target
                    session.add(user)
                    session.commit()
                    
                    send_message(chat_id, f"✅ **Recipient:** {name}\n**Enter Amount:**")
                except:
                    send_message(chat_id, "❌ Invalid QR.")
                return {"status": "ok"}

            if text == "/start":
                send_message(chat_id, "👋 **Welcome to SikaSwift!**\n\n/setpin - Security\n/myqr - Receive Money\n/history - Transactions")
                return {"status": "ok"}
            
            if text == "/setpin":
                if not user: request_phone_number(chat_id)
                else:
                    user.state = "AWAITING_NEW_PIN"
                    session.add(user)
                    session.commit()
                    send_message(chat_id, "🔐 Enter **4-digit PIN**:")
                return {"status": "ok"}

            if text == "/resetpin":
                if not user: send_message(chat_id, "Register first.")
                else:
                    user.state = "AWAITING_RESET_AUTH"
                    session.add(user)
                    session.commit()
                    request_phone_number(chat_id) 
                    send_message(chat_id, "⚠️ **Security Check**\nTap 'Share Phone Number' below.")
                return {"status": "ok"}
            
            if text == "/history":
                if not user: return {"status": "ok"}
                statement = select(Transaction).where(Transaction.sender_phone == user.phone_number).order_by(Transaction.created_at.desc()).limit(5)
                txns = session.exec(statement).all()
                if not txns:
                    send_message(chat_id, "📭 No transactions found.")
                else:
                    msg = "📜 **Recent Transactions**\n\n"
                    for t in txns:
                        icon = "✅" if t.status in ["DISBURSING", "COMPLETE"] else "⏳"
                        msg += f"{icon} **{t.amount} GHS** → {t.recipient_phone}\n\n"
                    send_message(chat_id, msg)
                return {"status": "ok"}

            # --- INTELLIGENT ROUTING (NLP vs CHAT) ---
            nlp_result = parse_message(text)
            
            if nlp_result["intent"] == "SEND_MONEY":
                # --- FINANCIAL LOGIC ---
                if nlp_result["amount"] and nlp_result["recipient"]:
                    if not user:
                        request_phone_number(chat_id)
                        return {"status": "ok"}
                    
                    if not user.pin_hash:
                        send_message(chat_id, "⚠️ Set a PIN first: /setpin")
                        return {"status": "ok"}

                    send_message(chat_id, "🔍 Verifying recipient...")
                    verification = resolve_mobile_money(nlp_result["recipient"])
                    
                    if verification["status"]:
                        send_name_confirmation(chat_id, nlp_result["amount"], nlp_result["recipient"], verification["account_name"])
                    else:
                        send_message(chat_id, "⚠️ Could not verify name.")
                else:
                    send_message(chat_id, "Try: 'Send 50 to 055...'")
            
            else:
                # --- CONVERSATIONAL AI LOGIC ---
                # 1. Show 'Typing...' status
                try:
                    requests.post(f"{BASE_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
                except: pass
                
                # 2. Get AI Response
                ai_reply = get_ai_response(text)
                send_message(chat_id, ai_reply)

    return {"status": "ok"}

# =============================================================================
# 2. HELPER FUNCTIONS
# =============================================================================

async def handle_callback(callback, session):
    chat_id = str(callback["message"]["chat"]["id"])
    message_id = callback["message"]["message_id"]
    callback_id = callback["id"]
    action_data = callback["data"]
    
    answer_callback(callback_id) 
    delete_message_buttons(chat_id, message_id)
    
    if action_data == "cancel":
        send_message(chat_id, "🚫 Cancelled.")
        return

    if action_data.startswith("pay_"):
        parts = action_data.split("_")
        amount = parts[1]
        recipient = parts[2]
        
        user = session.get(User, chat_id)
        if not user: return

        user.state = "AWAITING_PIN_AUTH"
        user.temp_data = f"{amount}|{recipient}"
        session.add(user)
        session.commit()
        
        send_message(chat_id, "🔒 **Security Check**\nEnter your **4-digit PIN**:")

async def execute_charge(chat_id, user, amount, recipient, session):
    send_message(chat_id, f"⏳ Authenticated. Prompt sent to {user.phone_number}...")
    
    response = initiate_charge(user.phone_number, amount)
    
    if response.get("status"):
        ref = response["data"]["reference"]
        p_status = response["data"].get("status")
        
        txn_status = "WAITING_FOR_OTP" if p_status == "send_otp" else "PENDING_DEBIT"
        msg = "🔐 **OTP Required!**" if p_status == "send_otp" else "✅ **Prompt Sent.** Approve on phone."

        new_txn = Transaction(
            telegram_chat_id=chat_id,
            sender_phone=user.phone_number,
            recipient_phone=recipient,
            amount=amount,
            status=txn_status,
            paystack_reference=ref
        )
        session.add(new_txn)
        session.commit()
        send_message(chat_id, msg)
    else:
        send_message(chat_id, f"❌ Charge Failed: {response.get('message')}")

async def handle_otp_entry(chat_id, otp_code, txn, session):
    send_message(chat_id, "🔄 Verifying OTP...")
    resp = submit_otp(txn.paystack_reference, otp_code)
    
    if resp.get("status"):
        txn.status = "DEBIT_SUCCESS"
        session.add(txn)
        session.commit()
        send_message(chat_id, "✅ Verified! Processing transfer...")
    else:
        send_message(chat_id, f"❌ Wrong OTP.")

# =============================================================================
# 3. PAYSTACK WEBHOOK
# =============================================================================

@app.post("/webhook")
async def paystack_webhook(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not signature: return {"status": "denied"}
        
    hash_calc = hmac.new(PAYSTACK_SECRET.encode('utf-8'), body, hashlib.sha512).hexdigest()
    if hash_calc != signature: return {"status": "denied"}

    event_data = await request.json()
    event_type = event_data.get("event")
    data = event_data.get("data", {})
    
    if event_type == "charge.success":
        reference = data.get("reference")
        statement = select(Transaction).where(Transaction.paystack_reference == reference)
        txn = session.exec(statement).first()
        
        if txn and txn.status != "DISBURSING" and txn.status != "COMPLETE":
            txn.status = "DEBIT_SUCCESS"
            session.add(txn)
            session.commit()
            
            if txn.telegram_chat_id:
                send_message(txn.telegram_chat_id, f"✅ **Payment Received!**\nMoving money to recipient...")

            await asyncio.sleep(2)
            
            recip_resp = create_transfer_recipient("Verified User", txn.recipient_phone)
            
            if recip_resp.get("status"):
                r_code = recip_resp['data']['recipient_code']
                txn.transfer_code = r_code
                
                transfer_resp = initiate_transfer(txn.amount, r_code)
                
                if transfer_resp.get("status"):
                    txn.status = "DISBURSING"
                    if txn.telegram_chat_id:
                        receipt_file = generate_receipt(txn.sender_phone, txn.recipient_phone, txn.amount, txn.paystack_reference)
                        send_photo(txn.telegram_chat_id, receipt_file, caption="✅ **Transfer Complete!**")
                        try: os.remove(receipt_file)
                        except: pass
                else:
                    txn.status = "TRANSFER_FAILED"
                    if txn.telegram_chat_id:
                        send_message(txn.telegram_chat_id, f"⚠️ Debit Success, Transfer Failed: {transfer_resp.get('message')}")
            
            session.add(txn)
            session.commit()

    return {"status": "received"}