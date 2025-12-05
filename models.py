from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

class Transaction(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Who is Sending the money?
    sender_phone: str
    receiver_phone: str
    amount: float
    
    # Status Machine
    status: str = Field(default="INIT")
    # Options: INIT, PENDING_DEBIT, DEBIT_SUCCESS, DISBURSING, COMPLETE, FAILED
    
    # Tracking IDs 
    paystack_reference: Optional[str] = None # The ID for the "Charge"
    recipient_code: Optional[str] = None # The ID for the "Transfer"
    
    # Timestammps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)