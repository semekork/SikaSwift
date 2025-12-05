from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel
from database import init_db, get_session
from models import Transaction
from paystack_utils import initiate_charge, submit_otp
from contextlib import asynccontextmanager

# --- DATA MODELS (Input Validation) ---
class PaymentRequest(BaseModel):
    sender_phone: str   # Who is paying? (e.g., 055...)
    amount: float       # How much? (e.g., 1.0)
    recipient: str      # Who gets it? (e.g., 024...)

# --- LIFECYCLE ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan, title="SikaSwift API ⚡")

@app.get("/")
def home():
    return {"message": "SikaSwift Financial Core is Running"}

@app.post("/pay")
def trigger_payment(request: PaymentRequest, session: Session = Depends(get_session)):
    """
    Directly triggers a MoMo prompt on the sender's phone.
    """
    print(f"💰 Processing Request: {request.amount} GHS from {request.sender_phone}")

    # 1. Call Paystack
    pay_response = initiate_charge(request.sender_phone, request.amount)
    
    status = "FAILED"
    ref = None
    
    # 2. Check Result
    if pay_response.get("status"):
        status = "PENDING_DEBIT"
        ref = pay_response["data"]["reference"]
        message = "Prompt sent! Check your phone."
    else:
        # Paystack rejected it (e.g., invalid number)
        message = "Payment initialization failed."
        print(f"❌ Paystack Error: {pay_response}")

    # 3. Save to Postgres
    new_txn = Transaction(
        sender_phone=request.sender_phone,
        recipient_phone=request.recipient,
        amount=request.amount,
        status=status,
        paystack_reference=ref
    )
    session.add(new_txn)
    session.commit()
    session.refresh(new_txn)
    
    return {
        "message": message,
        "transaction_id": new_txn.id,
        "paystack_ref": ref,
        "status": status
    }
    
class OTPRequest(BaseModel):
    reference: str  # The transaction ID Paystack gave you earlier
    otp: str        # The code the user got via SMS

@app.post("/submit-otp")
def finalize_payment(request: OTPRequest, session: Session = Depends(get_session)):
    """
    Step 2: Send the OTP to finalize the transaction.
    """
    print(f"🔐 Submitting OTP: {request.otp} for Ref: {request.reference}")
    
    response = submit_otp(request.reference, request.otp)
    
    if response.get("status"):
        return {"message": "Payment Successful!", "data": response['data']}
    else:
        return {"message": "OTP Failed", "error": response.get("message")}