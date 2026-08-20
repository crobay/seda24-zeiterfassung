from fastapi import APIRouter, Depends, HTTPException, status, Body
from datetime import time
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timedelta, date
from typing import List
import math
import random

from app.db.database import get_db
from app.models.models import TimeEntry, Employee, Object, User, Schedule, ShiftChangeRequest, PushNotification, ServiceType, EmployeeObjectAssignment
from app.schemas.time_entry_schema import CheckIn, CheckOut, TimeEntryResponse
from app.core.validation_service import ValidationService
from app.api.v1.endpoints.auth import get_current_user
from app.services.bie2_logger import log_bie2

router = APIRouter()

# ========== Bie2 Hilfsfunktionen ==========

def is_c_assignment(employee_id: int, object_id: int, db) -> bool:
    """Prueft ob die Zuweisung tracking_category=C hat."""
    assignment = db.query(EmployeeObjectAssignment).filter(
        EmployeeObjectAssignment.employee_id == employee_id,
        EmployeeObjectAssignment.object_id == object_id,
        EmployeeObjectAssignment.is_active == True,
        EmployeeObjectAssignment.tracking_category == "C"
    ).first()
    return assignment is not None


def get_scheduled_end(employee_id: int, check_in: datetime, db) -> datetime:
    """Ermittelt das geplante Schichtende anhand des Dienstplans.
    Fallback: check_in + 8 Stunden wenn kein Dienstplan vorhanden."""
    schedule = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.date == check_in.date(),
        Schedule.end_time != None,
    ).first()
    if schedule:
        scheduled_end = datetime.combine(check_in.date(), schedule.end_time)
        # Nachtschicht: end_time < start_time → +1 Tag
        if schedule.start_time and schedule.end_time < schedule.start_time:
            scheduled_end += timedelta(days=1)
        return scheduled_end
    return check_in + timedelta(hours=8)


BIE2_OBJECT_ID = 20  # Lidl Neu Bie2

def check_min_duration_bie2(employee_id: int, object_id: int, check_in_time: datetime, now: datetime, db):
    """Prueft Mindest-Stempeldauer fuer Bie2 (object_id=20).
    Gibt None zurueck wenn OK, sonst HTTPException mit Restzeit.
    Nur wenn ein Dienstplan-Eintrag fuer diesen Tag + MA + Objekt existiert.
    """
    if object_id != BIE2_OBJECT_ID:
        return None

    today = check_in_time.date()
    schedule = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.object_id == object_id,
        Schedule.date == today,
        Schedule.start_time != None,
        Schedule.end_time != None
    ).first()

    if not schedule:
        return None  # Kein Dienstplan → keine Einschraenkung

    # Geplante Dauer berechnen (end_time - start_time)
    from datetime import datetime as dt
    start_dt = dt.combine(today, schedule.start_time)
    end_dt = dt.combine(today, schedule.end_time)
    planned_seconds = (end_dt - start_dt).total_seconds()
    if planned_seconds <= 0:
        return None  # Ungueltig → keine Einschraenkung

    # Tatsaechliche Dauer seit Kommen
    actual_seconds = (now - check_in_time).total_seconds()

    if actual_seconds < planned_seconds:
        remaining_seconds = planned_seconds - actual_seconds
        remaining_min = math.ceil(remaining_seconds / 60)
        planned_hours = planned_seconds / 3600
        planned_str = f"{planned_hours:.1f}".replace('.', ',')
        raise HTTPException(
            status_code=422,
            detail=f"Noch nicht möglich zu gehen – noch {remaining_min} Min bis zur Mindestarbeitszeit ({planned_str} Std)."
        )

    return None


def calculate_billed_hours_bie2(check_in_time, check_out_time, breaks_list):
    """
    Bie2-Berechnung:
    1. Brutto = check_out - check_in
    2. Pausen summieren
    3. Netto = Brutto - Pausen
    4. Pflichtpause: >6h Netto UND Pausen < 30min -> (30 - Pausen) abziehen
    5. Auf 5 Minuten AUFRUNDEN (ceil)
    """
    brutto_seconds = (check_out_time - check_in_time).total_seconds()
    
    # Pausen summieren
    total_break_seconds = 0
    for b in breaks_list:
        if b.end_time:
            total_break_seconds += (b.end_time - b.start_time).total_seconds()
    
    netto_seconds = brutto_seconds - total_break_seconds
    netto_minutes = netto_seconds / 60
    total_break_minutes = total_break_seconds / 60
    
    # Pflichtpause: >6h Netto UND Pausen < 30min
    pflichtpause_abzug = 0
    if netto_minutes > 360 and total_break_minutes < 30:
        pflichtpause_abzug = 30 - total_break_minutes
        netto_minutes -= pflichtpause_abzug
    
    # Auf 5 Minuten aufrunden
    netto_minutes = max(0, netto_minutes)
    rounded_minutes = math.ceil(netto_minutes / 5) * 5
    billed_hours = round(rounded_minutes / 60, 4)
    
    return {
        "billed_hours": billed_hours,
        "brutto_minutes": round(brutto_seconds / 60, 1),
        "break_minutes": round(total_break_minutes, 1),
        "netto_minutes": round(netto_seconds / 60, 1),
        "pflichtpause_abzug": round(pflichtpause_abzug, 1),
        "rounded_minutes": rounded_minutes,
    }

# KM-Berechnung für time_entries.py
# DIESE FUNKTION NACH DEN IMPORTS EINFÜGEN

def calculate_and_save_km(employee_id: int, object_id: int, date: date, time_entry_id: int, db: Session):
    """
    Berechnet KM für eine Fahrt und speichert in km_daily_entries.
    Nur die weiteste Fahrt des Tages wird abgerechnet.
    Spezialregel: Matej (6) und Ljubica (5) am selben Tag/Objekt -> nur Matej bekommt KM.
    """
    print(f"DEBUG KM: employee_id={employee_id}, object_id={object_id}, date={date}")
    from sqlalchemy import text
    
    # SPEZIALREGEL: Matej (6) & Ljubica (5) zusammen
    if employee_id == 5:  # Ljubica
        # Prüfe ob Matej (6) heute am selben Objekt war
        matej_check = db.execute(
            text("SELECT id FROM km_daily_entries WHERE employee_id = 6 AND date = :dt AND object_id = :obj"),
            {"dt": date, "obj": object_id}
        ).fetchone()
        
        if matej_check:
            # Matej war auch da -> Ljubica bekommt 0 km
            distance_km = 0.0
            rate = 0.30
            amount = 0.0
            print(f"DEBUG KM: Ljubica + Matej zusammen -> Ljubica = 0 km")
        else:
            # Matej war nicht da -> normale KM für Ljubica
            result = db.execute(
                text("SELECT distance_km, rate_per_km FROM km_distances WHERE employee_id = :emp AND object_id = :obj"),
                {"emp": employee_id, "obj": object_id}
            ).fetchone()
            
            if not result:
                distance_km = 0.0
                rate = 0.30
            else:
                distance_km = float(result[0])
                rate = float(result[1] or 0.30)
            amount = distance_km * rate
    else:
        # Normale KM-Berechnung für alle anderen
        result = db.execute(
            text("SELECT distance_km, rate_per_km FROM km_distances WHERE employee_id = :emp AND object_id = :obj"),
            {"emp": employee_id, "obj": object_id}
        ).fetchone()
        
        if not result:
            distance_km = 0.0
            rate = 0.30
        else:
            distance_km = float(result[0])
            rate = float(result[1] or 0.30)
        amount = distance_km * rate
    
    # Prüfe ob Eintrag schon existiert
    existing = db.execute(
        text("SELECT id FROM km_daily_entries WHERE employee_id = :emp AND date = :dt AND object_id = :obj"),
        {"emp": employee_id, "dt": date, "obj": object_id}
    ).fetchone()
    
    if existing:
        # Update (is_billable wird später gesetzt)
        db.execute(
            text("""UPDATE km_daily_entries 
                   SET distance_km = :dist, amount = :amt, time_entry_id = :te_id
                   WHERE id = :id"""),
            {"dist": distance_km, "amt": amount, "te_id": time_entry_id, "id": existing[0]}
        )
    else:
        # Insert (is_billable = false erstmal)
        db.execute(
            text("""INSERT INTO km_daily_entries 
                   (employee_id, date, object_id, distance_km, amount, is_billable, is_longest_trip, time_entry_id)
                   VALUES (:emp, :dt, :obj, :dist, :amt, false, false, :te_id)"""),
            {"emp": employee_id, "dt": date, "obj": object_id, "dist": distance_km, "amt": amount, "te_id": time_entry_id}
        )
    
    # WICHTIG: Erst alle auf FALSE setzen
    db.execute(
        text("UPDATE km_daily_entries SET is_longest_trip = false, is_billable = false WHERE employee_id = :emp AND date = :dt"),
        {"emp": employee_id, "dt": date}
    )
    
    # Dann NUR die weiteste Fahrt auf TRUE setzen
    db.execute(
        text("""UPDATE km_daily_entries 
               SET is_longest_trip = true, is_billable = true
               WHERE id = (
                   SELECT id FROM km_daily_entries 
                   WHERE employee_id = :emp AND date = :dt 
                   ORDER BY distance_km DESC LIMIT 1
               )"""),
        {"emp": employee_id, "dt": date}
    )
    
    db.commit()




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

