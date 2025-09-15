from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class CustomerBase(BaseModel):
    name: str
    address: str
    billing_type: str = "pauschale"
    monthly_rate: Optional[float] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerResponse(CustomerBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
