import os
import hmac
import hashlib
import asyncio
import requests
from fastapi import FastAPI, Request, Depends
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import init_db, get_session
from models import Transaction, User, Beneficiary # <--- Make sure Beneficiary is imported
from nlp import parse_message
from telegram_utils import (
    BASE_URL, send_message, send_photo, send_name_confirmation, 
    request_phone_number, delete_message_buttons, delete_message, answer_callback
)
from paystack_utils import (
    initiate_charge, submit_otp, create_transfer_recipient, 
    initiate_transfer, resolve_mobile_money
)
from security_utils import hash_pin, verify_pin
from receipt_utils import generate_receipt
from qr_utils import generate_payment_qr
from chat_utils import get_ai_response

load_dotenv()
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = "YOUR_ADMIN_ID"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan, title="SikaSwift Bot 🤖")

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, session: Session = Depends(get_session)):
    data = await request.json()
    
    if "callback_query" in data:
        await handle_callback(data["callback_query"], session)
        return {"status": "ok"}
    
    if "message" in data:
        msg = data["message"]
        chat_id = str(msg["chat"]["id"])
        message_id = msg.get("message_id")
        
        # 1. CONTACT SHARING
        if "contact" in msg:
            phone = msg["contact"]["phone_number"].replace("+", "")
            user = session.get(User, chat_id)
            
            if user and user.state == "AWAITING_RESET_AUTH":
                if user.phone_number == phone:
                    user.pin_hash = None
                    user.state = "AWAITING_NEW_PIN"
                    session.add(user)
                    session.commit()
                    send_message(chat_id, "✅ **Identity Verified!**\nEnter **NEW 4-digit PIN**:")
                else:
                    user.state = "IDLE"
                    session.add(user)
                    session.commit()
                    send_message(chat_id, "❌ Number mismatch.")
                return {"status": "ok"}
            
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
                # AUTO-DELETE PIN
                if user.state in ["AWAITING_NEW_PIN", "AWAITING_PIN_AUTH"] and len(text) == 4 and text.isdigit():
                    delete_message(chat_id, message_id)

                # STATE: SET PIN
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

                # STATE: VERIFY PIN (PAYMENT)
                if user.state == "AWAITING_PIN_AUTH":
                    if verify_pin(text, user.pin_hash):
                        try:
                            amount, recipient = user.temp_data.split("|")
                            amount = float(amount)
                            user.state = "IDLE"
                            user.temp_data = None
                            session.add(user)
                            session.commit()
                            
                            send_message(chat_id, "🔓 **PIN Verified.** Processing...")
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

                # STATE: QR AMOUNT
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
                
                # OTP CHECK
                statement = select(Transaction).where(Transaction.sender_phone == user.phone_number, Transaction.status == "WAITING_FOR_OTP")
                pending_txn = session.exec(statement).first()
                if pending_txn:
                    await handle_otp_entry(chat_id, text, pending_txn, session)
                    return {"status": "ok"}

            # --- COMMANDS ---

            # SAVE CONTACT
            if text.startswith("/save"):
                try:
                    parts = text.split()
                    if len(parts) != 3:
                        send_message(chat_id, "⚠️ Usage: `/save Mom 0555111222`")
                        return {"status": "ok"}
                    
                    name_alias = parts[1].lower()
                    number = parts[2]
                    
                    if not number.isdigit() or len(number) != 10:
                        send_message(chat_id, "❌ Invalid phone number.")
                        return {"status": "ok"}

                    contact = Beneficiary(user_id=chat_id, name=name_alias, phone_number=number)
                    session.add(contact)
                    session.commit()
                    send_message(chat_id, f"✅ Saved **{parts[1]}** ({number})")
                except:
                    send_message(chat_id, "❌ Error saving contact.")
                return {"status": "ok"}

            # LIST CONTACTS
            if text == "/contacts":
                contacts = session.exec(select(Beneficiary).where(Beneficiary.user_id == chat_id)).all()
                if not contacts:
                    send_message(chat_id, "📭 No contacts. Use `/save Mom 055...`")
                else:
                    msg = "📖 **My Contacts**\n\n"
                    for c in contacts:
                        msg += f"👤 **{c.name.title()}**: {c.phone_number}\n"
                    send_message(chat_id, msg)
                return {"status": "ok"}

            if text == "/start":
                send_message(chat_id, "👋 **Welcome!**\n\n/setpin\n/save [Name] [Number]\n/myqr\n/history")
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
            
            if text == "/myqr":
                if not user:
                    send_message(chat_id, "Register first.")
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

            # SEND MONEY LOGIC
            nlp_result = parse_message(text)
            if nlp_result["intent"] == "SEND_MONEY":
                if nlp_result["amount"] and nlp_result["recipient"]:
                    
                    # RESOLVE CONTACT VS NUMBER
                    recipient_input = nlp_result["recipient"]
                    final_number = None

                    if recipient_input.isdigit() and len(recipient_input) >= 10:
                        final_number = recipient_input
                    else:
                        # Lookup Name in DB
                        contact = session.exec(select(Beneficiary).where(Beneficiary.user_id == chat_id, Beneficiary.name == recipient_input.lower())).first()
                        if contact:
                            final_number = contact.phone_number
                            send_message(chat_id, f"📖 Found: **{contact.name.title()}** ({final_number})")
                        else:
                            send_message(chat_id, f"❌ Unknown contact '{recipient_input}'.\nUse `/save {recipient_input} 055...`")
                            return {"status": "ok"}

                    if not user:
                        request_phone_number(chat_id)
                        return {"status": "ok"}
                    
                    if not user.pin_hash:
                        send_message(chat_id, "⚠️ Set a PIN first: /setpin")
                        return {"status": "ok"}

                    send_message(chat_id, "🔍 Verifying recipient...")
                    verification = resolve_mobile_money(final_number)
                    
                    if verification["status"]:
                        send_name_confirmation(chat_id, nlp_result["amount"], final_number, verification["account_name"])
                    else:
                        send_message(chat_id, "⚠️ Could not verify name.")
                
                elif nlp_result["intent"] == "SEND_MONEY":
                     # Intent found but details missing
                    send_message(chat_id, "Try: 'Send 50 to 055...'")
            
            else:
                # CHAT MODE
                try: requests.post(f"{BASE_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
                except: pass
                ai_reply = get_ai_response(text)
                send_message(chat_id, ai_reply)

    return {"status": "ok"}

# --- HELPER FUNCTIONS ---

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
        
        send_message(chat_id, "🔒 **Security Check**\nEnter **4-digit PIN**:")

async def execute_charge(chat_id, user, amount, recipient, session):
    send_message(chat_id, f"⏳ Prompt sent to {user.phone_number}...")
    response = initiate_charge(user.phone_number, amount)
    
    if response.get("status"):
        ref = response["data"]["reference"]
        p_status = response["data"].get("status")
        txn_status = "WAITING_FOR_OTP" if p_status == "send_otp" else "PENDING_DEBIT"
        msg = "🔐 **OTP Required!**" if p_status == "send_otp" else "✅ **Prompt Sent.** Approve on phone."
        new_txn = Transaction(telegram_chat_id=chat_id, sender_phone=user.phone_number, recipient_phone=recipient, amount=amount, status=txn_status, paystack_reference=ref)
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
        send_message(chat_id, "✅ Verified! Processing...")
    else:
        send_message(chat_id, f"❌ Wrong OTP.")

# --- WEBHOOK ---

@app.post("/webhook")
async def paystack_webhook(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not signature: return {"status": "denied"}
    if hmac.new(PAYSTACK_SECRET.encode('utf-8'), body, hashlib.sha512).hexdigest() != signature: return {"status": "denied"}

    event_data = await request.json()
    if event_data.get("event") == "charge.success":
        data = event_data.get("data", {})
        ref = data.get("reference")
        txn = session.exec(select(Transaction).where(Transaction.paystack_reference == ref)).first()
        
        if txn and txn.status not in ["DISBURSING", "COMPLETE"]:
            txn.status = "DEBIT_SUCCESS"
            session.add(txn)
            session.commit()
            if txn.telegram_chat_id: send_message(txn.telegram_chat_id, f"✅ **Received!** sending to recipient...")
            
            await asyncio.sleep(2)
            
            recip = create_transfer_recipient("Verified User", txn.recipient_phone)
            if recip.get("status"):
                txn.transfer_code = recip['data']['recipient_code']
                trans = initiate_transfer(txn.amount, txn.transfer_code)
                if trans.get("status"):
                    txn.status = "DISBURSING"
                    if txn.telegram_chat_id:
                        f = generate_receipt(txn.sender_phone, txn.recipient_phone, txn.amount, txn.paystack_reference)
                        send_photo(txn.telegram_chat_id, f, caption="✅ **Transfer Complete!**")
                        try: os.remove(f)
                        except: pass
                else:
                    txn.status = "TRANSFER_FAILED"
                    if txn.telegram_chat_id: send_message(txn.telegram_chat_id, f"⚠️ Debit OK, Transfer Failed: {trans.get('message')}")
            session.add(txn)
            session.commit()
    return {"status": "received"}