def get_service_type_for_object(object_name):
    """Ermittelt Leistungsart basierend auf Objektname"""
    if not object_name:
        return 'Unterhaltsreinigung'
    object_upper = object_name.upper()
    if "FENSTER" in object_upper or "WINDOW" in object_upper:
        return 'Fensterreinigung'
    elif "GRUND" in object_upper or "BASIC" in object_upper:
        return 'Grundreinigung'
    return 'Unterhaltsreinigung'


def get_hourly_rate_for_object(employee, object_name):
    """Ermittelt Stundensatz basierend auf Objektname"""
    service_type = get_service_type_for_object(object_name)
    if service_type == 'Fensterreinigung':
        return employee.hourly_rate_window if hasattr(employee, 'hourly_rate_window') else 20.00
    elif service_type == 'Grundreinigung':
        return employee.hourly_rate_basic if hasattr(employee, 'hourly_rate_basic') else 20.00
    # Buero/Zentrale -> Fensterreinigung-Rate
    if object_name:
        upper = object_name.upper()
        if "BÜRO" in upper or "ZENTRALE" in upper:
            return employee.hourly_rate_window if hasattr(employee, 'hourly_rate_window') else 20.00
    return employee.hourly_rate or employee.hourly_rate_standard or 15.00


def get_assignment_rate_and_service(employee_id, object_id, db):
    """Prüft ob für die MA-Objekt-Zuweisung custom_hourly_rate/custom_service_type gesetzt ist.
    Gibt (rate_or_None, service_or_None) zurück."""
    assignment = db.query(EmployeeObjectAssignment).filter(
        EmployeeObjectAssignment.employee_id == employee_id,
        EmployeeObjectAssignment.object_id == object_id,
        EmployeeObjectAssignment.is_active == True
    ).first()
    if assignment:
        return (
            float(assignment.custom_hourly_rate) if assignment.custom_hourly_rate else None,
            assignment.custom_service_type if assignment.custom_service_type else None
        )
    return (None, None)


