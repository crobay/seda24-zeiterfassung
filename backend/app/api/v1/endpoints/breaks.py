from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
from app.db.database import get_db
from app.models.models import BreakEntry, TimeEntry
from app.schemas.break_schema import BreakStart, BreakEnd, BreakResponse
from app.api.v1.endpoints.auth import get_current_user
from app.services.bie2_logger import log_bie2
from app.models.models import Employee, Object, EmployeeObjectAssignment

router = APIRouter()

def _parse_client_timestamp(ts_str):
    """Parst client_timestamp String zu naive datetime (Lokalzeit CEST)."""
    if not ts_str:
        return datetime.now()
    try:
        # "Z" → "+00:00" für fromisoformat, NICHT danach nochmal strippen!
        ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        # UTC → Lokalzeit (CEST) konvertieren, dann naive machen
        if dt.tzinfo:
            import pytz
            dt = dt.astimezone(pytz.timezone('Europe/Berlin')).replace(tzinfo=None)
        return dt
    except:
        return datetime.now()

@router.post("/start", response_model=BreakResponse)
def start_break(
    break_data: BreakStart,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    stamp_time = _parse_client_timestamp(break_data.client_timestamp)

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
        # Idempotent bei Offline-Sync: aktive Pause zurückgeben statt Fehler
        if break_data.client_id:
            return active_break
        raise HTTPException(status_code=400, detail="Pause läuft bereits")

    # Neue Pause erstellen
    new_break = BreakEntry(
        time_entry_id=active_entry.id,
        start_time=stamp_time,
        is_paid=break_data.is_paid
    )

    db.add(new_break)
    db.commit()
    db.refresh(new_break)

    # Bie2-Log bei Pause Start
    try:
        c_assign = db.query(EmployeeObjectAssignment).filter(
            EmployeeObjectAssignment.employee_id == current_user.employee.id,
            EmployeeObjectAssignment.object_id == active_entry.object_id,
            EmployeeObjectAssignment.tracking_category == "C",
            EmployeeObjectAssignment.is_active == True
        ).first()
        if c_assign:
            emp = current_user.employee
            obj = db.query(Object).filter(Object.id == active_entry.object_id).first()
            log_bie2("PAUSE START", f"{emp.first_name} {emp.last_name}", obj.name if obj else "?")
    except Exception:
        pass

    return new_break

@router.post("/end", response_model=BreakResponse)
def end_break(
    break_data: BreakEnd,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    stamp_time = _parse_client_timestamp(break_data.client_timestamp)
    break_entry = None

    # Wenn break_id mitgegeben -> direkt suchen
    if break_data.break_id:
        break_entry = db.query(BreakEntry).filter(
            BreakEntry.id == break_data.break_id,
            BreakEntry.end_time == None
        ).first()

    # Fallback: Aktive Pause über aktive Stempelung suchen
    if not break_entry:
        active_entry = db.query(TimeEntry).filter(
            TimeEntry.employee_id == current_user.employee.id,
            TimeEntry.check_out == None
        ).first()
        if active_entry:
            break_entry = db.query(BreakEntry).filter(
                BreakEntry.time_entry_id == active_entry.id,
                BreakEntry.end_time == None
            ).first()

    if not break_entry:
        # Idempotent bei Offline-Sync: letzte beendete Pause zurückgeben
        if break_data.client_id:
            active_entry = db.query(TimeEntry).filter(
                TimeEntry.employee_id == current_user.employee.id,
                TimeEntry.check_out == None
            ).first()
            if active_entry:
                last_break = db.query(BreakEntry).filter(
                    BreakEntry.time_entry_id == active_entry.id,
                    BreakEntry.end_time != None
                ).order_by(BreakEntry.id.desc()).first()
                if last_break:
                    duration = (last_break.end_time - last_break.start_time).total_seconds() / 60
                    return BreakResponse(id=last_break.id, time_entry_id=last_break.time_entry_id,
                        start_time=last_break.start_time, end_time=last_break.end_time,
                        is_paid=last_break.is_paid, duration_minutes=int(duration))
        raise HTTPException(status_code=404, detail="Keine aktive Pause gefunden")

    # Pause beenden
    break_entry.end_time = stamp_time
    duration = (break_entry.end_time - break_entry.start_time).total_seconds() / 60

    db.commit()
    db.refresh(break_entry)
    
    # Bie2-Log bei Pause Ende
    try:
        te = db.query(TimeEntry).filter(TimeEntry.id == break_entry.time_entry_id).first()
        if te:
            c_assign = db.query(EmployeeObjectAssignment).filter(
                EmployeeObjectAssignment.employee_id == te.employee_id,
                EmployeeObjectAssignment.object_id == te.object_id,
                EmployeeObjectAssignment.tracking_category == "C",
                EmployeeObjectAssignment.is_active == True
            ).first()
            if c_assign:
                emp = db.query(Employee).filter(Employee.id == te.employee_id).first()
                obj = db.query(Object).filter(Object.id == te.object_id).first()
                log_bie2("PAUSE ENDE", f"{emp.first_name} {emp.last_name}" if emp else "?",
                         obj.name if obj else "?", f"Dauer={int(duration)}min")
    except Exception:
        pass

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
        duration = (datetime.now() - active_break.start_time).total_seconds() / 60
        return {
            "active_break": {
                "id": active_break.id,
                "start_time": active_break.start_time,
                "duration_minutes": int(duration)
            }
        }
    
    return {"active_break": None}
