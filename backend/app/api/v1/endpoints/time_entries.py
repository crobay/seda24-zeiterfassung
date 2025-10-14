from fastapi import APIRouter, Depends, HTTPException, status
from datetime import time
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta, date
from typing import List
import math

from app.db.database import get_db
from app.models.models import TimeEntry, Employee, Object, User, Schedule
from app.schemas.time_entry_schema import CheckIn, CheckOut, TimeEntryResponse
from app.core.validation_service import ValidationService
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

def calculate_distance(lat1, lng1, lat2, lng2):
    """Berechnet Distanz zwischen zwei GPS-Punkten in Metern"""
    R = 6371000  # Erdradius in Metern
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    return distance


def update_total_hours(employee_id: int, db: Session):
    """Aktualisiert total_hours_since_start nach jedem Stempeln"""
    from sqlalchemy import func
    
    total_booked = db.query(func.sum(
        func.extract('epoch', TimeEntry.check_out - TimeEntry.check_in) / 3600
    )).filter(
        TimeEntry.employee_id == employee_id,
        TimeEntry.check_out.isnot(None)
    ).scalar()
    
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee:
        start = float(employee.start_hours or 0)
        booked = float(total_booked or 0)
        employee.total_hours_since_start = float(start + booked)
        db.commit()

def get_hourly_rate_for_object(employee, object_name):
    """Ermittelt Stundensatz basierend auf Objektname"""
    if not object_name:
        return employee.hourly_rate_standard if hasattr(employee, 'hourly_rate_standard') else 15.00
        
    object_upper = object_name.upper()
    
    # Fensterreinigung
    if "FENSTER" in object_upper or "WINDOW" in object_upper:
        return employee.hourly_rate_window if hasattr(employee, 'hourly_rate_window') else 20.00
    # Grundreinigung
    elif "GRUND" in object_upper or "BASIC" in object_upper:
        return employee.hourly_rate_basic if hasattr(employee, 'hourly_rate_basic') else 20.00
    # Büro/Zentrale (für Drazen)
    elif "BÜRO" in object_upper or "ZENTRALE" in object_upper:
        return employee.hourly_rate_window if hasattr(employee, 'hourly_rate_window') else 20.00
    # Standard
    else:
        return employee.hourly_rate_standard if hasattr(employee, 'hourly_rate_standard') else 15.00

