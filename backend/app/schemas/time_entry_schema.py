from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TimeEntryBase(BaseModel):
    object_id: int
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    notes: Optional[str] = None

class CheckIn(TimeEntryBase):
    pass

class CheckOut(BaseModel):
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None

class TimeEntryResponse(BaseModel):
    id: int
    employee_id: int
    object_id: int
    check_in: datetime
    check_out: Optional[datetime]
    gps_lat: Optional[float]
    gps_lng: Optional[float]
    is_manual_entry: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
