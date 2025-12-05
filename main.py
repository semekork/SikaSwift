import os
import hmac
import hashlib
import asyncio
from fastapi import FastAPI, Request, Depends, HTTPException
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import init_db, get_session
from models import Transaction, User
from nlp import parse_message
from telegram_utils import (
    send_message, 
    send_name_confirmation, 
    request_phone_number, 
    delete_message_buttons,
    answer_callback
)
from paystack_utils import (
    initiate_charge, 
    submit_otp, 
    create_transfer_recipient, 
    initiate_transfer,
    resolve_mobile_money
)

load_dotenv()
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan, title="SikaSwift Bot 🤖")

# --- 1. TELEGRAM WEBHOOK ---

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, session: Session = Depends(get_session)):
    data = await request.json()
    
    # A. HANDLE BUTTONS
    if "callback_query" in data:
        await handle_callback(data["callback_query"], session)
        return {"status": "ok"}
    
    # B. HANDLE MESSAGES
    if "message" in data:
        msg = data["message"]
        chat_id = str(msg["chat"]["id"])
        
        if "contact" in msg:
            phone = msg["contact"]["phone_number"].replace("+", "")
            user = User(telegram_id=chat_id, phone_number=phone)
            session.merge(user)
            session.commit()
            send_message(chat_id, "✅ Phone saved! Try sending money again.")
            return {"status": "ok"}
            
        if "text" in msg:
            text = msg["text"].strip()
            
            # OTP Check
            user = session.get(User, chat_id)
            if user:
                statement = select(Transaction).where(
                    Transaction.sender_phone == user.phone_number,
                    Transaction.status == "WAITING_FOR_OTP"
                )
                pending_txn = session.exec(statement).first()
                if pending_txn:
                    await handle_otp_entry(chat_id, text, pending_txn, session)
                    return {"status": "ok"}

            if text == "/start":
                send_message(chat_id, "👋 Welcome! Type 'Send 1 to 055...'")
                return {"status": "ok"}

            nlp_result = parse_message(text)
            
            if nlp_result["intent"] == "SEND_MONEY":
                if nlp_result["amount"] and nlp_result["recipient"]:
                    if not user:
                        request_phone_number(chat_id)
                    else:
                        # NEW: VERIFY NAME BEFORE CONFIRMATION
                        send_message(chat_id, "🔍 Verifying recipient...")
                        verification = resolve_mobile_money(nlp_result["recipient"])
                        
                        if verification["status"]:
                            send_name_confirmation(
                                chat_id, 
                                nlp_result["amount"], 
                                nlp_result["recipient"], 
                                verification["account_name"]
                            )
                        else:
                            send_message(chat_id, "⚠️ Could not verify that number. Please check it.")
                else:
                    send_message(chat_id, "I need amount and recipient.")
            else:
                send_message(chat_id, "I didn't understand.")

    return {"status": "ok"}

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
        amount = float(parts[1])
        recipient = parts[2]
        
        user = session.get(User, chat_id)
        if not user:
            send_message(chat_id, "❌ User not found.")
            return

        send_message(chat_id, f"⏳ Initiating Charge... Check your phone!")
        
        response = initiate_charge(user.phone_number, amount)
        
        if response.get("status"):
            ref = response["data"]["reference"]
            p_status = response["data"].get("status")
            
            txn_status = "WAITING_FOR_OTP" if p_status == "send_otp" else "PENDING_DEBIT"
            msg = "🔐 **OTP Required!** Type it here." if p_status == "send_otp" else "✅ **Prompt Sent.** Approve on your phone."

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
            send_message(chat_id, f"❌ Error: {response.get('message')}")

async def handle_otp_entry(chat_id, otp_code, txn, session):
    send_message(chat_id, "🔄 Verifying OTP...")
    resp = submit_otp(txn.paystack_reference, otp_code)
    
    if resp.get("status"):
        txn.status = "DEBIT_SUCCESS"
        session.add(txn)
        session.commit()
        send_message(chat_id, "✅ OTP Verified! Waiting for confirmation...")
    else:
        send_message(chat_id, f"❌ Wrong OTP.")

# --- 2. PAYSTACK WEBHOOK ---

@app.post("/webhook")
async def paystack_webhook(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    hash_calc = hmac.new(PAYSTACK_SECRET.encode('utf-8'), body, hashlib.sha512).hexdigest()
    
    if hash_calc != signature:
        return {"status": "denied"}

    event_data = await request.json()
    event_type = event_data.get("event")
    data = event_data.get("data", {})
    
    if event_type == "charge.success":
        reference = data.get("reference")
        statement = select(Transaction).where(Transaction.paystack_reference == reference)
        txn = session.exec(statement).first()
        
        if txn and txn.status != "DISBURSING":
            if txn.telegram_chat_id:
                send_message(txn.telegram_chat_id, f"✅ **Received!**\nWe have your {txn.amount} GHS.")

            txn.status = "DEBIT_SUCCESS"
            session.add(txn)
            session.commit()
            
            # WAIT FOR BALANCE UPDATE
            await asyncio.sleep(2)
            
            # TRANSFER TO RECIPIENT
            recip_resp = create_transfer_recipient("Verified User", txn.recipient_phone)
            if recip_resp.get("status"):
                r_code = recip_resp['data']['recipient_code']
                txn.transfer_code = r_code
                
                send_message(txn.telegram_chat_id, "🔄 Sending to recipient...")
                transfer_resp = initiate_transfer(txn.amount, r_code)
                
                if transfer_resp.get("status"):
                    txn.status = "DISBURSING"
                    send_message(txn.telegram_chat_id, f"🚀 **Sent!** Money is on the way.")
                else:
                    txn.status = "TRANSFER_FAILED"
                    err = transfer_resp.get("message")
                    send_message(txn.telegram_chat_id, f"⚠️ Debit Success, but Transfer Failed: {err}")
            
            session.add(txn)
            session.commit()

    return {"status": "received"}