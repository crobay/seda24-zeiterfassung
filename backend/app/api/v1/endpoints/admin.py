from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import date, datetime, timedelta, time
from typing import List, Optional
from jose import jwt
from app.db.database import get_db
from app.models.models import User, Employee, TimeEntry, Schedule, Object, Customer
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
        raise HTTPException(status_code=401)
    token = authorization.split(" ")[1]
    payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if user.role != "admin":
        raise HTTPException(status_code=403)
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

@router.get("/schedules")
def get_all_schedules(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    schedules = db.query(Schedule).all()
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
            "weekday": s.weekday,
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else "",
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else "",
            "planned_hours": s.planned_hours
        })
    return result

@router.post("/schedules")
def create_schedule(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from datetime import time, datetime, timedelta
    start_parts = data["start_time"].split(":")
    end_parts = data["end_time"].split(":")
    
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
        weekday=data["weekday"],
        start_time=time(int(start_parts[0]), int(start_parts[1])),
        end_time=time(int(end_parts[0]), int(end_parts[1])),
        planned_hours=hours_diff  # Automatisch berechnet!
    )
    db.add(schedule)
    db.commit()
    return {"status": "ok", "id": schedule.id}

@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from datetime import time, datetime, timedelta
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404)
    
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
    if "weekday" in data:
        schedule.weekday = data["weekday"]
def update_schedule(schedule_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from datetime import time
    
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404)
    
    if "start_time" in data:
        start_parts = data["start_time"].split(":")
        schedule.start_time = time(int(start_parts[0]), int(start_parts[1]))
    
    if "end_time" in data:
        end_parts = data["end_time"].split(":")
        schedule.end_time = time(int(end_parts[0]), int(end_parts[1]))
    
    if "planned_hours" in data:
        schedule.planned_hours = data["planned_hours"]
    
    if "object_id" in data:
        schedule.object_id = data["object_id"]
    
    if "weekday" in data:
        schedule.weekday = data["weekday"]
    
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
    week_offset: int = Query(0, description="Wochen-Offset (0=aktuelle Woche)"),
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Hole Dienstplan für eine komplette Woche"""
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week += timedelta(weeks=week_offset)
    
    schedules = db.query(Schedule).all()
    employees = db.query(Employee).filter(Employee.personal_nr != 'A0001').all()
    objects = db.query(Object).all()
    
    week_data = {
        'week_start': start_of_week.isoformat(),
        'week_number': start_of_week.isocalendar()[1],
        'year': start_of_week.year,
        'days': [],
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
                'gps_lng': obj.gps_lng
            } for obj in objects
        ]
    }
    
    for i in range(7):
        current_date = start_of_week + timedelta(days=i)
        day_name = WEEKDAY_NAMES[i]
        day_schedules = [s for s in schedules if s.weekday == i + 1]
        
        day_data = {
            'date': current_date.isoformat(),
            'weekday': day_name,
            'weekday_index': i,
            'schedules': []
        }
        
        for schedule in day_schedules:
            emp = schedule.employee
            obj = db.query(Object).filter(Object.id == schedule.object_id).first()
            
            day_data['schedules'].append({
                'id': schedule.id,
                'employee_id': schedule.employee_id,
                'employee_name': f"{emp.first_name} {emp.last_name}",
                'object_id': schedule.object_id,
                'object_name': obj.name if obj else f"Objekt {schedule.object_id}",
                'start_time': schedule.start_time.strftime("%H:%M") if schedule.start_time else "06:00",
                'end_time': schedule.end_time.strftime("%H:%M") if schedule.end_time else "14:00",
                'planned_hours': schedule.planned_hours,
                'status': getattr(schedule, 'status', 'normal'),
                'replacement_for': getattr(schedule, 'replacement_for', None)
            })
        
        week_data['days'].append(day_data)
    
    return week_data

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
        
        if 'employee_id' in update:
            schedule.employee_id = update['employee_id']
        if 'object_id' in update:
            schedule.object_id = update['object_id']
        if 'weekday' in update:
            weekday = update['weekday']
            if isinstance(weekday, str):
                schedule.weekday = WEEKDAY_MAP.get(weekday, 0)
            else:
                schedule.weekday = weekday
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

@router.post("/schedules/copy-week")
def copy_week_schedule(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Kopiere Dienstplan von einer Woche in eine andere"""
    source_week = data.get('source_week')
    target_week = data.get('target_week')
    
    if not source_week or not target_week:
        raise HTTPException(status_code=400, detail="source_week und target_week erforderlich")
    
    source_date = datetime.fromisoformat(source_week).date()
    target_date = datetime.fromisoformat(target_week).date()
    
    schedules = db.query(Schedule).all()
    copied_count = 0
    
    for schedule in schedules:
        existing = db.query(Schedule).filter(
            and_(
                Schedule.employee_id == schedule.employee_id,
                Schedule.object_id == schedule.object_id,
                Schedule.weekday == schedule.weekday
            )
        ).first()
        
        if not existing:
            new_schedule = Schedule(
                employee_id=schedule.employee_id,
                object_id=schedule.object_id,
                weekday=schedule.weekday,
                start_time=schedule.start_time,
                end_time=schedule.end_time,
                planned_hours=schedule.planned_hours,
                status='normal'
            )
            db.add(new_schedule)
            copied_count += 1
    
    db.commit()
    
    return {
        'status': 'ok',
        'copied_count': copied_count,
        'message': f'{copied_count} Schichten kopiert'
    }

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
    """Schnellzuweisung: Mitarbeiter zu Objekt für bestimmten Tag"""
    employee_id = data.get('employee_id')
    object_id = data.get('object_id')
    weekday = data.get('weekday')
    start_time_str = data.get('start_time', '06:00')
    end_time_str = data.get('end_time', '14:00')
    
    if isinstance(weekday, str):
        weekday = WEEKDAY_MAP.get(weekday, 0)
    
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
            Schedule.weekday == weekday
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
    week_offset: int = Query(0),
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Prüfe auf Konflikte im Dienstplan"""
    conflicts = []
    schedules = db.query(Schedule).all()
    
    employee_schedules = defaultdict(list)
    
    for schedule in schedules:
        key = f"{schedule.employee_id}_{schedule.weekday}"
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
                            'weekday': WEEKDAY_NAMES.get(current.weekday, str(current.weekday)),
                            'shift1': {
                                'object': current.object_id,
                                'time': f"{current.start_time.strftime('%H:%M')}-{current.end_time.strftime('%H:%M')}"
                            },
                            'shift2': {
                                'object': next_shift.object_id,
                                'time': f"{next_shift.start_time.strftime('%H:%M')}-{next_shift.end_time.strftime('%H:%M')}"
                            }
                        })
    
    return {
        'status': 'ok',
        'conflict_count': len(conflicts),
        'conflicts': conflicts
    }
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

@router.get("/test-objects")
def get_test_objects(db: Session = Depends(get_db)):
    """Test-Endpoint ohne Auth"""
    objects = db.query(Object).all()
    return [{"id": o.id, "name": o.name, "address": o.address} for o in objects]
