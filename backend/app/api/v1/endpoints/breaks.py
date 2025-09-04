from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
from app.db.database import get_db
from app.models.models import BreakEntry, TimeEntry
from app.schemas.break_schema import BreakStart, BreakEnd, BreakResponse
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

@router.post("/start", response_model=BreakResponse)
def start_break(
    break_data: BreakStart,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Aktive Stempelung finden
    active_entry = db.query(TimeEntry).filter(
        TimeEntry.employee_id == current_user.employee.id,
        TimeEntry.check_out == None
    ).first()
    
    if not active_entry:
        raise HTTPException(status_code=400, detail="Keine aktive Stempelung")
    
    # Prüfen ob schon eine Pause läuft
    active_break = db.query(BreakEntry).filter(
        BreakEntry.time_entry_id == active_entry.id,
        BreakEntry.end_time == None
    ).first()
    
    if active_break:
        raise HTTPException(status_code=400, detail="Pause läuft bereits")
    
    # Neue Pause erstellen
    new_break = BreakEntry(
        time_entry_id=active_entry.id,
        start_time=datetime.utcnow(),
        is_paid=break_data.is_paid
    )
    
    db.add(new_break)
    db.commit()
    db.refresh(new_break)
    
    return new_break

@router.post("/end", response_model=BreakResponse)
def end_break(
    break_data: BreakEnd,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Pause finden
    break_entry = db.query(BreakEntry).filter(
        BreakEntry.id == break_data.break_id,
        BreakEntry.end_time == None
    ).first()
    
    if not break_entry:
        raise HTTPException(status_code=404, detail="Keine aktive Pause gefunden")
    
    # Pause beenden
    break_entry.end_time = datetime.utcnow()
    duration = (break_entry.end_time - break_entry.start_time).total_seconds() / 60
    
    db.commit()
    db.refresh(break_entry)
    
    # Duration berechnen für Response
    break_response = BreakResponse(
        id=break_entry.id,
        time_entry_id=break_entry.time_entry_id,
        start_time=break_entry.start_time,
        end_time=break_entry.end_time,
        is_paid=break_entry.is_paid,
        duration_minutes=int(duration)
    )
    
    return break_response

@router.get("/current")
def get_current_break(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Aktive Stempelung finden
    active_entry = db.query(TimeEntry).filter(
        TimeEntry.employee_id == current_user.employee.id,
        TimeEntry.check_out == None
    ).first()
    
    if not active_entry:
        return {"active_break": None}
    
    # Aktive Pause finden
    active_break = db.query(BreakEntry).filter(
        BreakEntry.time_entry_id == active_entry.id,
        BreakEntry.end_time == None
    ).first()
    
    if active_break:
        duration = (datetime.utcnow() - active_break.start_time).total_seconds() / 60
        return {
            "active_break": {
                "id": active_break.id,
                "start_time": active_break.start_time,
                "duration_minutes": int(duration)
            }
        }
    
    return {"active_break": None}
