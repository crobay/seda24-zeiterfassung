from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from app.db.database import get_db
from app.models.models import User, TimeEntry, Employee, Object, VacationEntitlement, BreakEntry
from sqlalchemy import func
from app.api.v1.endpoints.auth import get_current_user
import pandas as pd
from io import BytesIO
from fastapi.responses import StreamingResponse
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter()

# ========== NEUE SCHEMAS FÜR HISTORY ==========
class HistoryEntry(BaseModel):
    id: int
    date: date
    object_name: str
    check_in: datetime
    check_out: Optional[datetime]
    total_hours: float
    service_type: Optional[str]
    hourly_rate: float
    amount: float
    brutto_hours: Optional[float] = None
    pause_minutes: Optional[int] = 0
    
    class Config:
        from_attributes = True

class HistoryResponse(BaseModel):
    entries: List[HistoryEntry]
    total_hours: float
    total_amount: float
    period_start: date
    period_end: date

# ========== BESTEHENDE ENDPOINTS ==========

@router.get("/my/today")
def get_my_today_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"\n=== DEBUG TODAY ===")  # DEBUG
    print(f"User: {current_user.email}")  # DEBUG
    
    # Employee für current_user finden
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    
    if not employee:
        print("KEIN EMPLOYEE!")  # DEBUG
        return {"date": date.today().isoformat(), "total_hours": 0, "entries": []}
    
    print(f"Employee ID: {employee.id}")  # DEBUG
    
    # Heute
    today = datetime.now().date()
    
    # Einträge von heute
    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee.id,
        func.date(TimeEntry.check_in) == today
    ).all()
    
    print(f"Einträge gefunden: {len(entries)}")  # DEBUG
    
    total_hours = 0
    for entry in entries:
        if entry.check_out:
            # Skip Urlaub (object_id = 999)
            if entry.object_id == 999:
                continue
            # billed_hours hat Vorrang (Kat B mit Sollstunden)
            if entry.billed_hours and entry.billed_hours > 0:
                total_hours += entry.billed_hours
                print(f"+ {entry.billed_hours:.2f}h (billed)")  # DEBUG
            else:
                diff = entry.check_out - entry.check_in
                total_hours += max(0, diff.total_seconds() / 3600)
                print(f"+ {diff.total_seconds()/3600:.2f}h (diff)")  # DEBUG
    
    print(f"TOTAL: {total_hours}")  # DEBUG
    
    return {
        "date": today.isoformat(),
        "total_hours": round(total_hours, 2),
        "entries": []
    }

@router.get("/my/week")
def get_my_week_hours(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Wochenstunden"""
    if not current_user.employee:
        return {"total_hours": 0, "entries": []}
    
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    
    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == current_user.employee.id,
        TimeEntry.check_in >= monday,
        TimeEntry.check_in <= sunday + timedelta(days=1)
    ).all()
    
    total_hours = 0
    for entry in entries:
        if entry.check_out:
            if entry.object_id == 999:
                continue
            if entry.billed_hours and entry.billed_hours > 0:
                total_hours += entry.billed_hours
            else:
                diff = entry.check_out - entry.check_in
                total_hours += max(0, diff.total_seconds() / 3600)

    return {
        "total_hours": round(total_hours, 2),
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "entries": len(entries)
    }

@router.get("/my/month")
def get_my_month_hours(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Monatsstunden"""
    if not current_user.employee:
        return {"total_hours": 0, "entries": []}
    
    today = datetime.now().date()
    first_day = today.replace(day=1)
    
    if today.month == 12:
        last_day = today.replace(day=31)
    else:
        last_day = today.replace(month=today.month+1, day=1) - timedelta(days=1)
    
    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == current_user.employee.id,
        TimeEntry.check_in >= first_day,
        TimeEntry.check_in <= last_day + timedelta(days=1)
    ).all()
    
    total_hours = 0
    for entry in entries:
        if entry.check_out:
            if entry.object_id == 999:
                continue
            if entry.billed_hours and entry.billed_hours > 0:
                total_hours += entry.billed_hours
            else:
                diff = entry.check_out - entry.check_in
                total_hours += max(0, diff.total_seconds() / 3600)

    return {
        "total_hours": round(total_hours, 2),
        "month": today.month,
        "year": today.year,
        "entries": len(entries)
    }

# ========== NEUER HISTORY ENDPOINT ==========

