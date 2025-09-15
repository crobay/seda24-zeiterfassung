from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ObjectBase(BaseModel):
    customer_id: int
    name: str
    address: str
    gps_lat: float = Field(..., ge=-90, le=90)
    gps_lng: float = Field(..., ge=-180, le=180)
    radius_meters: int = 100

class ObjectCreate(ObjectBase):
    pass

class ObjectResponse(ObjectBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class GPSValidation(BaseModel):
    object_id: int
    current_lat: float
    current_lng: float
    
class GPSValidationResponse(BaseModel):
    is_valid: bool
    distance_meters: float
    object_name: str
    allowed_radius: int