def resolve_rate_and_service(employee, object_id, object_name, db):
    """Zentrale Funktion: Zuweisung hat Vorrang, sonst Standard-Logik."""
    custom_rate, custom_service = get_assignment_rate_and_service(employee.id, object_id, db)
    rate = custom_rate if custom_rate is not None else get_hourly_rate_for_object(employee, object_name)
    service = custom_service if custom_service is not None else get_service_type_for_object(object_name)
    return rate, service

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
    
    # Offline-Sync: client_timestamp und client_id
    client_id = data.get("client_id")
    client_ts_str = data.get("client_timestamp")
    stamp_time = datetime.now()
    if client_ts_str:
        try:
            # "Z" → "+00:00" für fromisoformat, NICHT danach nochmal strippen!
            ts = client_ts_str.replace("Z", "+00:00")
            stamp_time = datetime.fromisoformat(ts)
            # UTC → Lokalzeit (CEST) konvertieren, dann naive machen
            if stamp_time.tzinfo:
                import pytz
                stamp_time = stamp_time.astimezone(pytz.timezone('Europe/Berlin')).replace(tzinfo=None)
        except:
            stamp_time = datetime.now()

    # Dedup: Wenn client_id schon existiert, bestehenden Eintrag zurückgeben
    if client_id:
        existing = db.query(TimeEntry).filter(TimeEntry.client_id == client_id).first()
        if existing:
            return existing

    # Prüfe offene Einträge
    old_entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee.id,
        TimeEntry.check_out == None
    ).all()

    # Bei C-Zuweisungen: Doppel-Stempelung verhindern
    target_object_id = data.get("object_id", 1)
    if old_entries and is_c_assignment(employee.id, target_object_id, db):
        raise HTTPException(
            status_code=400,
            detail="Du bist bereits eingestempelt. Bitte zuerst GEHEN drücken."
        )

    # Alte offene Einträge schließen (nur bei Nicht-C-Zuweisungen)
    for entry in old_entries:
        entry.check_out = stamp_time

    if old_entries:
        db.commit()

    # Neuer Eintrag
    try:
        object_id = data.get("object_id", 1)
        time_entry = TimeEntry(
            employee_id=employee.id,
            object_id=object_id,
            check_in=stamp_time,
            client_id=client_id,
            server_received_at=datetime.now()
        )
        db.add(time_entry)
        db.commit()
        db.refresh(time_entry)

        # Bie2-Log bei KOMMEN
        if is_c_assignment(employee.id, object_id, db):
            obj = db.query(Object).filter(Object.id == object_id).first()
            # Nur [OFFLINE] taggen wenn Handy-Zeit > 2 Min vor Server-Zeit
            offline_tag = ""
            if client_ts_str and stamp_time:
                delay = (datetime.now() - stamp_time).total_seconds()
                offline_tag = " [OFFLINE]" if delay > 120 else ""
            log_bie2("KOMMEN", f"{employee.first_name} {employee.last_name}",
                     obj.name if obj else str(object_id),
                     f"Zeit={stamp_time.strftime('%H:%M:%S')}{offline_tag}")

            # Entwarnung: Wurde fuer diese Schicht bereits "fehlend" gemeldet? (nur Bie2)
            notified_sched = None
            if object_id == 20:
                notified_sched = db.query(Schedule).filter(
                    Schedule.employee_id == employee.id,
                    Schedule.object_id == 20,
                    Schedule.date == stamp_time.date(),
                    Schedule.no_stamp_notified == True
                ).first()
            if notified_sched:
                delay_text = ""
                if notified_sched.start_time:
                    planned_start = datetime.combine(stamp_time.date(), notified_sched.start_time)
                    delay_min = round((stamp_time - planned_start).total_seconds() / 60)
                    if delay_min >= 60:
                        hours, mins = divmod(delay_min, 60)
                        delay_text = f", verzoegert um {hours}h {mins}min"
                    elif delay_min > 0:
                        delay_text = f", verzoegert um {delay_min}min"
                from app.services.telegram_bot import notify_admin
                notify_admin(
                    f"Stempelung ist eingegangen fuer {employee.first_name} {employee.last_name} "
                    f"({stamp_time.strftime('%H:%M')}{delay_text})."
                )

        return time_entry
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-out")
def check_out(
    data: dict = Body(default={}),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Offline-Sync: client_timestamp und client_id
    client_id = data.get("client_id") if data else None
    client_ts_str = data.get("client_timestamp") if data else None
    stamp_time = datetime.now()
    if client_ts_str:
        try:
            # "Z" → "+00:00" für fromisoformat, NICHT danach nochmal strippen!
            ts = client_ts_str.replace("Z", "+00:00")
            stamp_time = datetime.fromisoformat(ts)
            # UTC → Lokalzeit (CEST) konvertieren, dann naive machen
            if stamp_time.tzinfo:
                import pytz
                stamp_time = stamp_time.astimezone(pytz.timezone('Europe/Berlin')).replace(tzinfo=None)
        except:
            stamp_time = datetime.now()

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
        # Idempotent: Wenn client_id, letzten Eintrag des MA zurückgeben
        if client_id:
            last = db.query(TimeEntry).filter(
                TimeEntry.employee_id == employee.id,
                TimeEntry.check_out != None
            ).order_by(TimeEntry.id.desc()).first()
            if last:
                return last
        raise HTTPException(status_code=400, detail="Kein aktiver Check-in gefunden!")

    # Mindestdauer-Pruefung fuer Bie2 (object_id=20)
    check_min_duration_bie2(employee.id, active_entry.object_id, active_entry.check_in, stamp_time, db)

    # Setze check_out Zeit
    active_entry.check_out = stamp_time
    active_entry.server_received_at = datetime.now()

    # hourly_rate + service_type aus Zuweisung (Vorrang) oder Stammblatt setzen
    obj = db.query(Object).filter(Object.id == active_entry.object_id).first()
    obj_name = obj.name if obj else ""
    co_rate, co_service = resolve_rate_and_service(employee, active_entry.object_id, obj_name, db)
    active_entry.hourly_rate = co_rate
    active_entry.service_type = co_service

    # Prüfe ob zu zweit gearbeitet wurde (aus notes)
    colleague_id = None
    if active_entry.notes and "colleague_id:" in active_entry.notes:
        try:
            colleague_id = int(active_entry.notes.split("colleague_id:")[1].split(")")[0])
        except:
            pass

    # Wenn zu zweit, halbiere die Zeit und erstelle Kollegen-Eintrag
    if colleague_id:
        from app.models.models import Schedule
        schedule = db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.object_id == active_entry.object_id,
            Schedule.date == stamp_time.date()
        ).first()

        if schedule:
            work_duration = (active_entry.check_out - active_entry.check_in).total_seconds() / 3600
            half_duration = timedelta(hours=work_duration / 2)
            new_checkout = active_entry.check_in + half_duration
            active_entry.check_out = new_checkout

            colleague_entry = TimeEntry(
                employee_id=colleague_id,
                object_id=active_entry.object_id,
                check_in=active_entry.check_in,
                check_out=new_checkout,
                is_manual_entry=True,
                notes=f"Zu zweit mit {employee.first_name} {employee.last_name}"
            )
            db.add(colleague_entry)
            update_total_hours(colleague_id, db)

    # KM berechnen und speichern
    calculate_and_save_km(
        employee_id=employee.id,
        object_id=active_entry.object_id,
        date=active_entry.check_in.date(),
        time_entry_id=active_entry.id,
        db=db
    )

    # ========== Bie2-Berechnung bei C-Zuweisung ==========
    from app.models.models import BreakEntry
    if is_c_assignment(employee.id, active_entry.object_id, db):
        breaks_list = db.query(BreakEntry).filter(
            BreakEntry.time_entry_id == active_entry.id
        ).all()
        # Offene Pausen schliessen
        for b in breaks_list:
            if not b.end_time:
                b.end_time = stamp_time
        calc = calculate_billed_hours_bie2(active_entry.check_in, active_entry.check_out, breaks_list)
        active_entry.billed_hours = calc["billed_hours"]
        # Objekt-Name fuer Log
        obj = db.query(Object).filter(Object.id == active_entry.object_id).first()
        obj_name = obj.name if obj else str(active_entry.object_id)
        emp_name = f"{employee.first_name} {employee.last_name}"
        # Nur [OFFLINE] taggen wenn Handy-Zeit > 2 Min vor Server-Zeit
        offline_tag = ""
        if client_ts_str and stamp_time:
            delay = (datetime.now() - stamp_time).total_seconds()
            offline_tag = " [OFFLINE]" if delay > 120 else ""
        log_bie2("GEHEN", emp_name, obj_name,
            f"Brutto={calc['brutto_minutes']}min Pausen={calc['break_minutes']}min "
            f"Netto={calc['netto_minutes']}min Pflichtpause={calc['pflichtpause_abzug']}min "
            f"Gerundet={calc['rounded_minutes']}min Abrechnung={calc['billed_hours']}h{offline_tag}")

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
    active_entry.check_out = datetime.now()
    active_entry.server_received_at = datetime.now()

    # Prüfe ob zu zweit gearbeitet wurde (aus notes)
    colleague_id = None
    if active_entry.notes and "colleague_id:" in active_entry.notes:
        try:
            colleague_id = int(active_entry.notes.split("colleague_id:")[1].split(")")[0])
        except:
            pass
    
    # Wenn zu zweit, halbiere die Zeit und erstelle Kollegen-Eintrag
    if colleague_id:
        from app.models.models import Schedule
        schedule = db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.object_id == active_entry.object_id,
            Schedule.date == datetime.now().date()
        ).first()
        
        if schedule:
            work_duration = (active_entry.check_out - active_entry.check_in).total_seconds() / 3600
            half_duration = timedelta(hours=work_duration / 2)
            new_checkout = active_entry.check_in + half_duration
            active_entry.check_out = new_checkout
            
            colleague_entry = TimeEntry(
                employee_id=colleague_id,
                object_id=active_entry.object_id,
                check_in=active_entry.check_in,
                check_out=new_checkout,
                is_manual_entry=True,
                notes=f"Zu zweit mit {employee.first_name} {employee.last_name}"
            )
            db.add(colleague_entry)
            update_total_hours(colleague_id, db)
    active_entry.check_out_lat = data.gps_lat
    active_entry.check_out_lng = data.gps_lng
    active_entry.notes = (active_entry.notes or "") + f" | Wechsel zu Objekt {data.object_id}"
    
    # Erstelle neuen Eintrag am neuen Objekt
    new_entry = TimeEntry(
        employee_id=employee.id,
        object_id=data.object_id,
        check_in=datetime.now(),
        gps_lat=data.gps_lat,
        gps_lng=data.gps_lng,
        notes=f"Wechsel von Objekt {active_entry.object_id}",
        server_received_at=datetime.now()
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
        from app.models.models import BreakEntry
        # Zombie-Check: Wenn älter als 14 Stunden
        is_zombie = datetime.now() - current_entry.check_in > timedelta(hours=14)

        if is_zombie:
            # C-Zuweisungen: NICHT auto-closen, stattdessen Nachtrag-Hinweis
            if is_c_assignment(employee.id, current_entry.object_id, db):
                # Pause-Status ermitteln
                active_break = db.query(BreakEntry).filter(
                    BreakEntry.time_entry_id == current_entry.id,
                    BreakEntry.end_time == None
                ).first()
                completed_breaks = db.query(BreakEntry).filter(
                    BreakEntry.time_entry_id == current_entry.id,
                    BreakEntry.end_time != None
                ).all()
                total_pause = sum((b.end_time - b.start_time).total_seconds() for b in completed_breaks)
                return {
                    "is_working": True,
                    "is_open_catchup": True,
                    "check_in": current_entry.check_in.isoformat(),
                    "object_id": current_entry.object_id,
                    "entry_id": current_entry.id,
                    "is_paused": active_break is not None,
                    "pause_start_time": active_break.start_time.isoformat() if active_break else None,
                    "total_pause_duration": total_pause,
                }
            else:
                # B-Zuweisungen: Auto-close wie bisher
                current_entry.check_out = datetime.now()
                db.commit()
                return {"is_working": False}

        # Pause-Status ermitteln
        active_break = db.query(BreakEntry).filter(
            BreakEntry.time_entry_id == current_entry.id,
            BreakEntry.end_time == None
        ).first()
        completed_breaks = db.query(BreakEntry).filter(
            BreakEntry.time_entry_id == current_entry.id,
            BreakEntry.end_time != None
        ).all()
        total_pause = sum((b.end_time - b.start_time).total_seconds() for b in completed_breaks)

        # Overdue-Prüfung: Schichtende überschritten?
        scheduled_end = get_scheduled_end(employee.id, current_entry.check_in, db)
        now = datetime.now()
        overdue_seconds = max(0, (now - scheduled_end).total_seconds())
        overdue_minutes = int(overdue_seconds / 60)

        return {
            "is_working": True,
            "check_in": current_entry.check_in.isoformat(),
            "object_id": current_entry.object_id,
            "entry_id": current_entry.id,
            "is_paused": active_break is not None,
            "pause_start_time": active_break.start_time.isoformat() if active_break else None,
            "total_pause_duration": total_pause,
            "overdue_warning": overdue_minutes >= 30,
            "scheduled_end_time": scheduled_end.strftime("%H:%M"),
            "overdue_minutes": overdue_minutes,
        }

    # Heutige abgeschlossene Einträge mitliefern (für Checkout-Feedback)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee.id,
        TimeEntry.check_in >= today_start,
        TimeEntry.check_out != None,
        TimeEntry.object_id != 999,  # Kein Urlaub
    ).order_by(TimeEntry.check_in).all()

    today_list = []
    for te in today_entries:
        dur = (te.check_out - te.check_in).total_seconds() / 60
        obj = db.query(Object).filter(Object.id == te.object_id).first()
        today_list.append({
            "check_in": te.check_in.strftime("%H:%M"),
            "check_out": te.check_out.strftime("%H:%M"),
            "duration_minutes": round(dur),
            "object_name": obj.name if obj else "Unbekannt",
        })

    return {"is_working": False, "today_entries": today_list}

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
        schedule = db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.date == datetime.now().date(),
            Schedule.object_id == object_id
        ).first()

    # planned_hours berechnen: aus DB oder aus start/end_time
    if schedule and schedule.planned_hours:
        scheduled_hours = schedule.planned_hours
    elif schedule and schedule.start_time and schedule.end_time:
        from datetime import datetime as dt
        start_dt = dt.combine(today, schedule.start_time)
        end_dt = dt.combine(today, schedule.end_time)
        diff = (end_dt - start_dt).total_seconds() / 3600
        scheduled_hours = round(diff, 2) if diff > 0 else 4.0
    else:
        scheduled_hours = 4.0
    
    # Prüfe ob zu zweit gearbeitet wurde
    colleague_id = data.get("colleague_id")
    if colleague_id:
        scheduled_hours = scheduled_hours / 2
    
    # Erstelle Zeiteintrag mit Zufallszeiten ±2 Min (Pruefungssicherheit)
    start_var = random.randint(-2, 2)
    end_var = random.randint(-2, 2)

    base_start = datetime.combine(datetime.today(), schedule.start_time if schedule else time(6, 0))
    check_in = base_start + timedelta(minutes=start_var)
    # check_out aus planned_hours berechnen (nicht aus end_time!)
    check_out = check_in + timedelta(hours=scheduled_hours) + timedelta(minutes=end_var)

    # Leistungsart + Stundensatz: Zuweisung hat Vorrang, sonst Standard
    obj = db.query(Object).filter(Object.id == object_id).first()
    obj_name = obj.name if obj else ""
    hourly_rate, service_type = resolve_rate_and_service(employee, object_id, obj_name, db)

    time_entry = TimeEntry(
        employee_id=employee.id,
        object_id=object_id,
        check_in=check_in,
        check_out=check_out,
        billed_hours=scheduled_hours,
        service_type=service_type,
        hourly_rate=hourly_rate,
        is_manual_entry=True,
        notes=f"War anwesend (Kategorie B) - {service_type}"
    )

    db.add(time_entry)

    # Wenn zu zweit, erstelle Eintrag fuer Kollegen
    if colleague_id:
        colleague = db.query(Employee).filter(Employee.id == colleague_id).first()
        colleague_rate, colleague_service = resolve_rate_and_service(colleague, object_id, obj_name, db) if colleague else (hourly_rate, service_type)
        colleague_entry = TimeEntry(
            employee_id=colleague_id,
            object_id=object_id,
            check_in=check_in,
            check_out=check_out,
            billed_hours=scheduled_hours,
            service_type=colleague_service,
            hourly_rate=colleague_rate,
            is_manual_entry=True,
            notes=f"Zu zweit mit {employee.first_name} {employee.last_name} - {colleague_service}"
        )
        db.add(colleague_entry)
        update_total_hours(colleague_id, db)
    # KM berechnen und speichern (war-anwesend)
    db.flush()  # Damit time_entry.id verfuegbar ist
    calculate_and_save_km(
        employee_id=employee.id,
        object_id=object_id,
        date=check_in.date(),
        time_entry_id=time_entry.id,
        db=db
    )
    if colleague_id:
        calculate_and_save_km(
            employee_id=colleague_id,
            object_id=object_id,
            date=check_in.date(),
            time_entry_id=colleague_entry.id,
            db=db
        )

    db.commit()

    print(f"WAR-ANWESEND: Employee {employee.id}, Object {object_id}, "
          f"{scheduled_hours}h, {check_in.strftime('%H:%M')}-{check_out.strftime('%H:%M')}")

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

