from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ScheduleBase(BaseModel):
    employee_id: int
    object_id: int
    weekday: int
    start_time: str
    end_time: str
    
class ScheduleCreate(ScheduleBase):
    pass

class ScheduleResponse(ScheduleBase):
    id: int
    is_active: bool
    
    class Config:
        from_attributes = True

class WarningBase(BaseModel):
    warning_type: str
    message: str

class WarningCreate(WarningBase):
    employee_id: int

class WarningResponse(WarningBase):
    id: int
    employee_id: int
    is_resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime]
    
    class Config:
        from_attributes = True
