from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
import uuid

class User(SQLModel, table=True):
    telegram_id: str = Field(primary_key=True)
    phone_number: str
    pin_hash: Optional[str] = None
    state: str = Field(default="IDLE")
    temp_data: Optional[str] = None
    referred_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Beneficiary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.telegram_id")
    name: str  # e.g., "Mom", "Barber"
    phone_number: str
    
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