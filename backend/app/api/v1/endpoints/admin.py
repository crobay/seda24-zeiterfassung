from fastapi import APIRouter, Depends, HTTPException, Header, Query, Body, Request
# KmDistance is in models
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, text
from datetime import date, datetime, timedelta, time
from typing import List, Optional
from jose import jwt
from app.db.database import get_db
from app.models.models import User, Employee, TimeEntry, Schedule, Object, Customer, KmDistance, ShiftChangeRequest, MasterScheduleEntry, CustomerRevenue, UserObjectAssignment, ObjectStandardTime, FinanceSetting, FixedCost, MonthlyFixedCost
import os
from dotenv import load_dotenv
from app.api.v1.endpoints.auth import get_current_user
from app.core.security import get_password_hash
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

def check_schedule_overlap(db: Session, employee_id: int, check_date, start_time, end_time, exclude_id: int = None):
    """Prueft ob ein MA am gleichen Tag eine ueberschneidende Schicht hat.
    Gibt None zurueck wenn OK, sonst einen Fehler-String."""
    filters = [
        Schedule.employee_id == employee_id,
        Schedule.date == check_date,
        Schedule.start_time < end_time,
        Schedule.end_time > start_time,
    ]
    if exclude_id:
        filters.append(Schedule.id != exclude_id)

    conflict = db.query(Schedule).filter(and_(*filters)).first()
    if conflict:
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        emp_name = f"{emp.first_name} {emp.last_name}" if emp else f"MA {employee_id}"
        obj = conflict.object
        obj_name = obj.name if obj else f"Objekt {conflict.object_id}"
        return (
            f"{emp_name} hat am {check_date.strftime('%d.%m.%Y')} bereits eine Schicht "
            f"bei {obj_name} ({conflict.start_time.strftime('%H:%M')}-{conflict.end_time.strftime('%H:%M')}). "
            f"Zeitueberschneidung!"
        )
    return None


def check_vacation_conflict(db: Session, employee_id: int, check_date):
    """Prueft ob ein MA an einem Datum Urlaub oder Abwesenheit hat.
    Gibt None zurueck wenn OK, sonst einen Warn-/Fehler-String."""
    from app.models.models import VacationRequest
    conflict = db.query(VacationRequest).filter(
        VacationRequest.employee_id == employee_id,
        VacationRequest.status == 'approved',
        VacationRequest.start_date <= check_date,
        VacationRequest.end_date >= check_date,
    ).first()
    if conflict:
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        emp_name = f"{emp.first_name} {emp.last_name}" if emp else f"MA {employee_id}"
        req_type = getattr(conflict, 'type', 'urlaub') or 'urlaub'
        label = "Urlaub" if req_type == 'urlaub' else "Abwesenheit"
        return (
            f"{emp_name} hat am {check_date.strftime('%d.%m.%Y')} {label} "
            f"({conflict.start_date.strftime('%d.%m.')}-{conflict.end_date.strftime('%d.%m.%Y')}). "
            f"Schicht kann nicht angelegt werden."
        )
    return None


def check_and_reset_confirmation(db, employee_id: int, schedule_date):
    """Prueft ob eine Monatsbestaetigung zurueckgesetzt werden muss,
    wenn eine neue Schicht nach Bestaetigung angelegt wird."""
    from app.models.models import MonthlyConfirmation, PushNotification
    conf = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee_id,
        MonthlyConfirmation.year == schedule_date.year,
        MonthlyConfirmation.month == schedule_date.month,
        MonthlyConfirmation.status.in_(['confirmed', 'disputed']),
    ).first()
    if conf:
        old_status = conf.status
        conf.status = 'pending'
        conf.sent_at = None
        conf.confirmed_at = None
        conf.dispute_reason = None
        # PushNotification-Duplikatschutz entfernen
        db.query(PushNotification).filter(
            PushNotification.employee_id == employee_id,
            PushNotification.notification_type == 'monthly_confirmation',
            PushNotification.created_at >= datetime.combine(
                date(schedule_date.year, schedule_date.month, 1), time(0, 0)),
        ).delete()
        db.commit()
        logger.info(f"MonthlyConfirmation reset: MA {employee_id}, "
                    f"{schedule_date.month}/{schedule_date.year}, war {old_status}")


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


def verify_admin_or_objektleiter(authorization: str = Header(None), db: Session = Depends(get_db)):
    """Admin oder Objektleiter verifizieren. Gibt User + zugewiesene Object-IDs zurueck."""
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
    if not user or user.role not in ('admin', 'objektleiter'):
        raise HTTPException(status_code=403, detail="Kein Zugriff")
    return user


def get_user_object_ids(db: Session, user: User):
    """Gibt die Object-IDs zurueck, auf die ein User Zugriff hat.
    Admin: None (= alle). Objektleiter: Liste der zugewiesenen IDs."""
    if user.role == 'admin':
        return None  # Alle
    assignments = db.query(UserObjectAssignment).filter(
        UserObjectAssignment.user_id == user.id,
        UserObjectAssignment.is_active == True,
    ).all()
    return [a.object_id for a in assignments]