@router.get("/colleagues-at-object")
def get_colleagues_at_object(
    object_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from datetime import date
    today = date.today()
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []
    schedules = db.query(Schedule).filter(
        Schedule.object_id == object_id,
        Schedule.date == today
    ).all()
    colleagues = []
    for schedule in schedules:
        if schedule.employee_id != employee.id:
            emp = db.query(Employee).filter(Employee.id == schedule.employee_id).first()
            if emp:
                colleagues.append({
                    "employee_id": emp.id,
                    "name": f"{emp.first_name} {emp.last_name}",
                    "personal_nr": emp.personal_nr,
                    "start_time": schedule.start_time.strftime("%H:%M") if schedule.start_time else None,
                    "end_time": schedule.end_time.strftime("%H:%M") if schedule.end_time else None
                })
    return colleagues


# ==================== SCHICHTAENDERUNGSANFRAGEN (MA-Seite) ====================

@router.post("/shift-requests")
def create_shift_request(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mitarbeiter stellt Schichtaenderungsantrag."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    request_type = data.get("request_type")
    if request_type not in ("swap", "cancel", "change"):
        raise HTTPException(status_code=400, detail="Typ muss 'swap', 'cancel' oder 'change' sein")

    from datetime import date as date_type, time as time_type

    req = ShiftChangeRequest(
        employee_id=employee.id,
        schedule_id=data.get("schedule_id"),
        request_type=request_type,
        reason=data.get("reason", ""),
        status="pending",
    )

    if data.get("requested_date"):
        req.requested_date = date_type.fromisoformat(data["requested_date"])
    if data.get("requested_start"):
        parts = data["requested_start"].split(":")
        req.requested_start = time_type(int(parts[0]), int(parts[1]))
    if data.get("requested_end"):
        parts = data["requested_end"].split(":")
        req.requested_end = time_type(int(parts[0]), int(parts[1]))
    if data.get("swap_employee_id"):
        req.swap_employee_id = int(data["swap_employee_id"])

    db.add(req)
    db.commit()
    return {"id": req.id, "status": "pending"}


@router.get("/shift-requests/my")
def get_my_shift_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eigene Schichtaenderungsanfragen."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []

    requests = db.query(ShiftChangeRequest).filter(
        ShiftChangeRequest.employee_id == employee.id
    ).order_by(ShiftChangeRequest.created_at.desc()).limit(20).all()

    result = []
    for sr in requests:
        swap_emp = None
        if sr.swap_employee_id:
            swap_emp = db.query(Employee).filter(Employee.id == sr.swap_employee_id).first()
        result.append({
            "id": sr.id,
            "request_type": sr.request_type,
            "requested_date": str(sr.requested_date) if sr.requested_date else None,
            "requested_start": str(sr.requested_start) if sr.requested_start else None,
            "requested_end": str(sr.requested_end) if sr.requested_end else None,
            "swap_employee_name": f"{swap_emp.first_name} {swap_emp.last_name}" if swap_emp else None,
            "reason": sr.reason,
            "status": sr.status,
            "admin_response": sr.admin_response,
            "created_at": sr.created_at.isoformat() if sr.created_at else None,
        })
    return result


# ============================================================
# Kat-B V3.0: Leistungsarten + Heutige Schichten mit Status
# ============================================================

@router.get("/service-types")
def get_service_types(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Leistungsarten mit MA-spezifischen Stundenraten"""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()

    # MA-spezifische Raten (Fallback auf Defaults)
    rate_standard = employee.hourly_rate_standard if employee else 15.00
    rate_window = employee.hourly_rate_window if employee else 20.00
    rate_basic = employee.hourly_rate_basic if employee else 20.00

    return [
        {"id": 1, "name": "Unterhaltsreinigung", "hourly_rate": rate_standard},
        {"id": 2, "name": "Fensterreinigung", "hourly_rate": rate_window},
        {"id": 3, "name": "Grundreinigung", "hourly_rate": rate_basic},
    ]


@router.get("/my-shifts-today")
def get_my_shifts_today(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Heutige Schichten mit Status (open/confirmed/push_sent) fuer Kat-B Dashboard"""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []

    today = date.today()

    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.date == today
    ).order_by(Schedule.start_time).all()

    result = []
    for s in schedules:
        # Pruefe ob TimeEntry existiert (= bestaetigt) - NUR exakt per schedule_id
        # Kein Fallback! Alle V3.0-Buchungen setzen schedule_id.
        # Alte Orphan-Entries ohne schedule_id duerfen keine neuen Schichten als "gebucht" markieren.
        time_entry = db.query(TimeEntry).filter(
            TimeEntry.schedule_id == s.id
        ).first()

        # Pruefe ob Push gesendet (offen ODER beantwortet)
        push_open = db.query(PushNotification).filter(
            PushNotification.employee_id == employee.id,
            PushNotification.schedule_id == s.id,
            PushNotification.status.in_(['pending', 'sent', 'failed']),
            PushNotification.response_status.is_(None)
        ).first()

        # Pruefe ob Push beantwortet mit "nicht da" (not_present)
        push_declined = db.query(PushNotification).filter(
            PushNotification.employee_id == employee.id,
            PushNotification.schedule_id == s.id,
            PushNotification.response_status == 'not_present',
        ).first()

        if time_entry:
            shift_status = 'confirmed'
        elif push_declined:
            shift_status = 'declined'
        elif push_open and push_open.status == 'failed':
            shift_status = 'push_failed'
        elif push_open:
            shift_status = 'push_sent'
        else:
            shift_status = 'open'

        obj = db.query(Object).filter(Object.id == s.object_id).first()

        now = datetime.now().time()
        shift_ended = bool(s.end_time and now >= s.end_time)

        result.append({
            "schedule_id": s.id,
            "object_id": s.object_id,
            "object_name": obj.name if obj else f"Objekt {s.object_id}",
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else "06:00",
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else "14:00",
            "planned_hours": s.planned_hours,
            "status": shift_status,
            "schedule_status": s.status or 'normal',
            "shift_ended": shift_ended,
            "time_entry_id": time_entry.id if time_entry else None,
            "push_id": (push_open.id if push_open else None) or (push_declined.id if push_declined else None),
            "service_type": time_entry.service_type if time_entry and hasattr(time_entry, 'service_type') else None,
        })

    return result


@router.get("/shift-colleagues")
def get_shift_colleagues(
    object_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kollegen die offiziell dem gleichen Objekt zugeordnet sind (employee_object_assignments)."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []

    assignments = db.query(EmployeeObjectAssignment).filter(
        EmployeeObjectAssignment.object_id == object_id,
        EmployeeObjectAssignment.employee_id != employee.id,
        EmployeeObjectAssignment.is_active == True,
    ).all()

    colleagues = []
    for assignment in assignments:
        emp = db.query(Employee).filter(Employee.id == assignment.employee_id, Employee.is_active == True).first()
        if emp:
            colleagues.append({
                "id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "personal_nr": emp.personal_nr,
            })
    return colleagues


@router.post("/shift-request")
def create_shift_request(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Schicht tauschen oder absagen - speichert in DB und benachrichtigt Admin per Telegram."""
    from app.services.telegram_bot import notify_admin
    import logging
    logger = logging.getLogger(__name__)

    schedule_id = data.get("schedule_id")
    request_type = data.get("request_type")  # "swap" oder "cancel"
    reason = data.get("reason", "")
    swap_with_employee_id = data.get("swap_with_employee_id")
    sick_from = data.get("sick_from")
    sick_until = data.get("sick_until")
    custom_reason = data.get("custom_reason", "")

    if not schedule_id or request_type not in ("swap", "cancel"):
        raise HTTPException(status_code=400, detail="schedule_id und request_type (swap/cancel) erforderlich")

    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    schedule = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.employee_id == employee.id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schicht nicht gefunden")

    obj = db.query(Object).filter(Object.id == schedule.object_id).first()
    obj_name = obj.name if obj else f"Objekt {schedule.object_id}"
    date_str = schedule.date.strftime("%d.%m.%Y") if schedule.date else "?"
    start_str = schedule.start_time.strftime("%H:%M") if schedule.start_time else "?"
    end_str = schedule.end_time.strftime("%H:%M") if schedule.end_time else "?"
    ma_name = f"{employee.first_name} {employee.last_name}"

    # In DB speichern
    scr_reason = reason
    if reason == 'Krank' and (sick_from or sick_until):
        scr_reason = f"Krank: {sick_from or date_str} bis {sick_until or 'unbekannt'}"
    elif reason == 'Sonstiges':
        scr_reason = custom_reason or 'Sonstiges'

    scr = ShiftChangeRequest(
        employee_id=employee.id,
        schedule_id=schedule_id,
        request_type=request_type,
        swap_employee_id=swap_with_employee_id,
        reason=scr_reason,
        status='pending',
    )
    db.add(scr)
    db.flush()

    # Schedule-Status aktualisieren
    if request_type == "swap":
        schedule.status = 'swapped'
        schedule.notes = f"Tausch beantragt (Request #{scr.id})"
    elif reason == 'Krank':
        schedule.status = 'sick'
        schedule.notes = f"Krank gemeldet"
    else:
        schedule.status = 'cancelled'
        schedule.notes = f"Abgesagt: {scr_reason}"

    # Telegram-Nachrichten
    try:
        if request_type == "swap":
            swap_emp_name = None
            if swap_with_employee_id:
                swap_emp = db.query(Employee).filter(Employee.id == swap_with_employee_id).first()
                swap_emp_name = f"{swap_emp.first_name} {swap_emp.last_name}" if swap_emp else None

            msg = (
                f"\U0001f504 TAUSCHANFRAGE\n\n"
                f"\U0001f464 {ma_name} ({employee.personal_nr})\n"
                f"\U0001f3e2 {obj_name}\n"
                f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n\n"
            )
            if swap_emp_name:
                msg += f"Tauschen mit: {swap_emp_name}"
            else:
                msg += "Admin soll Vertretung organisieren"

            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("\u2705 Genehmigen", callback_data=f"swa:{scr.id}"),
                        InlineKeyboardButton("\u274c Ablehnen", callback_data=f"swr:{scr.id}"),
                    ]
                ])
                notify_admin(msg, reply_markup=keyboard)
            except ImportError:
                notify_admin(msg)

        else:  # cancel
            if reason == 'Krank':
                sick_from_str = sick_from or date_str
                sick_until_str = sick_until or "unbekannt"
                msg = (
                    f"\u26a0\ufe0f <b>KRANKMELDUNG</b>\n\n"
                    f"\U0001f464 {ma_name} ({employee.personal_nr})\n"
                    f"\U0001f3e2 {obj_name}\n"
                    f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n"
                    f"\U0001f912 Krank: {sick_from_str} bis {sick_until_str}\n\n"
                    f"\u2757 Vertretung noetig!"
                )
            elif reason == 'Privat':
                msg = (
                    f"\u26a0\ufe0f <b>AUSFALL</b>\n\n"
                    f"\U0001f464 {ma_name} ({employee.personal_nr})\n"
                    f"\U0001f3e2 {obj_name}\n"
                    f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n\n"
                    f"Grund: Privat"
                )
            else:
                msg = (
                    f"\u26a0\ufe0f <b>AUSFALL</b>\n\n"
                    f"\U0001f464 {ma_name} ({employee.personal_nr})\n"
                    f"\U0001f3e2 {obj_name}\n"
                    f"\U0001f4c5 {date_str} | {start_str}-{end_str}\n\n"
                    f"Grund: {custom_reason or reason}"
                )
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("\u2705 Vertretung eingetragen", callback_data=f"scr_done:{scr.id}"),
                        InlineKeyboardButton("\U0001f4cb Notiert", callback_data=f"scr_note:{scr.id}"),
                    ]
                ])
                notify_admin(msg, reply_markup=keyboard)
            except ImportError:
                notify_admin(msg)

    except Exception as e:
        logger.error(f"Telegram notify_admin fehlgeschlagen: {e}")

    db.commit()

    # Kontextbezogene Bestaetigungsnachricht
    if request_type == "swap":
        confirmation = "Tauschanfrage gesendet!"
    elif reason == 'Krank':
        sick_display = f"Ab {sick_from or date_str}"
        if sick_until:
            sick_display += f" bis {sick_until}"
        confirmation = f"Krankmeldung eingetragen. {sick_display}. Gute Besserung! Bitte reiche deine AU bei der Verwaltung ein."
    elif reason == 'Privat':
        confirmation = f"Abwesenheit eingetragen fuer {date_str}. Die Verwaltung wurde informiert."
    else:
        confirmation = "Deine Nachricht wurde an die Verwaltung weitergeleitet."

    return {"status": "ok", "message": confirmation, "request_id": scr.id}


@router.get("/my-upcoming-shifts")
def get_my_upcoming_shifts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Zukuenftige Schichten aus dem Dienstplan (naechste 14 Tage)"""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []

    today = date.today()
    end_date = today + timedelta(days=14)

    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.date > today,
        Schedule.date <= end_date,
        Schedule.status.in_(['normal', 'vertretung', 'swapped', 'sick', 'cancelled']),
    ).order_by(Schedule.date, Schedule.start_time).all()

    result = []
    for s in schedules:
        obj = db.query(Object).filter(Object.id == s.object_id).first()
        entry = {
            "schedule_id": s.id,
            "date": s.date.isoformat(),
            "weekday": s.date.strftime("%A"),
            "object_id": s.object_id,
            "object_name": obj.name if obj else f"Objekt {s.object_id}",
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else "06:00",
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else "14:00",
            "planned_hours": s.planned_hours,
            "schedule_status": s.status,
        }

        # Bei Tausch: Swap-Partner-Name ermitteln
        if s.status == 'swapped':
            scr = db.query(ShiftChangeRequest).filter(
                ShiftChangeRequest.schedule_id == s.id,
                ShiftChangeRequest.request_type == 'swap',
            ).order_by(ShiftChangeRequest.created_at.desc()).first()
            if scr and scr.swap_employee_id:
                swap_emp = db.query(Employee).filter(Employee.id == scr.swap_employee_id).first()
                entry["swap_with"] = f"{swap_emp.first_name} {swap_emp.last_name}" if swap_emp else None

        result.append(entry)

    return result


# ========== Bie2 Stempeluhr Endpoints ==========

@router.get("/my-c-objects")
def get_my_c_objects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Gibt Objekte zurueck wo MA tracking_category='C' hat."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []

    assignments = db.query(EmployeeObjectAssignment).filter(
        EmployeeObjectAssignment.employee_id == employee.id,
        EmployeeObjectAssignment.tracking_category == "C",
        EmployeeObjectAssignment.is_active == True
    ).all()

    result = []
    for a in assignments:
        obj = db.query(Object).filter(Object.id == a.object_id).first()
        if obj:
            result.append({
                "id": obj.id,
                "name": obj.name,
                "address": obj.address,
            })

    return result


@router.get("/my-entries-for-correction")
def get_my_entries_for_correction(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eigene abgeschlossene TimeEntries für Korrektur-Anfragen."""
    from sqlalchemy import text
    from app.models.models import Zeitkonto

    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    cutoff = date.today() - timedelta(days=90)

    # Abgerechnete Monate ermitteln
    closed_months = db.query(Zeitkonto.year, Zeitkonto.month).filter(
        Zeitkonto.employee_id == employee.id,
        Zeitkonto.status == 'abgeschlossen'
    ).all()
    closed_set = {(z.year, z.month) for z in closed_months}

    rows = db.execute(text("""
        SELECT te.id, te.check_in, te.check_out, te.billed_hours, te.object_id,
               o.name as object_name
        FROM time_entries te
        JOIN objects o ON o.id = te.object_id
        WHERE te.employee_id = :emp_id
          AND te.check_out IS NOT NULL
          AND te.check_in >= :cutoff
        ORDER BY te.check_in DESC
        LIMIT 50
    """), {"emp_id": employee.id, "cutoff": cutoff}).fetchall()

    # Offene Korrekturen prüfen
    pending_corrections = db.execute(text("""
        SELECT related_time_entry_id FROM pending_bookings
        WHERE employee_id = :emp_id
          AND catch_up_type = 'zeit_korrektur'
          AND status = 'offen'
          AND related_time_entry_id IS NOT NULL
    """), {"emp_id": employee.id}).fetchall()
    pending_te_ids = {r.related_time_entry_id for r in pending_corrections}

    result = []
    for r in rows:
        entry_date = r.check_in.date() if hasattr(r.check_in, 'date') else r.check_in
        if (entry_date.year, entry_date.month) in closed_set:
            continue
        result.append({
            "id": r.id,
            "object_name": r.object_name,
            "date": str(entry_date),
            "start_time": r.check_in.strftime("%H:%M") if hasattr(r.check_in, 'strftime') else str(r.check_in)[:5],
            "end_time": r.check_out.strftime("%H:%M") if hasattr(r.check_out, 'strftime') else str(r.check_out)[:5],
            "billed_hours": float(r.billed_hours) if r.billed_hours else None,
            "has_pending_correction": r.id in pending_te_ids,
        })
    return result


@router.get("/my-catchups")
def get_my_catchups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eigene Nachträge (pending_bookings) des aktuellen MA abrufen."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT pb.id, pb.date, pb.start_time, pb.end_time, pb.catch_up_type,
               pb.reason, pb.status, pb.notes, pb.admin_notes, pb.created_at,
               pb.requested_hours, pb.correction_field, pb.approved_at, o.name as object_name
        FROM pending_bookings pb
        LEFT JOIN objects o ON o.id = pb.object_id
        WHERE pb.employee_id = :emp_id
          AND (
            pb.status = 'offen'
            OR (pb.approved_at IS NOT NULL AND pb.approved_at >= NOW() - INTERVAL '7 days')
          )
        ORDER BY pb.created_at DESC
    """), {"emp_id": employee.id}).fetchall()

    result = []
    for r in rows:
        result.append({
            "id": r.id,
            "date": str(r.date) if r.date else None,
            "start_time": str(r.start_time)[:5] if r.start_time else None,
            "end_time": str(r.end_time)[:5] if r.end_time else None,
            "catch_up_type": r.catch_up_type,
            "reason": r.reason,
            "status": r.status,
            "notes": r.notes,
            "admin_notes": r.admin_notes,
            "created_at": str(r.created_at) if r.created_at else None,
            "requested_hours": float(r.requested_hours) if r.requested_hours else None,
            "correction_field": r.correction_field if hasattr(r, 'correction_field') else None,
            "object_name": r.object_name,
        })
    return result


@router.post("/catch-up")
def catch_up_booking(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Nachtrag fuer vergessenes Kommen/Gehen/Beides (nur C-Zuweisungen).
    Typen:
      kommen_vergessen  - Kommen nachtr. + Gehen-Zeit angeben -> kompletter Eintrag
      gehen_vergessen   - offene Schicht schliessen
      beides_vergessen  - komplett nachtr., Kommen+Gehen
    Felder: object_id, catch_up_type, date,
            time (Kommen-Zeit bei kommen/beides, Gehen-Zeit bei gehen),
            time_end (Gehen-Zeit bei kommen/beides),
            notes
    Alle Nachtraege: exakt auf die Minute, KEIN Aufrunden.
    """
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    object_id = data.get("object_id")
    catch_up_type = data.get("catch_up_type")
    date_str = data.get("date")
    time_str = data.get("time")        # Kommen-Zeit (kommen/beides) oder Gehen-Zeit (gehen)
    time_end_str = data.get("time_end") # Gehen-Zeit (kommen/beides)
    notes = data.get("notes", "")
    reason = data.get("reason", "")

    from sqlalchemy import text
    from app.models.models import Zeitkonto

    # Bei zeit_korrektur: object_id und date kommen aus dem TimeEntry
    if catch_up_type == "zeit_korrektur":
        if not catch_up_type:
            raise HTTPException(status_code=400, detail="catch_up_type fehlt")
    else:
        if not object_id or not catch_up_type or not date_str:
            raise HTTPException(status_code=400, detail="Pflichtfelder fehlen")

        if not is_c_assignment(employee.id, object_id, db):
            raise HTTPException(status_code=403, detail="Nachtrag nur fuer C-Zuweisungen erlaubt")

        try:
            parsed_date = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungueltiges Datumsformat")

        today = date.today()
        if parsed_date > today:
            raise HTTPException(status_code=400, detail="Nachträge für zukünftige Tage sind nicht erlaubt.")

        zk = db.query(Zeitkonto).filter(
            Zeitkonto.employee_id == employee.id,
            Zeitkonto.year == parsed_date.year,
            Zeitkonto.month == parsed_date.month,
            Zeitkonto.status == 'abgeschlossen'
        ).first()
        if zk:
            raise HTTPException(status_code=400, detail="Dieser Monat ist bereits abgerechnet. Bitte melde dich bei der Verwaltung.")

    obj = db.query(Object).filter(Object.id == (object_id or 0)).first()
    obj_name = obj.name if obj else str(object_id)
    emp_name = f"{employee.first_name} {employee.last_name}"

    from app.models.models import BreakEntry

    # ===== ZEIT-KORREKTUR =====
    if catch_up_type == "zeit_korrektur":
        time_entry_id = data.get("time_entry_id")
        correction_field = data.get("correction_field", "beides")
        if not time_entry_id:
            raise HTTPException(status_code=400, detail="time_entry_id fehlt")
        if correction_field not in ("kommen", "gehen", "beides"):
            raise HTTPException(status_code=400, detail="correction_field muss 'kommen', 'gehen' oder 'beides' sein")

        # TimeEntry laden und validieren
        te = db.query(TimeEntry).filter(TimeEntry.id == time_entry_id, TimeEntry.employee_id == employee.id).first()
        if not te:
            raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden oder gehört nicht zu dir")
        if not te.check_out:
            raise HTTPException(status_code=400, detail="Nur abgeschlossene Einträge können korrigiert werden")

        te_date = te.check_in.date()
        # Monat nicht abgerechnet
        zk_check = db.query(Zeitkonto).filter(
            Zeitkonto.employee_id == employee.id,
            Zeitkonto.year == te_date.year,
            Zeitkonto.month == te_date.month,
            Zeitkonto.status == 'abgeschlossen'
        ).first()
        if zk_check:
            raise HTTPException(status_code=400, detail="Dieser Monat ist bereits abgerechnet.")

        # Object-Name aus dem TimeEntry laden
        te_obj = db.query(Object).filter(Object.id == te.object_id).first()
        obj_name = te_obj.name if te_obj else str(te.object_id)

        # Keine doppelte offene Korrektur
        existing_correction = db.execute(text("""
            SELECT id FROM pending_bookings
            WHERE employee_id = :emp_id AND related_time_entry_id = :te_id
              AND catch_up_type = 'zeit_korrektur' AND status = 'offen'
        """), {"emp_id": employee.id, "te_id": time_entry_id}).fetchone()
        if existing_correction:
            raise HTTPException(status_code=400, detail="Es gibt bereits eine offene Korrektur für diesen Eintrag")

        # Neue Zeiten bestimmen
        if correction_field == "kommen":
            if not time_str:
                raise HTTPException(status_code=400, detail="Neue Kommen-Zeit fehlt")
            new_start = time_str
            new_end = te.check_out.strftime("%H:%M")
        elif correction_field == "gehen":
            if not time_end_str:
                raise HTTPException(status_code=400, detail="Neue Gehen-Zeit fehlt")
            new_start = te.check_in.strftime("%H:%M")
            new_end = time_end_str
        else:  # beides
            if not time_str or not time_end_str:
                raise HTTPException(status_code=400, detail="Kommen- und Gehen-Zeit fehlen")
            new_start = time_str
            new_end = time_end_str

        # Gehen nach Kommen validieren
        try:
            dt_new_start = datetime.strptime(f"{te_date} {new_start}", "%Y-%m-%d %H:%M")
            dt_new_end = datetime.strptime(f"{te_date} {new_end}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungültiges Zeitformat")
        if dt_new_end <= dt_new_start:
            raise HTTPException(status_code=400, detail="Gehen-Zeit muss nach Kommen-Zeit liegen")

        netto_sec = (dt_new_end - dt_new_start).total_seconds()
        requested_hours = round(max(0, netto_sec) / 3600, 4)

        p_rate, p_service = resolve_rate_and_service(employee, te.object_id, obj_name, db)
        db.execute(text("""
            INSERT INTO pending_bookings
            (employee_id, object_id, date, start_time, end_time, service_type,
             is_driver, requested_hours, status, notes, created_at,
             catch_up_type, related_time_entry_id, correction_field, reason)
            VALUES (:emp_id, :obj_id, :dt, :st, :et, :svc,
                    false, :hours, 'offen', :notes, NOW(),
                    'zeit_korrektur', :related_id, :corr_field, :reason)
        """), {
            "svc": p_service,
            "emp_id": employee.id,
            "obj_id": te.object_id,
            "dt": te_date,
            "st": new_start,
            "et": new_end,
            "hours": requested_hours,
            "notes": f"[KORREKTUR] {notes}".strip(),
            "related_id": time_entry_id,
            "corr_field": correction_field,
            "reason": reason,
        })
        db.commit()

        corr_labels = {"kommen": "Kommen", "gehen": "Gehen", "beides": "Beides"}
        log_bie2("KORREKTUR", emp_name, obj_name,
            f"Feld={corr_labels.get(correction_field)} Neu: {new_start}-{new_end} | {requested_hours}h -> Admin-Genehmigung")

        # Telegram
        try:
            from app.services.telegram_bot import notify_admin
            notify_admin(
                f"[KORREKTUR] {emp_name}\n"
                f"Objekt: {obj_name}\n"
                f"Datum: {te_date.strftime('%d.%m.%Y')}\n"
                f"Korrektur: {corr_labels.get(correction_field, correction_field)}\n"
                f"Alt: {te.check_in.strftime('%H:%M')}-{te.check_out.strftime('%H:%M')}\n"
                f"Neu: {new_start}-{new_end}\n"
                f"Grund: {reason or '-'}\n"
                f"Hinweis: {notes or '-'}"
            )
        except Exception as e:
            print(f"Telegram-Benachrichtigung fehlgeschlagen: {e}")

        return {"status": "ok", "type": "zeit_korrektur"}

    if catch_up_type == "gehen_vergessen":
        if not time_str:
            raise HTTPException(status_code=400, detail="Gehen-Uhrzeit fehlt")
        try:
            dt_out = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungueltiges Datum/Uhrzeit Format")

        open_entry = db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee.id,
            TimeEntry.object_id == object_id,
            TimeEntry.check_out == None
        ).order_by(TimeEntry.id.desc()).first()

        if not open_entry:
            raise HTTPException(status_code=400, detail="Kein offener Eintrag fuer dieses Objekt gefunden")

        # Netto-Stunden berechnen (für pending_booking)
        breaks_list = db.query(BreakEntry).filter(BreakEntry.time_entry_id == open_entry.id).all()
        netto_sec = (dt_out - open_entry.check_in).total_seconds()
        for b in breaks_list:
            if b.end_time:
                netto_sec -= (b.end_time - b.start_time).total_seconds()
            elif b.start_time:
                netto_sec -= (dt_out - b.start_time).total_seconds()
        requested_hours = round(max(0, netto_sec) / 3600, 4)

        p_rate, p_service = resolve_rate_and_service(employee, object_id, obj_name, db)
        db.execute(text("""
            INSERT INTO pending_bookings
            (employee_id, object_id, date, start_time, end_time, service_type,
             is_driver, requested_hours, status, notes, created_at,
             catch_up_type, related_time_entry_id, reason)
            VALUES (:emp_id, :obj_id, :dt, :st, :et, :svc,
                    false, :hours, 'offen', :notes, NOW(),
                    'gehen_vergessen', :related_id, :reason)
        """), {
            "svc": p_service,
            "emp_id": employee.id,
            "obj_id": object_id,
            "dt": open_entry.check_in.date(),
            "st": open_entry.check_in.strftime("%H:%M"),
            "et": dt_out.strftime("%H:%M"),
            "hours": requested_hours,
            "notes": f"[NACHTRAG] Gehen vergessen. {notes}".strip(),
            "related_id": open_entry.id,
            "reason": reason,
        })
        db.commit()

        log_bie2("NACHTRAG GEHEN", emp_name, obj_name,
            f"Kommen={open_entry.check_in.strftime('%H:%M')} Gehen={dt_out.strftime('%H:%M')} | Angefragt={requested_hours}h -> Admin-Genehmigung")
        telegram_dt = f"{open_entry.check_in.strftime('%d.%m.%Y %H:%M')} - {dt_out.strftime('%H:%M')}"

    elif catch_up_type == "kommen_vergessen" and not time_end_str:
        # Nur Kommen vergessen (ohne Gehen) -> direkter Check-In, MA stempelt Gehen spaeter
        if not time_str:
            raise HTTPException(status_code=400, detail="Kommen-Uhrzeit fehlt")
        try:
            dt_in = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungueltiges Datum/Uhrzeit Format")

        # Pruefen ob schon eine offene Schicht existiert
        existing = db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee.id,
            TimeEntry.check_out == None
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Du hast bereits eine offene Schicht")

        n_rate, n_service = resolve_rate_and_service(employee, object_id, obj_name, db)
        reason_label = f" Grund: {reason}." if reason else ""
        time_entry = TimeEntry(
            employee_id=employee.id,
            object_id=object_id,
            check_in=dt_in,
            check_out=None,
            hourly_rate=n_rate,
            service_type=n_service,
            notes=f"[NACHTRAG] Kommen nachgetragen.{reason_label} {notes}".strip(),
            is_manual_entry=True,
        )
        db.add(time_entry)
        db.commit()

        log_bie2("NACHTRAG KOMMEN", emp_name, obj_name,
            f"Kommen={dt_in.strftime('%H:%M')} (Gehen offen) Grund={reason or '-'}")
        telegram_dt = dt_in.strftime('%d.%m.%Y %H:%M')

    elif catch_up_type in ("kommen_vergessen", "beides_vergessen"):
        # kommen_vergessen MIT Gehen-Zeit (Quick-Gehen) oder beides_vergessen -> pending_booking
        if not time_str:
            raise HTTPException(status_code=400, detail="Kommen-Uhrzeit fehlt")
        if not time_end_str:
            raise HTTPException(status_code=400, detail="Gehen-Uhrzeit fehlt")
        try:
            dt_in = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            dt_out = datetime.strptime(f"{date_str} {time_end_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Ungueltiges Datum/Uhrzeit Format")

        # Gleiche Zeiten abweisen
        if dt_in == dt_out:
            raise HTTPException(status_code=400, detail="Kommen- und Gehen-Zeit duerfen nicht identisch sein")

        # Nachtschicht: Wenn Gehen vor Kommen liegt, war Kommen am Vortag
        if dt_out < dt_in:
            from datetime import timedelta
            dt_in = dt_in - timedelta(days=1)
        if dt_out <= dt_in:
            raise HTTPException(status_code=400, detail="Gehen-Zeit muss nach Kommen-Zeit liegen")

        netto_sec = (dt_out - dt_in).total_seconds()
        requested_hours = round(max(0, netto_sec) / 3600, 4)

        # Obergrenze: Max 12 Stunden
        if requested_hours > 12:
            raise HTTPException(status_code=400, detail=f"Maximale Dauer ist 12 Stunden. Dein Nachtrag ergibt {requested_hours:.1f}h — bitte Zeiten pruefen.")

        label = "Kommen vergessen" if catch_up_type == "kommen_vergessen" else "Beides vergessen"

        # In pending_bookings eintragen -> Admin muss genehmigen
        p_rate, p_service = resolve_rate_and_service(employee, object_id, obj_name, db)
        db.execute(text("""
            INSERT INTO pending_bookings
            (employee_id, object_id, date, start_time, end_time, service_type,
             is_driver, requested_hours, status, notes, created_at,
             catch_up_type, reason)
            VALUES (:emp_id, :obj_id, :dt, :st, :et, :svc,
                    false, :hours, 'offen', :notes, NOW(),
                    :catch_up_type, :reason)
        """), {
            "svc": p_service,
            "emp_id": employee.id,
            "obj_id": object_id,
            "dt": dt_in.date(),
            "st": dt_in.strftime("%H:%M"),
            "et": dt_out.strftime("%H:%M"),
            "hours": requested_hours,
            "notes": f"[NACHTRAG] {label}. {notes}".strip(),
            "catch_up_type": catch_up_type,
            "reason": reason,
        })
        db.commit()

        log_bie2(f"NACHTRAG {label.upper()}", emp_name, obj_name,
            f"Kommen={dt_in.strftime('%H:%M')} Gehen={dt_out.strftime('%H:%M')} | Angefragt={requested_hours}h -> Admin-Genehmigung")
        telegram_dt = f"{dt_in.strftime('%d.%m.%Y %H:%M')} - {dt_out.strftime('%H:%M')}"

    else:
        raise HTTPException(status_code=400, detail="Ungueltiger catch_up_type")

    # Telegram an Admin (D0001)
    try:
        from app.services.telegram_bot import notify_admin
        type_labels = {
            "kommen_vergessen": "Kommen nachgetragen",
            "gehen_vergessen": "Gehen nachgetragen",
            "beides_vergessen": "Komplett nachgetragen",
        }
        reason_labels = {"technisch": "Technisch", "vergessen": "Vergessen", "sonstiges": "Sonstiges"}
        notify_admin(
            f"[NACHTRAG] {emp_name}\n"
            f"Objekt: {obj_name}\n"
            f"Typ: {type_labels.get(catch_up_type, catch_up_type)}\n"
            f"Datum/Zeit: {telegram_dt}\n"
            f"Grund: {reason_labels.get(reason, reason or '-')}\n"
            f"Hinweis: {notes or '-'}"
        )
    except Exception as e:
        print(f"Telegram-Benachrichtigung fehlgeschlagen: {e}")

    return {"status": "ok", "type": catch_up_type}