@router.post("/check-in")
async def awr_anwesend(
    object_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kategorie B - War anwesend Button"""
    # Rufe einfach check_in auf
    return await check_in(object_data, db, current_user)
async def check_in(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Employee finden oder erstellen
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        employee = Employee(
            user_id=current_user.id,
            personal_nr=f"D{current_user.id:03d}",
            first_name="User",
            last_name=str(current_user.id),
            hourly_rate=15.0
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)
    
    # WICHTIG: Alte offene Einträge IMMER schließen
    old_entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee.id,
        TimeEntry.check_out == None
    ).all()
    
    for entry in old_entries:
        entry.check_out = datetime.utcnow()
    
    if old_entries:
        db.commit()
        
    # Neuer Eintrag
    try:
        time_entry = TimeEntry(
            employee_id=employee.id,
            object_id=data.get("object_id", 1),
            check_in=datetime.utcnow()
        )
        db.add(time_entry)
        db.commit()
        db.refresh(time_entry)
        return time_entry
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-out")
def check_out(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Hole Employee
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Finde aktiven Eintrag
    active_entry = db.query(TimeEntry).filter(
        and_(
            TimeEntry.employee_id == employee.id,
            TimeEntry.check_out == None
        )
    ).first()
    
    if not active_entry:
        raise HTTPException(status_code=400, detail="Kein aktiver Check-in gefunden!")
    
    # Setze check_out Zeit
    active_entry.check_out = datetime.utcnow()
    # GPS beim Ausstempeln ist optional - lassen wir weg
    
    db.commit()
    # Tachometer aktualisieren
    update_total_hours(employee.id, db)
    db.refresh(active_entry)
    
    return active_entry

@router.post("/switch-object", response_model=TimeEntryResponse)
def switch_object(
    data: CheckIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Wechselt von einem Objekt zum anderen - beendet aktuellen und startet neuen"""
    
    # Hole Employee
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Finde und beende aktiven Eintrag
    active_entry = db.query(TimeEntry).filter(
        and_(
            TimeEntry.employee_id == employee.id,
            TimeEntry.check_out == None
        )
    ).first()
    
    if not active_entry:
        raise HTTPException(status_code=400, detail="Kein aktiver Check-in zum Wechseln!")
    
    # Beende alten Eintrag
    active_entry.check_out = datetime.utcnow()
    active_entry.check_out_lat = data.gps_lat
    active_entry.check_out_lng = data.gps_lng
    active_entry.notes = (active_entry.notes or "") + f" | Wechsel zu Objekt {data.object_id}"
    
    # Erstelle neuen Eintrag am neuen Objekt
    new_entry = TimeEntry(
        employee_id=employee.id,
        object_id=data.object_id,
        check_in=datetime.utcnow(),
        gps_lat=data.gps_lat,
        gps_lng=data.gps_lng,
        notes=f"Wechsel von Objekt {active_entry.object_id}"
    )
    
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    
    return new_entry

@router.get("/current")
def get_current_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return {"is_working": False}
    
    # WICHTIG: NUR den NEUESTEN offenen Eintrag nehmen!
    # Sortiert nach ID absteigend, nimmt nur den ersten
    current_entry = db.query(TimeEntry)\
        .filter(TimeEntry.employee_id == employee.id)\
        .filter(TimeEntry.check_out == None)\
        .order_by(TimeEntry.id.desc())\
        .first()  # NUR DER NEUESTE!
    
    if current_entry:
        # Zombie-Check: Wenn älter als 14 Stunden, ignorieren!
        from datetime import datetime, timedelta
        if datetime.now() - current_entry.check_in > timedelta(hours=14):
            # Zombie-Eintrag automatisch schließen
            current_entry.check_out = datetime.now()
            db.commit()
            return {"is_working": False}
        
        return {
            "is_working": True,
            "check_in": current_entry.check_in.isoformat(),
            "object_id": current_entry.object_id,
            "entry_id": current_entry.id
        }
    
    return {"is_working": False}

@router.post("/war-anwesend")
def war_anwesend_booking(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kategorie B: Bucht Sollstunden für den Tag mit einem Klick
    """
    # Prüfe ob MA Kategorie B hat
    employee = db.query(Employee).filter(
        Employee.user_id == current_user.id
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Object ID holen
    object_id = data.get('object_id')
    if not object_id:
        raise HTTPException(status_code=400, detail="Objekt fehlt")
        
    service_type = data.get('service_type', 'Unterhaltsreinigung')
    # Vereinfacht - keine Kategorie-Prüfung mehr
    # Prüfe ob heute schon gebucht wurde
    today = datetime.now().date()
    existing = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee.id,
        TimeEntry.object_id == object_id,  # WICHTIG: Pro Objekt prüfen!
        func.date(TimeEntry.check_in) == today
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Du hast heute bereits Stunden für dieses Objekt gebucht"
        )
    

# Hole Sollstunden aus Dienstplan
    schedule = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.object_id == object_id,
        Schedule.date == datetime.now().date()
    ).first()
    
    if not schedule:
        # Fallback: Standard-Stunden für Kategorie B
        # Matej und Ruzica arbeiten meist 4 Stunden
        # Hole Sollstunden aus Dienstplan
        schedule = db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.date == datetime.now().date(),
            Schedule.object_id == data.object_id
        ).first()
        scheduled_hours = schedule.planned_hours if schedule else 4.0
    else:
        scheduled_hours = schedule.planned_hours
    
    # Erstelle Zeiteintrag
    check_in = datetime.combine(datetime.today(), schedule.start_time if schedule else time(6,0))
    check_out = datetime.combine(datetime.today(), schedule.end_time if schedule else time(6,0)) if schedule else check_in + timedelta(hours=scheduled_hours)
    
    if service_type == 'Fensterreinigung':
        hourly_rate = 20.0
    elif service_type == 'Grundreinigung':
        hourly_rate = 20.0
    else:  # Unterhaltsreinigung und alles andere
        hourly_rate = 15.0
    
    time_entry = TimeEntry(
        employee_id=employee.id,
        object_id=object_id,
        check_in=check_in,
        check_out=check_out,
        service_type=service_type,
        hourly_rate=hourly_rate,  # <-- UND DIESE ZEILE DAZU
        is_manual_entry=True,
        notes=f"War anwesend (Kategorie B) - {service_type}"
    )
    
    db.add(time_entry)
    db.commit()
    
    return {
        "message": "Sollstunden erfolgreich gebucht",
        "scheduled_hours": scheduled_hours,
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat()
    }
 
 # Neuer Endpoint für time_entries.py
# Füge das zu /root/zeiterfassung/backend/app/api/v1/endpoints/time_entries.py hinzu

@router.get("/my-objects-today")
def get_my_scheduled_objects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Gibt nur die Objekte zurück, die laut Dienstplan heute (oder mit Puffer) dran sind"""
    from datetime import date, timedelta
    
    today = date.today()
    weekday = today.weekday()  # 0=Montag, 6=Sonntag
    
    # Hole den Mitarbeiter
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []
    
    # Basis: Heutiger Dienstplan
    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.date == today
    ).all()
    
    # Kategorie B und C: 2 Tage Puffer (gestern und morgen auch erlaubt)
    if current_user.category in ["B", "C"]:
        yesterday = (weekday - 1) % 7
        tomorrow = (weekday + 1) % 7
        
        extra_schedules = db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            # Schedule.weekday.in_([yesterday, tomorrow])
        ).all()
        schedules.extend(extra_schedules)
    
    # Hole die Objekt-Details
    object_ids = list(set([s.object_id for s in schedules]))  # Unique IDs
    
    if not object_ids:
        return []
    
    objects = db.query(Object).filter(Object.id.in_(object_ids)).all()
    
    # Formatiere für Frontend
    result = []
    for obj in objects:
        # Finde die passende Schedule für dieses Objekt
        obj_schedule = next((s for s in schedules if s.object_id == obj.id), None)
        
        result.append({
            "id": obj.id,
            "name": obj.name,
            "address": obj.address,
            "gps_lat": obj.gps_lat,
            "gps_lng": obj.gps_lng,
#            "radius": obj.radius,
            "planned_hours": round(((obj_schedule.end_time.hour * 60 + obj_schedule.end_time.minute) - (obj_schedule.start_time.hour * 60 + obj_schedule.start_time.minute)) / 60, 2) if obj_schedule and obj_schedule.start_time and obj_schedule.end_time else 4,
            "start_time": obj_schedule.start_time.strftime("%H:%M") if obj_schedule and obj_schedule.start_time else "06:00",
            "end_time": obj_schedule.end_time.strftime("%H:%M") if obj_schedule and obj_schedule.end_time else "14:00",
            "is_scheduled_today": obj_schedule.weekday == weekday if obj_schedule else False
        })
    
    return result