@router.get("/dashboard/stats")
def get_stats(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import SickNote, VacationRequest, Message as MsgModel

    total = db.query(Employee).join(User).filter(User.role != "admin", Employee.is_active == True).count()
    active = db.query(TimeEntry).filter(
        TimeEntry.check_out == None,
        func.date(TimeEntry.check_in) == date.today()
    ).count()

    today_seconds = db.query(
        func.sum(
            func.greatest(
                func.extract('epoch', func.coalesce(TimeEntry.check_out, func.now()) - TimeEntry.check_in),
                0
            )
        )
    ).filter(
        func.date(TimeEntry.check_in) == date.today()
    ).scalar() or 0

    # Offene Punkte zaehlen
    pending_sick = db.query(SickNote).filter(SickNote.status == 'pending').count()
    pending_vacation = db.query(VacationRequest).filter(VacationRequest.status == 'pending').count()
    new_messages = db.query(MsgModel).filter(
        MsgModel.status == 'neu',
        MsgModel.sender_employee_id.isnot(None),
        MsgModel.parent_id.is_(None),
    ).count()

    # Heutige Schichten
    today_schedules = db.query(Schedule).filter(
        Schedule.date == date.today(),
        Schedule.status.in_(['normal', 'vertretung']),
    ).count()

    # Offene Push-Notifications (unbeantwortet)
    from app.models.models import PushNotification
    open_pushes = db.query(PushNotification).filter(
        PushNotification.response_status == 'pending',
        func.date(PushNotification.created_at) >= date.today() - timedelta(days=2),
    ).count()

    return {
        "active_employees": active,
        "paused_employees": 0,
        "offline_employees": total - active,
        "total_employees": total,
        "total_hours_today": round(today_seconds / 3600, 1),
        "pending_sick": pending_sick,
        "pending_vacation": pending_vacation,
        "new_messages": new_messages,
        "today_schedules": today_schedules,
        "open_pushes": open_pushes,
    }

@router.get("/live-status")
def get_live(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Live-Status: Aktive Schichten, heute gestempelt, kommende Schichten."""
    from app.models.models import TimeEntry, Employee, Object
    now = datetime.now()
    today = now.date()
    current_time = now.time()

    # 1. Aktive Dienstplan-Schichten
    active_schedules = db.query(Schedule).join(Employee).filter(
        Schedule.date == today,
        Schedule.start_time <= current_time,
        Schedule.end_time >= current_time,
        Schedule.status.in_(['normal', 'vertretung']),
        Employee.is_active == True,
    ).all()

    active = []
    for s in active_schedules:
        emp = s.employee
        obj = s.object
        minutes_since = int((now - datetime.combine(today, s.start_time)).total_seconds() // 60)
        active.append({
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "object_name": obj.name if obj else "?",
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
            "minutes_since": minutes_since,
            "is_driver": s.is_driver if s.is_driver else False,
        })

    # 2. Jetzt eingestempelt (offene time_entries ohne check_out)
    checked_in = db.execute(text("""
        SELECT te.id, te.check_in, te.object_id,
               e.first_name, e.last_name, e.personal_nr,
               COALESCE(o.name, te.custom_object_name, 'Unbekannt') as object_name
        FROM time_entries te
        JOIN employees e ON e.id = te.employee_id
        LEFT JOIN objects o ON o.id = te.object_id
        WHERE te.check_out IS NULL
          AND te.object_id != 999
        ORDER BY te.check_in
    """)).fetchall()

    stamped_in = []
    for row in checked_in:
        minutes = int((now - row.check_in).total_seconds() // 60)
        stamped_in.append({
            "employee_name": f"{row.first_name} {row.last_name}",
            "personal_nr": row.personal_nr,
            "object_name": row.object_name,
            "check_in": row.check_in.strftime("%H:%M"),
            "minutes_since": minutes,
        })

    # 3. Heute gestempelt/gebucht (abgeschlossene time_entries von heute)
    today_entries = db.execute(text("""
        SELECT te.id, te.check_in, te.check_out, te.billed_hours, te.is_manual_entry,
               e.first_name, e.last_name, e.personal_nr,
               COALESCE(o.name, te.custom_object_name, 'Unbekannt') as object_name
        FROM time_entries te
        JOIN employees e ON e.id = te.employee_id
        LEFT JOIN objects o ON o.id = te.object_id
        WHERE DATE(te.check_in) = :today
          AND te.check_out IS NOT NULL
          AND te.object_id != 999
        ORDER BY te.check_in DESC
    """), {"today": today}).fetchall()

    today_booked = []
    for row in today_entries:
        today_booked.append({
            "employee_name": f"{row.first_name} {row.last_name}",
            "personal_nr": row.personal_nr,
            "object_name": row.object_name,
            "check_in": row.check_in.strftime("%H:%M"),
            "check_out": row.check_out.strftime("%H:%M") if row.check_out else None,
            "billed_hours": round(float(row.billed_hours), 2) if row.billed_hours else 0,
            "is_manual": row.is_manual_entry or False,
        })

    # 4. Kommende Dienstplan-Schichten
    upcoming_schedules = db.query(Schedule).join(Employee).filter(
        Schedule.date == today,
        Schedule.start_time > current_time,
        Schedule.status.in_(['normal', 'vertretung']),
        Employee.is_active == True,
    ).order_by(Schedule.start_time).all()

    upcoming = []
    for s in upcoming_schedules:
        emp = s.employee
        obj = s.object
        upcoming.append({
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "object_name": obj.name if obj else "?",
            "start_time": s.start_time.strftime("%H:%M"),
            "end_time": s.end_time.strftime("%H:%M"),
        })

    return {
        "active": active,
        "active_count": len(active),
        "stamped_in": stamped_in,
        "stamped_in_count": len(stamped_in),
        "today_booked": today_booked,
        "today_booked_count": len(today_booked),
        "upcoming": upcoming,
        "upcoming_count": len(upcoming),
    }


@router.get("/badge-counts")
def get_badge_counts(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Badge-Zaehler fuer Mehr-Menue: Offene Punkte, Krank, Post, Urlaub."""
    from app.models.models import PushNotification, VacationRequest, Message as MsgModel, CorrectionRequest

    # Offene Punkte: abgelaufene Pushes + nicht-anwesend + Korrekturen + Shift-Requests
    expired_pushes = db.query(PushNotification).filter(
        PushNotification.status == 'expired',
        PushNotification.response_status.is_(None),
    ).count()
    not_present = db.query(PushNotification).filter(
        PushNotification.response_status == 'not_present',
    ).count()
    telegram_corrections = db.query(PushNotification).filter(
        PushNotification.response_status == 'correction',
    ).count()
    open_corrections = db.query(CorrectionRequest).filter(
        CorrectionRequest.status == 'pending',
    ).count()
    open_shift_requests = db.query(ShiftChangeRequest).filter(
        ShiftChangeRequest.status == 'pending',
    ).count()
    offene_punkte = expired_pushes + not_present + telegram_corrections + open_corrections + open_shift_requests

    # Krankmeldungen: pending krank-Meldungen
    krankmeldungen = db.query(ShiftChangeRequest).filter(
        ShiftChangeRequest.request_type == 'krank',
        ShiftChangeRequest.status == 'pending',
    ).count()

    # Posteingang: neue/ungelesene Nachrichten von MA
    posteingang = db.query(MsgModel).filter(
        MsgModel.status == 'neu',
        MsgModel.sender_employee_id.isnot(None),
        MsgModel.parent_id.is_(None),
    ).count()

    # Urlaub: pending Antraege
    urlaub = db.query(VacationRequest).filter(
        VacationRequest.status == 'pending',
    ).count()

    # Telegram: Kat-B MAs ohne Telegram-Verbindung
    from sqlalchemy import or_
    telegram = db.query(Employee).filter(
        Employee.tracking_mode == 'B',
        Employee.is_active == True,
        or_(Employee.telegram_chat_id.is_(None), Employee.telegram_chat_id == '0'),
    ).count()

    # Monatsbestaetigungen: unbestaetigte MAs im aktuellen Monat
    from app.models.models import MonthlyConfirmation
    now = datetime.now()
    total_bc = db.query(Employee).filter(
        Employee.is_active == True,
        Employee.tracking_mode.in_(['B', 'C']),
    ).count()
    confirmed_count = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.year == now.year,
        MonthlyConfirmation.month == now.month,
        MonthlyConfirmation.status == 'confirmed',
    ).count()
    monatsbestaetigung = max(0, total_bc - confirmed_count)

    return {
        "offene_punkte": offene_punkte,
        "krankmeldungen": krankmeldungen,
        "posteingang": posteingang,
        "urlaub": urlaub,
        "telegram": telegram,
        "monatsbestaetigung": monatsbestaetigung,
    }


@router.get("/employees-with-categories")
def get_employees_with_categories(include_inactive: bool = Query(False), db: Session = Depends(get_db)):
    query = db.query(Employee)
    if not include_inactive:
        query = query.filter(Employee.is_active == True)
    employees = query.all()
    return [{"id": e.id, "personal_nr": e.personal_nr, "name": f"{e.first_name} {e.last_name}", "first_name": e.first_name, "last_name": e.last_name, "tracking_mode": e.tracking_mode or "C", "category": e.tracking_mode or "C", "hourly_rate": e.hourly_rate, "hourly_rate_standard": e.hourly_rate_standard, "email": e.user.email if e.user else f"{e.personal_nr.lower()}@seda24.de", "is_active": e.is_active, "work_days_profile": e.work_days_profile} for e in employees]

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


@router.put("/employees/{employee_id}/work-days-profile")
def update_work_days_profile(employee_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Arbeitstagsprofil setzen. Erwartet {"work_days_profile": "0,1,2,3,4"} (Python: 0=Mo..6=So)."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    profile = data.get("work_days_profile")
    if profile is not None and profile != "":
        # Validierung: nur Ziffern 0-6, kommasepariert
        days = [d.strip() for d in str(profile).split(",") if d.strip()]
        for d in days:
            if d not in ("0", "1", "2", "3", "4", "5", "6"):
                raise HTTPException(status_code=400, detail=f"Ungueltiger Wochentag: {d}. Erlaubt: 0=Mo bis 6=So")
        emp.work_days_profile = ",".join(sorted(set(days), key=int))
    else:
        emp.work_days_profile = None
    db.commit()
    return {"status": "ok", "work_days_profile": emp.work_days_profile}


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
    
    # Urlaubs-/Abwesenheits-Check
    if schedule_date:
        vacation_msg = check_vacation_conflict(db, data["employee_id"], schedule_date)
        if vacation_msg:
            raise HTTPException(status_code=409, detail=vacation_msg)

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

    # Auto-Reset: Monatsbestaetigung zuruecksetzen falls MA schon bestaetigt hat
    if schedule_date:
        check_and_reset_confirmation(db, data["employee_id"], schedule_date)

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

    # Wenn Schicht einen Partner hat: Partner-Stunden + end_time wiederherstellen
    if schedule.partner_schedule_id:
        partner = db.query(Schedule).filter(Schedule.id == schedule.partner_schedule_id).first()
        if partner:
            if partner.original_planned_hours is not None:
                partner.planned_hours = partner.original_planned_hours
            if partner.original_end_time is not None:
                partner.end_time = partner.original_end_time
            partner.original_planned_hours = None
            partner.original_end_time = None
            partner.partner_schedule_id = None

    db.delete(schedule)
    db.commit()
    return {"status": "ok"}


@router.post("/schedules/split-shift")
def split_shift(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Schicht teilen: Partner-MA hinzufuegen, Stunden halbieren."""
    schedule_id = data.get("schedule_id")
    partner_employee_id = data.get("partner_employee_id")

    if not schedule_id or not partner_employee_id:
        raise HTTPException(status_code=400, detail="schedule_id und partner_employee_id erforderlich")

    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schicht nicht gefunden")

    if schedule.partner_schedule_id:
        raise HTTPException(status_code=400, detail="Schicht ist bereits geteilt")

    if schedule.employee_id == partner_employee_id:
        raise HTTPException(status_code=400, detail="Partner kann nicht der gleiche MA sein")

    original_hours = schedule.planned_hours or 0
    half_hours = round(original_hours / 2, 2)

    # Neue end_time berechnen: start_time + halbe Stunden
    start_dt = datetime.combine(date.today(), schedule.start_time)
    half_minutes = int(half_hours * 60)
    new_end_dt = start_dt + timedelta(minutes=half_minutes)
    new_end_time = new_end_dt.time()

    # Urlaubs-/Abwesenheits-Check fuer Partner
    if schedule.date:
        vacation_msg = check_vacation_conflict(db, partner_employee_id, schedule.date)
        if vacation_msg:
            raise HTTPException(status_code=409, detail=vacation_msg)

    # Overlap-Check fuer Partner mit neuer (halbierter) Zeit
    overlap_msg = check_schedule_overlap(db, partner_employee_id, schedule.date, schedule.start_time, new_end_time)
    if overlap_msg:
        raise HTTPException(status_code=409, detail=overlap_msg)

    # Partner-Schedule erstellen
    partner_schedule = Schedule(
        employee_id=partner_employee_id,
        object_id=schedule.object_id,
        weekday=schedule.weekday,
        date=schedule.date,
        start_time=schedule.start_time,
        end_time=new_end_time,
        planned_hours=half_hours,
        status=schedule.status,
        notes=schedule.notes,
        is_driver=True,
        is_last_shift_of_month=False,
        original_planned_hours=original_hours,
        original_end_time=schedule.end_time,
    )
    db.add(partner_schedule)
    db.flush()

    # Gegenseitig verknuepfen + Original end_time sichern
    schedule.original_planned_hours = original_hours
    schedule.original_end_time = schedule.end_time
    schedule.planned_hours = half_hours
    schedule.end_time = new_end_time
    schedule.partner_schedule_id = partner_schedule.id
    partner_schedule.partner_schedule_id = schedule.id

    db.commit()

    partner_emp = db.query(Employee).filter(Employee.id == partner_employee_id).first()
    partner_name = f"{partner_emp.first_name} {partner_emp.last_name}" if partner_emp else f"MA {partner_employee_id}"

    return {
        "status": "ok",
        "message": f"Schicht geteilt mit {partner_name}",
        "partner_schedule_id": partner_schedule.id,
        "hours_each": half_hours,
        "original_hours": original_hours,
    }


@router.post("/schedules/unsplit-shift")
def unsplit_shift(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Schicht-Teilung aufheben: Partner entfernen, Stunden wiederherstellen."""
    schedule_id = data.get("schedule_id")

    if not schedule_id:
        raise HTTPException(status_code=400, detail="schedule_id erforderlich")

    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schicht nicht gefunden")

    if not schedule.partner_schedule_id:
        raise HTTPException(status_code=400, detail="Schicht ist nicht geteilt")

    partner = db.query(Schedule).filter(Schedule.id == schedule.partner_schedule_id).first()

    # Original-Stunden und end_time wiederherstellen
    if schedule.original_planned_hours is not None:
        schedule.planned_hours = schedule.original_planned_hours
    if schedule.original_end_time is not None:
        schedule.end_time = schedule.original_end_time

    schedule.partner_schedule_id = None
    schedule.original_planned_hours = None
    schedule.original_end_time = None

    # Partner loeschen
    if partner:
        db.delete(partner)

    db.commit()
    return {"status": "ok", "message": "Schicht wieder einzeln", "restored_hours": schedule.planned_hours}

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
            # Fahrer-Status: Schedule-Wert hat Prioritaet, sonst aus Zuweisung
            driver_val = getattr(s, 'is_driver', None)
            if driver_val is None:
                from app.models.models import EmployeeObjectAssignment
                assign = db.query(EmployeeObjectAssignment).filter(
                    EmployeeObjectAssignment.employee_id == s.employee_id,
                    EmployeeObjectAssignment.object_id == s.object_id,
                    EmployeeObjectAssignment.is_active == True
                ).first()
                driver_val = assign.is_driver if assign else False
            # Partner-Daten laden
            partner_name = None
            partner_emp_id = None
            if getattr(s, 'partner_schedule_id', None):
                partner_sched = db.query(Schedule).filter(Schedule.id == s.partner_schedule_id).first()
                if partner_sched and partner_sched.employee:
                    partner_name = f"{partner_sched.employee.first_name} {partner_sched.employee.last_name}"
                    partner_emp_id = partner_sched.employee_id

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
                'replacement_for': s.replacement_for,
                'is_driver': bool(driver_val),
                'is_last_shift_of_month': bool(getattr(s, 'is_last_shift_of_month', False)),
                'notes': s.notes or '',
                'partner_schedule_id': getattr(s, 'partner_schedule_id', None),
                'original_planned_hours': getattr(s, 'original_planned_hours', None),
                'original_end_time': s.original_end_time.strftime("%H:%M") if getattr(s, 'original_end_time', None) else None,
                'partner_employee_name': partner_name,
                'partner_employee_id': partner_emp_id,
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
            # Urlaubs-/Abwesenheits-Check
            if check_vacation_conflict(db, source.employee_id, new_date):
                continue
            new_schedule = Schedule(
                employee_id=source.employee_id,
                object_id=source.object_id,
                date=new_date,
                weekday=new_date.weekday(),
                start_time=source.start_time,
                end_time=source.end_time,
                planned_hours=source.planned_hours,
                status=source.status or "normal",
                is_driver=source.is_driver
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

        # Felder temporaer berechnen fuer Overlap-Check
        new_date = datetime.strptime(update['date'], "%Y-%m-%d").date() if 'date' in update else schedule.date
        new_emp = update.get('employee_id', schedule.employee_id)
        if 'start_time' in update:
            sp = update['start_time'].split(':')
            new_start = time(int(sp[0]), int(sp[1]))
        else:
            new_start = schedule.start_time
        if 'end_time' in update:
            ep = update['end_time'].split(':')
            new_end = time(int(ep[0]), int(ep[1]))
        else:
            new_end = schedule.end_time

        # Overlap-Check (nur wenn zeitrelevante Felder geaendert werden)
        time_relevant = any(k in update for k in ('date', 'employee_id', 'start_time', 'end_time'))
        if time_relevant and new_date and new_start and new_end:
            overlap_msg = check_schedule_overlap(db, new_emp, new_date, new_start, new_end, schedule_id)
            if overlap_msg:
                db.rollback()
                raise HTTPException(status_code=409, detail=overlap_msg)

        # Update all provided fields
        if 'date' in update:
            schedule.date = new_date
            schedule.weekday = new_date.weekday()
        if 'employee_id' in update:
            schedule.employee_id = update['employee_id']
        if 'object_id' in update:
            schedule.object_id = update['object_id']
        if 'start_time' in update:
            schedule.start_time = new_start
        if 'end_time' in update:
            schedule.end_time = new_end
        # planned_hours automatisch neu berechnen wenn Zeiten geändert werden
        if ('start_time' in update or 'end_time' in update) and new_start and new_end:
            dt_start = datetime.combine(new_date or date.today(), new_start)
            dt_end = datetime.combine(new_date or date.today(), new_end)
            if dt_end < dt_start:
                dt_end += timedelta(days=1)
            schedule.planned_hours = (dt_end - dt_start).total_seconds() / 3600
        elif 'planned_hours' in update:
            schedule.planned_hours = update['planned_hours']
        if 'status' in update:
            schedule.status = update['status']
        if 'replacement_for' in update:
            schedule.replacement_for = update['replacement_for']
        if 'is_driver' in update:
            schedule.is_driver = update['is_driver']
        if 'is_last_shift_of_month' in update:
            schedule.is_last_shift_of_month = update['is_last_shift_of_month']
        if 'notes' in update:
            schedule.notes = update['notes']

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

    # Zeiten: von Original uebernehmen, Fallback auf Objekt-Standardzeiten
    r_start = original.start_time
    r_end = original.end_time
    r_hours = original.planned_hours

    if not r_start or not r_end:
        # Standardzeiten des Objekts fuer den Wochentag laden
        weekday = original.date.weekday() if original.date else original.weekday
        std = db.query(ObjectStandardTime).filter(
            ObjectStandardTime.object_id == original.object_id,
            ObjectStandardTime.weekday == weekday,
        ).first()
        if std and std.start_time and std.end_time:
            r_start = std.start_time
            r_end = std.end_time
            r_hours = std.standard_hours
        else:
            # Kein Wochentag-Eintrag: Fallback auf objects.start_time/end_time
            obj = db.query(Object).filter(Object.id == original.object_id).first()
            if obj and obj.start_time and obj.end_time:
                r_start = obj.start_time
                r_end = obj.end_time
                from datetime import datetime as dt_cls
                delta = dt_cls.combine(original.date, obj.end_time) - dt_cls.combine(original.date, obj.start_time)
                r_hours = round(delta.total_seconds() / 3600, 2)

    if not r_start or not r_end:
        raise HTTPException(
            status_code=400,
            detail="Fuer dieses Objekt sind keine Standardzeiten hinterlegt. Bitte Zeiten manuell eintragen."
        )

    replacement = Schedule(
        employee_id=replacement_employee_id,
        object_id=original.object_id,
        date=original.date,
        weekday=original.weekday,
        start_time=r_start,
        end_time=r_end,
        planned_hours=r_hours,
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
    new_start = time(start_h, start_m)
    new_end = time(end_h, end_m)

    existing = db.query(Schedule).filter(
        and_(
            Schedule.employee_id == employee_id,
            Schedule.object_id == object_id,
            Schedule.date == assign_date
        )
    ).first()

    # Urlaubs-/Abwesenheits-Check
    if assign_date:
        vacation_msg = check_vacation_conflict(db, employee_id, assign_date)
        if vacation_msg:
            raise HTTPException(status_code=409, detail=vacation_msg)

    # Overlap-Check: Pruefe ob MA zur selben Zeit schon eingeplant ist
    exclude_id = existing.id if existing else None
    overlap_msg = check_schedule_overlap(db, employee_id, assign_date, new_start, new_end, exclude_id)
    if overlap_msg:
        raise HTTPException(status_code=409, detail=overlap_msg)

    if existing:
        existing.start_time = new_start
        existing.end_time = new_end
        existing.planned_hours = planned_hours
        message = "Schicht aktualisiert"
    else:
        schedule = Schedule(
            employee_id=employee_id,
            object_id=object_id,
            date=assign_date,
            weekday=weekday,
            start_time=new_start,
            end_time=new_end,
            planned_hours=planned_hours,
            status='normal',
            notes=data.get('notes', ''),
            is_driver=data.get('is_driver', True),
        )
        db.add(schedule)
        message = "Schicht erstellt"

    db.commit()

    return {'status': 'ok', 'message': message}


@router.get("/schedules/month")
def get_month_schedule(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2024, le=2030),
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Hole Monatsplan fuer einen bestimmten Monat."""
    import calendar
    from app.models.models import EmployeeObjectAssignment

    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    schedules = db.query(Schedule).filter(
        and_(Schedule.date >= first_day, Schedule.date <= last_day)
    ).all()

    # Standard-Zeiten
    standard_times_query = text("SELECT object_id, start_time, end_time, standard_hours FROM object_standard_times")
    standard_times_result = db.execute(standard_times_query).fetchall()
    standard_times_dict = {row[0]: {"start": str(row[1])[:5] if row[1] else "06:00", "end": str(row[2])[:5] if row[2] else "14:00"} for row in standard_times_result}

    employees = db.query(Employee).filter(Employee.personal_nr != 'A0001').all()
    objects = db.query(Object).all()

    days_data = []
    current = first_day
    while current <= last_day:
        day_schedules = [s for s in schedules if s.date == current]
        day_name = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'][current.weekday()]

        schedules_data = []
        for s in day_schedules:
            driver_val = getattr(s, 'is_driver', None)
            if driver_val is None:
                assign = db.query(EmployeeObjectAssignment).filter(
                    EmployeeObjectAssignment.employee_id == s.employee_id,
                    EmployeeObjectAssignment.object_id == s.object_id,
                    EmployeeObjectAssignment.is_active == True
                ).first()
                driver_val = assign.is_driver if assign else False
            # Partner-Daten laden
            partner_name_m = None
            partner_emp_id_m = None
            if getattr(s, 'partner_schedule_id', None):
                partner_sched_m = db.query(Schedule).filter(Schedule.id == s.partner_schedule_id).first()
                if partner_sched_m and partner_sched_m.employee:
                    partner_name_m = f"{partner_sched_m.employee.first_name} {partner_sched_m.employee.last_name}"
                    partner_emp_id_m = partner_sched_m.employee_id

            schedules_data.append({
                'id': s.id,
                'employee_id': s.employee_id,
                'employee_name': f"{s.employee.first_name} {s.employee.last_name}" if s.employee else f"MA {s.employee_id}",
                'object_id': s.object_id,
                'object_name': s.object.name if s.object else f"Objekt {s.object_id}",
                'start_time': s.start_time.strftime("%H:%M") if s.start_time else "",
                'end_time': s.end_time.strftime("%H:%M") if s.end_time else "",
                'planned_hours': s.planned_hours,
                'status': s.status or 'normal',
                'replacement_for': s.replacement_for,
                'is_driver': bool(driver_val),
                'is_last_shift_of_month': bool(getattr(s, 'is_last_shift_of_month', False)),
                'notes': s.notes or '',
                'partner_schedule_id': getattr(s, 'partner_schedule_id', None),
                'original_planned_hours': getattr(s, 'original_planned_hours', None),
                'original_end_time': s.original_end_time.strftime("%H:%M") if getattr(s, 'original_end_time', None) else None,
                'partner_employee_name': partner_name_m,
                'partner_employee_id': partner_emp_id_m,
            })

        days_data.append({
            'date': current.isoformat(),
            'weekday': day_name,
            'weekday_index': current.weekday(),
            'schedules': schedules_data,
        })
        current += timedelta(days=1)

    return {
        'year': year,
        'month': month,
        'days': days_data,
        'employees': [
            {'id': emp.id, 'name': f"{emp.first_name} {emp.last_name}", 'personal_nr': emp.personal_nr, 'category': getattr(emp, 'tracking_mode', 'C')}
            for emp in employees
        ],
        'objects': [
            {'id': obj.id, 'name': obj.name, 'customer_name': obj.customer.name if obj.customer else '',
             'start_time': standard_times_dict.get(obj.id, {}).get('start', '06:00'),
             'end_time': standard_times_dict.get(obj.id, {}).get('end', '14:00')}
            for obj in objects
        ],
    }


@router.post("/schedules/copy-to-week")
def copy_shift_to_week(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Kopiert eine Schicht auf alle Werktage derselben Woche."""
    schedule_id = data.get('schedule_id')
    include_saturday = data.get('include_saturday', False)

    source = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Schicht nicht gefunden")

    # Montag der Woche berechnen
    monday = source.date - timedelta(days=source.date.weekday())
    end_day = 5 if include_saturday else 4  # 0=Mo, 4=Fr, 5=Sa

    created = 0
    skipped = 0
    for i in range(end_day + 1):
        target_date = monday + timedelta(days=i)
        if target_date == source.date:
            continue  # Quell-Tag ueberspringen

        # Duplikat-Check
        existing = db.query(Schedule).filter(
            and_(
                Schedule.employee_id == source.employee_id,
                Schedule.object_id == source.object_id,
                Schedule.date == target_date,
                Schedule.start_time == source.start_time,
            )
        ).first()
        if existing:
            skipped += 1
            continue

        # Urlaubs-/Abwesenheits-Check
        if check_vacation_conflict(db, source.employee_id, target_date):
            skipped += 1
            continue

        # Overlap-Check
        overlap_msg = check_schedule_overlap(db, source.employee_id, target_date, source.start_time, source.end_time)
        if overlap_msg:
            skipped += 1
            continue

        new_schedule = Schedule(
            employee_id=source.employee_id,
            object_id=source.object_id,
            date=target_date,
            weekday=target_date.weekday(),
            start_time=source.start_time,
            end_time=source.end_time,
            planned_hours=source.planned_hours,
            status='normal',
            is_driver=source.is_driver,
            notes=source.notes,
        )
        db.add(new_schedule)
        created += 1

    db.commit()
    return {'status': 'ok', 'created': created, 'skipped': skipped, 'message': f"{created} Schichten erstellt, {skipped} uebersprungen"}


@router.post("/schedules/repeat")
def repeat_shift(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Wiederholt eine Schicht woechentlich bis zum Enddatum."""
    schedule_id = data.get('schedule_id')
    until_date_str = data.get('until_date')

    source = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Schicht nicht gefunden")

    until_date = datetime.strptime(until_date_str, "%Y-%m-%d").date()
    if until_date <= source.date:
        raise HTTPException(status_code=400, detail="Enddatum muss nach dem Startdatum liegen")

    created = 0
    skipped = 0
    current_date = source.date + timedelta(weeks=1)

    while current_date <= until_date:
        # Duplikat-Check
        existing = db.query(Schedule).filter(
            and_(
                Schedule.employee_id == source.employee_id,
                Schedule.object_id == source.object_id,
                Schedule.date == current_date,
                Schedule.start_time == source.start_time,
            )
        ).first()
        if existing:
            skipped += 1
            current_date += timedelta(weeks=1)
            continue

        # Urlaubs-/Abwesenheits-Check
        if check_vacation_conflict(db, source.employee_id, current_date):
            skipped += 1
            current_date += timedelta(weeks=1)
            continue

        # Overlap-Check
        overlap_msg = check_schedule_overlap(db, source.employee_id, current_date, source.start_time, source.end_time)
        if overlap_msg:
            skipped += 1
            current_date += timedelta(weeks=1)
            continue

        new_schedule = Schedule(
            employee_id=source.employee_id,
            object_id=source.object_id,
            date=current_date,
            weekday=current_date.weekday(),
            start_time=source.start_time,
            end_time=source.end_time,
            planned_hours=source.planned_hours,
            status='normal',
            is_driver=source.is_driver,
            notes=source.notes,
        )
        db.add(new_schedule)
        created += 1
        current_date += timedelta(weeks=1)

    db.commit()
    return {'status': 'ok', 'created': created, 'skipped': skipped, 'message': f"{created} Wiederholungen erstellt, {skipped} uebersprungen"}


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
                        day_names = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
                        conflicts.append({
                            'type': 'zeitüberschneidung',
                            'employee': f"{emp.first_name} {emp.last_name}",
                            'date': current.date.isoformat(),
                            'weekday': day_names[current.date.weekday()],
                            'schedule_ids': [current.id, next_shift.id],
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
        password_hash=get_password_hash('temp123')
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


@router.post("/employees/{employee_id:int}/reset-password")
def reset_employee_password(employee_id: int, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Admin setzt Passwort eines MA auf 'seda2026' zurueck."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    user = db.query(User).filter(User.id == employee.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User-Account nicht gefunden")

    temp_password = "seda2026"
    user.password_hash = get_password_hash(temp_password)
    user.must_change_password = True
    db.commit()

    return {
        "status": "ok",
        "message": f"Passwort fuer {employee.first_name} {employee.last_name} zurueckgesetzt",
        "temp_password": temp_password
    }


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
    if 'address' in employee_data:
        employee.address = employee_data['address']
    if 'kuerzel' in employee_data:
        employee.kuerzel = employee_data['kuerzel']
    if 'employment_type' in employee_data:
        employee.employment_type = employee_data['employment_type']
    if 'gps_required' in employee_data:
        employee.gps_required = bool(employee_data['gps_required'])
    if 'is_active' in employee_data:
        employee.is_active = bool(employee_data['is_active'])
        if employee.user:
            employee.user.is_active = bool(employee_data['is_active'])
    if 'email' in employee_data and employee.user:
        employee.user.email = employee_data['email']
    db.commit()
    return {"status": "success", "message": "Mitarbeiter aktualisiert"}

@router.put("/employees/{personal_nr}")
def update_employee(personal_nr: str, employee_data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    employee = db.query(Employee).filter(Employee.personal_nr == personal_nr).first()
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
    if 'address' in employee_data:
        employee.address = employee_data['address']
    if 'kuerzel' in employee_data:
        employee.kuerzel = employee_data['kuerzel']
    if 'employment_type' in employee_data:
        employee.employment_type = employee_data['employment_type']
    if 'gps_required' in employee_data:
        employee.gps_required = bool(employee_data['gps_required'])
    if 'is_active' in employee_data:
        employee.is_active = bool(employee_data['is_active'])
        if employee.user:
            employee.user.is_active = bool(employee_data['is_active'])
    if 'email' in employee_data and employee.user:
        employee.user.email = employee_data['email']
    db.commit()
    return {"status": "success", "message": "Mitarbeiter aktualisiert"}

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
def get_all_customers(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Alle Kunden abrufen inkl. Jahresumsatz."""
    from sqlalchemy import func
    current_year = datetime.now().year
    customers = db.query(Customer).all()
    result = []
    for c in customers:
        # Objekte dieses Kunden
        objs = db.query(Object).filter(Object.customer_id == c.id).all()
        obj_ids = [o.id for o in objs]
        obj_names = [o.name for o in objs if o.is_active]

        # Jahresumsatz aus CustomerRevenue
        yearly_revenue = 0
        if obj_ids:
            rev_sum = db.query(func.sum(CustomerRevenue.revenue)).filter(
                CustomerRevenue.object_id.in_(obj_ids),
                CustomerRevenue.year == current_year,
            ).scalar()
            yearly_revenue = rev_sum or 0

        result.append({
            "id": c.id,
            "name": c.name,
            "address": getattr(c, 'address', ''),
            "hourly_rate": getattr(c, 'hourly_rate', 0),
            "is_active": c.is_active if hasattr(c, 'is_active') else True,
            "object_count": len(obj_names),
            "object_names": obj_names[:3],
            "yearly_revenue": round(yearly_revenue, 2),
            "objects": [{"id": o.id, "name": o.name, "address": o.address or '', "is_active": o.is_active} for o in objs],
        })
    return result


@router.post("/customers")
def create_customer(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Neuen Kunden anlegen."""
    name = data.get('name', '').strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name ist erforderlich")
    existing = db.query(Customer).filter(Customer.name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Kunde existiert bereits")
    customer = Customer(name=name, is_active=True)
    if data.get('billing_type'):
        customer.billing_type = data['billing_type']
    if data.get('monthly_rate'):
        customer.monthly_rate = float(data['monthly_rate'])
    db.add(customer)
    db.flush()
    # Optional: Objekt direkt mitanlegen
    if data.get('address') or data.get('hourly_rate'):
        obj = Object(
            customer_id=customer.id,
            name=name,
            address=data.get('address', ''),
            is_active=True,
        )
        db.add(obj)
    db.commit()
    return {"id": customer.id, "name": customer.name, "status": "created"}


@router.put("/customers/{customer_id}")
def update_customer(customer_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Kunden aktualisieren (Name, Adresse, is_active)."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
    if 'name' in data:
        customer.name = data['name']
    if 'billing_type' in data:
        customer.billing_type = data['billing_type']
    if 'monthly_rate' in data:
        customer.monthly_rate = float(data['monthly_rate']) if data['monthly_rate'] else None
    if 'is_active' in data:
        customer.is_active = data['is_active']
        # Bei Deaktivierung: Alle Objekte des Kunden auch deaktivieren
        if not data['is_active']:
            db.query(Object).filter(
                Object.customer_id == customer_id,
                Object.id != 999,  # Urlaub-Objekt nicht anfassen
            ).update({"is_active": False})
    db.commit()
    return {"status": "ok", "id": customer.id}


@router.get("/objects-list")
def get_objects_for_display(
    include_special: bool = Query(False),
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Objekte fuer AdminDashboard Anzeige. Filtert Urlaub/Krank-Objekte raus."""
    query = db.query(Object).filter(Object.is_active == True)
    if not include_special:
        # Objekt 999 (Urlaub) und alle mit 'krank' im Namen ausfiltern
        query = query.filter(Object.id != 999)
        query = query.filter(~Object.name.ilike('%krank%'))
    objects = query.all()
    return [
        {
            "id": obj.id,
            "name": obj.name,
            "address": obj.address,
            "is_active": obj.is_active,
            "start_time": obj.start_time.strftime('%H:%M') if obj.start_time else None,
            "end_time": obj.end_time.strftime('%H:%M') if obj.end_time else None,
        }
        for obj in objects
    ]

@router.get("/objects/{object_id}/standard-times")
def get_object_standard_times(object_id: int, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Sollstunden pro Wochentag fuer ein Objekt abrufen."""
    entries = db.query(ObjectStandardTime).filter(
        ObjectStandardTime.object_id == object_id
    ).order_by(ObjectStandardTime.weekday).all()
    return [{
        "id": e.id,
        "weekday": e.weekday,
        "start_time": e.start_time.strftime("%H:%M") if e.start_time else None,
        "end_time": e.end_time.strftime("%H:%M") if e.end_time else None,
        "standard_hours": e.standard_hours,
    } for e in entries]


@router.put("/objects/{object_id}/standard-times")
async def set_object_standard_times(object_id: int, request: Request, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Sollstunden pro Wochentag fuer ein Objekt setzen. Loescht alte und erstellt neue."""
    data = await request.json()
    # Objekt pruefen
    obj = db.query(Object).filter(Object.id == object_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")

    # Alte Eintraege loeschen
    db.query(ObjectStandardTime).filter(ObjectStandardTime.object_id == object_id).delete()

    # Neue Eintraege erstellen
    for entry in data:
        weekday = entry.get("weekday")
        start_str = entry.get("start_time")
        end_str = entry.get("end_time")
        hours = entry.get("standard_hours")

        if start_str and end_str:
            sp = start_str.split(":")
            ep = end_str.split(":")
            st = time(int(sp[0]), int(sp[1]))
            et = time(int(ep[0]), int(ep[1]))
        else:
            st = None
            et = None

        new_entry = ObjectStandardTime(
            object_id=object_id,
            weekday=weekday,
            start_time=st,
            end_time=et,
            standard_hours=float(hours) if hours else None,
        )
        db.add(new_entry)

    db.commit()
    return {"status": "ok", "count": len(data)}


@router.put("/objects/{object_id}")
def update_object(object_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Objekt aktualisieren (Name, Adresse, is_active)."""
    obj = db.query(Object).filter(Object.id == object_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Objekt nicht gefunden")
    if 'name' in data:
        obj.name = data['name']
    if 'address' in data:
        obj.address = data['address']
    if 'is_active' in data:
        obj.is_active = data['is_active']
    db.commit()
    return {"status": "ok", "id": obj.id}


@router.get("/test-objects")
def get_test_objects(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """Test-Endpoint für Objekte"""
    objects = db.query(Object).all()
    return [{"id": o.id, "name": o.name, "address": o.address} for o in objects]
@router.get("/bookings/all")
def get_all_bookings(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import TimeEntry, Employee, Object, VacationEntitlement, BreakEntry
    entries = db.query(TimeEntry).order_by(TimeEntry.check_in.desc()).limit(1000).all()
    result = []

    # Alle break_entries in einem Query laden (performant)
    entry_ids = [e.id for e in entries]
    all_breaks = db.query(BreakEntry).filter(BreakEntry.time_entry_id.in_(entry_ids)).all() if entry_ids else []
    breaks_by_entry = {}
    for b in all_breaks:
        breaks_by_entry.setdefault(b.time_entry_id, []).append(b)

    # Cache vacation_rates pro employee+year
    vac_cache = {}
    for e in entries:
        emp = db.query(Employee).filter(Employee.id == e.employee_id).first()
        obj = db.query(Object).filter(Object.id == e.object_id).first()

        # Urlaub: Fester Tagessatz aus dem time_entry (dort bei Buchung fixiert)
        if e.object_id == 999 or e.service_type == 'Urlaub':
            billed_hours = 1.0
            hourly_rate = float(e.hourly_rate) if e.hourly_rate else 0
        else:
            billed_hours = float(e.billed_hours) if e.billed_hours else (
                float((e.check_out - e.check_in).total_seconds() / 3600) if (e.check_in and e.check_out) else 0
            )
            hourly_rate = float(e.hourly_rate) if e.hourly_rate else 0

        # Brutto-Stunden (check_out - check_in) und Pause berechnen
        brutto_hours = None
        pause_minutes = 0
        if e.check_in and e.check_out and e.object_id != 999 and e.service_type != 'Urlaub':
            brutto_hours = round((e.check_out - e.check_in).total_seconds() / 3600, 2)
            entry_breaks = breaks_by_entry.get(e.id, [])
            for b in entry_breaks:
                if b.start_time and b.end_time:
                    pause_minutes += (b.end_time - b.start_time).total_seconds() / 60
            pause_minutes = round(pause_minutes)

        # Offline-Sync Delay berechnen
        delay = None
        if e.server_received_at:
            ref_time = e.check_out or e.check_in
            if ref_time:
                d = (e.server_received_at - ref_time).total_seconds() / 60
                delay = round(d) if d >= 5 else 0

        result.append({
            "id": e.id,
            "employee_id": e.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "Unbekannt",
            "object_id": e.object_id,
            "object_name": obj.name if obj else (e.custom_object_name or e.service_type or "Unbekannt"),
            "check_in": e.check_in.isoformat() if e.check_in else None,
            "check_out": e.check_out.isoformat() if e.check_out else None,
            "billed_hours": billed_hours,
            "brutto_hours": brutto_hours,
            "pause_minutes": pause_minutes,
            "hourly_rate": hourly_rate,
            "service_type": e.service_type,
            "notes": e.notes,
            "is_manual_entry": e.is_manual_entry,
            "server_received_at": e.server_received_at.isoformat() if e.server_received_at else None,
            "sync_delay_minutes": delay,
        })
    return result

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
    elif 'check_in' in data and 'check_out' in data:
        # billed_hours automatisch neu berechnen wenn Zeiten geaendert
        # aber kein expliziter billed_hours-Wert mitgeschickt wurde
        try:
            ci = datetime.fromisoformat(data['check_in'].replace('Z', '+00:00'))
            co = datetime.fromisoformat(data['check_out'].replace('Z', '+00:00'))
            entry.billed_hours = round((co - ci).total_seconds() / 3600, 2)
        except Exception:
            pass

    # Bei Datumsänderung: KM-Einträge mitverschieben
    if 'check_in' in data:
        new_date = datetime.fromisoformat(data['check_in'].replace('Z', '+00:00')).date()
        db.execute(text(
            "UPDATE km_daily_entries SET date = :new_date WHERE time_entry_id = :te_id"
        ), {"new_date": new_date, "te_id": booking_id})

    db.commit()
    return {"status": "ok", "message": "Buchung aktualisiert"}

@router.delete("/bookings/{booking_id}")
def delete_booking(booking_id: int, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import TimeEntry
    from sqlalchemy import text

    entry = db.query(TimeEntry).filter(TimeEntry.id == booking_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")

    # KM-Einträge mitlöschen (gleicher MA, Objekt, Tag)
    km_deleted = 0
    if entry.object_id and entry.employee_id:
        entry_date = entry.check_in.date() if entry.check_in else None
        if entry_date:
            result = db.execute(
                text("DELETE FROM km_daily_entries WHERE employee_id = :emp AND object_id = :obj AND date = :dt"),
                {"emp": entry.employee_id, "obj": entry.object_id, "dt": entry_date}
            )
            km_deleted = result.rowcount

            # is_longest_trip für verbleibende KM des Tages neu berechnen
            if km_deleted > 0:
                db.execute(
                    text("UPDATE km_daily_entries SET is_longest_trip = false, is_billable = false WHERE employee_id = :emp AND date = :dt"),
                    {"emp": entry.employee_id, "dt": entry_date}
                )
                db.execute(
                    text("""UPDATE km_daily_entries
                           SET is_longest_trip = true, is_billable = true
                           WHERE id = (
                               SELECT id FROM km_daily_entries
                               WHERE employee_id = :emp AND date = :dt
                               ORDER BY distance_km DESC LIMIT 1
                           )"""),
                    {"emp": entry.employee_id, "dt": entry_date}
                )

    # Break-Einträge mitlöschen (Foreign Key auf time_entries)
    db.execute(text("DELETE FROM break_entries WHERE time_entry_id = :tid"), {"tid": booking_id})

    db.delete(entry)
    db.commit()
    return {"status": "ok", "km_deleted": km_deleted}

@router.post("/bookings/bulk-delete")
def bulk_delete_bookings(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    from app.models.models import TimeEntry
    from sqlalchemy import text

    ids = data.get('ids', [])
    if not ids:
        raise HTTPException(status_code=400, detail="Keine IDs angegeben")

    # Zuerst KM-Einträge zu den Buchungen löschen
    entries = db.query(TimeEntry).filter(TimeEntry.id.in_(ids)).all()
    affected_days = set()  # (employee_id, date) für Neuberechnung
    for entry in entries:
        if entry.object_id and entry.employee_id and entry.check_in:
            entry_date = entry.check_in.date()
            db.execute(
                text("DELETE FROM km_daily_entries WHERE employee_id = :emp AND object_id = :obj AND date = :dt"),
                {"emp": entry.employee_id, "obj": entry.object_id, "dt": entry_date}
            )
            affected_days.add((entry.employee_id, entry_date))

    # is_longest_trip neu berechnen
    for emp_id, dt in affected_days:
        db.execute(
            text("UPDATE km_daily_entries SET is_longest_trip = false, is_billable = false WHERE employee_id = :emp AND date = :dt"),
            {"emp": emp_id, "dt": dt}
        )
        db.execute(
            text("""UPDATE km_daily_entries
                   SET is_longest_trip = true, is_billable = true
                   WHERE id = (
                       SELECT id FROM km_daily_entries
                       WHERE employee_id = :emp AND date = :dt
                       ORDER BY distance_km DESC LIMIT 1
                   )"""),
            {"emp": emp_id, "dt": dt}
        )

    # Break-Einträge mitlöschen (Foreign Key auf time_entries)
    db.execute(text("DELETE FROM break_entries WHERE time_entry_id IN :ids"), {"ids": tuple(ids)})

    deleted = db.query(TimeEntry).filter(TimeEntry.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}

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
    
    # Stundensatz: manuell eingegebener Satz hat Vorrang, sonst Employee-Stammdaten
    service_type = data.get('service_type', 'Unterhaltsreinigung')
    if data.get('hourly_rate') is not None and float(data['hourly_rate']) > 0:
        hourly_rate = float(data['hourly_rate'])
    elif service_type in ('Fensterreinigung',):
        hourly_rate = employee.hourly_rate_window or 20.00
    elif service_type in ('Grundreinigung',):
        hourly_rate = employee.hourly_rate_basic or 20.00
    else:
        hourly_rate = employee.hourly_rate or employee.hourly_rate_standard or 15.00

    if service_type == 'Urlaub' or data.get('object_id') == 999:
        from app.api.v1.endpoints.vacation import _calc_vacation_rate
        from app.models.models import VacationEntitlement
        check_in_date = datetime.fromisoformat(data['check_in']).date()
        calc = _calc_vacation_rate(db, data['employee_id'], ref_date=check_in_date)
        if calc['worked_days'] > 0:
            hourly_rate = calc['vacation_rate']
        else:
            # Fallback: vacation_entitlements
            ent = db.query(VacationEntitlement).filter(
                VacationEntitlement.employee_id == data['employee_id'],
                VacationEntitlement.year == check_in_date.year,
            ).first()
            if ent and ent.vacation_rate:
                hourly_rate = ent.vacation_rate

    # Erstelle TimeEntry
    entry = TimeEntry(
        employee_id=data['employee_id'],
        object_id=object_id,
        custom_object_name=custom_object_name,
        check_in=datetime.fromisoformat(data['check_in']),
        check_out=datetime.fromisoformat(data['check_out']),
        hourly_rate=hourly_rate,
        service_type=service_type,
        notes=data.get('notes', ''),
        is_manual_entry=True
    )

    # Stunden: manuell uebergeben oder aus Zeiten berechnen
    if data.get('billed_hours') is not None and float(data['billed_hours']) > 0:
        entry.billed_hours = float(data['billed_hours'])
    else:
        duration = (entry.check_out - entry.check_in).total_seconds() / 3600
        entry.billed_hours = duration

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return {"status": "ok", "message": "Buchung erstellt", "id": entry.id, "vacation_rate_used": hourly_rate if (service_type == 'Urlaub' or data.get('object_id') == 999) else None}

@router.post("/km/manual")
def create_manual_km(data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    """KM-Eintrag manuell erstellen (nach manueller Buchung)"""
    from sqlalchemy import text

    employee_id = data.get('employee_id')
    object_id = data.get('object_id')  # Kann None sein bei einmaligen Kunden
    custom_object_name = data.get('custom_object_name')
    entry_date = data.get('date')
    time_entry_id = data.get('time_entry_id')
    distance_km = float(data.get('distance_km', 0))

    if not employee_id or not entry_date or distance_km <= 0:
        raise HTTPException(status_code=400, detail="employee_id, date und distance_km > 0 erforderlich")
    if not object_id and not custom_object_name:
        raise HTTPException(status_code=400, detail="object_id oder custom_object_name erforderlich")

    rate = 0.30
    amount = round(distance_km * rate, 2)

    # Prüfe ob schon existiert (bei custom objects: nach time_entry_id oder date+custom_name)
    if object_id:
        existing = db.execute(
            text("SELECT id FROM km_daily_entries WHERE employee_id = :emp AND date = :dt AND object_id = :obj"),
            {"emp": employee_id, "dt": entry_date, "obj": object_id}
        ).fetchone()
    elif time_entry_id:
        existing = db.execute(
            text("SELECT id FROM km_daily_entries WHERE employee_id = :emp AND date = :dt AND time_entry_id = :te_id"),
            {"emp": employee_id, "dt": entry_date, "te_id": time_entry_id}
        ).fetchone()
    else:
        existing = None

    if existing:
        db.execute(
            text("UPDATE km_daily_entries SET distance_km = :dist, amount = :amt, time_entry_id = :te_id, custom_object_name = :custom WHERE id = :id"),
            {"dist": distance_km, "amt": amount, "te_id": time_entry_id, "custom": custom_object_name, "id": existing[0]}
        )
    else:
        db.execute(
            text("""INSERT INTO km_daily_entries
                   (employee_id, date, object_id, distance_km, amount, is_billable, is_longest_trip, time_entry_id, custom_object_name)
                   VALUES (:emp, :dt, :obj, :dist, :amt, false, false, :te_id, :custom)"""),
            {"emp": employee_id, "dt": entry_date, "obj": object_id, "dist": distance_km, "amt": amount, "te_id": time_entry_id, "custom": custom_object_name}
        )

    # is_longest_trip neu berechnen
    db.execute(
        text("UPDATE km_daily_entries SET is_longest_trip = false, is_billable = false WHERE employee_id = :emp AND date = :dt"),
        {"emp": employee_id, "dt": entry_date}
    )
    db.execute(
        text("""UPDATE km_daily_entries
               SET is_longest_trip = true, is_billable = true
               WHERE id = (
                   SELECT id FROM km_daily_entries
                   WHERE employee_id = :emp AND date = :dt
                   ORDER BY distance_km DESC LIMIT 1
               )"""),
        {"emp": employee_id, "dt": entry_date}
    )

    db.commit()
    return {"status": "ok", "message": f"KM-Eintrag erstellt: {distance_km} km"}

# ========== PDF-Abrechnungen ==========

from fastapi.responses import FileResponse, StreamingResponse
from app.core.pdf_generator import PDFGenerator
import zipfile
from io import BytesIO
from pydantic import BaseModel

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
            COALESCE(o.name, k.custom_object_name, 'Unbekannt') as object_name,
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
    """Fuegt manuellen KM-Eintrag hinzu mit auto Laengste-Fahrt-Berechnung."""
    from sqlalchemy import text

    emp_id = data["employee_id"]
    booking_date = data["booking_date"]
    distance_km = float(data["distance_km"])
    rate = float(data.get("rate", 0.30))

    db.execute(text("""
        INSERT INTO km_daily_entries
        (employee_id, object_id, date, distance_km, amount, is_billable, is_longest_trip)
        VALUES (:emp, :obj, :date, :km, :amt, true, false)
    """), {
        "emp": emp_id,
        "obj": data.get("object_id"),
        "date": booking_date,
        "km": distance_km,
        "amt": distance_km * rate,
    })

    # Auto Laengste-Fahrt: nur die laengste des Tages ist billable
    all_today = db.execute(text("""
        SELECT id, distance_km FROM km_daily_entries
        WHERE employee_id = :emp AND date = :date
        ORDER BY distance_km DESC
    """), {"emp": emp_id, "date": booking_date}).fetchall()

    if all_today:
        longest_id = all_today[0][0]
        for entry in all_today:
            is_longest = entry[0] == longest_id
            db.execute(text("""
                UPDATE km_daily_entries
                SET is_longest_trip = :longest, is_billable = :longest
                WHERE id = :id
            """), {"longest": is_longest, "id": entry[0]})

    db.commit()
    return {"status": "ok", "message": f"{distance_km} km eingetragen"}

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

@router.post("/km-journal/bulk-delete")
def bulk_delete_km_entries(
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Löscht mehrere KM-Einträge auf einmal"""
    from sqlalchemy import text

    ids = data.get("ids", [])
    if not ids:
        return {"status": "ok", "deleted": 0}

    db.execute(text("DELETE FROM km_daily_entries WHERE id = ANY(:ids)"), {"ids": ids})
    db.commit()
    return {"status": "ok", "deleted": len(ids)}


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
    date: str = Query(None),
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """KM-Eintrag bearbeiten (KM + optional Datum)"""
    from sqlalchemy import text

    if date:
        db.execute(text("""
            UPDATE km_daily_entries
            SET distance_km = :km, amount = :amount, date = :date
            WHERE id = :id
        """), {"id": entry_id, "km": distance_km, "amount": round(distance_km * 0.30, 2), "date": date})

        # is_longest_trip für altes + neues Datum neu berechnen
        row = db.execute(text("SELECT employee_id FROM km_daily_entries WHERE id = :id"), {"id": entry_id}).fetchone()
        if row:
            emp_id = row[0]
            for dt in [date]:
                db.execute(text("UPDATE km_daily_entries SET is_longest_trip = false, is_billable = false WHERE employee_id = :emp AND date = :dt"), {"emp": emp_id, "dt": dt})
                db.execute(text("""UPDATE km_daily_entries SET is_longest_trip = true, is_billable = true
                    WHERE id = (SELECT id FROM km_daily_entries WHERE employee_id = :emp AND date = :dt ORDER BY distance_km DESC LIMIT 1)"""), {"emp": emp_id, "dt": dt})
    else:
        db.execute(text("""
            UPDATE km_daily_entries
            SET distance_km = :km, amount = :amount
            WHERE id = :id
        """), {"id": entry_id, "km": distance_km, "amount": round(distance_km * 0.30, 2)})

    db.commit()
    return {"message": "KM aktualisiert", "new_km": distance_km, "new_amount": round(distance_km * 0.30, 2)}

@router.get("/schedule/{employee_id}/{object_id}/{date}")
def get_schedule_for_booking(
    employee_id: int,
    object_id: int,
    date: str,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Lädt Dienstplan-Daten für manuelle Buchung"""
    from datetime import datetime
    schedule_date = datetime.strptime(date, '%Y-%m-%d').date()
    
    schedule = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.object_id == object_id,
        Schedule.date == schedule_date
    ).first()
    
    if not schedule:
        employee = db.query(Employee).filter(Employee.id == employee_id).first()

        # Fallback 1: ObjectStandardTime für den Wochentag
        weekday = schedule_date.weekday()  # 0=Mo, 1=Di, ...
        std_time = db.query(ObjectStandardTime).filter(
            ObjectStandardTime.object_id == object_id,
            ObjectStandardTime.weekday == weekday
        ).first()

        if std_time:
            return {
                "start_time": std_time.start_time.strftime('%H:%M') if std_time.start_time else '09:00',
                "end_time": std_time.end_time.strftime('%H:%M') if std_time.end_time else '17:00',
                "hourly_rate": float(employee.hourly_rate) if employee else 15.50
            }

        # Fallback 2: Object.start_time / end_time
        obj = db.query(Object).filter(Object.id == object_id).first()
        if obj and obj.start_time:
            return {
                "start_time": obj.start_time.strftime('%H:%M'),
                "end_time": obj.end_time.strftime('%H:%M') if obj.end_time else '17:00',
                "hourly_rate": float(employee.hourly_rate) if employee else 15.50
            }

        raise HTTPException(status_code=404, detail="Kein Dienstplan gefunden")

    employee = db.query(Employee).filter(Employee.id == employee_id).first()

    return {
        "start_time": schedule.start_time.strftime('%H:%M'),
        "end_time": schedule.end_time.strftime('%H:%M'),
        "hourly_rate": float(employee.hourly_rate) if employee else 15.50
    }

# ============================================================
# LOHNÜBERSICHT ENDPOINT
# ============================================================
from calendar import monthrange
from app.services.holidays_bw import is_feiertag_bw

def _berechne_stunden_split(db, employee_id, first_day, last_day):
    """Berechnet normal/sonder/sonntag/nacht/feiertag Stunden aus TimeEntries."""
    normal_hours = sonder_hours = sonntag_hours = nacht_hours = feiertag_hours = 0.0
    sonder_amount = 0.0
    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee_id,
        func.date(TimeEntry.check_in) >= first_day,
        func.date(TimeEntry.check_in) <= last_day,
        TimeEntry.check_out != None
    ).all()
    for entry in entries:
        if not entry.check_in or not entry.check_out:
            continue
        hours = entry.billed_hours or (entry.check_out - entry.check_in).total_seconds() / 3600
        entry_date = entry.check_in.date()
        is_sonder = entry.service_type in ('Fensterreinigung', 'Sonderreinigung', 'Grundreinigung')
        if is_feiertag_bw(entry_date):
            feiertag_hours += hours
        elif is_sonder:
            sonder_hours += hours
            sonder_amount += hours * (entry.hourly_rate or 20.0)
        elif entry_date.weekday() == 6:
            normal_hours += hours
            sonntag_hours += hours
        else:
            normal_hours += hours
            ci_time = entry.check_in.time()
            co_time = entry.check_out.time()
            if ci_time.hour < 6:
                nacht_h = min(hours, (6 - ci_time.hour - ci_time.minute/60))
                nacht_hours += nacht_h
            elif co_time.hour >= 23:
                nacht_h = co_time.hour - 23 + co_time.minute/60
                nacht_hours += nacht_h
    return {
        "normal_hours": round(normal_hours, 2),
        "sonder_hours": round(sonder_hours, 2),
        "sonder_amount": round(sonder_amount, 2),
        "sonntag_hours": round(sonntag_hours, 2),
        "nacht_hours": round(nacht_hours, 2),
        "feiertag_hours": round(feiertag_hours, 2),
    }


@router.get("/lohn-uebersicht")
def get_lohn_uebersicht(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    employees = db.query(Employee).filter(Employee.is_active == True).order_by(Employee.personal_nr).all()
    result = []

    for emp in employees:
        if emp.personal_nr and emp.personal_nr.startswith('A'):
            continue

        split = _berechne_stunden_split(db, emp.id, first_day, last_day)
        normal_hours = split["normal_hours"]
        sonder_hours = split["sonder_hours"]
        sonder_amount_from_entries = split["sonder_amount"]
        sonntag_hours = split["sonntag_hours"]
        nacht_hours = split["nacht_hours"]
        feiertag_hours = split["feiertag_hours"]
        
        urlaub_schedules = db.query(Schedule).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= first_day, Schedule.date <= last_day,
            Schedule.status == 'urlaub'
        ).all()
        urlaub_days = len(set(s.date for s in urlaub_schedules))

        # Urlaubsgeld aus time_entries berechnen (hourly_rate = Tagessatz bei Urlaub)
        urlaub_entries = db.query(TimeEntry).filter(
            TimeEntry.employee_id == emp.id,
            func.date(TimeEntry.check_in) >= first_day,
            func.date(TimeEntry.check_in) <= last_day,
            TimeEntry.service_type == 'Urlaub'
        ).all()
        urlaub_amount = sum(float(e.hourly_rate) for e in urlaub_entries if e.hourly_rate)

        km_result = db.execute(text(
            "SELECT COALESCE(SUM(amount), 0) FROM km_daily_entries WHERE employee_id = :emp_id AND date >= :first AND date <= :last AND is_billable = true"
        ), {"emp_id": emp.id, "first": first_day, "last": last_day}).fetchone()
        km_amount = float(km_result[0]) if km_result else 0.0

        hourly_rate = emp.hourly_rate or 15.50
        normal_amount = normal_hours * hourly_rate
        sonder_amount = sonder_amount_from_entries
        gesamt = normal_amount + sonder_amount + urlaub_amount
        
        # Uebertrag laden
        from app.models.models import MonthlyCarryover
        carryover = db.query(MonthlyCarryover).filter(
            MonthlyCarryover.employee_id == emp.id,
            MonthlyCarryover.year == year,
            MonthlyCarryover.month == month,
        ).first()
        carryover_amount = carryover.carryover_amount if carryover else 0.0

        # Zeitkonto-Daten (nur wenn aktiviert)
        zeitkonto_data = None
        if getattr(emp, 'zeitkonto_aktiv', False):
            from app.models.models import Zeitkonto
            zk = db.query(Zeitkonto).filter(
                Zeitkonto.employee_id == emp.id,
                Zeitkonto.year == year,
                Zeitkonto.month == month,
            ).first()
            if zk:
                zeitkonto_data = {
                    "soll_stunden": zk.soll_stunden,
                    "ist_stunden_normal": zk.ist_stunden_normal or round(normal_hours, 2),
                    "uebertrag_stunden": zk.uebertrag_stunden,
                    "vortrag_stunden": zk.vortrag_stunden,
                    "konto_saldo": zk.konto_saldo,
                    "vorschuss_betrag": zk.vorschuss_betrag,
                    "status": zk.status,
                }
            else:
                # Live-Berechnung
                prev_month = month - 1
                prev_year = year
                if prev_month < 1:
                    prev_month = 12
                    prev_year = year - 1
                prev_zk = db.query(Zeitkonto).filter(
                    Zeitkonto.employee_id == emp.id,
                    Zeitkonto.year == prev_year,
                    Zeitkonto.month == prev_month,
                ).first()
                vortrag = prev_zk.konto_saldo if prev_zk else 0.0
                default_soll = 140.0
                uebertrag = round(normal_hours - default_soll, 2)
                zeitkonto_data = {
                    "soll_stunden": default_soll,
                    "ist_stunden_normal": round(normal_hours, 2),
                    "uebertrag_stunden": uebertrag,
                    "vortrag_stunden": round(vortrag, 2),
                    "konto_saldo": round(vortrag + uebertrag, 2),
                    "vorschuss_betrag": 0.0,
                    "status": "entwurf",
                }

        result.append({
            "employee_id": emp.id, "personal_nr": emp.personal_nr,
            "name": f"{emp.first_name} {emp.last_name}", "hourly_rate": hourly_rate,
            "normal_hours": round(normal_hours, 2), "normal_amount": round(normal_amount, 2),
            "sonder_hours": round(sonder_hours, 2), "sonder_amount": round(sonder_amount, 2),
            "sonntag_hours": round(sonntag_hours, 2), "nacht_hours": round(nacht_hours, 2),
            "feiertag_hours": round(feiertag_hours, 2),
            "urlaub_days": urlaub_days, "urlaub_amount": round(urlaub_amount, 2),
            "km_amount": round(km_amount, 2), "carryover": round(carryover_amount, 2),
            "gesamt": round(gesamt + carryover_amount, 2),
            "zeitkonto_aktiv": getattr(emp, 'zeitkonto_aktiv', False) or False,
            "zeitkonto": zeitkonto_data,
        })
    return result


@router.put("/lohn-uebersicht/carryover")
def update_carryover(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Uebertrag fuer Mitarbeiter/Monat setzen."""
    from app.models.models import MonthlyCarryover
    emp_id = data["employee_id"]
    year = data["year"]
    month = data["month"]
    amount = float(data["carryover_amount"])

    existing = db.query(MonthlyCarryover).filter(
        MonthlyCarryover.employee_id == emp_id,
        MonthlyCarryover.year == year,
        MonthlyCarryover.month == month,
    ).first()

    if existing:
        existing.carryover_amount = amount
        existing.notes = data.get("notes", existing.notes)
    else:
        entry = MonthlyCarryover(
            employee_id=emp_id, year=year, month=month,
            carryover_amount=amount, notes=data.get("notes", ""),
        )
        db.add(entry)

    db.commit()
    return {"status": "ok"}


# ============================================================
# ZEITKONTO ENDPOINTS
# ============================================================

@router.get("/zeitkonto/detail")
def get_zeitkonto_detail(
    employee_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Zeitkonto-Detail: Live berechnete + gespeicherte Werte."""
    from app.models.models import Zeitkonto
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp or not getattr(emp, 'zeitkonto_aktiv', False):
        raise HTTPException(status_code=404, detail="Mitarbeiter hat kein aktives Zeitkonto")

    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    # Ist-Stunden live berechnen
    split = _berechne_stunden_split(db, employee_id, first_day, last_day)

    # Gespeicherten Record holen
    zk = db.query(Zeitkonto).filter(
        Zeitkonto.employee_id == employee_id,
        Zeitkonto.year == year,
        Zeitkonto.month == month,
    ).first()

    # Vortrag vom Vormonat
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year = year - 1
    prev_zk = db.query(Zeitkonto).filter(
        Zeitkonto.employee_id == employee_id,
        Zeitkonto.year == prev_year,
        Zeitkonto.month == prev_month,
    ).first()
    vortrag = prev_zk.konto_saldo if prev_zk else 0.0

    soll = zk.soll_stunden if zk else 140.0
    ist_normal = split["normal_hours"]
    uebertrag = round(ist_normal - soll, 2)
    konto_saldo = round(vortrag + uebertrag, 2)

    # Vorschuss-Vorschlag: Uebertrag * 11€, abgerundet auf 10er
    vorschuss_vorschlag = max(0, int((uebertrag * 11.0) / 10) * 10) if uebertrag > 0 else 0.0

    # Offener Vorschuss aus Vormonat
    offener_vorschuss_vormonat = prev_zk.vorschuss_betrag if prev_zk and prev_zk.vorschuss_betrag > 0 else 0.0

    return {
        "employee_id": employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name}",
        "year": year,
        "month": month,
        "ist_stunden_normal": split["normal_hours"],
        "ist_stunden_sonntag": split["sonntag_hours"],
        "ist_stunden_nacht": split["nacht_hours"],
        "ist_stunden_feiertag": split["feiertag_hours"],
        "soll_stunden": soll,
        "vortrag_stunden": round(vortrag, 2),
        "uebertrag_stunden": uebertrag,
        "konto_saldo": konto_saldo,
        "vorschuss_betrag": zk.vorschuss_betrag if zk else 0.0,
        "vorschuss_vorschlag": vorschuss_vorschlag,
        "offener_vorschuss_vormonat": offener_vorschuss_vormonat,
        "status": zk.status if zk else "entwurf",
    }


@router.put("/zeitkonto/soll-stunden")
def update_zeitkonto_soll(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Soll-Stunden fuer einen Monat aendern."""
    from app.models.models import Zeitkonto
    emp_id = data["employee_id"]
    year = data["year"]
    month = data["month"]
    soll = float(data["soll_stunden"])

    zk = db.query(Zeitkonto).filter(
        Zeitkonto.employee_id == emp_id,
        Zeitkonto.year == year,
        Zeitkonto.month == month,
    ).first()

    if zk and zk.status == 'abgeschlossen':
        raise HTTPException(status_code=400, detail="Monat bereits abgeschlossen")

    if zk:
        zk.soll_stunden = soll
    else:
        zk = Zeitkonto(employee_id=emp_id, year=year, month=month, soll_stunden=soll)
        db.add(zk)

    db.commit()
    return {"status": "ok", "soll_stunden": soll}


@router.post("/zeitkonto/abschliessen")
def zeitkonto_abschliessen(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Monat abschliessen: Ist-Stunden festschreiben, Saldo berechnen."""
    from app.models.models import Zeitkonto
    emp_id = data["employee_id"]
    year = data["year"]
    month = data["month"]
    vorschuss = float(data.get("vorschuss_betrag", 0))
    soll = float(data.get("soll_stunden", 140.0))

    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    # Ist-Stunden berechnen
    split = _berechne_stunden_split(db, emp_id, first_day, last_day)
    ist_normal = split["normal_hours"]
    ist_sonntag = split["sonntag_hours"]
    ist_nacht = split["nacht_hours"]
    ist_feiertag = split["feiertag_hours"]

    # Vortrag vom Vormonat
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year = year - 1
    prev_zk = db.query(Zeitkonto).filter(
        Zeitkonto.employee_id == emp_id,
        Zeitkonto.year == prev_year,
        Zeitkonto.month == prev_month,
    ).first()
    vortrag = prev_zk.konto_saldo if prev_zk else 0.0

    uebertrag = round(ist_normal - soll, 2)
    konto_saldo = round(vortrag + uebertrag, 2)

    zk = db.query(Zeitkonto).filter(
        Zeitkonto.employee_id == emp_id,
        Zeitkonto.year == year,
        Zeitkonto.month == month,
    ).first()

    if zk:
        zk.ist_stunden_normal = round(ist_normal, 2)
        zk.ist_stunden_sonntag = round(ist_sonntag, 2)
        zk.ist_stunden_nacht = round(ist_nacht, 2)
        zk.ist_stunden_feiertag = round(ist_feiertag, 2)
        zk.soll_stunden = soll
        zk.vortrag_stunden = round(vortrag, 2)
        zk.uebertrag_stunden = uebertrag
        zk.konto_saldo = konto_saldo
        zk.vorschuss_betrag = vorschuss
        zk.status = 'abgeschlossen'
        zk.abgeschlossen_am = datetime.now()
    else:
        zk = Zeitkonto(
            employee_id=emp_id, year=year, month=month,
            ist_stunden_normal=round(ist_normal, 2),
            ist_stunden_sonntag=round(ist_sonntag, 2),
            ist_stunden_nacht=round(ist_nacht, 2),
            ist_stunden_feiertag=round(ist_feiertag, 2),
            soll_stunden=soll,
            vortrag_stunden=round(vortrag, 2),
            uebertrag_stunden=uebertrag,
            konto_saldo=konto_saldo,
            vorschuss_betrag=vorschuss,
            status='abgeschlossen',
            abgeschlossen_am=datetime.now(),
        )
        db.add(zk)

    db.commit()
    return {
        "status": "ok",
        "konto_saldo": konto_saldo,
        "uebertrag_stunden": uebertrag,
        "vorschuss_betrag": vorschuss,
    }


# ========== V3.0 ENDPOINTS ==========

@router.get("/audit-log")
def get_audit_log(
    start_date: str = None,
    end_date: str = None,
    employee_id: int = None,
    action: str = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Audit-Log mit Filtern."""
    from app.models.models import AuditLog
    query = db.query(AuditLog)

    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(AuditLog.created_at >= sd)
        except ValueError:
            pass
    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(AuditLog.created_at < ed)
        except ValueError:
            pass
    if employee_id:
        query = query.filter(AuditLog.employee_id == employee_id)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))

    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for log in logs:
        emp_name = None
        if log.employee_id:
            emp = db.query(Employee).filter(Employee.id == log.employee_id).first()
            emp_name = f"{emp.first_name} {emp.last_name}" if emp else None

        result.append({
            "id": log.id,
            "action": log.action,
            "employee_id": log.employee_id,
            "employee_name": emp_name,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return result


@router.post("/mark-sick/{employee_id}")
def mark_employee_sick(
    employee_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """S3: Admin markiert MA als krank. Schichten werden auf 'krank' gesetzt."""
    from app.models.models import AuditLog
    from app.services.booking_service import log_audit

    target_date_str = data.get('date', date.today().isoformat())
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungueltiges Datum")

    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.date == target_date
    ).all()

    if not schedules:
        raise HTTPException(status_code=404, detail="Keine Schichten an diesem Tag")

    for sched in schedules:
        sched.status = 'krank'

    # Optional Vertretung eintragen
    replacement_id = data.get('replacement_employee_id')
    if replacement_id:
        for sched in schedules:
            new_schedule = Schedule(
                employee_id=replacement_id,
                object_id=sched.object_id,
                weekday=sched.weekday,
                date=sched.date,
                start_time=sched.start_time,
                end_time=sched.end_time,
                planned_hours=sched.planned_hours,
                status='vertretung',
                replacement_for=employee_id,
            )
            db.add(new_schedule)

    log_audit(
        db, admin.id, employee_id, 'mark_sick',
        'schedule', None,
        details=f"Krank gemeldet fuer {target_date_str}"
        + (f", Vertretung: {replacement_id}" if replacement_id else "")
    )

    db.commit()
    return {
        "status": "ok",
        "schedules_updated": len(schedules),
        "replacement": replacement_id,
    }


@router.get("/open-items")
def get_open_items(
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Alle offenen Punkte fuer den Admin."""
    from app.models.models import PushNotification, CorrectionRequest, MonthlyConfirmation, ShiftChangeRequest

    items = []

    # 1. Abgelaufene/unbearbeitete Pushes
    expired_pushes = db.query(PushNotification).filter(
        PushNotification.status.in_(['expired']),
        PushNotification.response_status.is_(None),
    ).order_by(PushNotification.created_at.desc()).limit(20).all()

    for p in expired_pushes:
        emp = db.query(Employee).filter(Employee.id == p.employee_id).first()
        items.append({
            "type": "expired_push",
            "id": p.id,
            "employee_id": p.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "title": p.title,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "schedule_id": p.schedule_id,
        })

    # 2. Unbearbeitete "war nicht da" Meldungen
    not_present = db.query(PushNotification).filter(
        PushNotification.response_status == 'not_present',
    ).order_by(PushNotification.responded_at.desc()).limit(20).all()

    for p in not_present:
        emp = db.query(Employee).filter(Employee.id == p.employee_id).first()
        items.append({
            "type": "not_present",
            "id": p.id,
            "employee_id": p.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "title": p.title,
            "response_data": p.response_data,
            "responded_at": p.responded_at.isoformat() if p.responded_at else None,
        })

    # 3. Offene Korrekturen
    corrections = db.query(CorrectionRequest).filter(
        CorrectionRequest.status == 'pending'
    ).order_by(CorrectionRequest.created_at.desc()).limit(20).all()

    for c in corrections:
        emp = db.query(Employee).filter(Employee.id == c.employee_id).first()
        items.append({
            "type": "correction",
            "id": c.id,
            "employee_id": c.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "correction_type": c.correction_type,
            "reason": c.reason,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    # 4. Offene Schichtaenderungsanfragen
    shift_requests = db.query(ShiftChangeRequest).filter(
        ShiftChangeRequest.status == 'pending'
    ).order_by(ShiftChangeRequest.created_at.desc()).limit(20).all()

    for sr in shift_requests:
        emp = db.query(Employee).filter(Employee.id == sr.employee_id).first()
        schedule_info = {}
        if sr.schedule_id:
            sched = db.query(Schedule).filter(Schedule.id == sr.schedule_id).first()
            if sched:
                obj = db.query(Object).filter(Object.id == sched.object_id).first()
                schedule_info = {
                    "object_name": obj.name if obj else f"Objekt {sched.object_id}",
                    "date": sched.date.isoformat() if sched.date else None,
                    "start_time": sched.start_time.strftime("%H:%M") if sched.start_time else None,
                    "end_time": sched.end_time.strftime("%H:%M") if sched.end_time else None,
                }
        items.append({
            "type": "shift_change",
            "id": sr.id,
            "employee_id": sr.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "request_type": sr.request_type,
            "reason": sr.reason,
            "status": sr.status,
            "created_at": sr.created_at.isoformat() if sr.created_at else None,
            **schedule_info,
        })

    # 5. Kat-B MAs ohne Telegram-Verbindung
    not_connected = db.query(Employee).filter(
        Employee.tracking_mode == 'B',
        Employee.is_active == True,
        or_(Employee.telegram_chat_id.is_(None), Employee.telegram_chat_id == '0'),
    ).all()

    for emp in not_connected:
        items.append({
            "type": "telegram_not_connected",
            "id": emp.id,
            "employee_id": emp.id,
            "employee_name": f"{emp.first_name} {emp.last_name}",
            "personal_nr": emp.personal_nr,
        })

    # 6. Auto-gebucht (48h) - letzte 30 Tage
    from app.models.models import AuditLog
    thirty_days_ago = datetime.now() - timedelta(days=30)
    auto_booked = db.query(AuditLog).filter(
        AuditLog.action == 'auto_booked_48h',
        AuditLog.created_at >= thirty_days_ago,
    ).order_by(AuditLog.created_at.desc()).limit(20).all()

    for ab in auto_booked:
        emp = db.query(Employee).filter(Employee.id == ab.employee_id).first()
        items.append({
            "type": "auto_booked",
            "id": ab.id,
            "employee_id": ab.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "details": ab.details,
            "created_at": ab.created_at.isoformat() if ab.created_at else None,
        })

    # 7. Telegram-Korrekturen (andere_zeiten, mit_kollege)
    telegram_corrections = db.query(PushNotification).filter(
        PushNotification.response_status == 'correction',
    ).order_by(PushNotification.responded_at.desc()).limit(20).all()

    for tc in telegram_corrections:
        emp = db.query(Employee).filter(Employee.id == tc.employee_id).first()
        items.append({
            "type": "telegram_correction",
            "id": tc.id,
            "employee_id": tc.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "title": tc.title,
            "response_data": tc.response_data,
            "responded_at": tc.responded_at.isoformat() if tc.responded_at else None,
        })

    # 8. Monatskorrekturen (disputed)
    from app.models.models import MonthlyConfirmation as MC
    now = datetime.now()
    disputes = db.query(MC).filter(
        MC.status == 'disputed',
    ).all()

    for d in disputes:
        emp = db.query(Employee).filter(Employee.id == d.employee_id).first()
        items.append({
            "type": "month_dispute",
            "id": d.id,
            "employee_id": d.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "year": d.year,
            "month": d.month,
            "dispute_reason": d.dispute_reason or "",
            "created_at": d.created_at.isoformat() if d.created_at else None,
        })

    return items


@router.put("/open-items/{item_type}/{item_id}/resolve")
def resolve_open_item(
    item_type: str,
    item_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Offenen Punkt als erledigt markieren."""
    from app.models.models import PushNotification, CorrectionRequest, AuditLog as AuditLogModel
    action = data.get("action", "noted")  # noted, booked, rejected, not_book
    note = data.get("note", "")

    if item_type == "expired_push":
        p = db.query(PushNotification).filter(PushNotification.id == item_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Push nicht gefunden")
        p.response_status = f"admin_{action}"
        p.response_data = note or p.response_data
        p.responded_at = datetime.now()
        db.commit()
        return {"status": "resolved"}

    elif item_type == "not_present":
        p = db.query(PushNotification).filter(PushNotification.id == item_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Push nicht gefunden")
        p.response_status = f"admin_{action}"
        p.response_data = note or p.response_data
        db.commit()
        return {"status": "resolved"}

    elif item_type == "correction":
        c = db.query(CorrectionRequest).filter(CorrectionRequest.id == item_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Korrektur nicht gefunden")
        c.status = "approved" if action == "booked" else "rejected" if action == "rejected" else "noted"
        c.admin_response = note
        c.processed_by = admin.id
        c.processed_at = datetime.now()
        db.commit()
        return {"status": "resolved"}

    elif item_type == "telegram_correction":
        p = db.query(PushNotification).filter(PushNotification.id == item_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Push nicht gefunden")
        p.response_status = f"admin_{action}"
        p.response_data = note or p.response_data
        db.commit()
        return {"status": "resolved"}

    elif item_type == "auto_booked":
        # AuditLog entry - mark as acknowledged by adding admin note
        entry = db.query(AuditLogModel).filter(AuditLogModel.id == item_id).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
        entry.details = (entry.details or "") + f" [Admin: {action}] {note}"
        db.commit()
        return {"status": "resolved"}

    elif item_type == "month_dispute":
        from app.models.models import MonthlyConfirmation as MC
        d = db.query(MC).filter(MC.id == item_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="Monatskorrektur nicht gefunden")
        d.status = 'resolved'
        db.commit()
        return {"status": "resolved"}

    else:
        raise HTTPException(status_code=400, detail=f"Unbekannter Typ: {item_type}")


@router.post("/resend-monthly-confirmation/{employee_id}")
def resend_monthly_confirmation(
    employee_id: int,
    data: dict = None,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Monatsbestaetigung erneut senden nach Admin-Korrektur."""
    from app.models.models import MonthlyConfirmation as MC, KmDailyEntry
    from calendar import monthrange
    from app.services.telegram_bot import send_monthly_confirmation

    if not data:
        data = {}
    year = data.get("year", datetime.now().year)
    month = data.get("month", datetime.now().month)

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    if not emp.telegram_chat_id:
        raise HTTPException(status_code=400, detail="Kein Telegram verknuepft")

    # MonthlyConfirmation zuruecksetzen
    conf = db.query(MC).filter(
        MC.employee_id == employee_id,
        MC.year == year,
        MC.month == month,
    ).first()
    if conf:
        conf.status = 'pending'
        conf.dispute_reason = None
        conf.confirmed_at = None
        db.commit()

    # PushNotification fuer diesen Monat loeschen (damit Duplikat-Schutz nicht greift)
    from app.models.models import PushNotification
    db.query(PushNotification).filter(
        PushNotification.employee_id == employee_id,
        PushNotification.notification_type == 'monthly_confirmation',
        PushNotification.created_at >= datetime.combine(date(year, month, 1), time(0, 0)),
    ).delete()
    db.commit()

    # Stunden + KM neu berechnen
    _, last_day_num = monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, last_day_num)

    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee_id,
        TimeEntry.check_in >= datetime.combine(first_day, time(0, 0)),
        TimeEntry.check_in <= datetime.combine(last_day, time(23, 59, 59)),
        TimeEntry.object_id != 999,
    ).all()
    total_hours = sum(e.billed_hours or 0 for e in entries)
    shift_count = len(entries)
    total_amount = sum((e.billed_hours or 0) * float(e.hourly_rate or 15.0) for e in entries)

    km_entries = db.query(KmDailyEntry).filter(
        KmDailyEntry.employee_id == employee_id,
        KmDailyEntry.date >= first_day,
        KmDailyEntry.date <= last_day,
    ).all()
    total_km = sum(e.distance_km or 0 for e in km_entries)

    # Neu senden
    send_monthly_confirmation(
        employee_id, year, month,
        total_hours, total_km,
        shift_count=shift_count,
        total_amount=total_amount,
    )

    # sent_at aktualisieren
    conf = db.query(MC).filter(
        MC.employee_id == employee_id, MC.year == year, MC.month == month,
    ).first()
    if conf:
        conf.sent_at = datetime.now()
        db.commit()

    return {"status": "sent", "hours": total_hours, "shifts": shift_count, "amount": total_amount}


@router.get("/open-items/resolved")
def get_resolved_items(
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Erledigte offene Punkte (letzte 7 Tage)."""
    from app.models.models import PushNotification, CorrectionRequest, ShiftChangeRequest
    seven_days_ago = datetime.now() - timedelta(days=7)
    items = []

    # Erledigte Pushes (admin_*)
    resolved_pushes = db.query(PushNotification).filter(
        PushNotification.response_status.like('admin_%'),
        PushNotification.responded_at >= seven_days_ago,
    ).order_by(PushNotification.responded_at.desc()).limit(30).all()

    for p in resolved_pushes:
        emp = db.query(Employee).filter(Employee.id == p.employee_id).first()
        items.append({
            "type": "push",
            "id": p.id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "title": p.title,
            "action": p.response_status.replace("admin_", ""),
            "resolved_at": p.responded_at.isoformat() if p.responded_at else None,
        })

    # Erledigte Korrekturen
    resolved_corrections = db.query(CorrectionRequest).filter(
        CorrectionRequest.status.in_(['approved', 'rejected', 'noted']),
        CorrectionRequest.processed_at >= seven_days_ago,
    ).order_by(CorrectionRequest.processed_at.desc()).limit(20).all()

    for c in resolved_corrections:
        emp = db.query(Employee).filter(Employee.id == c.employee_id).first()
        items.append({
            "type": "correction",
            "id": c.id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "title": c.reason or c.correction_type,
            "action": c.status,
            "resolved_at": c.processed_at.isoformat() if c.processed_at else None,
        })

    # Erledigte Schichtaenderungen
    resolved_shifts = db.query(ShiftChangeRequest).filter(
        ShiftChangeRequest.status.in_(['resolved', 'noted', 'approved', 'rejected']),
        ShiftChangeRequest.processed_at >= seven_days_ago,
    ).order_by(ShiftChangeRequest.processed_at.desc()).limit(20).all()

    for sr in resolved_shifts:
        emp = db.query(Employee).filter(Employee.id == sr.employee_id).first()
        items.append({
            "type": "shift_change",
            "id": sr.id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "title": sr.reason or sr.request_type,
            "action": sr.status,
            "resolved_at": sr.processed_at.isoformat() if sr.processed_at else None,
        })

    items.sort(key=lambda x: x.get("resolved_at") or "", reverse=True)
    return items


@router.get("/assignments")
def get_all_assignments(
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Alle Employee-Object-Assignments."""
    from app.models.models import EmployeeObjectAssignment
    assignments = db.query(EmployeeObjectAssignment).filter(
        EmployeeObjectAssignment.is_active == True
    ).all()

    result = []
    for a in assignments:
        emp = db.query(Employee).filter(Employee.id == a.employee_id).first()
        obj = db.query(Object).filter(Object.id == a.object_id).first()
        result.append({
            "id": a.id,
            "employee_id": a.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "object_id": a.object_id,
            "object_name": obj.name if obj else "?",
            "role": a.role,
            "is_driver": a.is_driver,
            "tracking_category": a.tracking_category or "B",
            "custom_hourly_rate": float(a.custom_hourly_rate) if a.custom_hourly_rate else None,
            "custom_service_type": a.custom_service_type or None,
        })

    return result


@router.post("/assignments")
def create_assignment(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Neue Zuweisung erstellen."""
    from app.models.models import EmployeeObjectAssignment

    assignment = EmployeeObjectAssignment(
        employee_id=data.get("employee_id"),
        object_id=data.get("object_id"),
        role=data.get("role", "mitarbeiter"),
        is_driver=data.get("is_driver", False),
        tracking_category=data.get("tracking_category", "B"),
        custom_hourly_rate=data.get("custom_hourly_rate"),
        custom_service_type=data.get("custom_service_type"),
    )
    db.add(assignment)
    db.commit()
    return {"id": assignment.id, "status": "created"}


@router.put("/assignments/{assignment_id}")
def update_assignment(
    assignment_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Zuweisung aendern."""
    from app.models.models import EmployeeObjectAssignment

    assignment = db.query(EmployeeObjectAssignment).filter(
        EmployeeObjectAssignment.id == assignment_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Zuweisung nicht gefunden")

    if "role" in data:
        assignment.role = data["role"]
    if "is_driver" in data:
        assignment.is_driver = data["is_driver"]
    if "is_active" in data:
        assignment.is_active = data["is_active"]
    if "tracking_category" in data:
        assignment.tracking_category = data["tracking_category"]
    if "custom_hourly_rate" in data:
        assignment.custom_hourly_rate = data["custom_hourly_rate"]
    if "custom_service_type" in data:
        assignment.custom_service_type = data["custom_service_type"]

    db.commit()
    return {"status": "updated"}


# ==================== PUSH-VERWALTUNG ====================

@router.get("/push-settings")
def get_push_settings(
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Push-Kanal-Einstellungen aller Mitarbeiter (ohne Admin)."""
    emps = db.query(Employee).filter(
        Employee.is_active == True,
        ~Employee.personal_nr.like('A%')
    ).order_by(Employee.last_name).all()
    result = []
    for e in emps:
        user = db.query(User).filter(User.id == e.user_id).first()
        result.append({
            "id": e.id,
            "name": f"{e.first_name} {e.last_name}",
            "personal_nr": e.personal_nr,
            "tracking_mode": e.tracking_mode,
            "push_channel": e.push_channel or "telegram",
            "telegram_chat_id": e.telegram_chat_id or "",
            "email": user.email if user else "",
        })
    return result


@router.put("/push-settings/{employee_id}")
def update_push_settings(
    employee_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Push-Kanal eines Mitarbeiters aendern."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    if "push_channel" in data:
        if data["push_channel"] not in ("browser", "telegram", "none"):
            raise HTTPException(status_code=400, detail="Ungueltiger Kanal")
        emp.push_channel = data["push_channel"]
    if "telegram_chat_id" in data:
        emp.telegram_chat_id = data["telegram_chat_id"]

    db.commit()
    return {"status": "updated"}


# ==================== SCHICHTAENDERUNGEN ====================

@router.get("/shift-requests")
def get_shift_requests(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Alle Schichtaenderungsanfragen (optional nach Status filtern)."""
    q = db.query(ShiftChangeRequest).order_by(ShiftChangeRequest.created_at.desc())
    if status:
        q = q.filter(ShiftChangeRequest.status == status)
    requests = q.limit(100).all()

    result = []
    for sr in requests:
        emp = db.query(Employee).filter(Employee.id == sr.employee_id).first()
        swap_emp = None
        if sr.swap_employee_id:
            swap_emp = db.query(Employee).filter(Employee.id == sr.swap_employee_id).first()
        result.append({
            "id": sr.id,
            "employee_id": sr.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "request_type": sr.request_type,
            "requested_date": str(sr.requested_date) if sr.requested_date else None,
            "requested_start": str(sr.requested_start) if sr.requested_start else None,
            "requested_end": str(sr.requested_end) if sr.requested_end else None,
            "swap_employee_id": sr.swap_employee_id,
            "swap_employee_name": f"{swap_emp.first_name} {swap_emp.last_name}" if swap_emp else None,
            "reason": sr.reason,
            "status": sr.status,
            "admin_response": sr.admin_response,
            "created_at": sr.created_at.isoformat() if sr.created_at else None,
        })
    return result


@router.put("/shift-requests/{request_id}")
def process_shift_request(
    request_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Schichtaenderungsanfrage genehmigen/ablehnen."""
    sr = db.query(ShiftChangeRequest).filter(ShiftChangeRequest.id == request_id).first()
    if not sr:
        raise HTTPException(status_code=404, detail="Anfrage nicht gefunden")

    new_status = data.get("status")
    if new_status not in ("approved", "rejected", "resolved", "noted"):
        raise HTTPException(status_code=400, detail="Status muss 'approved', 'rejected', 'resolved' oder 'noted' sein")

    sr.status = new_status
    sr.admin_response = data.get("admin_response", "")
    sr.processed_by = admin.id
    sr.processed_at = datetime.now()

    db.commit()
    return {"status": "updated"}


# ========== CLEANUP ENDPOINT ==========

@router.post("/cleanup-test-data")
def cleanup_test_data(
    db: Session = Depends(get_db)
):
    """Einmaliges Cleanup: Stale Push-Subscriptions deaktivieren, Duplikat-Schedules loeschen."""
    results = []

    # 1. Stale Push-Subscriptions deaktivieren (die seit >4h nicht genutzt wurden)
    try:
        threshold = datetime.now() - timedelta(hours=4)
        stale = db.execute(text("""
            UPDATE push_subscriptions SET is_active = false
            WHERE is_active = true AND last_used_at < :threshold
            RETURNING id
        """), {"threshold": threshold}).fetchall()
        results.append(f"Deaktivierte Subscriptions: {[r[0] for r in stale]}")
    except Exception as e:
        results.append(f"Sub-Cleanup Fehler: {e}")

    # 2. Duplikat-Schedules entfernen (gleicher employee+object+date+start_time, behalte neueste)
    try:
        dupes = db.execute(text("""
            DELETE FROM schedules
            WHERE id IN (
                SELECT s1.id FROM schedules s1
                JOIN schedules s2 ON s1.employee_id = s2.employee_id
                    AND s1.object_id = s2.object_id
                    AND s1.date = s2.date
                    AND s1.start_time = s2.start_time
                    AND s1.id < s2.id
            )
            RETURNING id, date
        """)).fetchall()
        results.append(f"Geloeschte Duplikat-Schedules: {[(r[0], str(r[1])) for r in dupes]}")
    except Exception as e:
        results.append(f"Schedule-Cleanup Fehler: {e}")

    db.commit()
    return {"results": results}


# ========== KRANKMELDUNGEN / SICK NOTES ==========

@router.get("/sick-notes")
def get_sick_notes(
    status: str = None,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Alle Krankmeldungen (Admin)."""
    from app.models.models import SickNote
    query = db.query(SickNote).order_by(SickNote.created_at.desc())
    if status:
        query = query.filter(SickNote.status == status)
    notes = query.limit(100).all()

    result = []
    for n in notes:
        emp = db.query(Employee).filter(Employee.id == n.employee_id).first()
        result.append({
            "id": n.id,
            "employee_id": n.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "personal_nr": emp.personal_nr if emp else "?",
            "start_date": n.start_date.isoformat(),
            "end_date": n.end_date.isoformat(),
            "working_days": n.working_days,
            "au_photo_path": n.au_photo_path,
            "has_au_photo": bool(n.au_photo_path),
            "status": n.status,
            "notes": n.notes,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "confirmed_at": n.confirmed_at.isoformat() if n.confirmed_at else None,
        })
    return result


@router.post("/sick-notes")
def create_sick_note(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Admin erstellt Krankmeldung manuell."""
    from app.models.models import SickNote
    from app.services.booking_service import log_audit

    employee_id = data.get("employee_id")
    start_str = data.get("start_date")
    end_str = data.get("end_date")

    if not employee_id or not start_str or not end_str:
        raise HTTPException(status_code=400, detail="employee_id, start_date, end_date erforderlich")

    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)

    from app.api.v1.endpoints.vacation import _count_working_days
    working_days = _count_working_days(db, employee_id, start, end)

    note = SickNote(
        employee_id=employee_id,
        start_date=start,
        end_date=end,
        working_days=working_days,
        status='confirmed',
        notes=data.get("notes", ""),
        confirmed_at=datetime.now(),
        confirmed_by=admin.id,
    )
    db.add(note)
    db.flush()

    # Schichten auf 'krank' setzen + Lohnfortzahlung buchen
    _process_sick_days(db, note, admin.id)

    log_audit(
        db, admin.id, employee_id, 'sick_note_created',
        'sick_note', note.id,
        details=f"Krankmeldung {start_str} bis {end_str}, {working_days} Tage"
    )

    db.commit()
    return {"status": "ok", "id": note.id, "working_days": working_days}


@router.put("/sick-notes/{note_id}")
def update_sick_note(
    note_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Krankmeldung bestaetigen, ablehnen, stornieren oder Daten aendern."""
    from app.models.models import SickNote, TimeEntry
    from app.services.booking_service import log_audit

    note = db.query(SickNote).filter(SickNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Krankmeldung nicht gefunden")

    new_status = data.get("status")
    new_start = data.get("start_date")
    new_end = data.get("end_date")
    new_notes = data.get("notes")

    # Notizen aktualisieren
    if new_notes is not None:
        note.notes = new_notes

    # Datum-Aenderungen (nur wenn explizit uebergeben)
    if new_start or new_end:
        old_start = note.start_date
        old_end = note.end_date
        parsed_start = date.fromisoformat(new_start) if new_start else note.start_date
        parsed_end = date.fromisoformat(new_end) if new_end else note.end_date

        if parsed_start > parsed_end:
            raise HTTPException(status_code=400, detail="Startdatum muss vor Enddatum liegen")

        # Wenn bereits bestaetigt: alte Krank-Buchungen revertieren
        if note.status == 'confirmed':
            _revert_sick_note(db, note)

        note.start_date = parsed_start
        note.end_date = parsed_end

        from app.api.v1.endpoints.vacation import _count_working_days
        note.working_days = _count_working_days(db, note.employee_id, parsed_start, parsed_end)

        # Wenn bestaetigt: neu buchen mit neuen Daten
        if note.status == 'confirmed':
            _process_sick_days(db, note, admin.id)

        log_audit(
            db, admin.id, note.employee_id, 'sick_note_edited',
            'sick_note', note.id,
            details=f"Datum geaendert: {old_start}-{old_end} -> {parsed_start}-{parsed_end}"
        )

    # Status-Aenderung
    if new_status:
        if new_status not in ("confirmed", "rejected", "cancelled"):
            raise HTTPException(status_code=400, detail="Status muss 'confirmed', 'rejected' oder 'cancelled' sein")

        old_status = note.status

        # Stornieren: Krank-Buchungen rueckgaengig machen
        if new_status == 'cancelled' and old_status == 'confirmed':
            _revert_sick_note(db, note)

        # Ablehnen nach Bestaetigung: auch revertieren
        if new_status == 'rejected' and old_status == 'confirmed':
            _revert_sick_note(db, note)

        note.status = new_status
        note.confirmed_at = datetime.now()
        note.confirmed_by = admin.id

        if new_status == 'confirmed' and old_status != 'confirmed':
            _process_sick_days(db, note, admin.id)

        # Telegram-Benachrichtigung
        emp = db.query(Employee).filter(Employee.id == note.employee_id).first()
        if emp and emp.telegram_chat_id:
            try:
                from app.services.telegram_service import send_telegram_message
                status_text = {'confirmed': 'bestaetigt', 'rejected': 'abgelehnt', 'cancelled': 'storniert'}
                msg = f"Deine Krankmeldung ({note.start_date} - {note.end_date}) wurde {status_text.get(new_status, new_status)}."
                send_telegram_message(emp.telegram_chat_id, msg)
            except Exception:
                pass

        log_audit(
            db, admin.id, note.employee_id, f'sick_note_{new_status}',
            'sick_note', note.id,
            details=f"Krankmeldung {old_status} -> {new_status}: {note.start_date} bis {note.end_date}"
        )

    db.commit()
    return {"status": "ok", "new_status": note.status, "working_days": note.working_days}


def _revert_sick_note(db: Session, note):
    """Krank-Buchungen rueckgaengig machen: TimeEntries loeschen, Schichten zuruecksetzen."""
    from app.models.models import TimeEntry

    # Krank-TimeEntries dieser Krankmeldung loeschen
    db.query(TimeEntry).filter(
        TimeEntry.employee_id == note.employee_id,
        TimeEntry.notes.like(f"%Krankmeldung #{note.id}%"),
        TimeEntry.service_type == 'Krank',
    ).delete(synchronize_session='fetch')

    # Schichten von 'krank' zurueck auf 'normal' setzen
    sick_schedules = db.query(Schedule).filter(
        Schedule.employee_id == note.employee_id,
        Schedule.date >= note.start_date,
        Schedule.date <= note.end_date,
        Schedule.status == 'krank',
        Schedule.notes.like(f"%Krankmeldung #{note.id}%"),
    ).all()
    for sched in sick_schedules:
        sched.status = 'normal'
        sched.notes = None


@router.delete("/sick-notes/{note_id}")
def delete_sick_note(
    note_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Krankmeldung komplett loeschen."""
    from app.models.models import SickNote
    note = db.query(SickNote).filter(SickNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Krankmeldung nicht gefunden")
    # Wenn confirmed: erst Buchungen rueckgaengig machen
    if note.status == 'confirmed':
        _revert_sick_note(db, note)
    # Audit-Log
    emp = db.query(Employee).filter(Employee.id == note.employee_id).first()
    emp_name = f"{emp.first_name} {emp.last_name}" if emp else "?"
    from app.services.booking_service import log_audit
    log_audit(db, admin.id, note.employee_id, 'sick_note_deleted',
        'sick_note', note.id,
        details=f"Krankmeldung geloescht: {emp_name}, {note.start_date} bis {note.end_date}")
    db.delete(note)
    db.commit()
    return {"status": "ok"}


@router.get("/sick-notes/{note_id}/photo")
def get_sick_note_photo(
    note_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """AU-Foto herunterladen."""
    from app.models.models import SickNote
    from fastapi.responses import FileResponse
    import os

    note = db.query(SickNote).filter(SickNote.id == note_id).first()
    if not note or not note.au_photo_path:
        raise HTTPException(status_code=404, detail="Kein AU-Foto vorhanden")

    if not os.path.exists(note.au_photo_path):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")

    return FileResponse(note.au_photo_path)


def _process_sick_days(db: Session, note, admin_id: int):
    """Schichten auf 'krank' setzen + Lohnfortzahlung-TimeEntries erstellen."""
    from app.models.models import TimeEntry, SickNote

    emp = db.query(Employee).filter(Employee.id == note.employee_id).first()
    if not emp:
        return

    # Arbeitstage im Zeitraum ermitteln
    from app.api.v1.endpoints.vacation import _count_working_days
    current = note.start_date
    while current <= note.end_date:
        # Schicht(en) an diesem Tag
        day_schedules = db.query(Schedule).filter(
            Schedule.employee_id == note.employee_id,
            Schedule.date == current,
            Schedule.status.in_(['normal', 'vertretung']),
        ).all()

        for sched in day_schedules:
            # Schicht auf krank setzen
            sched.status = 'krank'
            sched.notes = f"Krankmeldung #{note.id}"

            # Lohnfortzahlung: TimeEntry erstellen mit gleichen Stunden/Rate
            hours = sched.planned_hours or 0
            rate = emp.hourly_rate or 15.0

            # Pruefen ob bereits ein Krank-TimeEntry existiert
            existing = db.query(TimeEntry).filter(
                TimeEntry.employee_id == note.employee_id,
                TimeEntry.check_in >= datetime.combine(current, time(0, 0)),
                TimeEntry.check_in <= datetime.combine(current, time(23, 59)),
                TimeEntry.notes.like(f"%Krankmeldung #{note.id}%"),
            ).first()

            if not existing and hours > 0:
                check_in = datetime.combine(current, sched.start_time or time(8, 0))
                check_out = datetime.combine(current, sched.end_time or time(16, 0))
                entry = TimeEntry(
                    employee_id=note.employee_id,
                    object_id=sched.object_id,
                    check_in=check_in,
                    check_out=check_out,
                    billed_hours=hours,
                    hourly_rate=rate,
                    service_type='Krank',
                    is_manual_entry=True,
                    notes=f"Lohnfortzahlung - Krankmeldung #{note.id}",
                    schedule_id=sched.id,
                )
                db.add(entry)

        # Falls keine Schicht an dem Tag aber Arbeitstag: Trotzdem pruefen
        if not day_schedules:
            # Check ob es ein normaler Arbeitstag waere
            past_schedules = db.query(Schedule.weekday).filter(
                Schedule.employee_id == note.employee_id,
                Schedule.status.in_(['normal', 'vertretung']),
            ).distinct().all()
            working_weekdays = set(wd[0] for wd in past_schedules) if past_schedules else {0,1,2,3,4}

            if current.weekday() in working_weekdays:
                # Typische Schicht suchen fuer diesen Wochentag
                typical = db.query(Schedule).filter(
                    Schedule.employee_id == note.employee_id,
                    Schedule.weekday == current.weekday(),
                    Schedule.status.in_(['normal', 'vertretung']),
                ).order_by(Schedule.date.desc()).first()

                hours = typical.planned_hours if typical else 0
                rate = emp.hourly_rate or 15.0
                obj_id = typical.object_id if typical else None
                start_t = typical.start_time if typical else time(8, 0)
                end_t = typical.end_time if typical else time(16, 0)

                if hours > 0:
                    check_in = datetime.combine(current, start_t)
                    check_out = datetime.combine(current, end_t)
                    entry = TimeEntry(
                        employee_id=note.employee_id,
                        object_id=obj_id,
                        check_in=check_in,
                        check_out=check_out,
                        billed_hours=hours,
                        hourly_rate=rate,
                        service_type='Krank',
                        is_manual_entry=True,
                        notes=f"Lohnfortzahlung - Krankmeldung #{note.id}",
                    )
                    db.add(entry)

        current += timedelta(days=1)


# ========== STAMM-DIENSTPLAN ==========

@router.get("/master-schedule")
def get_master_schedule(
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Alle aktiven Stamm-Dienstplan-Eintraege laden."""
    entries = db.query(MasterScheduleEntry).filter(
        MasterScheduleEntry.is_active == True
    ).order_by(MasterScheduleEntry.employee_id, MasterScheduleEntry.weekday).all()

    RHYTHM_LABELS = {
        'weekly': 'Woechentlich',
        'biweekly_even': '14-taegig (gerade KW)',
        'biweekly_odd': '14-taegig (ungerade KW)',
        'monthly': 'Monatlich',
    }

    result = []
    for e in entries:
        emp = db.query(Employee).filter(Employee.id == e.employee_id).first()
        obj = db.query(Object).filter(Object.id == e.object_id).first()
        result.append({
            'id': e.id,
            'employee_id': e.employee_id,
            'employee_name': f"{emp.first_name} {emp.last_name}" if emp else f"MA {e.employee_id}",
            'personal_nr': emp.personal_nr if emp else '',
            'object_id': e.object_id,
            'object_name': obj.name if obj else f"Objekt {e.object_id}",
            'weekday': e.weekday,
            'weekday_name': WEEKDAY_NAMES.get(e.weekday, str(e.weekday)),
            'start_time': e.start_time.strftime('%H:%M') if e.start_time else '',
            'end_time': e.end_time.strftime('%H:%M') if e.end_time else '',
            'planned_hours': e.planned_hours,
            'is_driver': e.is_driver,
            'rhythm': e.rhythm or 'weekly',
            'rhythm_label': RHYTHM_LABELS.get(e.rhythm or 'weekly', e.rhythm or 'weekly'),
            'month_week': e.month_week,
        })
    return result


@router.post("/master-schedule")
def create_master_schedule(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Neuen Stamm-Dienstplan-Eintrag erstellen. Unterstuetzt Mehrfach-Wochentage."""
    employee_id = data.get('employee_id')
    object_id = data.get('object_id')
    weekdays = data.get('weekdays', [])  # Array von Wochentagen
    weekday = data.get('weekday')         # Einzelner Wochentag (Rueckwaerts-kompatibel)
    start_str = data.get('start_time', '08:00')
    end_str = data.get('end_time', '16:00')
    is_driver = data.get('is_driver', False)
    rhythm = data.get('rhythm', 'weekly')
    month_week = data.get('month_week')

    # Wenn weekdays leer, aber weekday gesetzt -> Einzeln-Modus
    if not weekdays and weekday is not None:
        weekdays = [weekday]

    if employee_id is None or object_id is None or not weekdays:
        raise HTTPException(status_code=400, detail="employee_id, object_id und weekday(s) erforderlich")

    if rhythm not in ('weekly', 'biweekly_even', 'biweekly_odd', 'monthly', 'daily'):
        raise HTTPException(status_code=400, detail="Ungueltiger Rhythmus")

    # Bei daily: Mo-Fr automatisch
    if rhythm == 'daily':
        weekdays = [0, 1, 2, 3, 4]  # Mo-Fr
        rhythm = 'weekly'  # Intern als weekly pro Tag speichern

    start_time = datetime.strptime(start_str, '%H:%M').time()
    end_time = datetime.strptime(end_str, '%H:%M').time()

    start_dt = datetime.combine(date.today(), start_time)
    end_dt = datetime.combine(date.today(), end_time)
    planned_hours = round((end_dt - start_dt).total_seconds() / 3600, 2)

    created_ids = []
    skipped = []
    for wd in weekdays:
        wd = int(wd)
        existing = db.query(MasterScheduleEntry).filter(
            MasterScheduleEntry.employee_id == employee_id,
            MasterScheduleEntry.object_id == object_id,
            MasterScheduleEntry.weekday == wd,
            MasterScheduleEntry.rhythm == rhythm,
        ).first()
        if existing:
            skipped.append(wd)
            continue

        entry = MasterScheduleEntry(
            employee_id=employee_id,
            object_id=object_id,
            weekday=wd,
            start_time=start_time,
            end_time=end_time,
            planned_hours=planned_hours,
            is_driver=is_driver,
            rhythm=rhythm,
            month_week=month_week if rhythm == 'monthly' else None,
        )
        db.add(entry)
        db.flush()
        created_ids.append(entry.id)

    db.commit()
    return {
        "status": "ok",
        "created": len(created_ids),
        "skipped": len(skipped),
        "ids": created_ids,
    }


@router.put("/master-schedule/{entry_id}")
def update_master_schedule(
    entry_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Stamm-Dienstplan-Eintrag aktualisieren."""
    entry = db.query(MasterScheduleEntry).filter(MasterScheduleEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    if 'start_time' in data:
        entry.start_time = datetime.strptime(data['start_time'], '%H:%M').time()
    if 'end_time' in data:
        entry.end_time = datetime.strptime(data['end_time'], '%H:%M').time()
    if 'is_driver' in data:
        entry.is_driver = data['is_driver']
    if 'object_id' in data:
        entry.object_id = data['object_id']
    if 'employee_id' in data:
        entry.employee_id = data['employee_id']
    if 'weekday' in data:
        entry.weekday = data['weekday']
    if 'rhythm' in data:
        entry.rhythm = data['rhythm']
    if 'month_week' in data:
        entry.month_week = data['month_week']

    # Stunden neu berechnen
    start_dt = datetime.combine(date.today(), entry.start_time)
    end_dt = datetime.combine(date.today(), entry.end_time)
    entry.planned_hours = round((end_dt - start_dt).total_seconds() / 3600, 2)

    db.commit()
    return {"status": "ok"}


@router.delete("/master-schedule/{entry_id}")
def delete_master_schedule(
    entry_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Stamm-Dienstplan-Eintrag loeschen."""
    entry = db.query(MasterScheduleEntry).filter(MasterScheduleEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    db.delete(entry)
    db.commit()
    return {"status": "ok"}


@router.post("/master-schedule/generate")
def generate_month_schedule(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Dienstplan fuer einen Monat aus Stamm-Dienstplan generieren.
    Ueberspringt Tage mit bestehenden Urlaub-/Krank-Eintraegen.
    dry_run=true: Nur Vorschau, keine DB-Aenderung.
    """
    target_month = data.get('month')
    target_year = data.get('year')
    overwrite = data.get('overwrite', False)
    dry_run = data.get('dry_run', False)

    if not target_month or not target_year:
        raise HTTPException(status_code=400, detail="month und year erforderlich")

    # Alle aktiven Master-Eintraege laden
    masters = db.query(MasterScheduleEntry).filter(
        MasterScheduleEntry.is_active == True
    ).all()

    if not masters:
        raise HTTPException(status_code=400, detail="Keine Stamm-Dienstplan-Eintraege vorhanden")

    # Erster und letzter Tag des Monats
    import calendar
    _, last_day = calendar.monthrange(target_year, target_month)
    first_date = date(target_year, target_month, 1)
    last_date = date(target_year, target_month, last_day)

    # Fuer dry_run: Employee/Object-Dicts fuer Namen
    if dry_run:
        all_emps = {e.id: e for e in db.query(Employee).all()}
        all_objs = {o.id: o for o in db.query(Object).all()}
        preview_items = []

    WEEKDAY_NAMES = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

    created = 0
    skipped = 0
    conflicts = []
    affected_employee_ids = set()

    for master in masters:
        rhythm = master.rhythm or 'weekly'

        # Jeden Tag im Monat pruefen
        current = first_date
        while current <= last_date:
            # Python weekday(): Mo=0..So=6 - passt zu unserem Mapping
            if current.weekday() == master.weekday:

                # === RHYTHMUS-CHECK ===
                if rhythm == 'biweekly_even':
                    iso_week = current.isocalendar()[1]
                    if iso_week % 2 != 0:
                        current += timedelta(days=1)
                        continue
                elif rhythm == 'biweekly_odd':
                    iso_week = current.isocalendar()[1]
                    if iso_week % 2 != 1:
                        current += timedelta(days=1)
                        continue
                elif rhythm == 'monthly':
                    target_week = master.month_week or 1
                    if target_week == -1:
                        import calendar
                        _, ml = calendar.monthrange(current.year, current.month)
                        last_of_month = date(current.year, current.month, ml)
                        diff = (last_of_month.weekday() - master.weekday) % 7
                        last_matching = last_of_month - timedelta(days=diff)
                        if current != last_matching:
                            current += timedelta(days=1)
                            continue
                    else:
                        day_count = 0
                        check = date(current.year, current.month, 1)
                        while check <= current:
                            if check.weekday() == master.weekday:
                                day_count += 1
                            check += timedelta(days=1)
                        if day_count != target_week:
                            current += timedelta(days=1)
                            continue

                # Pruefen ob bereits ein Eintrag existiert (Urlaub/Krank)
                existing = db.query(Schedule).filter(
                    Schedule.employee_id == master.employee_id,
                    Schedule.date == current,
                    Schedule.status.in_(['urlaub', 'krank']),
                ).first()

                if existing:
                    skipped += 1
                    current += timedelta(days=1)
                    continue

                # Pruefen ob bereits eine normale Schicht existiert
                existing_normal = db.query(Schedule).filter(
                    Schedule.employee_id == master.employee_id,
                    Schedule.object_id == master.object_id,
                    Schedule.date == current,
                    Schedule.status.in_(['normal', 'vertretung']),
                ).first()

                if existing_normal and not overwrite:
                    skipped += 1
                    current += timedelta(days=1)
                    continue

                if existing_normal and overwrite:
                    if not dry_run:
                        existing_normal.start_time = master.start_time
                        existing_normal.end_time = master.end_time
                        existing_normal.planned_hours = master.planned_hours
                        existing_normal.is_driver = master.is_driver
                    else:
                        emp = all_emps.get(master.employee_id)
                        obj = all_objs.get(master.object_id)
                        preview_items.append({
                            "employee_id": master.employee_id,
                            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
                            "personal_nr": emp.personal_nr if emp else "?",
                            "object_id": master.object_id,
                            "object_name": obj.name if obj else "?",
                            "date": current.isoformat(),
                            "weekday_name": WEEKDAY_NAMES[current.weekday()],
                            "start_time": master.start_time.strftime("%H:%M"),
                            "end_time": master.end_time.strftime("%H:%M"),
                            "planned_hours": master.planned_hours,
                            "is_driver": master.is_driver,
                            "action": "update",
                        })
                    created += 1
                    affected_employee_ids.add(master.employee_id)
                    current += timedelta(days=1)
                    continue

                # Overlap-Check
                overlap = check_schedule_overlap(
                    db, master.employee_id, current,
                    master.start_time, master.end_time
                )
                if overlap:
                    conflicts.append(overlap)
                    skipped += 1
                    current += timedelta(days=1)
                    continue

                if not dry_run:
                    new_schedule = Schedule(
                        employee_id=master.employee_id,
                        object_id=master.object_id,
                        weekday=master.weekday,
                        date=current,
                        start_time=master.start_time,
                        end_time=master.end_time,
                        planned_hours=master.planned_hours,
                        status='normal',
                        is_driver=master.is_driver,
                    )
                    db.add(new_schedule)
                else:
                    emp = all_emps.get(master.employee_id)
                    obj = all_objs.get(master.object_id)
                    preview_items.append({
                        "employee_id": master.employee_id,
                        "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
                        "personal_nr": emp.personal_nr if emp else "?",
                        "object_id": master.object_id,
                        "object_name": obj.name if obj else "?",
                        "date": current.isoformat(),
                        "weekday_name": WEEKDAY_NAMES[current.weekday()],
                        "start_time": master.start_time.strftime("%H:%M"),
                        "end_time": master.end_time.strftime("%H:%M"),
                        "planned_hours": master.planned_hours,
                        "is_driver": master.is_driver,
                        "action": "create",
                    })
                created += 1
                affected_employee_ids.add(master.employee_id)

            current += timedelta(days=1)

    month_name = ['', 'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
                  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'][target_month]

    if dry_run:
        # Keine DB-Aenderung - Vorschau zurueckgeben
        preview_items.sort(key=lambda x: (x['personal_nr'], x['date']))
        return {
            "status": "preview",
            "preview": preview_items,
            "total": created,
            "skipped": skipped,
            "conflicts": conflicts[:10],
            "message": f"Vorschau: {created} Schichten fuer {month_name} {target_year}, {skipped} wuerden uebersprungen"
        }

    db.commit()

    # Auto-Reset: Bestaetigungen zuruecksetzen fuer betroffene MAs
    for emp_id in affected_employee_ids:
        check_and_reset_confirmation(db, emp_id, first_date)

    return {
        "status": "ok",
        "created": created,
        "skipped": skipped,
        "conflicts": conflicts[:10],
        "message": f"{created} Schichten fuer {month_name} {target_year} erstellt, {skipped} uebersprungen"
    }


# ========== KUNDEN-UMSAETZE ==========

@router.get("/customer-revenues")
def get_customer_revenues(
    year: int = Query(...),
    month: int = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Kunden-Umsaetze laden (nach Jahr, optional nach Monat)."""
    query = db.query(CustomerRevenue).filter(CustomerRevenue.year == year)
    if month:
        query = query.filter(CustomerRevenue.month == month)

    revenues = query.all()
    result = []
    for r in revenues:
        obj = db.query(Object).filter(Object.id == r.object_id).first()
        cust = db.query(Customer).filter(Customer.id == r.customer_id).first() if r.customer_id else None
        result.append({
            'id': r.id,
            'object_id': r.object_id,
            'object_name': obj.name if obj else f"Objekt {r.object_id}",
            'customer_id': r.customer_id,
            'customer_name': cust.name if cust else '',
            'year': r.year,
            'month': r.month,
            'revenue': r.revenue,
            'notes': r.notes or '',
        })
    return result


@router.post("/customer-revenues")
def create_or_update_revenue(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Kunden-Umsatz erstellen oder aktualisieren (Upsert)."""
    object_id = data.get('object_id')
    year = data.get('year')
    month = data.get('month')
    revenue = data.get('revenue', 0)
    notes = data.get('notes', '')

    if not object_id or not year or not month:
        raise HTTPException(status_code=400, detail="object_id, year, month erforderlich")

    # Customer-ID vom Objekt holen
    obj = db.query(Object).filter(Object.id == object_id).first()
    customer_id = obj.customer_id if obj else None

    # Upsert
    existing = db.query(CustomerRevenue).filter(
        CustomerRevenue.object_id == object_id,
        CustomerRevenue.year == year,
        CustomerRevenue.month == month,
    ).first()

    if existing:
        existing.revenue = revenue
        existing.notes = notes
        existing.customer_id = customer_id
    else:
        entry = CustomerRevenue(
            object_id=object_id,
            customer_id=customer_id,
            year=year,
            month=month,
            revenue=revenue,
            notes=notes,
        )
        db.add(entry)

    db.commit()
    return {"status": "ok"}


@router.post("/customer-revenues/bulk")
def bulk_update_revenues(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Mehrere Umsaetze auf einmal speichern."""
    entries = data.get('entries', [])
    updated = 0
    for entry_data in entries:
        object_id = entry_data.get('object_id')
        year = entry_data.get('year')
        month = entry_data.get('month')
        revenue = entry_data.get('revenue', 0)

        if not object_id or not year or not month:
            continue

        obj = db.query(Object).filter(Object.id == object_id).first()
        customer_id = obj.customer_id if obj else None

        existing = db.query(CustomerRevenue).filter(
            CustomerRevenue.object_id == object_id,
            CustomerRevenue.year == year,
            CustomerRevenue.month == month,
        ).first()

        if existing:
            existing.revenue = revenue
            existing.customer_id = customer_id
        else:
            new_entry = CustomerRevenue(
                object_id=object_id,
                customer_id=customer_id,
                year=year,
                month=month,
                revenue=revenue,
            )
            db.add(new_entry)
        updated += 1

    db.commit()
    return {"status": "ok", "updated": updated}


# ========== STATISTIKEN ==========

@router.get("/statistics/overview")
def get_statistics_overview(
    year: int = Query(...),
    month: int = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Statistik-Uebersicht: Stunden, Kosten, Umsatz, Gewinn pro Objekt/Monat."""
    import calendar

    if month:
        months = [month]
    else:
        months = list(range(1, 13))

    result = []
    objects = db.query(Object).filter(Object.is_active == True).all()

    for m in months:
        _, last_day = calendar.monthrange(year, m)
        start = datetime(year, m, 1)
        end = datetime(year, m, last_day, 23, 59, 59)

        month_data = {
            'month': m,
            'month_name': ['', 'Jan', 'Feb', 'Mrz', 'Apr', 'Mai', 'Jun',
                           'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'][m],
            'objects': [],
            'total_hours': 0,
            'total_costs': 0,
            'total_revenue': 0,
            'total_profit': 0,
        }

        for obj in objects:
            entries = db.query(TimeEntry).filter(
                TimeEntry.object_id == obj.id,
                TimeEntry.check_in >= start,
                TimeEntry.check_in <= end,
                TimeEntry.check_out != None,
            ).all()

            hours = sum(e.billed_hours or 0 for e in entries)
            costs = sum((e.billed_hours or 0) * (e.hourly_rate or 0) for e in entries)

            rev = db.query(CustomerRevenue).filter(
                CustomerRevenue.object_id == obj.id,
                CustomerRevenue.year == year,
                CustomerRevenue.month == m,
            ).first()
            revenue = rev.revenue if rev else 0

            profit = revenue - costs

            if hours > 0 or revenue > 0:
                # Personalkosten pro MA aufschluesseln
                emp_costs = {}
                for e in entries:
                    eid = e.employee_id
                    if eid not in emp_costs:
                        emp_obj = db.query(Employee).filter(Employee.id == eid).first()
                        emp_costs[eid] = {
                            'employee_id': eid,
                            'employee_name': f"{emp_obj.first_name} {emp_obj.last_name}" if emp_obj else f"MA {eid}",
                            'hours': 0,
                            'costs': 0,
                        }
                    emp_costs[eid]['hours'] += (e.billed_hours or 0)
                    emp_costs[eid]['costs'] += (e.billed_hours or 0) * (e.hourly_rate or 0)

                employees_detail = sorted(
                    [{'employee_id': v['employee_id'], 'employee_name': v['employee_name'],
                      'hours': round(v['hours'], 2), 'costs': round(v['costs'], 2)}
                     for v in emp_costs.values()],
                    key=lambda x: x['hours'], reverse=True
                )

                obj_data = {
                    'object_id': obj.id,
                    'object_name': obj.name,
                    'hours': round(hours, 2),
                    'costs': round(costs, 2),
                    'revenue': round(revenue, 2),
                    'profit': round(profit, 2),
                    'employee_count': len(set(e.employee_id for e in entries)),
                    'employees': employees_detail,
                }
                month_data['objects'].append(obj_data)
                month_data['total_hours'] += hours
                month_data['total_costs'] += costs
                month_data['total_revenue'] += revenue
                month_data['total_profit'] += profit

        month_data['total_hours'] = round(month_data['total_hours'], 2)
        month_data['total_costs'] = round(month_data['total_costs'], 2)
        month_data['total_revenue'] = round(month_data['total_revenue'], 2)
        month_data['total_profit'] = round(month_data['total_profit'], 2)
        result.append(month_data)

    return result


@router.get("/statistics/employees")
def get_employee_statistics(
    year: int = Query(...),
    month: int = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Statistik pro Mitarbeiter: Stunden, Kosten pro Monat."""
    import calendar

    if month:
        months = [month]
    else:
        months = list(range(1, 13))

    employees = db.query(Employee).join(User).filter(
        User.role != 'admin',
        Employee.is_active == True,
    ).all()

    result = []
    for emp in employees:
        emp_data = {
            'employee_id': emp.id,
            'employee_name': f"{emp.first_name} {emp.last_name}",
            'personal_nr': emp.personal_nr,
            'months': [],
            'total_hours': 0,
            'total_costs': 0,
        }

        for m in months:
            _, last_day = calendar.monthrange(year, m)
            start = datetime(year, m, 1)
            end = datetime(year, m, last_day, 23, 59, 59)

            entries = db.query(TimeEntry).filter(
                TimeEntry.employee_id == emp.id,
                TimeEntry.check_in >= start,
                TimeEntry.check_in <= end,
                TimeEntry.check_out != None,
            ).all()

            hours = sum(e.billed_hours or 0 for e in entries)
            costs = sum((e.billed_hours or 0) * (e.hourly_rate or 0) for e in entries)

            sick_hours = sum(
                (e.billed_hours or 0) for e in entries
                if e.service_type == 'Krank'
            )
            vacation_hours = sum(
                (e.billed_hours or 0) for e in entries
                if e.object_id == 999
            )

            emp_data['months'].append({
                'month': m,
                'hours': round(hours, 2),
                'costs': round(costs, 2),
                'sick_hours': round(sick_hours, 2),
                'vacation_hours': round(vacation_hours, 2),
            })
            emp_data['total_hours'] += hours
            emp_data['total_costs'] += costs

        emp_data['total_hours'] = round(emp_data['total_hours'], 2)
        emp_data['total_costs'] = round(emp_data['total_costs'], 2)
        result.append(emp_data)

    return result


# ========== OBJEKTLEITER-VERWALTUNG ==========

@router.get("/objektleiter")
def get_objektleiter_list(
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Alle User mit Rolle objektleiter laden inkl. zugewiesener Objekte."""
    from app.models.models import UserRole
    users = db.query(User).filter(User.role == 'objektleiter', User.is_active == True).all()
    result = []
    for u in users:
        emp = db.query(Employee).filter(Employee.user_id == u.id).first()
        assignments = db.query(UserObjectAssignment).filter(
            UserObjectAssignment.user_id == u.id,
            UserObjectAssignment.is_active == True,
        ).all()
        obj_names = []
        for a in assignments:
            obj = db.query(Object).filter(Object.id == a.object_id).first()
            obj_names.append({'id': a.object_id, 'name': obj.name if obj else f"Objekt {a.object_id}"})
        result.append({
            'user_id': u.id,
            'email': u.email,
            'name': f"{emp.first_name} {emp.last_name}" if emp else u.email,
            'personal_nr': emp.personal_nr if emp else '',
            'objects': obj_names,
        })
    return result


@router.put("/objektleiter/{user_id}/role")
def set_user_role(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """User-Rolle setzen (admin/objektleiter/mitarbeiter)."""
    new_role = data.get('role', 'mitarbeiter')
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    user.role = new_role
    db.commit()
    return {"status": "ok", "role": new_role}


@router.post("/objektleiter/{user_id}/objects")
def assign_objects_to_objektleiter(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(verify_admin)
):
    """Objekte einem Objektleiter zuweisen. Ersetzt bestehende Zuweisungen."""
    object_ids = data.get('object_ids', [])

    # Alle bestehenden deaktivieren
    db.query(UserObjectAssignment).filter(
        UserObjectAssignment.user_id == user_id
    ).update({'is_active': False})

    # Neue zuweisen
    for obj_id in object_ids:
        existing = db.query(UserObjectAssignment).filter(
            UserObjectAssignment.user_id == user_id,
            UserObjectAssignment.object_id == obj_id,
        ).first()
        if existing:
            existing.is_active = True
        else:
            db.add(UserObjectAssignment(
                user_id=user_id,
                object_id=obj_id,
                is_active=True,
            ))

    db.commit()
    return {"status": "ok", "assigned": len(object_ids)}


@router.get("/my-role")
def get_my_role(
    db: Session = Depends(get_db),
    user: User = Depends(verify_admin_or_objektleiter)
):
    """Eigene Rolle und zugewiesene Objekte abrufen."""
    object_ids = get_user_object_ids(db, user)
    objects = []
    if object_ids is not None:
        for oid in object_ids:
            obj = db.query(Object).filter(Object.id == oid).first()
            if obj:
                objects.append({'id': obj.id, 'name': obj.name})

    return {
        'user_id': user.id,
        'role': user.role,
        'is_admin': user.role == 'admin',
        'objects': objects if object_ids is not None else None,  # None = alle
    }


# ============================================================
# BWA / Statistik Endpoints
# ============================================================

@router.get("/bwa")
def get_bwa(
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
    admin=Depends(verify_admin)
):
    """Mini-BWA: Umsatz, Personalkosten, Fixkosten, Vorsteuer, Gewinn pro Objekt + Gesamt."""
    from calendar import monthrange
    _, last_day_num = monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, last_day_num)

    # Finanz-Einstellungen laden
    settings = {}
    for s in db.query(FinanceSetting).all():
        settings[s.setting_key] = s.setting_value
    vorsteuer_pct = float(settings.get('vorsteuer_pct', '60'))
    vat_rate = float(settings.get('vat_rate', '19'))

    # Lohnnebenkosten: monatsspezifisch oder Standard
    lnk_key = f"lohnnebenkosten_pct_{year}_{month:02d}"
    lnk_betrag_key = f"lohnnebenkosten_betrag_{year}_{month:02d}"
    lohnnebenkosten_pct = float(settings.get(lnk_key, settings.get('lohnnebenkosten_pct', '30')))
    lnk_betrag = float(settings[lnk_betrag_key]) if lnk_betrag_key in settings else None
    lnk_is_monthly = lnk_key in settings or lnk_betrag_key in settings

    # Fixkosten laden: Monatlich ueberschreibbar, sonst Standard
    monthly_fc = db.query(MonthlyFixedCost).filter(
        MonthlyFixedCost.year == year,
        MonthlyFixedCost.month == month,
    ).order_by(MonthlyFixedCost.sort_order).all()

    if monthly_fc:
        # Monatliche Werte: amount ist immer schon der Monatsbetrag
        fc_details = [{"id": fc.id, "name": fc.name, "amount": round(fc.amount, 2)} for fc in monthly_fc]
        uses_monthly = True
    else:
        # Standard: Jahreskosten durch 12 teilen
        std_fc = db.query(FixedCost).filter(FixedCost.is_active == True).order_by(FixedCost.sort_order).all()
        fc_details = []
        for fc in std_fc:
            ct = getattr(fc, 'cost_type', 'monthly') or 'monthly'
            monthly_amount = round(fc.amount / 12, 2) if ct == 'yearly' else fc.amount
            fc_details.append({
                "id": fc.id, "name": fc.name, "amount": round(monthly_amount, 2),
                "original_amount": fc.amount, "cost_type": ct,
            })
        uses_monthly = False
    total_fixed_costs = sum(fc['amount'] for fc in fc_details)

    # Alle aktiven Objekte (ohne Urlaub 999)
    objects = db.query(Object).filter(
        Object.is_active == True,
        Object.id != 999,
    ).all()
    # Auch inaktive Objekte einbeziehen wenn sie Umsatz haben
    inactive_with_revenue = db.query(Object).join(CustomerRevenue, CustomerRevenue.object_id == Object.id).filter(
        Object.is_active == False,
        CustomerRevenue.year == year,
        CustomerRevenue.month == month,
    ).all()
    all_objects = {o.id: o for o in objects}
    for o in inactive_with_revenue:
        if o.id not in all_objects:
            all_objects[o.id] = o

    # Umsaetze laden
    revenues = {}
    for rev in db.query(CustomerRevenue).filter(
        CustomerRevenue.year == year,
        CustomerRevenue.month == month,
    ).all():
        revenues[rev.object_id] = rev.revenue or 0

    # Personalkosten pro Objekt berechnen (aus time_entries)
    personal_costs = defaultdict(float)
    total_hours = 0.0
    entries = db.query(TimeEntry).filter(
        TimeEntry.check_in >= datetime.combine(first_day, time(0, 0)),
        TimeEntry.check_in <= datetime.combine(last_day, time(23, 59, 59)),
        TimeEntry.object_id != 999,
    ).all()
    for e in entries:
        hours = float(e.billed_hours or 0)
        rate = float(e.hourly_rate or 15.0)
        cost = hours * rate
        if e.object_id:
            personal_costs[e.object_id] += cost
        total_hours += hours

    # Lohnnebenkosten-Faktor oder fester Betrag
    lnk_faktor = 1 + lohnnebenkosten_pct / 100

    # Pro Objekt aufbereiten
    objekt_rows = []
    total_netto = 0.0
    total_personal_netto = 0.0
    for obj_id, obj in sorted(all_objects.items(), key=lambda x: x[1].name):
        netto = revenues.get(obj_id, 0)
        personal_netto = personal_costs.get(obj_id, 0)
        # Pro Objekt immer mit Prozent rechnen (Betrag gilt nur fuer Gesamt)
        personal_brutto = round(personal_netto * lnk_faktor, 2)
        gewinn = netto - personal_brutto
        objekt_rows.append({
            "object_id": obj_id,
            "object_name": obj.name,
            "is_active": obj.is_active,
            "netto_umsatz": round(netto, 2),
            "personalkosten_netto": round(personal_netto, 2),
            "personalkosten": round(personal_brutto, 2),
            "gewinn": round(gewinn, 2),
        })
        total_netto += netto
        total_personal_netto += personal_netto

    # Gesamt-Berechnung: Fester Betrag ueberschreibt Prozent
    if lnk_betrag is not None:
        total_personal_brutto = round(total_personal_netto + lnk_betrag, 2)
    else:
        total_personal_brutto = round(total_personal_netto * lnk_faktor, 2)
    brutto_umsatz = round(total_netto * (1 + vat_rate / 100), 2)
    mwst_betrag = round(total_netto * vat_rate / 100, 2)
    vorsteuer_abfuehrung = round(mwst_betrag * vorsteuer_pct / 100, 2)
    netto_gewinn = round(total_netto - total_personal_brutto - total_fixed_costs - vorsteuer_abfuehrung, 2)

    return {
        "year": year,
        "month": month,
        "gesamt": {
            "netto_umsatz": round(total_netto, 2),
            "brutto_umsatz": brutto_umsatz,
            "mwst_betrag": mwst_betrag,
            "vorsteuer_abfuehrung": vorsteuer_abfuehrung,
            "personalkosten_netto": round(total_personal_netto, 2),
            "personalkosten": round(total_personal_brutto, 2),
            "lohnnebenkosten_pct": lohnnebenkosten_pct,
            "lohnnebenkosten_betrag": lnk_betrag,
            "fixkosten": round(total_fixed_costs, 2),
            "netto_gewinn": netto_gewinn,
            "total_hours": round(total_hours, 2),
        },
        "objekte": objekt_rows,
        "fixkosten_details": fc_details,
        "fixkosten_is_monthly": uses_monthly,
        "lohnnebenkosten_is_monthly": lnk_is_monthly,
        "settings": {
            "vorsteuer_pct": vorsteuer_pct,
            "vat_rate": vat_rate,
            "lohnnebenkosten_pct": float(settings.get('lohnnebenkosten_pct', '30')),
            "display_mode": settings.get('display_mode', 'netto'),
        },
    }


# ============================================================
# Finanz-Einstellungen Endpoints
# ============================================================

@router.get("/finance-settings")
def get_finance_settings(db: Session = Depends(get_db), admin=Depends(verify_admin)):
    """Alle Finanz-Einstellungen + Fixkosten laden."""
    settings = {}
    for s in db.query(FinanceSetting).all():
        settings[s.setting_key] = s.setting_value

    fixed_costs = db.query(FixedCost).filter(
        FixedCost.is_active == True
    ).order_by(FixedCost.sort_order).all()

    return {
        "settings": settings,
        "fixed_costs": [
            {"id": fc.id, "name": fc.name, "amount": fc.amount, "cost_type": fc.cost_type or 'monthly', "sort_order": fc.sort_order}
            for fc in fixed_costs
        ],
    }


@router.put("/finance-settings")
async def update_finance_settings(request: Request, db: Session = Depends(get_db), admin=Depends(verify_admin)):
    """Finanz-Einstellungen speichern."""
    data = await request.json()

    # Settings updaten
    for key, value in data.get('settings', {}).items():
        setting = db.query(FinanceSetting).filter(FinanceSetting.setting_key == key).first()
        if setting:
            setting.setting_value = str(value)
            setting.updated_at = datetime.now()
        else:
            db.add(FinanceSetting(setting_key=key, setting_value=str(value)))

    # Fixkosten updaten
    if 'fixed_costs' in data:
        # Alle alten deaktivieren
        db.query(FixedCost).update({FixedCost.is_active: False})
        # Neue/aktualisierte einfuegen
        for i, fc in enumerate(data['fixed_costs']):
            cost_type = fc.get('cost_type', 'monthly')
            if fc.get('id'):
                existing = db.query(FixedCost).filter(FixedCost.id == fc['id']).first()
                if existing:
                    existing.name = fc['name']
                    existing.amount = float(fc['amount'])
                    existing.cost_type = cost_type
                    existing.is_active = True
                    existing.sort_order = i
                    continue
            db.add(FixedCost(
                name=fc['name'],
                amount=float(fc['amount']),
                cost_type=cost_type,
                is_active=True,
                sort_order=i,
            ))

    db.commit()
    return {"status": "ok"}


@router.put("/bwa/fixkosten")
async def save_monthly_fixkosten(request: Request, db: Session = Depends(get_db), admin=Depends(verify_admin)):
    """Fixkosten fuer einen bestimmten Monat speichern (ueberschreibt Standard)."""
    data = await request.json()
    yr = data.get('year')
    mo = data.get('month')
    costs = data.get('costs', [])

    if not yr or not mo:
        raise HTTPException(status_code=400, detail="year und month erforderlich")

    # Alte monatliche Eintraege loeschen
    db.query(MonthlyFixedCost).filter(
        MonthlyFixedCost.year == yr,
        MonthlyFixedCost.month == mo,
    ).delete()

    # Neue eintragen
    for i, fc in enumerate(costs):
        if fc.get('name', '').strip():
            db.add(MonthlyFixedCost(
                year=yr,
                month=mo,
                name=fc['name'].strip(),
                amount=float(fc.get('amount', 0)),
                sort_order=i,
            ))

    db.commit()
    return {"status": "saved"}


@router.delete("/bwa/fixkosten/{yr}/{mo}")
def reset_monthly_fixkosten(yr: int, mo: int, db: Session = Depends(get_db), admin=Depends(verify_admin)):
    """Monatliche Fixkosten loeschen -> faellt auf Standard zurueck."""
    deleted = db.query(MonthlyFixedCost).filter(
        MonthlyFixedCost.year == yr,
        MonthlyFixedCost.month == mo,
    ).delete()
    db.commit()
    return {"status": "reset", "deleted": deleted}


@router.put("/bwa/lohnnebenkosten")
async def save_monthly_lohnnebenkosten(request: Request, db: Session = Depends(get_db), admin=Depends(verify_admin)):
    """Lohnnebenkosten fuer einen bestimmten Monat speichern (Prozent UND/ODER Betrag)."""
    data = await request.json()
    yr = data.get('year')
    mo = data.get('month')
    pct = data.get('pct')
    betrag = data.get('betrag')

    if not yr or not mo:
        raise HTTPException(status_code=400, detail="year und month erforderlich")

    # Prozent speichern (wenn angegeben)
    if pct is not None:
        pct_key = f"lohnnebenkosten_pct_{yr}_{int(mo):02d}"
        setting = db.query(FinanceSetting).filter(FinanceSetting.setting_key == pct_key).first()
        if setting:
            setting.setting_value = str(pct)
            setting.updated_at = datetime.now()
        else:
            db.add(FinanceSetting(setting_key=pct_key, setting_value=str(pct)))

    # Betrag speichern oder loeschen
    betrag_key = f"lohnnebenkosten_betrag_{yr}_{int(mo):02d}"
    if betrag is not None and betrag != '' and float(betrag) > 0:
        setting = db.query(FinanceSetting).filter(FinanceSetting.setting_key == betrag_key).first()
        if setting:
            setting.setting_value = str(betrag)
            setting.updated_at = datetime.now()
        else:
            db.add(FinanceSetting(setting_key=betrag_key, setting_value=str(betrag)))
    else:
        # Betrag loeschen wenn leer/0
        db.query(FinanceSetting).filter(FinanceSetting.setting_key == betrag_key).delete()

    db.commit()
    return {"status": "saved"}


@router.delete("/bwa/lohnnebenkosten/{yr}/{mo}")
def reset_monthly_lohnnebenkosten(yr: int, mo: int, db: Session = Depends(get_db), admin=Depends(verify_admin)):
    """Monatliche Lohnnebenkosten loeschen -> faellt auf Standard zurueck."""
    pct_key = f"lohnnebenkosten_pct_{yr}_{int(mo):02d}"
    betrag_key = f"lohnnebenkosten_betrag_{yr}_{int(mo):02d}"
    d1 = db.query(FinanceSetting).filter(FinanceSetting.setting_key == pct_key).delete()
    d2 = db.query(FinanceSetting).filter(FinanceSetting.setting_key == betrag_key).delete()
    db.commit()
    return {"status": "reset", "deleted": d1 + d2}


# ============================================================
# Lexware XML Export
# ============================================================

def _merge_intervals(intervals):
    """Ueberlappende Zeitintervalle zusammenfassen. Gibt max 4 Bloecke zurueck."""
    if not intervals:
        return []
    # Sortieren nach Start
    sorted_ivs = sorted(intervals, key=lambda x: x[0])
    merged = [list(sorted_ivs[0])]
    for start, end in sorted_ivs[1:]:
        if start <= merged[-1][1]:
            # Ueberlappung: Ende erweitern
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged[:4]  # Lexware unterstuetzt max 4 Bloecke pro Tag


def _time_str(dt_val):
    """DateTime oder Time zu HH:MM String."""
    if isinstance(dt_val, datetime):
        return dt_val.strftime('%H:%M')
    if isinstance(dt_val, time):
        return dt_val.strftime('%H:%M')
    return str(dt_val)[:5]


def _generate_lexware_xml(employee_name, personal_nr, year, month, day_data):
    """Generiert eine Excel-XML-Datei (SpreadsheetML) fuer Lexware Import."""
    from calendar import monthrange
    _, last_day = monthrange(year, month)

    rows_xml = ""
    for day in range(1, last_day + 1):
        dt = date(year, month, day)
        date_str = dt.strftime('%d.%m.%Y')
        blocks = day_data.get(day, [])

        # Von1/Bis1 bis Von4/Bis4
        cells = [f'    <Cell><Data ss:Type="String">{date_str}</Data></Cell>']
        total_minutes = 0
        for i in range(4):
            if i < len(blocks):
                von = _time_str(blocks[i][0])
                bis = _time_str(blocks[i][1])
                cells.append(f'    <Cell><Data ss:Type="String">{von}</Data></Cell>')
                cells.append(f'    <Cell><Data ss:Type="String">{bis}</Data></Cell>')
                # Minuten berechnen
                start_dt = blocks[i][0] if isinstance(blocks[i][0], datetime) else datetime.combine(dt, blocks[i][0])
                end_dt = blocks[i][1] if isinstance(blocks[i][1], datetime) else datetime.combine(dt, blocks[i][1])
                diff = (end_dt - start_dt).total_seconds() / 60
                total_minutes += max(diff, 0)
            else:
                cells.append('    <Cell><Data ss:Type="String"></Data></Cell>')
                cells.append('    <Cell><Data ss:Type="String"></Data></Cell>')

        # Summe in Stunden
        total_hours = round(total_minutes / 60, 2)
        summe_str = f'{total_hours:.2f}'.replace('.', ',')
        cells.append(f'    <Cell><Data ss:Type="Number">{total_hours}</Data></Cell>')

        cells_str = "\n".join(cells)
        rows_xml += f'   <Row>\n{cells_str}\n   </Row>\n'

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles>
  <Style ss:ID="Default" ss:Name="Normal">
   <Font ss:FontName="Arial" ss:Size="10"/>
  </Style>
  <Style ss:ID="Header">
   <Font ss:FontName="Arial" ss:Size="10" ss:Bold="1"/>
   <Interior ss:Color="#D9E1F2" ss:Pattern="Solid"/>
  </Style>
 </Styles>
 <Worksheet ss:Name="{personal_nr}">
  <Table>
   <Column ss:Width="80"/>
   <Column ss:Width="50" ss:Span="8"/>
   <Column ss:Width="60"/>
   <Row ss:StyleID="Header">
    <Cell><Data ss:Type="String">Datum</Data></Cell>
    <Cell><Data ss:Type="String">Von1</Data></Cell>
    <Cell><Data ss:Type="String">Bis1</Data></Cell>
    <Cell><Data ss:Type="String">Von2</Data></Cell>
    <Cell><Data ss:Type="String">Bis2</Data></Cell>
    <Cell><Data ss:Type="String">Von3</Data></Cell>
    <Cell><Data ss:Type="String">Bis3</Data></Cell>
    <Cell><Data ss:Type="String">Von4</Data></Cell>
    <Cell><Data ss:Type="String">Bis4</Data></Cell>
    <Cell><Data ss:Type="String">Summe</Data></Cell>
   </Row>
{rows_xml}  </Table>
 </Worksheet>
</Workbook>'''
    return xml


def _generate_lexware_lohnarten_xml(personal_nr, year, month, lohnarten):
    """Generiert Lexware XML mit Lohnarten-Zeilen statt Tagesbloecken.
    lohnarten: Liste von dicts mit {lohnart, bezeichnung, stunden, betrag}
    """
    rows_xml = ""
    for la in lohnarten:
        stunden_cell = f'<Data ss:Type="Number">{la["stunden"]}</Data>' if la.get("stunden") is not None else '<Data ss:Type="String"></Data>'
        betrag_cell = f'<Data ss:Type="Number">{la["betrag"]}</Data>' if la.get("betrag") is not None else '<Data ss:Type="String"></Data>'
        rows_xml += f'''   <Row>
    <Cell><Data ss:Type="String">{personal_nr}</Data></Cell>
    <Cell><Data ss:Type="Number">{la["lohnart"]}</Data></Cell>
    <Cell><Data ss:Type="String">{la["bezeichnung"]}</Data></Cell>
    <Cell>{stunden_cell}</Cell>
    <Cell>{betrag_cell}</Cell>
   </Row>
'''

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles>
  <Style ss:ID="Default" ss:Name="Normal">
   <Font ss:FontName="Arial" ss:Size="10"/>
  </Style>
  <Style ss:ID="Header">
   <Font ss:FontName="Arial" ss:Size="10" ss:Bold="1"/>
   <Interior ss:Color="#D9E1F2" ss:Pattern="Solid"/>
  </Style>
 </Styles>
 <Worksheet ss:Name="{personal_nr}">
  <Table>
   <Column ss:Width="100"/>
   <Column ss:Width="60"/>
   <Column ss:Width="150"/>
   <Column ss:Width="80"/>
   <Column ss:Width="80"/>
   <Row ss:StyleID="Header">
    <Cell><Data ss:Type="String">Personalnummer</Data></Cell>
    <Cell><Data ss:Type="String">Lohnart</Data></Cell>
    <Cell><Data ss:Type="String">Bezeichnung</Data></Cell>
    <Cell><Data ss:Type="String">Stunden</Data></Cell>
    <Cell><Data ss:Type="String">Betrag</Data></Cell>
   </Row>
{rows_xml}  </Table>
 </Worksheet>
</Workbook>'''
    return xml


from fastapi.responses import StreamingResponse
import zipfile
import io

@router.get("/lexware-export")
def lexware_export(
    year: int = Query(...),
    month: int = Query(...),
    employee_ids: str = Query(None, description="Komma-separierte MA-IDs, leer = alle"),
    db: Session = Depends(get_db),
    admin=Depends(verify_admin)
):
    """Lexware XML Export: Pro MA eine XML-Datei, alle als ZIP."""
    from calendar import monthrange
    _, last_day_num = monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, last_day_num)

    # Basis-Filter
    q = db.query(TimeEntry).join(Employee).filter(
        TimeEntry.check_in >= datetime.combine(first_day, time(0, 0)),
        TimeEntry.check_in <= datetime.combine(last_day, time(23, 59, 59)),
        TimeEntry.check_out.isnot(None),
        TimeEntry.object_id != 999,  # Kein Urlaub
        Employee.is_active == True,
    )

    # Optional: nur bestimmte MAs
    if employee_ids:
        ids = [int(x) for x in employee_ids.split(",") if x.strip().isdigit()]
        if ids:
            q = q.filter(TimeEntry.employee_id.in_(ids))

    entries = q.all()

    # Gruppieren: employee_id -> day -> [(check_in, check_out)]
    emp_data = defaultdict(lambda: defaultdict(list))
    emp_info = {}
    for e in entries:
        emp_id = e.employee_id
        if emp_id not in emp_info:
            emp = e.employee
            emp_info[emp_id] = {
                "name": f"{emp.first_name}_{emp.last_name}",
                "personal_nr": emp.personal_nr,
            }
        day = e.check_in.day
        if e.check_out:
            emp_data[emp_id][day].append((e.check_in, e.check_out))

    # Zeitkonto-MAs identifizieren
    from app.models.models import Zeitkonto
    zeitkonto_emps = db.query(Employee).filter(
        Employee.zeitkonto_aktiv == True,
        Employee.is_active == True,
    ).all()
    zeitkonto_emp_ids = {e.id for e in zeitkonto_emps}

    # Filter: wenn employee_ids angegeben, nur diese Zeitkonto-MAs
    filtered_zk_emps = zeitkonto_emps
    if employee_ids:
        ids = [int(x) for x in employee_ids.split(",") if x.strip().isdigit()]
        filtered_zk_emps = [e for e in zeitkonto_emps if e.id in ids]

    if not emp_data and not filtered_zk_emps:
        raise HTTPException(status_code=404, detail="Keine Zeiteintraege fuer diesen Monat gefunden")

    # ZIP erstellen
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Normale MAs (Tagesbloecke) - OHNE Zeitkonto-MAs
        for emp_id in sorted(emp_data.keys(), key=lambda x: emp_info[x]['personal_nr']):
            if emp_id in zeitkonto_emp_ids:
                continue  # Zeitkonto-MAs separat
            info = emp_info[emp_id]
            day_blocks = {}
            for day, intervals in emp_data[emp_id].items():
                day_blocks[day] = _merge_intervals(intervals)

            xml_content = _generate_lexware_xml(
                info['name'], info['personal_nr'],
                year, month, day_blocks
            )
            filename = f"{info['personal_nr']}_{info['name']}_{month:02d}_{year}.xml"
            zf.writestr(filename, xml_content)

        # Zeitkonto-MAs (Lohnarten-Format)
        for zk_emp in filtered_zk_emps:
            zk = db.query(Zeitkonto).filter(
                Zeitkonto.employee_id == zk_emp.id,
                Zeitkonto.year == year,
                Zeitkonto.month == month,
            ).first()

            if zk:
                soll = zk.soll_stunden
                sonntag_h = zk.ist_stunden_sonntag
                nacht_h = zk.ist_stunden_nacht
            else:
                # Live berechnen
                split = _berechne_stunden_split(db, zk_emp.id, first_day, last_day)
                soll = 140.0
                sonntag_h = split["sonntag_hours"]
                nacht_h = split["nacht_hours"]

            lohnarten = [
                {"lohnart": 1, "bezeichnung": "Gehalt", "stunden": soll, "betrag": None},
            ]
            if sonntag_h > 0:
                lohnarten.append({"lohnart": 13, "bezeichnung": "Sonntagszuschlag", "stunden": round(sonntag_h, 2), "betrag": None})
            if nacht_h > 0:
                lohnarten.append({"lohnart": 11, "bezeichnung": "Nachtzuschlag", "stunden": round(nacht_h, 2), "betrag": None})

            # Vorschuss aus VORMONAT
            prev_m = month - 1
            prev_y = year
            if prev_m < 1:
                prev_m = 12
                prev_y = year - 1
            prev_zk = db.query(Zeitkonto).filter(
                Zeitkonto.employee_id == zk_emp.id,
                Zeitkonto.year == prev_y,
                Zeitkonto.month == prev_m,
            ).first()
            if prev_zk and prev_zk.vorschuss_betrag > 0:
                lohnarten.append({"lohnart": 6005, "bezeichnung": "Vorschuss-Abzug", "stunden": None, "betrag": -prev_zk.vorschuss_betrag})

            xml_content = _generate_lexware_lohnarten_xml(
                zk_emp.personal_nr, year, month, lohnarten
            )
            fname = f"{zk_emp.personal_nr}_{zk_emp.first_name}_{zk_emp.last_name}_{month:02d}_{year}.xml"
            zf.writestr(fname, xml_content)

    zip_buffer.seek(0)
    month_names = ['', 'Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
                   'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
    zip_filename = f"Lexware_Export_{month_names[month]}_{year}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


# ==================== PENDING BOOKINGS (Genehmigungen) ====================

@router.get("/pending-bookings")
def get_pending_bookings(
    status_filter: str = "offen",
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Alle ausstehenden Buchungen fuer Admin-Genehmigung."""
    query = """
        SELECT pb.id, pb.employee_id, pb.object_id, pb.date, pb.start_time, pb.end_time,
               pb.service_type, pb.is_driver, pb.requested_hours, pb.status,
               pb.notes, pb.admin_notes, pb.hourly_rate, pb.approved_hours,
               pb.created_at, pb.approved_at, pb.reason, pb.catch_up_type,
               pb.correction_field, pb.related_time_entry_id,
               e.first_name, e.last_name, e.personal_nr,
               e.hourly_rate as emp_hourly_rate,
               e.hourly_rate_standard, e.hourly_rate_window, e.hourly_rate_basic,
               o.name as object_name, o.address as object_address,
               kd.distance_km,
               eoa.custom_hourly_rate as obj_custom_rate
        FROM pending_bookings pb
        JOIN employees e ON e.id = pb.employee_id
        JOIN objects o ON o.id = pb.object_id
        LEFT JOIN employee_object_assignments eoa ON eoa.employee_id = pb.employee_id AND eoa.object_id = pb.object_id
        LEFT JOIN km_distances kd ON kd.employee_id = pb.employee_id AND kd.object_id = pb.object_id
    """
    params = {}
    if status_filter != "alle":
        query += " WHERE pb.status = :status"
        params["status"] = status_filter
    query += " ORDER BY pb.date DESC, pb.created_at DESC"

    result = db.execute(text(query), params)
    bookings = []
    for row in result:
        # Stundensatz vorschlagen: Objektzuweisung > MA-Satz > Standard > Fallback
        base_rate = float(row.obj_custom_rate or row.emp_hourly_rate or row.hourly_rate_standard or 15.0)
        if row.service_type in ('Fensterreinigung',):
            suggested_rate = float(row.hourly_rate_window or 20.0)
        elif row.service_type in ('Sonderreinigung', 'Grundreinigung'):
            suggested_rate = float(row.hourly_rate_basic or 20.0)
        else:
            suggested_rate = base_rate

        bookings.append({
            "id": row.id,
            "employee_id": row.employee_id,
            "object_id": row.object_id,
            "date": str(row.date),
            "start_time": str(row.start_time)[:5],
            "end_time": str(row.end_time)[:5],
            "service_type": row.service_type,
            "is_driver": row.is_driver,
            "requested_hours": float(row.requested_hours) if row.requested_hours else 0,
            "status": row.status,
            "notes": row.notes,
            "admin_notes": row.admin_notes,
            "hourly_rate": float(row.hourly_rate) if row.hourly_rate else None,
            "approved_hours": float(row.approved_hours) if row.approved_hours else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "employee_name": f"{row.first_name} {row.last_name}",
            "personal_nr": row.personal_nr,
            "object_name": row.object_name,
            "object_address": row.object_address or "",
            "km_distance": float(row.distance_km) if row.distance_km else None,
            "suggested_rate": suggested_rate,
            "reason": row.reason if hasattr(row, 'reason') else None,
            "catch_up_type": row.catch_up_type if hasattr(row, 'catch_up_type') else None,
            "correction_field": row.correction_field if hasattr(row, 'correction_field') else None,
            "related_time_entry_id": row.related_time_entry_id if hasattr(row, 'related_time_entry_id') else None,
            "original_start_time": None,
            "original_end_time": None,
        })

    # Für zeit_korrektur: Original-Zeiten aus time_entries nachladen
    for b in bookings:
        if b.get("catch_up_type") == "zeit_korrektur" and b.get("related_time_entry_id"):
            te_row = db.execute(text(
                "SELECT check_in, check_out FROM time_entries WHERE id = :id"
            ), {"id": b["related_time_entry_id"]}).fetchone()
            if te_row:
                b["original_start_time"] = te_row.check_in.strftime("%H:%M") if te_row.check_in else None
                b["original_end_time"] = te_row.check_out.strftime("%H:%M") if te_row.check_out else None

    return bookings


@router.get("/pending-bookings/count")
def get_pending_bookings_count(
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Anzahl offener Genehmigungen fuer Badge."""
    result = db.execute(text(
        "SELECT COUNT(*) FROM pending_bookings WHERE status = 'offen'"
    )).scalar()
    return {"count": result or 0}


@router.post("/pending-bookings/{booking_id}/approve")
def approve_pending_booking(
    booking_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Buchung genehmigen: Erstellt echten TimeEntry + optional KM."""
    import random

    pb = db.execute(text(
        "SELECT * FROM pending_bookings WHERE id = :id"
    ), {"id": booking_id}).fetchone()

    if not pb:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    if pb.status != 'offen':
        raise HTTPException(status_code=400, detail="Buchung ist nicht mehr offen")

    # Mitarbeiter-Satz ermitteln: Objektzuweisung > MA-Satz > Standard > Fallback
    emp_rate_row = db.execute(text("""
        SELECT COALESCE(eoa.custom_hourly_rate, e.hourly_rate, e.hourly_rate_standard, 15.0) as rate
        FROM employees e
        LEFT JOIN employee_object_assignments eoa ON eoa.employee_id = e.id AND eoa.object_id = :obj_id
        WHERE e.id = :emp_id
    """), {"emp_id": pb.employee_id, "obj_id": pb.object_id}).fetchone()
    default_rate = float(emp_rate_row.rate) if emp_rate_row else 15.0

    # Admin kann Werte anpassen
    approved_hours = float(data.get("approved_hours", pb.requested_hours))
    hourly_rate = float(data.get("hourly_rate", default_rate))
    start_time = data.get("start_time", str(pb.start_time)[:5])
    end_time = data.get("end_time", str(pb.end_time)[:5])
    admin_notes = data.get("admin_notes", "")
    service_type = data.get("service_type", pb.service_type)

    # Randomisierung +-2min
    start_var = random.randint(-2, 2)
    end_var = random.randint(-1, 2)

    check_in = datetime.combine(pb.date, datetime.strptime(start_time, "%H:%M").time()) + timedelta(minutes=start_var)
    check_out = datetime.combine(pb.date, datetime.strptime(end_time, "%H:%M").time()) + timedelta(minutes=end_var)

    # Prüfe ob gehen_vergessen oder zeit_korrektur (bestehende TimeEntry bearbeiten)
    related_id = pb.related_time_entry_id if hasattr(pb, 'related_time_entry_id') and pb.related_time_entry_id else None
    is_correction = (pb.catch_up_type == 'zeit_korrektur' if hasattr(pb, 'catch_up_type') else False) and related_id
    km_booked = None
    override_km = data.get("override_km")

    if is_correction:
        # ZEIT-KORREKTUR: bestehenden TimeEntry updaten
        correction_field = pb.correction_field if hasattr(pb, 'correction_field') else 'beides'

        # Keine Randomisierung bei Korrekturen
        corr_check_in = datetime.combine(pb.date, datetime.strptime(start_time, "%H:%M").time())
        corr_check_out = datetime.combine(pb.date, datetime.strptime(end_time, "%H:%M").time())

        update_parts = []
        update_params = {"te_id": related_id}

        if correction_field in ('kommen', 'beides'):
            update_parts.append("check_in = :ci")
            update_params["ci"] = corr_check_in
        if correction_field in ('gehen', 'beides'):
            update_parts.append("check_out = :co")
            update_params["co"] = corr_check_out

        update_parts.append("billed_hours = :hours")
        update_params["hours"] = approved_hours
        update_parts.append("is_manual_entry = true")
        update_parts.append("notes = COALESCE(notes, '') || :note_append")
        corr_label = {"kommen": "Kommen", "gehen": "Gehen", "beides": "Beides"}.get(correction_field, correction_field)
        update_params["note_append"] = f" [KORREKTUR GENEHMIGT] {corr_label} korrigiert. {admin_notes}".strip()

        db.execute(text(f"""
            UPDATE time_entries
            SET {', '.join(update_parts)}
            WHERE id = :te_id
        """), update_params)

        time_entry_id = related_id
        # KM NICHT verändern bei Korrekturen

    elif related_id:
        # gehen_vergessen: bestehende offene TimeEntry schließen
        db.execute(text("""
            UPDATE time_entries
            SET check_out = :co, billed_hours = :hours, hourly_rate = :rate,
                service_type = :stype, is_manual_entry = true,
                notes = COALESCE(notes, '') || :note_append
            WHERE id = :te_id
        """), {
            "co": check_out,
            "hours": approved_hours,
            "rate": hourly_rate,
            "stype": service_type,
            "note_append": f" [NACHTRAG GENEHMIGT] {admin_notes}".strip(),
            "te_id": related_id,
        })
        # Offene Pausen auf check_out schließen
        db.execute(text("""
            UPDATE break_entries SET end_time = :co
            WHERE time_entry_id = :te_id AND end_time IS NULL
        """), {"co": check_out, "te_id": related_id})
        time_entry_id = related_id

        # KM buchen für gehen_vergessen
        try:
            from app.api.v1.endpoints.time_entries import calculate_and_save_km
            te_row = db.execute(text("SELECT check_in FROM time_entries WHERE id = :id"), {"id": related_id}).fetchone()
            if te_row:
                calculate_and_save_km(pb.employee_id, pb.object_id, te_row.check_in.date() if hasattr(te_row.check_in, 'date') else pb.date, related_id, db)
        except Exception as e:
            print(f"KM-Berechnung fehlgeschlagen: {e}")
    else:
        # Bestehende Logik: neue TimeEntry erstellen
        te_result = db.execute(text("""
            INSERT INTO time_entries
            (employee_id, object_id, check_in, check_out, billed_hours, hourly_rate,
             is_manual_entry, service_type, notes)
            VALUES (:emp_id, :obj_id, :ci, :co, :hours, :rate, true, :stype, :notes)
            RETURNING id
        """), {
            "emp_id": pb.employee_id,
            "obj_id": pb.object_id,
            "ci": check_in,
            "co": check_out,
            "hours": approved_hours,
            "rate": hourly_rate,
            "stype": service_type,
            "notes": f"Selbstbuchung genehmigt. {admin_notes}".strip(),
        })
        time_entry_id = te_result.fetchone().id

        # KM buchen (nur bei neuen TimeEntries, nicht bei gehen_vergessen)
        if pb.is_driver:
            km_row = db.execute(text("""
                SELECT distance_km, rate_per_km FROM km_distances
                WHERE employee_id = :emp_id AND object_id = :obj_id
            """), {"emp_id": pb.employee_id, "obj_id": pb.object_id}).fetchone()

            auto_km = float(km_row.distance_km) if km_row and km_row.distance_km > 0 else 0
            km_rate = float(km_row.rate_per_km or 0.30) if km_row else 0.30

            if override_km is not None:
                final_km = float(override_km)
            else:
                final_km = auto_km

            if final_km > 0:
                km_amount = round(final_km * km_rate, 2)
                db.execute(text("""
                    INSERT INTO km_daily_entries
                    (employee_id, object_id, time_entry_id, date, distance_km, amount, is_billable, is_longest_trip)
                    VALUES (:emp_id, :obj_id, :te_id, :dt, :dist, :amount, TRUE, FALSE)
                    ON CONFLICT (employee_id, date, object_id)
                    DO UPDATE SET time_entry_id = :te_id, distance_km = :dist, amount = :amount
                """), {
                    "emp_id": pb.employee_id,
                    "obj_id": pb.object_id,
                    "te_id": time_entry_id,
                    "dt": pb.date,
                    "dist": final_km,
                    "amount": km_amount,
                })
                km_booked = final_km

    # Pending booking updaten
    db.execute(text("""
        UPDATE pending_bookings
        SET status = 'genehmigt', approved_hours = :hours, hourly_rate = :rate,
            admin_notes = :notes, approved_at = NOW(), approved_by = :admin_id
        WHERE id = :id
    """), {
        "id": booking_id,
        "hours": approved_hours,
        "rate": hourly_rate,
        "notes": admin_notes,
        "admin_id": admin.id,
    })

    db.commit()

    # Telegram-Benachrichtigung an MA
    try:
        from app.services.telegram_bot import send_message_sync
        emp = db.execute(text(
            "SELECT telegram_chat_id FROM employees WHERE id = :id"
        ), {"id": pb.employee_id}).fetchone()
        if emp and emp.telegram_chat_id:
            obj_name = db.execute(text(
                "SELECT name FROM objects WHERE id = :id"
            ), {"id": pb.object_id}).fetchone()
            obj_label = obj_name.name if obj_name else str(pb.object_id)
            if is_correction:
                send_message_sync(int(emp.telegram_chat_id),
                    f"Deine Zeitkorrektur vom {pb.date.strftime('%d.%m.%Y')} wurde übernommen:\n"
                    f"Objekt: {obj_label}\n"
                    f"{start_time}–{end_time}, {approved_hours} Std.")
            else:
                send_message_sync(int(emp.telegram_chat_id),
                    f"Deine nachgetragene Zeit vom {pb.date.strftime('%d.%m.%Y')} wurde eingetragen:\n"
                    f"Objekt: {obj_label}\n"
                    f"{start_time}–{end_time}, {approved_hours} Std.")
    except Exception as e:
        print(f"Telegram-Benachrichtigung (approve) fehlgeschlagen: {e}")

    brutto = round(approved_hours * hourly_rate, 2)
    return {
        "status": "ok",
        "message": "Buchung eingetragen",
        "time_entry_id": time_entry_id,
        "hours": approved_hours,
        "rate": hourly_rate,
        "brutto": brutto,
        "km_booked": km_booked,
    }


@router.post("/pending-bookings/{booking_id}/reject")
def reject_pending_booking(
    booking_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin = Depends(verify_admin)
):
    """Buchung ablehnen."""
    pb = db.execute(text(
        "SELECT * FROM pending_bookings WHERE id = :id"
    ), {"id": booking_id}).fetchone()

    if not pb:
        raise HTTPException(status_code=404, detail="Buchung nicht gefunden")
    if pb.status != 'offen':
        raise HTTPException(status_code=400, detail="Buchung ist nicht mehr offen")

    admin_notes = data.get("admin_notes", "")

    db.execute(text("""
        UPDATE pending_bookings
        SET status = 'abgelehnt', admin_notes = :notes, approved_at = NOW(), approved_by = :admin_id
        WHERE id = :id
    """), {
        "id": booking_id,
        "notes": admin_notes,
        "admin_id": admin.id,
    })
    db.commit()

    # Telegram-Benachrichtigung an MA
    try:
        from app.services.telegram_bot import send_message_sync
        emp = db.execute(text(
            "SELECT telegram_chat_id FROM employees WHERE id = :id"
        ), {"id": pb.employee_id}).fetchone()
        if emp and emp.telegram_chat_id:
            obj_name = db.execute(text(
                "SELECT name FROM objects WHERE id = :id"
            ), {"id": pb.object_id}).fetchone()
            obj_label = obj_name.name if obj_name else str(pb.object_id)
            grund_text = f"\n{admin_notes}" if admin_notes else ""
            is_reject_correction = (pb.catch_up_type == 'zeit_korrektur' if hasattr(pb, 'catch_up_type') else False)
            if is_reject_correction:
                send_message_sync(int(emp.telegram_chat_id),
                    f"Zu deiner Zeitkorrektur vom {pb.date.strftime('%d.%m.%Y')} "
                    f"({obj_label}) gibt es eine Rückfrage:{grund_text}")
            else:
                send_message_sync(int(emp.telegram_chat_id),
                    f"Zu deiner nachgetragenen Zeit vom {pb.date.strftime('%d.%m.%Y')} "
                    f"({obj_label}) gibt es eine Rückfrage:{grund_text}")
    except Exception as e:
        print(f"Telegram-Benachrichtigung (reject) fehlgeschlagen: {e}")

    return {"status": "ok", "message": "Rückfrage gestellt"}
