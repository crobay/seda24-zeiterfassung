from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import math
from app.db.database import get_db
from app.models.models import Object
from app.schemas.object_schema import ObjectCreate, ObjectResponse, GPSValidation, GPSValidationResponse
from app.models.models import Employee, Schedule, TimeEntry
from datetime import datetime, timedelta
from sqlalchemy import and_
from app.api.v1.endpoints.auth import get_current_user


router = APIRouter()

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000  # Erdradius in Metern
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c
    
@router.get("/", response_model=List[ObjectResponse])
d@router.get("/")
def get_objects(db: Session = Depends(get_db)):
    objects = db.query(Object).filter(Object.is_active == True).all()
    return objects

@router.post("/", response_model=ObjectResponse)
def create_object(obj: ObjectCreate, db: Session = Depends(get_db)):
    db_object = Object(**obj.dict())
    db.add(db_object)
    db.commit()
    db.refresh(db_object)
    return db_object

@router.get("/my-today")
def get_my_objects_today(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Hole Employee
    employee = db.query(Employee).filter(
        Employee.user_id == current_user.id
    ).first()
    
    if not employee:
        return []
    
    # Kategorie A = kein Dropdown
    if employee.tracking_mode == 'A':
        return []
    
    # Für B und C: NUR zugewiesene Objekte
    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee.id
    ).all()
    
    if not schedules:
        return []
    
    object_ids = list(set([s.object_id for s in schedules]))
    
    objects = db.query(Object).filter(
        and_(
            Object.id.in_(object_ids),
            Object.is_active == True
        )
    ).all()
    
    result = []
    for obj in objects:
        result.append({
            "id": obj.id,
            "name": obj.name,
            "address": getattr(obj, 'address', ""),
            "is_scheduled_today": False,
            "planned_hours": None
        })
    
    return result

@router.post("/validate-gps", response_model=GPSValidationResponse)
def validate_gps(validation: GPSValidation, db: Session = Depends(get_db)):
    obj = db.query(Object).filter(Object.id == validation.object_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    
    distance = calculate_distance(
        validation.current_lat, validation.current_lng,
        obj.gps_lat, obj.gps_lng
    )
    
    return GPSValidationResponse(
        is_valid=distance <= obj.radius_meters,
        distance_meters=round(distance, 2),
        object_name=obj.name,
        allowed_radius=obj.radius_meters
    )