@router.get("/my/history", response_model=HistoryResponse)
def get_my_history(
    days: int = Query(default=None, ge=1, le=365),
    date_from: str = Query(default=None),
    date_to: str = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Gibt die Historie der letzten X Tage für den eingeloggten Mitarbeiter zurück
    """
    # Employee für current_user finden
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    
    if not employee:
        return HistoryResponse(
            entries=[],
            total_hours=0,
            total_amount=0,
            period_start=date.today(),
            period_end=date.today()
        )
    
    # Zeitraum berechnen
    end_date = datetime.now().date()
    if date_from and date_to:
        start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
    elif days:
        start_date = end_date - timedelta(days=days)
    else:
        start_date = end_date - timedelta(days=30)
    
    # TimeEntry-Einträge mit Object-Namen abrufen (LEFT JOIN fuer Urlaub + custom)
    entries = db.query(
        TimeEntry,
        Object.name.label('object_name')
    ).outerjoin(
        Object, TimeEntry.object_id == Object.id
    ).filter(
        TimeEntry.employee_id == employee.id,
        func.date(TimeEntry.check_in) >= start_date,
        func.date(TimeEntry.check_in) <= end_date
    ).order_by(
        TimeEntry.check_in.desc()
    ).all()

    # Break-Daten fuer alle Eintraege laden
    entry_ids = [e.id for e, _ in entries]
    all_breaks = db.query(BreakEntry).filter(BreakEntry.time_entry_id.in_(entry_ids)).all() if entry_ids else []
    breaks_by_entry = {}
    for b in all_breaks:
        breaks_by_entry.setdefault(b.time_entry_id, []).append(b)

    # Daten aufbereiten
    history_entries = []
    total_hours = 0
    total_amount = 0

    for entry, object_name in entries:
        # Objektname: DB-Objekt > custom_object_name > service_type Fallback
        display_name = object_name or entry.custom_object_name or entry.service_type or "Unbekannt"

        # Urlaub (object_id=999) - fester Tagessatz aus dem time_entry
        if entry.object_id == 999 or entry.service_type == 'Urlaub':
            hourly_rate = float(entry.hourly_rate) if entry.hourly_rate else 0
            amount = hourly_rate  # 1 Tag = 1x Tagessatz (im Entry fixiert)
            hours = 1.0  # 1 Urlaubstag
            display_name = "Urlaub"
        elif entry.check_out:
            delta = entry.check_out - entry.check_in
            hours = entry.billed_hours if entry.billed_hours else (delta.total_seconds() / 3600)
            hourly_rate = entry.hourly_rate if entry.hourly_rate else (employee.hourly_rate or 0)
            amount = (entry.billed_hours if entry.billed_hours else hours) * hourly_rate
        else:
            # Laufende Zeit bis jetzt
            delta = datetime.now() - entry.check_in
            hours = entry.billed_hours if entry.billed_hours else (delta.total_seconds() / 3600)
            hourly_rate = entry.hourly_rate if entry.hourly_rate else (employee.hourly_rate or 0)
            amount = hours * hourly_rate
        
        total_hours += hours
        total_amount += amount
        
        # Pause berechnen
        brutto_hours = None
        pause_minutes = 0
        if entry.check_in and entry.check_out and entry.object_id != 999 and entry.service_type != 'Urlaub':
            brutto_hours = round((entry.check_out - entry.check_in).total_seconds() / 3600, 2)
            entry_breaks = breaks_by_entry.get(entry.id, [])
            for b in entry_breaks:
                if b.start_time and b.end_time:
                    pause_minutes += (b.end_time - b.start_time).total_seconds() / 60
            pause_minutes = round(pause_minutes)

        history_entries.append(HistoryEntry(
            id=entry.id,
            date=entry.check_in.date(),
            object_name=display_name,
            check_in=entry.check_in,
            check_out=entry.check_out,
            total_hours=round(hours, 2),
            service_type=entry.service_type,
            hourly_rate=hourly_rate,
            amount=round(amount, 2),
            brutto_hours=brutto_hours,
            pause_minutes=pause_minutes
        ))
    
    return HistoryResponse(
        entries=history_entries,
        total_hours=round(total_hours, 2),
        total_amount=round(total_amount, 2),
        period_start=start_date,
        period_end=end_date
    )

# ========== EXCEL EXPORT (BESTEHEND) ==========

@router.get("/export/excel/{year}/{month}")
def export_excel(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Excel-Export"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur für Admins")
    
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    employees = db.query(Employee).all()
    excel_data = []
    
    for emp in employees:
        entries = db.query(TimeEntry).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.check_in >= start_date,
            TimeEntry.check_in < end_date
        ).all()
        
        for entry in entries:
            if entry.check_out:
                diff = entry.check_out - entry.check_in
                hours = diff.total_seconds() / 3600
                
                excel_data.append({
                    'Personal-Nr': emp.personal_nr,
                    'Name': f"{emp.first_name} {emp.last_name}",
                    'Datum': entry.check_in.strftime('%d.%m.%Y'),
                    'Check-In': entry.check_in.strftime('%H:%M'),
                    'Check-Out': entry.check_out.strftime('%H:%M'),
                    'Stunden': round(hours, 2),
                    'Stundensatz': emp.hourly_rate,
                    'Lohn': round(hours * emp.hourly_rate, 2)
                })
    
    if not excel_data:
        excel_data = [{'Info': 'Keine Daten für diesen Monat'}]
    
    df = pd.DataFrame(excel_data)
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Zeiterfassung', index=False)
    
    output.seek(0)
    filename = f"SEDA24_Zeiterfassung_{year}_{month:02d}.xlsx"
    
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
    
@router.get("/my/tacho")
def get_my_tacho(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return {"total_hours_since_start": 0, "start_hours": 0}
    
    return {
    "total_hours_since_start": employee.total_hours_since_start or 0,
    "start_hours": employee.start_hours or 0
    }