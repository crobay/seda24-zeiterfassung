from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EmployeeBase(BaseModel):
    personal_nr: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    kuerzel: Optional[str] = None
    hourly_rate: Optional[float] = 15.0
    monthly_amount: Optional[float] = 556.0
    address: Optional[str] = None
    gps_required: Optional[bool] = True
    auto_stamp: Optional[bool] = False
    tracking_mode: Optional[str] = "C"

class EmployeeCreate(EmployeeBase):
    user_id: int

class EmployeeUpdate(EmployeeBase):
    pass

class EmployeeResponse(EmployeeBase):
    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
        orm_mode = True

class EmployeeWithUser(EmployeeResponse):
    email: Optional[str] = None
    role: Optional[str] = None
