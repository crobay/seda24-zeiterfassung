# SPEICHERORT: /root/zeiterfassung/backend/app/api/v1/endpoints/schedule.py
# Diese Datei muss NEU erstellt werden!

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from typing import List, Optional
from app.db.database import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.models import Schedule, Employee, Object

router = APIRouter()

# ========== DIENSTPLAN FÜR MITARBEITER ==========
@router.get("/employee/{employee_id}")
async def get_employee_schedule(
    employee_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Hole Dienstplan für einen Mitarbeiter
    """
    # Prüfe Berechtigung
    if current_user["role"] != "admin" and current_user.get("employee_id") != employee_id:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    
    # Query aufbauen
    query = db.query(Schedule).filter(Schedule.employee_id == employee_id)
    
    if start_date:
        query = query.filter(Schedule.date >= start_date)
    if end_date:
        query = query.filter(Schedule.date <= end_date)
    
    schedules = query.all()
    
    result = []
    for schedule in schedules:
        result.append({
            "id": schedule.id,
            "employee_id": schedule.employee_id,
            "object_id": schedule.object_id,
            "date": schedule.date.isoformat() if hasattr(schedule, 'date') else None,
            "weekday": schedule.weekday,
            "start_time": schedule.start_time.strftime("%H:%M") if schedule.start_time else None,
            "end_time": schedule.end_time.strftime("%H:%M") if schedule.end_time else None,
            "planned_hours": schedule.planned_hours
        })
    
    return result

# ========== WOCHEN-DIENSTPLAN FUER MA ==========
@router.get("/my-week")
async def get_my_week_schedule(
    week_offset: int = Query(0, description="0=aktuelle Woche, 1=naechste, -1=letzte"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Dienstplan des eingeloggten MA fuer eine Woche."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return {"days": [], "week_start": None, "week_end": None}

    today = date.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)

    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.date >= monday,
        Schedule.date <= sunday,
        Schedule.status.in_(["normal", "vertretung"])
    ).order_by(Schedule.date, Schedule.start_time).all()

    wochentage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    days = []
    for s in schedules:
        obj = db.query(Object).filter(Object.id == s.object_id).first()
        days.append({
            "date": s.date.isoformat(),
            "weekday": wochentage[s.date.weekday()],
            "weekday_short": wochentage[s.date.weekday()][:2],
            "object_name": obj.name if obj else f"Objekt {s.object_id}",
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else None,
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else None,
            "planned_hours": s.planned_hours,
            "is_driver": s.is_driver,
            "status": s.status,
        })

    return {
        "days": days,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "employee_name": f"{employee.first_name} {employee.last_name}",
    }


# ========== HEUTIGER DIENSTPLAN ==========
@router.get("/today")
async def get_today_schedule(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Hole Dienstplan für heute
    """
    employee_id = current_user.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=400, detail="Mitarbeiter-ID nicht gefunden")
    
    today = date.today()
    weekday = today.weekday()  # 0=Montag, 6=Sonntag
    
    # Suche nach Dienstplan für heute (nach Wochentag)
    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.weekday == weekday
    ).all()
    
    result = []
    for schedule in schedules:
        obj = db.query(Object).filter(Object.id == schedule.object_id).first()
        result.append({
            "id": schedule.id,
            "object_id": schedule.object_id,
            "object_name": obj.name if obj else f"Objekt {schedule.object_id}",
            "start_time": schedule.start_time.strftime("%H:%M") if schedule.start_time else None,
            "end_time": schedule.end_time.strftime("%H:%M") if schedule.end_time else None,
            "planned_hours": schedule.planned_hours
        })
    
    return result

# ========== OBJEKTE MIT ZEITPUFFER ==========
@router.get("/my-objects")
async def get_my_scheduled_objects(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Hole alle geplanten Objekte für Mitarbeiter (mit Kategorie-basiertem Puffer)
    """
    employee_id = current_user.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=400, detail="Mitarbeiter-ID nicht gefunden")
    
    # Hole Mitarbeiter-Kategorie
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    category = employee.tracking_mode or 'C'
    
    # Berechne Zeitraum basierend auf Kategorie
    today = date.today()
    
    if category in ['B', 'C']:
        # 2-Tage-Puffer (gestern bis morgen)
        start_weekday = (today.weekday() - 1) % 7
        end_weekday = (today.weekday() + 1) % 7
        weekdays = [start_weekday, today.weekday(), end_weekday]
    else:
        # Kategorie A: Nur heute
        weekdays = [today.weekday()]
    
    # Hole alle Dienstpläne für diese Wochentage
    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.weekday.in_(weekdays)
    ).all()
    
    # Sammle eindeutige Objekt-IDs
    object_ids = list(set([s.object_id for s in schedules]))
    
    # Hole Objekt-Details
    objects = db.query(Object).filter(Object.id.in_(object_ids)).all()
    
    result = []
    for obj in objects:
        result.append({
            "id": obj.id,
            "name": obj.name,
            "address": obj.address,
            "latitude": obj.latitude,
            "longitude": obj.longitude
        })
    
    return {
        "category": category,
        "objects": result,
        "message": f"Objekte für Kategorie {category}" + 
                   (" (mit 2-Tage-Puffer)" if category in ['B', 'C'] else " (nur heute)")
    }
