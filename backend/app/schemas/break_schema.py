from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class BreakStart(BaseModel):
    time_entry_id: Optional[int] = None
    is_paid: bool = False

class BreakEnd(BaseModel):
    break_id: int

class BreakResponse(BaseModel):
    id: int
    time_entry_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    is_paid: bool
    duration_minutes: Optional[int] = None
    
    class Config:
        from_attributes = True
