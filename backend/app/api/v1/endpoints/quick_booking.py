from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
import random
from app.db.database import get_db
from app.models.models import Employee, Schedule, TimeEntry, Object
from app.core.deps import get_current_user

router = APIRouter()

@router.post("/was-there")
async def quick_booking(
    object_id: int,
    with_partner: bool = False,
    partner_id: int = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kategorie B: War da Button - nimmt Sollstunden aus Dienstplan"""
    
    # Hole Mitarbeiter
    employee = db.query(Employee).filter(
        Employee.user_id == current_user["id"]
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Prüfe ob Kategorie B
    if employee.tracking_mode != "B":
        raise HTTPException(status_code=403, detail="Nur für Kategorie B Mitarbeiter")
    
    # Hole heutigen Dienstplan
    today = date.today()
    schedule = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.object_id == object_id,
        Schedule.date == today
    ).first()
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Kein Dienstplan für heute")
    
    # Generiere Zeiten mit 3-6 Min Variation
    variation_start = random.randint(3, 6)
    variation_end = random.randint(3, 6)
    
    check_in_time = datetime.combine(today, schedule.start_time) - timedelta(minutes=variation_start)
    check_out_time = datetime.combine(today, schedule.end_time) + timedelta(minutes=variation_end)
    
    # Erstelle Zeiteintrag
    time_entry = TimeEntry(
        employee_id=employee.id,
        object_id=object_id,
        check_in=check_in_time,
        check_out=check_out_time,
        is_manual_entry=True,
        notes="War da - Kategorie B"
    )
    
    db.add(time_entry)
    
    # Falls mit Partner
    if with_partner and partner_id:
        partner_entry = TimeEntry(
            employee_id=partner_id,
            object_id=object_id,
            check_in=check_in_time,
            check_out=check_out_time,
            is_manual_entry=True,
            notes=f"War da - Partner von {employee.first_name}"
        )
        db.add(partner_entry)
    
    db.commit()
    
    return {
        "message": "Erfolgreich gebucht",
        "hours": schedule.planned_hours,
        "check_in": check_in_time.strftime("%H:%M"),
        "check_out": check_out_time.strftime("%H:%M")
    }
