from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

class User(SQLModel, table=True):
    telegram_id: str = Field(primary_key=True)
    phone_number: str
    
    # SECURITY FIELDS
    pin_hash: Optional[str] = None       # Stores the "bcrypt" hash, not the real PIN
    state: str = Field(default="IDLE")   # Tracks user context: IDLE, SET_PIN, VERIFY_PIN
    temp_data: Optional[str] = None      # Temporarily holds data (like a transaction ID) while waiting for PIN
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Transaction(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    telegram_chat_id: Optional[str] = None 
    sender_phone: str
    recipient_phone: str 
    amount: float
    status: str = Field(default="INIT")
    paystack_reference: Optional[str] = None 
    transfer_code: Optional[str] = None      
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)