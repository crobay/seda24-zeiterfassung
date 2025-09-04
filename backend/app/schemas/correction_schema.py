from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CorrectionRequestBase(BaseModel):
    time_entry_id: int
    correction_type: str = Field(..., pattern="^(check_in|check_out|object|delete)$")
    old_value: str
    new_value: str
    reason: str = Field(..., min_length=10, description="Mindestens 10 Zeichen")

class CorrectionRequestCreate(CorrectionRequestBase):
    pass

class CorrectionRequestUpdate(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    admin_response: Optional[str] = None

class CorrectionRequestResponse(CorrectionRequestBase):
    id: int
    employee_id: int
    status: str
    admin_response: Optional[str]
    processed_by: Optional[int]
    processed_at: Optional[datetime]
    created_at: datetime
    
    # Zusatz-Infos
    employee_name: Optional[str] = None
    object_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class CorrectionRequestList(BaseModel):
    total: int
    pending: int
    corrections: list[CorrectionRequestResponse]
