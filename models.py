from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

class User(SQLModel, table=True):
    telegram_id: str = Field(primary_key=True)
    phone_number: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Transaction(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # We save this so the Webhook knows who to message
    telegram_chat_id: Optional[str] = None 
    
    sender_phone: str
    recipient_phone: str 
    amount: float
    status: str = Field(default="INIT")
    
    paystack_reference: Optional[str] = None 
    transfer_code: Optional[str] = None      
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)