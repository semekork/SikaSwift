import os
import hmac
import hashlib
import asyncio
import httpx 
from fastapi import FastAPI, Request, Depends
from contextlib import asynccontextmanager
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import init_db, get_session
from models import Transaction, User, Beneficiary
from nlp import parse_message
# Imported async functions from updated utils
from telegram_utils import (
    BASE_URL, send_message, send_photo, send_name_confirmation, 
    request_phone_number, delete_message_buttons, delete_message, answer_callback
)
from paystack_utils import (
    initiate_charge, submit_otp, create_transfer_recipient, 
    initiate_transfer, resolve_mobile_money, refund_charge
)
from security_utils import hash_pin, verify_pin
from receipt_utils import generate_receipt
from qr_utils import generate_payment_qr
from chat_utils import get_ai_response

load_dotenv()
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
ADMIN_ID = os.getenv("ADMIN_ID", "YOUR_ADMIN_ID")

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

        # 1. UX: TYPING INDICATOR
        # Fire immediately so the user knows we are processing
        try: 
            async with httpx.AsyncClient() as client:
                await client.post(f"{BASE_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
        except: pass
        
        # 2. CONTACT SHARING
        if "contact" in msg:
            phone = msg["contact"]["phone_number"].replace("+", "")
            user = session.get(User, chat_id)
            
            if user and user.state == "AWAITING_RESET_AUTH":
                if user.phone_number == phone:
                    user.pin_hash = None
                    user.state = "AWAITING_NEW_PIN"
                    session.add(user)
                    session.commit()
                    await send_message(chat_id, "✅ **Identity Verified!**\nEnter **NEW 4-digit PIN**:")
                else:
                    user.state = "IDLE"
                    session.add(user)
                    session.commit()
                    await send_message(chat_id, "❌ Number mismatch.")
                return {"status": "ok"}
            
            if not user:
                user = User(telegram_id=chat_id, phone_number=phone, state="IDLE")
                session.merge(user)
                session.commit()
                await send_message(chat_id, "✅ Phone saved! **Type /setpin to secure your account.**")
                return {"status": "ok"}
            
        # 3. TEXT PROCESSING
        if "text" in msg:
            text = msg["text"].strip()
            user = session.get(User, chat_id)
            
            if user:
                # AUTO-DELETE PIN
                if user.state in ["AWAITING_NEW_PIN", "AWAITING_PIN_AUTH"] and len(text) == 4 and text.isdigit():
                    await delete_message(chat_id, message_id)

                # STATE: SET PIN
                if user.state == "AWAITING_NEW_PIN":
                    if len(text) == 4 and text.isdigit():
                        user.pin_hash = hash_pin(text)
                        user.state = "IDLE"
                        session.add(user)
                        session.commit()
                        await send_message(chat_id, "🔐 **PIN Set Successfully!**")
                    else:
                        await send_message(chat_id, "❌ PIN must be 4 digits.")
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
                            
                            await send_message(chat_id, "🔓 **PIN Verified.** Processing...")
                            await execute_charge(chat_id, user, amount, recipient, session)
                        except:
                            await send_message(chat_id, "❌ Error. Try again.")
                            user.state = "IDLE"
                            session.add(user)
                            session.commit()
                    else:
                        await send_message(chat_id, "❌ **Wrong PIN.** Cancelled.")
                        user.state = "IDLE"
                        user.temp_data = None
                        session.add(user)
                        session.commit()
                    return {"status": "ok"}

                # STATE: EDIT AMOUNT (UX)
                if user.state == "AWAITING_EDIT_AMOUNT":
                    clean_text = text.replace('.', '', 1)
                    if clean_text.isdigit():
                        new_amount = float(text)
                        recipient_phone = user.temp_data # We stored phone here in the callback
                        
                        user.state = "IDLE"
                        user.temp_data = None
                        session.add(user)
                        session.commit()
                        
                        # Re-confirm with new amount
                        verification = await resolve_mobile_money(recipient_phone)
                        name = verification["account_name"] if verification["status"] else "Unknown"
                        
                        await send_message(chat_id, "🔄 Updating...")
                        await send_name_confirmation(chat_id, new_amount, recipient_phone, name)
                    else:
                        await send_message(chat_id, "❌ Invalid amount. Please enter a number (e.g. 50).")
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
                        
                        verification = await resolve_mobile_money(recipient)
                        name = verification["account_name"] if verification["status"] else "Unknown"
                        await send_name_confirmation(chat_id, amount, recipient, name)
                    else:
                        await send_message(chat_id, "❌ Invalid amount.")
                    return {"status": "ok"}
                
                # OTP CHECK
                statement = select(Transaction).where(Transaction.sender_phone == user.phone_number, Transaction.status == "WAITING_FOR_OTP")
                pending_txn = session.exec(statement).first()
                if pending_txn:
                    await handle_otp_entry(chat_id, text, pending_txn, session)
                    return {"status": "ok"}

            # --- COMMANDS ---

            if text.startswith("/save"):
                try:
                    parts = text.split()
                    if len(parts) != 3:
                        await send_message(chat_id, "⚠️ Usage: `/save Mom 0555111222`")
                        return {"status": "ok"}
                    
                    name_alias = parts[1].lower()
                    number = parts[2]
                    
                    if not number.isdigit() or len(number) != 10:
                        await send_message(chat_id, "❌ Invalid phone number.")
                        return {"status": "ok"}

                    contact = Beneficiary(user_id=chat_id, name=name_alias, phone_number=number)
                    session.add(contact)
                    session.commit()
                    await send_message(chat_id, f"✅ Saved **{parts[1]}** ({number})")
                except:
                    await send_message(chat_id, "❌ Error saving contact.")
                return {"status": "ok"}

            if text == "/contacts":
                contacts = session.exec(select(Beneficiary).where(Beneficiary.user_id == chat_id)).all()
                if not contacts:
                    await send_message(chat_id, "📭 No contacts. Use `/save Mom 055...`")
                else:
                    msg = "📖 **My Contacts**\n\n"
                    for c in contacts:
                        msg += f"👤 **{c.name.title()}**: {c.phone_number}\n"
                    await send_message(chat_id, msg)
                return {"status": "ok"}

            if text == "/start":
                await send_message(chat_id, "👋 **Welcome!**\n\n/setpin\n/save [Name] [Number]\n/myqr\n/history")
                return {"status": "ok"}
            
            if text == "/setpin":
                if not user: await request_phone_number(chat_id)
                else:
                    user.state = "AWAITING_NEW_PIN"
                    session.add(user)
                    session.commit()
                    await send_message(chat_id, "🔐 Enter **4-digit PIN**:")
                return {"status": "ok"}

            if text == "/resetpin":
                if not user: await send_message(chat_id, "Register first.")
                else:
                    user.state = "AWAITING_RESET_AUTH"
                    session.add(user)
                    session.commit()
                    await request_phone_number(chat_id) 
                    await send_message(chat_id, "⚠️ **Security Check**\nTap 'Share Phone Number' below.")
                return {"status": "ok"}
            
            if text == "/myqr":
                if not user:
                    await send_message(chat_id, "Register first.")
                    return {"status": "ok"}
                qr_file = generate_payment_qr(user.phone_number)
                await send_photo(chat_id, qr_file, caption=f"Scan to pay **{user.phone_number}**")
                try: os.remove(qr_file) 
                except: pass
                return {"status": "ok"}

            # NEW: HISTORY COMMAND
            if text == "/history":
                if not user:
                    await send_message(chat_id, "Please register first.")
                    return {"status": "ok"}

                statement = select(Transaction).where(
                    Transaction.sender_phone == user.phone_number
                ).order_by(Transaction.created_at.desc()).limit(5)
                
                txns = session.exec(statement).all()

                if not txns:
                    await send_message(chat_id, "📭 **No transactions found.**")
                else:
                    msg = "📜 **Recent Activity**\n\n"
                    for t in txns:
                        icon = "✅"
                        if "FAIL" in t.status or "REFUND" in t.status: icon = "❌"
                        elif "WAIT" in t.status or "PENDING" in t.status: icon = "⏳"
                        
                        msg += f"{icon} **GHS {t.amount:.2f}** ➡ {t.recipient_phone}\n"
                        msg += f"📅 {t.created_at.strftime('%d-%b %H:%M')} | {t.status}\n\n"
                    
                    await send_message(chat_id, msg)
                return {"status": "ok"}
            
            if text.startswith("/start pay_"):
                try:
                    target = text.split("pay_")[1]
                    if not user:
                        await request_phone_number(chat_id)
                        return {"status": "ok"}
                    verification = await resolve_mobile_money(target)
                    name = verification["account_name"] if verification["status"] else "Unknown"
                    user.state = "AWAITING_QR_AMOUNT"
                    user.temp_data = target
                    session.add(user)
                    session.commit()
                    await send_message(chat_id, f"✅ **Recipient:** {name}\n**Enter Amount:**")
                except:
                    await send_message(chat_id, "❌ Invalid QR.")
                return {"status": "ok"}

            # SEND MONEY LOGIC
            nlp_result = parse_message(text)
            if nlp_result["intent"] == "SEND_MONEY":
                if nlp_result["amount"] and nlp_result["recipient"]:
                    
                    recipient_input = nlp_result["recipient"]
                    final_number = None

                    if recipient_input.isdigit() and len(recipient_input) >= 10:
                        final_number = recipient_input
                    else:
                        contact = session.exec(select(Beneficiary).where(Beneficiary.user_id == chat_id, Beneficiary.name == recipient_input.lower())).first()
                        if contact:
                            final_number = contact.phone_number
                            await send_message(chat_id, f"📖 Found: **{contact.name.title()}** ({final_number})")
                        else:
                            await send_message(chat_id, f"❌ Unknown contact '{recipient_input}'.\nUse `/save {recipient_input} 055...`")
                            return {"status": "ok"}

                    if not user:
                        await request_phone_number(chat_id)
                        return {"status": "ok"}
                    
                    if not user.pin_hash:
                        await send_message(chat_id, "⚠️ Set a PIN first: /setpin")
                        return {"status": "ok"}

                    await send_message(chat_id, "🔍 Verifying recipient...")
                    verification = await resolve_mobile_money(final_number)
                    
                    if verification["status"]:
                        await send_name_confirmation(chat_id, nlp_result["amount"], final_number, verification["account_name"])
                    else:
                        await send_message(chat_id, "⚠️ Could not verify name.")
                
                elif nlp_result["intent"] == "SEND_MONEY":
                    await send_message(chat_id, "Try: 'Send 50 to 055...'")
            
            else:
                # CHAT MODE
                ai_reply = get_ai_response(text)
                await send_message(chat_id, ai_reply)

    return {"status": "ok"}

# --- HELPER FUNCTIONS ---

async def handle_callback(callback, session):
    chat_id = str(callback["message"]["chat"]["id"])
    message_id = callback["message"]["message_id"]
    callback_id = callback["id"]
    action_data = callback["data"]
    
    await answer_callback(callback_id) 
    await delete_message_buttons(chat_id, message_id)
    
    if action_data == "cancel":
        await send_message(chat_id, "🚫 Cancelled.")
        return

    # NEW: HANDLE EDIT AMOUNT
    if action_data.startswith("edit_"):
        target_phone = action_data.split("_")[1]
        user = session.get(User, chat_id)
        if user:
            user.state = "AWAITING_EDIT_AMOUNT"
            user.temp_data = target_phone
            session.add(user)
            session.commit()
            await send_message(chat_id, f"📝 **Enter New Amount** for {target_phone}:")
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
        
        await send_message(chat_id, "🔒 **Security Check**\nEnter **4-digit PIN**:")

async def execute_charge(chat_id, user, amount, recipient, session):
    await send_message(chat_id, f"⏳ Prompt sent to {user.phone_number}...")
    response = await initiate_charge(user.phone_number, amount)
    
    if response.get("status"):
        ref = response["data"]["reference"]
        p_status = response["data"].get("status")
        txn_status = "WAITING_FOR_OTP" if p_status == "send_otp" else "PENDING_DEBIT"
        msg = "🔐 **OTP Required!**" if p_status == "send_otp" else "✅ **Prompt Sent.** Approve on phone."
        new_txn = Transaction(telegram_chat_id=chat_id, sender_phone=user.phone_number, recipient_phone=recipient, amount=amount, status=txn_status, paystack_reference=ref)
        session.add(new_txn)
        session.commit()
        await send_message(chat_id, msg)
    else:
        await send_message(chat_id, f"❌ Charge Failed: {response.get('message')}")

async def handle_otp_entry(chat_id, otp_code, txn, session):
    await send_message(chat_id, "🔄 Verifying OTP...")
    resp = await submit_otp(txn.paystack_reference, otp_code)
    if resp.get("status"):
        txn.status = "DEBIT_SUCCESS"
        session.add(txn)
        session.commit()
        await send_message(chat_id, "✅ Verified! Processing...")
    else:
        await send_message(chat_id, f"❌ Wrong OTP.")

# --- WEBHOOK (WITH AUTO-REFUND & ASYNC) ---

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
        
        if txn and txn.status not in ["DISBURSING", "COMPLETE", "REFUNDED"]:
            txn.status = "DEBIT_SUCCESS"
            session.add(txn)
            session.commit()
            
            if txn.telegram_chat_id: 
                await send_message(txn.telegram_chat_id, f"✅ **Received!** Sending to recipient...")
            
            await asyncio.sleep(2)
            
            # Async Create Recipient
            recip = await create_transfer_recipient("Verified User", txn.recipient_phone)
            
            if recip.get("status"):
                txn.transfer_code = recip['data']['recipient_code']
                
                # Async Initiate Transfer
                trans = await initiate_transfer(txn.amount, txn.transfer_code)
                
                if trans.get("status"):
                    txn.status = "DISBURSING"
                    if txn.telegram_chat_id:
                        f = generate_receipt(txn.sender_phone, txn.recipient_phone, txn.amount, txn.paystack_reference)
                        await send_photo(txn.telegram_chat_id, f, caption="✅ **Transfer Complete!**")
                        try: os.remove(f)
                        except: pass
                else:
                    # TRANSFER FAILED -> REFUND
                    error_msg = trans.get('message', 'Unknown error')
                    txn.status = "TRANSFER_FAILED"
                    if txn.telegram_chat_id:
                        await send_message(txn.telegram_chat_id, f"⚠️ Transfer Failed: {error_msg}\n🔄 Initiating Refund...")
                    
                    # Async Auto-Reversal
                    refund = await refund_charge(txn.paystack_reference)
                    if refund.get("status"):
                        txn.status = "REFUNDED"
                        if txn.telegram_chat_id: await send_message(txn.telegram_chat_id, "✅ **Refund Successful.** Check your wallet.")
                    else:
                        txn.status = "REFUND_FAILED"
                        if txn.telegram_chat_id: await send_message(txn.telegram_chat_id, "❌ **Refund Failed.** Please contact support.")

            else:
                # RECIPIENT FAIL -> REFUND
                txn.status = "RECIPIENT_FAIL"
                if txn.telegram_chat_id:
                    await send_message(txn.telegram_chat_id, "⚠️ System Error (Recipient).\n🔄 Initiating Refund...")
                
                # Async Auto-Reversal
                refund = await refund_charge(txn.paystack_reference)
                if refund.get("status"):
                    txn.status = "REFUNDED"
                    if txn.telegram_chat_id: await send_message(txn.telegram_chat_id, "✅ **Refund Successful.**")
                else:
                    txn.status = "REFUND_FAILED"
                    if txn.telegram_chat_id: await send_message(txn.telegram_chat_id, "❌ **Refund Failed.** Please contact support.")

            session.add(txn)
            session.commit()
            
    return {"status": "received"}