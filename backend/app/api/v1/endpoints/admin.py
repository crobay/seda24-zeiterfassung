from fastapi import APIRouter, Depends, HTTPException, Header, Query
# KmDistance is in models
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import date, datetime, timedelta, time
from typing import List, Optional
from jose import jwt
from app.db.database import get_db
from app.models.models import User, Employee, TimeEntry, Schedule, Object, Customer, KmDistance
import os
from dotenv import load_dotenv
from app.api.v1.endpoints.auth import get_current_user
from collections import defaultdict

load_dotenv()
router = APIRouter()

# Weekday Mappings für Integer-basierte Speicherung
WEEKDAY_MAP = {
    'Montag': 0,
    'Dienstag': 1,
    'Mittwoch': 2,
    'Donnerstag': 3,
    'Freitag': 4,
    'Samstag': 5,
    'Sonntag': 6
}

WEEKDAY_NAMES = {
    0: 'Montag',
    1: 'Dienstag',
    2: 'Mittwoch',
    3: 'Donnerstag',
    4: 'Freitag',
    5: 'Samstag',
    6: 'Sonntag'
}

def verify_admin(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=401, detail="No authorization header")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = parts[1]
    try:
        payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Not an admin")
    return user

@router.get("/dashboard/stats")
def get_stats(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    total = db.query(Employee).join(User).filter(User.role != "admin").count()
    active = db.query(TimeEntry).filter(
        TimeEntry.check_out == None,
        func.date(TimeEntry.check_in) == date.today()
    ).count()
    
    today_seconds = db.query(
        func.sum(
            func.extract('epoch', func.coalesce(TimeEntry.check_out, func.now()) - TimeEntry.check_in)
        )
    ).filter(
        func.date(TimeEntry.check_in) == date.today()
    ).scalar() or 0
    
    return {
        "active_employees": active,
        "paused_employees": 0,
        "offline_employees": total - active,
        "total_employees": total,
        "total_hours_today": round(today_seconds / 3600, 1)
    }

@router.get("/live-status")
def get_live(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    return []

@router.get("/employees-with-categories")
def get_employees_with_categories(db: Session = Depends(get_db)):
    employees = db.query(Employee).all()
    return [{"id": e.id, "personal_nr": e.personal_nr, "name": f"{e.first_name} {e.last_name}", "tracking_mode": e.tracking_mode or "C", "category": e.tracking_mode or "C", "hourly_rate": e.hourly_rate, "hourly_rate_standard": e.hourly_rate_standard, "email": e.user.email if e.user else f"{e.personal_nr.lower()}@seda24.de"} for e in employees]

@router.put("/update-category")
def update_category(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    emp = db.query(Employee).filter(Employee.id == data["employee_id"]).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    emp_user = db.query(User).filter(User.id == emp.user_id).first()
    if not emp_user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")
    
    new_category = data.get("tracking_mode", "C")
    emp_user.category = new_category
    
    if new_category == "C":
        emp.gps_required = data.get("gps_required", True)
    else:
        emp.gps_required = False
    
    db.commit()
    return {"status": "ok", "message": f"Kategorie auf {new_category} gesetzt"}

# ========== NEUE DATUMSBASIERTE SCHEDULE FUNKTIONEN ==========

@router.get("/schedules")
def get_all_schedules(
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db), 
    admin = Depends(verify_admin)
):
    """Hole alle Schedules, optional gefiltert nach Datum"""
    query = db.query(Schedule)
    
    if start_date:
        query = query.filter(Schedule.date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        query = query.filter(Schedule.date <= datetime.strptime(end_date, "%Y-%m-%d").date())
    
    schedules = query.all()
    result = []
    
    for s in schedules:
        emp = s.employee
        obj = db.query(Object).filter(Object.id == s.object_id).first()
        result.append({
            "id": s.id,
            "employee_id": s.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "object_id": s.object_id,
            "object_name": obj.name if obj else f"Objekt {s.object_id}",
            "date": s.date.isoformat() if s.date else None,
            "weekday": s.weekday,  # Behalten für Kompatibilität
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else "",
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else "",
            "planned_hours": s.planned_hours,
            "status": s.status
        })
    return result

@router.post("/schedules")
def create_schedule(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Erstelle neue Schedule mit Datum"""
    from datetime import time
    
    # Parse date
    schedule_date = datetime.strptime(data["date"], "%Y-%m-%d").date() if "date" in data else None
    
    # Parse times
    start_parts = data["start_time"].split(":")
    end_parts = data["end_time"].split(":")
    
    # Calculate weekday from date (für Kompatibilität)
    weekday = schedule_date.weekday() if schedule_date else data.get("weekday", 0)
    
    # Berechne die Stunden automatisch
    start = datetime.strptime(data["start_time"], "%H:%M")
    end = datetime.strptime(data["end_time"], "%H:%M")
    
    # Falls Ende vor Start ist (über Mitternacht), addiere einen Tag
    if end < start:
        end += timedelta(days=1)
    
    # Berechne Stunden als Dezimalzahl
    hours_diff = (end - start).total_seconds() / 3600
    
    schedule = Schedule(
        employee_id=data["employee_id"],
        object_id=data["object_id"],
        date=schedule_date,
        weekday=weekday,
        start_time=time(int(start_parts[0]), int(start_parts[1])),
        end_time=time(int(end_parts[0]), int(end_parts[1])),
        planned_hours=hours_diff,  # Automatisch berechnet!
        status=data.get("status", "normal")
    )
    
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    
    return {"status": "ok", "id": schedule.id}

@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Update Schedule mit Datum"""
    from datetime import time
    
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404)
    
    # Update date if provided
    if "date" in data:
        schedule.date = datetime.strptime(data["date"], "%Y-%m-%d").date()
        # Update weekday based on date
        schedule.weekday = schedule.date.weekday()
    
    if "start_time" in data:
        start_parts = data["start_time"].split(":")
        schedule.start_time = time(int(start_parts[0]), int(start_parts[1]))
    
    if "end_time" in data:
        end_parts = data["end_time"].split(":")
        schedule.end_time = time(int(end_parts[0]), int(end_parts[1]))
    
    # Wenn Start- oder Endzeit geändert wurde, berechne planned_hours neu
    if "start_time" in data or "end_time" in data:
        # Hole aktuelle Zeiten (entweder neue oder bestehende)
        start_str = data.get("start_time", schedule.start_time.strftime("%H:%M"))
        end_str = data.get("end_time", schedule.end_time.strftime("%H:%M"))
        
        # Berechne die Stunden automatisch
        start = datetime.strptime(start_str, "%H:%M")
        end = datetime.strptime(end_str, "%H:%M")
        
        # Falls Ende vor Start ist (über Mitternacht), addiere einen Tag
        if end < start:
            end += timedelta(days=1)
        
        # Berechne und setze Stunden
        schedule.planned_hours = (end - start).total_seconds() / 3600
    
    if "object_id" in data:
        schedule.object_id = data["object_id"]
    if "employee_id" in data:
        schedule.employee_id = data["employee_id"]
    if "status" in data:
        schedule.status = data["status"]
    
    db.commit()
    return {"status": "ok"}

@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404)
    
    db.delete(schedule)
    db.commit()
    return {"status": "ok"}

# ===== NEUE ENDPOINTS FÜR EDITIERBAREN DIENSTPLAN =====

@router.get("/schedules/week")
def get_week_schedule(
    week_start: str = None,
    week_offset: int = Query(0, description="Wochen-Offset (0=aktuelle Woche)"),
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Hole Wochenplan für ein bestimmtes Datum"""
    
    # Parse start date or use current week
    if week_start:
        start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
    else:
        today = date.today()
        # Get Monday of current week
        start_date = today - timedelta(days=today.weekday())
        start_date += timedelta(weeks=week_offset)
    
    # Calculate end of week (Sunday)
    end_date = start_date + timedelta(days=6)
    
    # Get all schedules for this week
    schedules = db.query(Schedule).filter(
        and_(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        )
    ).all()
    
    
    # Hole Standard-Zeiten für Objekte
    from sqlalchemy import text
    standard_times_query = text("SELECT object_id, start_time, end_time, standard_hours FROM object_standard_times")
    standard_times_result = db.execute(standard_times_query).fetchall()
    standard_times_dict = {row[0]: {"start": str(row[1])[:5] if row[1] else "06:00", "end": str(row[2])[:5] if row[2] else "14:00", "hours": float(row[3]) if row[3] else 8.0} for row in standard_times_result}
    # Get all employees and objects for the UI
    employees = db.query(Employee).filter(Employee.personal_nr != 'A0001').all()
    objects = db.query(Object).all()
    
    # Organize by day
    days_data = []
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        day_schedules = [s for s in schedules if s.date == current_date]
        
        day_name = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'][i]
        
        schedules_data = []
        for s in day_schedules:
            schedules_data.append({
                'id': s.id,
                'employee_id': s.employee_id,
                'employee_name': f"{s.employee.first_name} {s.employee.last_name}",
                'object_id': s.object_id,
                'object_name': s.object.name if s.object else f"Objekt {s.object_id}",
                'start_time': s.start_time.strftime("%H:%M") if s.start_time else "",
                'end_time': s.end_time.strftime("%H:%M") if s.end_time else "",
                'planned_hours': s.planned_hours,
                'status': s.status or 'normal',
                'replacement_for': s.replacement_for
            })
        
        days_data.append({
            'date': current_date.isoformat(),
            'weekday': day_name,
            'weekday_index': i,
            'schedules': schedules_data
        })
    
    return {
        'week_start': start_date.isoformat(),
        'week_end': end_date.isoformat(),
        'week_number': start_date.isocalendar()[1],
        'year': start_date.year,
        'days': days_data,
        'employees': [
            {
                'id': emp.id,
                'name': f"{emp.first_name} {emp.last_name}",
                'personal_nr': emp.personal_nr,
                'category': getattr(emp, 'tracking_mode', 'C')
            } for emp in employees
        ],
        'objects': [
            {
                'id': obj.id,
                'name': obj.name,
                'customer_name': obj.customer.name if obj.customer else '',
                'gps_lat': obj.gps_lat,
                'start_time': standard_times_dict.get(obj.id, {}).get('start', '06:00'),
                'end_time': standard_times_dict.get(obj.id, {}).get('end', '14:00'),
                'gps_lng': obj.gps_lng
            } for obj in objects
        ]
    }

@router.post("/schedules/copy-week")
def copy_week_schedule(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Kopiere eine komplette Woche in eine neue Woche"""
    source_week = datetime.fromisoformat(data["source_week"].split('T')[0]).date()
    target_week = datetime.fromisoformat(data["target_week"].split('T')[0]).date()
    
    # Get source week schedules
    source_end = source_week + timedelta(days=6)
    source_schedules = db.query(Schedule).filter(
        and_(
            Schedule.date >= source_week,
            Schedule.date <= source_end
        )
    ).all()
    
    # Calculate day difference
    day_diff = (target_week - source_week).days
    
    # Copy each schedule
    copied = 0
    for source in source_schedules:
        
        # Check if schedule already exists
        new_date = source.date + timedelta(days=day_diff)
        
        existing = db.query(Schedule).filter(
            and_(
                Schedule.date == new_date,
                Schedule.employee_id == source.employee_id,
                Schedule.start_time == source.start_time
            )
        ).first()
        
        if not existing:
            new_schedule = Schedule(
                employee_id=source.employee_id,
                object_id=source.object_id,
                date=new_date,
                weekday=new_date.weekday(),
                start_time=source.start_time,
                end_time=source.end_time,
                planned_hours=source.planned_hours,
                status=source.status or "normal"
            )
            db.add(new_schedule)
            copied += 1
    
    db.commit()
    
    return {
        "status": "ok",
        "copied": copied,
        "message": f"{copied} Schichten wurden kopiert"
    }

@router.post("/schedules/bulk-update")
def bulk_update_schedules(
    updates: List[dict],
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Mehrere Schichten auf einmal aktualisieren"""
    results = []
    
    for update in updates:
        schedule_id = update.get('id')
        
        if schedule_id:
            schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
            if not schedule:
                results.append({'id': schedule_id, 'status': 'not_found'})
                continue
        else:
            schedule = Schedule()
            db.add(schedule)
        
        # Update all provided fields
        if 'date' in update:
            schedule.date = datetime.strptime(update['date'], "%Y-%m-%d").date()
            schedule.weekday = schedule.date.weekday()
        if 'employee_id' in update:
            schedule.employee_id = update['employee_id']
        if 'object_id' in update:
            schedule.object_id = update['object_id']
        if 'start_time' in update:
            parts = update['start_time'].split(':')
            schedule.start_time = time(int(parts[0]), int(parts[1]))
        if 'end_time' in update:
            parts = update['end_time'].split(':')
            schedule.end_time = time(int(parts[0]), int(parts[1]))
        if 'planned_hours' in update:
            schedule.planned_hours = update['planned_hours']
        if 'status' in update:
            schedule.status = update['status']
        if 'replacement_for' in update:
            schedule.replacement_for = update['replacement_for']
        
        results.append({'id': schedule.id, 'status': 'updated'})
    
    db.commit()
    return {'status': 'ok', 'results': results}

@router.post("/schedules/replacement")
def create_replacement(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Erstelle Vertretung für Urlaub/Krankheit"""
    original_schedule_id = data.get('original_schedule_id')
    replacement_employee_id = data.get('replacement_employee_id')
    reason = data.get('reason', 'vertretung')
    
    original = db.query(Schedule).filter(Schedule.id == original_schedule_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Original-Schicht nicht gefunden")
    
    original.status = reason
    
    replacement = Schedule(
        employee_id=replacement_employee_id,
        object_id=original.object_id,
        date=original.date,  # NEU: Verwende Datum statt weekday
        weekday=original.weekday,
        start_time=original.start_time,
        end_time=original.end_time,
        planned_hours=original.planned_hours,
        status='vertretung',
        replacement_for=original.employee_id
    )
    
    db.add(replacement)
    db.commit()
    
    return {
        'status': 'ok',
        'original_id': original.id,
        'replacement_id': replacement.id,
        'message': f'Vertretung erstellt für {reason}'
    }

@router.post("/schedules/quick-assign")
def quick_assign_schedule(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Schnellzuweisung: Mitarbeiter zu Objekt für bestimmtes Datum"""
    employee_id = data.get('employee_id')
    object_id = data.get('object_id')
    assign_date = datetime.strptime(data.get('date'), "%Y-%m-%d").date() if 'date' in data else None
    weekday = assign_date.weekday() if assign_date else data.get('weekday', 0)
    start_time_str = data.get('start_time', '06:00')
    end_time_str = data.get('end_time', '14:00')
    
    start_parts = start_time_str.split(':')
    end_parts = end_time_str.split(':')
    start_h = int(start_parts[0])
    start_m = int(start_parts[1])
    end_h = int(end_parts[0])
    end_m = int(end_parts[1])
    
    planned_hours = (end_h - start_h) + (end_m - start_m) / 60
    
    existing = db.query(Schedule).filter(
        and_(
            Schedule.employee_id == employee_id,
            Schedule.object_id == object_id,
            Schedule.date == assign_date
        )
    ).first()
    
    if existing:
        existing.start_time = time(start_h, start_m)
        existing.end_time = time(end_h, end_m)
        existing.planned_hours = planned_hours
        message = "Schicht aktualisiert"
    else:
        schedule = Schedule(
            employee_id=employee_id,
            object_id=object_id,
            date=assign_date,
            weekday=weekday,
            start_time=time(start_h, start_m),
            end_time=time(end_h, end_m),
            planned_hours=planned_hours,
            status='normal'
        )
        db.add(schedule)
        message = "Schicht erstellt"
    
    db.commit()
    
    return {'status': 'ok', 'message': message}

@router.get("/schedules/conflicts")
def check_schedule_conflicts(
    week_start: str = None,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Prüfe auf Konflikte im Dienstplan"""
    
    if week_start:
        start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
    else:
        today = date.today()
        start_date = today - timedelta(days=today.weekday())
    
    end_date = start_date + timedelta(days=6)
    
    schedules = db.query(Schedule).filter(
        and_(
            Schedule.date >= start_date,
            Schedule.date <= end_date
        )
    ).all()
    
    conflicts = []
    employee_schedules = defaultdict(list)
    
    for schedule in schedules:
        key = f"{schedule.employee_id}_{schedule.date}"
        employee_schedules[key].append(schedule)
    
    for key, schichten in employee_schedules.items():
        if len(schichten) > 1:
            schichten.sort(key=lambda s: s.start_time or time(0, 0))
            
            for i in range(len(schichten) - 1):
                current = schichten[i]
                next_shift = schichten[i + 1]
                
                if current.end_time and next_shift.start_time:
                    if current.end_time > next_shift.start_time:
                        emp = current.employee
                        conflicts.append({
                            'type': 'zeitüberschneidung',
                            'employee': f"{emp.first_name} {emp.last_name}",
                            'date': current.date.isoformat(),
                            'shift1': {
                                'object': current.object.name if current.object else f"Objekt {current.object_id}",
                                'time': f"{current.start_time.strftime('%H:%M')}-{current.end_time.strftime('%H:%M')}"
                            },
                            'shift2': {
                                'object': next_shift.object.name if next_shift.object else f"Objekt {next_shift.object_id}",
                                'time': f"{next_shift.start_time.strftime('%H:%M')}-{next_shift.end_time.strftime('%H:%M')}"
                            }
                        })
    
    return {
        'status': 'ok',
        'conflict_count': len(conflicts),
        'conflicts': conflicts
    }

# ===== RESTLICHE ENDPOINTS BLEIBEN UNVERÄNDERT =====

@router.post("/employees")
def create_employee(employee_data: dict, db: Session = Depends(get_db)):
    # Neuen User erstellen
    user = User(
        email=employee_data.get('email'),
        role='mitarbeiter',
        password_hash='temp123'  # Temporäres Passwort
    )
    db.add(user)
    db.flush()
    
    # Employee erstellen
    employee = Employee(
        user_id=user.id,
        personal_nr=employee_data.get('personal_nr'),
        first_name=employee_data.get('first_name'),
        last_name=employee_data.get('last_name'),
        hourly_rate=float(employee_data.get('hourly_rate', 15)),
        tracking_mode=employee_data.get('tracking_mode', 'C'),
        is_active=True
    )
    db.add(employee)
    db.commit()
    return {"status": "success", "message": "Mitarbeiter erstellt"}


@router.put("/employees/{employee_id:int}")
def update_employee_by_id(employee_id: int, employee_data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    if 'first_name' in employee_data:
        employee.first_name = employee_data['first_name']
    if 'last_name' in employee_data:
        employee.last_name = employee_data['last_name']
    if 'hourly_rate' in employee_data:
        employee.hourly_rate = float(employee_data['hourly_rate'])
    if 'tracking_mode' in employee_data:
        employee.tracking_mode = employee_data['tracking_mode']
    if 'email' in employee_data and employee.user:
        employee.user.email = employee_data['email']
    db.commit()
    return {"status": "success", "message": "Mitarbeiter aktualisiert"}
@router.put("/employees/{personal_nr}")
def update_employee(personal_nr: str, employee_data: dict, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.personal_nr == personal_nr).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Update alle Employee-Felder
    if 'first_name' in employee_data:
        employee.first_name = employee_data['first_name']
    if 'last_name' in employee_data:
        employee.last_name = employee_data['last_name']
    if 'hourly_rate' in employee_data:
        employee.hourly_rate = float(employee_data['hourly_rate'])
    if 'daily_hours' in employee_data:
        # Daily hours ist nicht in der DB, aber wir können es ignorieren
        pass
    if "tracking_mode" in employee_data:
        employee.tracking_mode = employee_data["tracking_mode"]
    if "address" in employee_data:
        employee.address = employee_data["address"]
    if "kuerzel" in employee_data:
        employee.kuerzel = employee_data["kuerzel"]
    if "employment_type" in employee_data:
        employee.employment_type = employee_data["employment_type"]
    if "gps_required" in employee_data:
        employee.gps_required = bool(employee_data["gps_required"])
        employee.gps_required = bool(employee_data['gps_required'])
    
    # Update User E-Mail (ACHTUNG: Das ist der Login!)
    if 'email' in employee_data and employee.user:
        employee.user.email = employee_data['email']

    db.commit()
    return {"status": "success", "message": "Mitarbeiter aktualisiert - Bei E-Mail-Änderung neuer Login nötig!"}

# OBJEKT-VERWALTUNG
@router.get("/objects")
def get_all_objects(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Alle Objekte mit Kundennamen abrufen"""
    objects = db.query(Object).filter(Object.is_active == True).all()
    result = []
    for obj in objects:
        customer = db.query(Customer).filter(Customer.id == obj.customer_id).first()
        result.append({
            "id": obj.id,
            "name": obj.name,
            "customer_name": customer.name if customer else "Unbekannt",
            "customer_id": obj.customer_id,
            "address": obj.address,
            "cleaning_type": obj.cleaning_type,
            "radius_m": obj.radius_m
        })
    return result

@router.post("/objects")
def create_object(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Neues Objekt anlegen"""
    new_object = Object(
        name=data["name"],
        customer_id=data.get("customer_id", 1),
        address=data.get("address", ""),
        cleaning_type=data.get("cleaning_type", "Unterhaltsreinigung"),
        radius_m=data.get("radius_m", 100),
        is_active=True
    )
    db.add(new_object)
    db.commit()
    return {"status": "ok", "id": new_object.id}

@router.put("/objects/{object_id}")
def update_object(object_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Objekt bearbeiten"""
    obj = db.query(Object).filter(Object.id == object_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    
    if "name" in data:
        obj.name = data["name"]
    if "address" in data:
        obj.address = data["address"]
    if "cleaning_type" in data:
        obj.cleaning_type = data["cleaning_type"]
    
    db.commit()
    return {"status": "ok"}

@router.get("/customers")
def get_all_objects(db: Session = Depends(get_db), ):
    """Alle Kunden abrufen"""
    objects = db.query(Object).all()
    return [{"id": o.id, "name": o.name} for o in objects]

@router.get("/objects-list")
def get_objects_for_display(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Objekte für AdminDashboard Anzeige"""
    objects = db.query(Object).filter(Object.is_active == True).all()
    return [
        {
            "id": obj.id,
            "name": obj.name,
            "address": obj.address,
            "phone": obj.phone,
            "email": obj.email,
            "monthly_amount_netto": obj.monthly_amount_netto,
            "invoice_type": obj.invoice_type
        }
        for obj in objects
    ]

@router.get("/test-objects")
def get_test_objects(db: Session = Depends(get_db)):
    """Test-Endpoint ohne Auth"""
    objects = db.query(Object).all()
    return [{"id": o.id, "name": o.name, "address": o.address} for o in objects]
@router.get("/bookings/all")
def get_all_bookings(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import TimeEntry, Employee, Object
    entries = db.query(TimeEntry).order_by(TimeEntry.check_in.desc()).limit(1000).all()
    return [{
        "id": e.id,
        "employee_id": e.employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name}" if (emp := db.query(Employee).filter(Employee.id == e.employee_id).first()) else "Unbekannt",
        "object_id": e.object_id,
        "object_name": obj.name if (obj := db.query(Object).filter(Object.id == e.object_id).first()) else "Unbekannt",
        "check_in": e.check_in.isoformat() if e.check_in else None,
        "check_out": e.check_out.isoformat() if e.check_out else None,
        "billed_hours": float((e.check_out - e.check_in).total_seconds() / 3600) if (e.check_in and e.check_out) else (float(e.billed_hours) if hasattr(e, 'billed_hours') and e.billed_hours else 0),
        "hourly_rate": float(e.hourly_rate) if e.hourly_rate else 0,
        "service_type": e.service_type,
        "notes": e.notes,
        "is_manual_entry": e.is_manual_entry
    } for e in entries]

@router.put("/bookings/{booking_id}")
def update_booking(booking_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import TimeEntry
    from datetime import datetime
    
    entry = db.query(TimeEntry).filter(TimeEntry.id == booking_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    
    # Update Felder
    if 'check_in' in data:
        entry.check_in = datetime.fromisoformat(data['check_in'].replace('Z', '+00:00'))
    if 'check_out' in data:
        entry.check_out = datetime.fromisoformat(data['check_out'].replace('Z', '+00:00'))
    if 'object_id' in data:
        entry.object_id = data['object_id']
    if 'service_type' in data:
        entry.service_type = data['service_type']
    if 'notes' in data:
        entry.notes = data['notes']
    if 'employee_id' in data:
        entry.employee_id = data['employee_id']
    if 'hourly_rate' in data:
        entry.hourly_rate = data['hourly_rate']
    if 'billed_hours' in data:
        entry.billed_hours = data['billed_hours']
    
    db.commit()
    return {"status": "ok", "message": "Buchung aktualisiert"}

@router.delete("/bookings/{booking_id}")
def delete_booking(booking_id: int, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import TimeEntry
    
    entry = db.query(TimeEntry).filter(TimeEntry.id == booking_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    
    db.delete(entry)
    db.commit()

@router.post("/bookings/manual")
def create_manual_booking(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import TimeEntry, Employee, Object
    from datetime import datetime
    
    # Validierung
    employee = db.query(Employee).filter(Employee.id == data['employee_id']).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Prüfe ob Kunde oder einmalig
    if data.get('object_id'):
        obj = db.query(Object).filter(Object.id == data['object_id']).first()
        if not obj:
            raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
        object_id = data['object_id']
        custom_object_name = None
    else:
        object_id = None
        custom_object_name = data.get('custom_object_name', 'Einmaliger Kunde')
    
    # Erstelle TimeEntry
    entry = TimeEntry(
        employee_id=data['employee_id'],
        object_id=object_id,
        custom_object_name=custom_object_name,
        check_in=datetime.fromisoformat(data['check_in']),
        check_out=datetime.fromisoformat(data['check_out']),
        hourly_rate=data['hourly_rate'],
        service_type=data.get('service_type', 'Unterhaltsreinigung'),
        notes=data.get('notes', ''),
        is_manual_entry=True
    )
    
    # Berechne Stunden
    duration = (entry.check_out - entry.check_in).total_seconds() / 3600
    entry.billed_hours = duration
    
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    return {"status": "ok", "message": "Buchung erstellt", "id": entry.id}
    return {"status": "ok", "message": "Buchung gelöscht"}
"""
SEDA24 - Neue Admin-Endpoints für PDF-Abrechnungen
Diese Endpoints MÜSSEN zu deiner bestehenden admin.py HINZUGEFÜGT werden!
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.pdf_generator import PDFGenerator
import os
import zipfile
from io import BytesIO
from typing import List
from pydantic import BaseModel

# Deine bestehende verify_admin Funktion wird verwendet!

# ========== SCHEMAS ==========

class PDFRequest(BaseModel):
    """Request für einzelne PDF-Generation"""
    employee_id: int
    year: int
    month: int

class BulkPDFRequest(BaseModel):
    """Request für Bulk-PDF-Generation"""
    employee_ids: List[int]
    year: int
    month: int
    include_zeitnachweis: bool = True
    include_kilometer: bool = True


# ========== ENDPOINTS ==========

@router.post("/generate-pdf-zeitnachweis")
def generate_zeitnachweis_pdf(
    request: PDFRequest,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Generiert Zeitnachweis-PDF für einen Mitarbeiter"""
    try:
        generator = PDFGenerator(db)
        pdf_path = generator.generate_zeitnachweis(
            request.employee_id,
            request.year,
            request.month
        )
        
        # PDF zurückgeben
        return FileResponse(
            pdf_path,
            media_type='application/pdf',
            filename=os.path.basename(pdf_path)
        )
        
    except Exception as e:
        print(f"PDF FEHLER: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-pdf-kilometer")
def generate_kilometer_pdf(
    request: PDFRequest,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Generiert Kilometer-PDF für einen Mitarbeiter"""
    try:
        generator = PDFGenerator(db)
        pdf_path = generator.generate_kilometer(
            request.employee_id,
            request.year,
            request.month
        )
        
        return FileResponse(
            pdf_path,
            media_type='application/pdf',
            filename=os.path.basename(pdf_path)
        )
        
    except Exception as e:
        print(f"PDF FEHLER: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-pdf-komplett")
def generate_komplett_pdf(
    request: PDFRequest,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Generiert Zeitnachweis + Kilometer als ZIP"""
    try:
        generator = PDFGenerator(db)
        
        # Beide PDFs generieren
        zeit_pdf = generator.generate_zeitnachweis(
            request.employee_id,
            request.year,
            request.month
        )
        km_pdf = generator.generate_kilometer(
            request.employee_id,
            request.year,
            request.month
        )
        
        # ZIP erstellen
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(zeit_pdf, os.path.basename(zeit_pdf))
            zip_file.write(km_pdf, os.path.basename(km_pdf))
        
        zip_buffer.seek(0)
        
        # Mitarbeiter-Name für Dateiname
        from app.models.models import Employee
        emp = db.query(Employee).filter(Employee.id == request.employee_id).first()
        filename = f"SEDA24_Komplett_{emp.first_name}_{emp.last_name}_{request.month:02d}_{request.year}.zip"
        
        return StreamingResponse(
            zip_buffer,
            media_type='application/zip',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        print(f"PDF FEHLER: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-pdf-bulk")
def generate_bulk_pdfs(
    request: BulkPDFRequest,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Generiert PDFs für mehrere Mitarbeiter als ZIP"""
    try:
        generator = PDFGenerator(db)
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for emp_id in request.employee_ids:
                try:
                    # Zeitnachweis
                    if request.include_zeitnachweis:
                        zeit_pdf = generator.generate_zeitnachweis(emp_id, request.year, request.month)
                        zip_file.write(zeit_pdf, os.path.basename(zeit_pdf))
                    
                    # Kilometer
                    if request.include_kilometer:
                        km_pdf = generator.generate_kilometer(emp_id, request.year, request.month)
                        zip_file.write(km_pdf, os.path.basename(km_pdf))
                        
                except Exception as e:
                    print(f"PDF FEHLER: {e}")
                    # Fehler bei einzelnem MA nicht abbrechen lassen
                    print(f"Fehler bei MA {emp_id}: {e}")
                    continue
        
        zip_buffer.seek(0)
        
        # Dateiname
        ma_count = len(request.employee_ids)
        filename = f"SEDA24_Bulk_{ma_count}_MA_{request.month:02d}_{request.year}.zip"
        
        return StreamingResponse(
            zip_buffer,
            media_type='application/zip',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )
        
    except Exception as e:
        print(f"PDF FEHLER: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/employees-for-pdf")
def get_employees_for_pdf(
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Gibt Liste aller Mitarbeiter für PDF-Dropdown zurück"""
    from app.models.models import Employee
    
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    
    return [
        {
            "id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}",
            "personal_nr": emp.personal_nr
        }
        for emp in employees
    ]
# KM-Journal Endpoints - IN admin.py EINFÜGEN

@router.get("/km-journal/all")
def get_all_km_entries(
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Holt alle KM-Einträge für Journal"""
    from sqlalchemy import text
    
    result = db.execute(text("""
        SELECT 
            k.id,
            k.employee_id,
            e.first_name || ' ' || e.last_name as employee_name,
            k.object_id,
            o.name as object_name,
            k.date as date,
            k.distance_km,
            k.amount,
            k.is_billable,
            k.is_longest_trip,
            k.time_entry_id
        FROM km_daily_entries k
        JOIN employees e ON k.employee_id = e.id
        LEFT JOIN objects o ON k.object_id = o.id
        ORDER BY k.date DESC, k.employee_id
    """)).fetchall()
    
    return [dict(row._mapping) for row in result]

@router.post("/km-journal/add")
def add_km_entry(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Fügt manuellen KM-Eintrag hinzu"""
    from sqlalchemy import text
    
    db.execute(text("""
        INSERT INTO km_daily_entries 
        (employee_id, object_id, booking_date, distance_km, amount, is_billable)
        VALUES (:emp, :obj, :date, :km, :amt, :bill)
    """), {
        "emp": data["employee_id"],
        "obj": data.get("object_id"),
        "date": data["booking_date"],
        "km": data["distance_km"],
        "emp_id": data.get("employee_id"),
        "obj_id": data.get("object_id"),
        "amt": float(data["distance_km"]) * 0.30,
        "bill": data.get("is_billable", True),
    })
    db.commit()
    return {"status": "ok"}

@router.delete("/km-journal/{entry_id}")
def delete_km_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Löscht KM-Eintrag"""
    from sqlalchemy import text
    
    db.execute(text("DELETE FROM km_daily_entries WHERE id = :id"), {"id": entry_id})
    db.commit()
    return {"status": "ok"}


# ==================== KM-VERWALTUNG ====================

@router.get("/km-distances/all")
def get_all_km_distances(
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Lädt ALLE Standard-Entfernungen"""
    from sqlalchemy import text
    
    result = db.execute(text("""
        SELECT 
            kd.id,
            kd.employee_id,
            kd.object_id,
            kd.distance_km,
            e.personal_nr,
            e.first_name || ' ' || e.last_name as employee_name,
            o.name as object_name,
            o.address as object_address
        FROM km_distances kd
        JOIN employees e ON e.id = kd.employee_id
        JOIN objects o ON o.id = kd.object_id
        ORDER BY e.last_name, o.name
    """))
    
    distances = []
    for row in result:
        distances.append({
            "id": row.id,
            "employee_id": row.employee_id,
            "object_id": row.object_id,
            "distance_km": float(row.distance_km),
            "personal_nr": row.personal_nr,
            "employee_name": row.employee_name,
            "object_name": row.object_name,
            "object_address": row.object_address or ""
        })
    
    return distances
@router.get("/km-distances/{employee_id}")
def get_km_distances(
    employee_id: int,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Lädt alle Standard-Entfernungen für einen Mitarbeiter"""
    from sqlalchemy import text
    
    result = db.execute(text("""
        SELECT 
            kd.id,
            kd.employee_id,
            kd.object_id,
            kd.distance_km,
            o.name as object_name,
            o.address as object_address
        FROM km_distances kd
        JOIN objects o ON o.id = kd.object_id
        WHERE kd.employee_id = :emp_id
        ORDER BY o.name
    """), {"emp_id": employee_id})
    
    distances = []
    for row in result:
        distances.append({
            "id": row.id,
            "employee_id": row.employee_id,
            "object_id": row.object_id,
            "distance_km": float(row.distance_km),
            "object_name": row.object_name,
            "object_address": row.object_address or ""
        })
    
    return distances

@router.put("/km-distances/{distance_id}")
def update_km_distance(
    distance_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Aktualisiert Standard-Entfernung"""
    from sqlalchemy import text
    
    db.execute(text("""
        UPDATE km_distances
        SET distance_km = :km,
            employee_id = :emp_id,
            object_id = :obj_id
        WHERE id = :id
    """), {
        "id": distance_id,
        "km": data["distance_km"],
        "emp_id": data.get("employee_id"),
        "obj_id": data.get("object_id")
    })
    db.commit()
    
    return {"status": "ok", "message": "Entfernung aktualisiert"}


@router.delete("/km-distances/{distance_id}")
def delete_km_distance(
    distance_id: int,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Löscht eine Standard-Entfernung"""
    distance = db.query(KmDistance).filter(KmDistance.id == distance_id).first()
    if not distance:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    
    db.delete(distance)
    db.commit()
    return {"message": "Gelöscht"}

@router.post("/km-distances")
def create_km_distance(
    distance: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Erstellt eine neue Standard-Entfernung"""
    # KmDistance is in models
    
    new_distance = KmDistance(
        employee_id=distance['employee_id'],
        object_id=distance['object_id'],
        distance_km=distance['distance_km'],
        rate_per_km=0.30
    )
    db.add(new_distance)
    db.commit()
    return {"message": "Erstellt", "id": new_distance.id}


@router.put("/km-journal/{entry_id}")
def update_km_entry(
    entry_id: int,
    distance_km: float = Query(...),
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """KM-Eintrag bearbeiten"""
    from sqlalchemy import text
    
    # Update mit SQL
    db.execute(text("""
        UPDATE km_daily_entries
        SET distance_km = :km,
            amount = :amount
        WHERE id = :id
    """), {
        "id": entry_id,
        "km": distance_km,
        "amount": distance_km * 0.30
    })
    db.commit()
    
    return {"message": "KM aktualisiert", "new_km": distance_km, "new_amount": distance_km * 0.30}