# Zusätzlich: Prüfe ob heute Arbeitstag laut Dienstplan
@router.get("/has-work-today")
def check_if_working_today(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Prüft ob der Mitarbeiter heute laut Dienstplan arbeitet"""
    today = date.today()
    weekday = today.weekday()
    
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return {"has_work": False, "category": current_user.category}
    
    # Prüfe Dienstplan
    schedule_today = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.date == today
    ).first()
    
    return {
        "has_work": schedule_today is not None,
        "category": current_user.category,
        "auto_checked_in": current_user.category == "A" and schedule_today is not None
    }
@router.post("/validate-gps")
def validate_gps(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """GPS-Validierung nur für Eldina (D010)"""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    
    # Nur für Eldina (D010) GPS prüfen
    if not employee or employee.personal_nr != "D010":
        return {"valid": True, "message": "GPS-Check nicht erforderlich"}
    
    object_id = data.get("object_id")
    user_lat = data.get("lat")
    user_lng = data.get("lng")
    
    if not user_lat or not user_lng:
        return {"valid": True, "warning": "Keine GPS-Position verfügbar"}
    
    obj = db.query(Object).filter(Object.id == object_id).first()
    if not obj or not obj.gps_lat or not obj.gps_lng:
        return {"valid": True, "message": "Keine GPS-Daten für Objekt"}
    
    # Distanz berechnen
    from math import sin, cos, sqrt, atan2, radians
    R = 6371000  # Erdradius in Metern
    
    lat1 = radians(float(user_lat))
    lat2 = radians(float(obj.gps_lat))
    lon1 = radians(float(user_lng))
    lon2 = radians(float(obj.gps_lng))
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    
    if distance > 100:
        return {
            "valid": True,  # Trotzdem erlauben
            "warning": f"Du bist {round(distance)}m vom Objekt entfernt",
            "distance": distance
        }
    
    return {"valid": True, "distance": distance}
