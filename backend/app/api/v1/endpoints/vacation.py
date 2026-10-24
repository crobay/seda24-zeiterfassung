"""
Urlaubsanträge-Endpoints fuer SEDA24 V3.0
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, date, timedelta
from app.db.database import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.models import (
    User, Employee, VacationRequest, VacationEntitlement,
    Schedule, Object, EmployeeObjectAssignment, TimeEntry
)
from sqlalchemy import func, extract

router = APIRouter()


def _get_employee(db: Session, user: User) -> Employee:
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    return emp


def _verify_admin(current_user: User = Depends(get_current_user)):
    if current_user.role.value != 'admin':
        raise HTTPException(status_code=403, detail="Nur Admin")
    return current_user


def _verify_admin_or_objektleiter(current_user: User = Depends(get_current_user)):
    if current_user.role.value not in ('admin', 'objektleiter'):
        raise HTTPException(status_code=403, detail="Kein Zugriff")
    return current_user


def _count_working_days(db: Session, employee_id: int, start_date: date, end_date: date) -> float:
    """
    Zählt nur die Tage im Zeitraum, an denen der MA laut Dienstplan normalerweise arbeitet.

    Reihenfolge:
    0. Wenn avg_work_days_per_week gesetzt (Abrufkraefte): Kalenderwochen × Durchschnitt
    1. Existierende Schedules mit status 'normal'/'vertretung' im Zeitraum
    2. Wochentage aus vergangenen Schedules
    3. Fallback Mo-Fr
    """
    # Methode 0: Durchschnittliche Arbeitstage pro Woche (fuer Abrufkraefte)
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if emp and emp.avg_work_days_per_week is not None:
        total_days = (end_date - start_date).days + 1
        weeks = total_days / 7.0
        return round(weeks * emp.avg_work_days_per_week)

    # Methode 1: Zähle existierende normale Schedules im Zeitraum
    existing = db.query(Schedule).filter(
        Schedule.employee_id == employee_id,
        Schedule.date >= start_date,
        Schedule.date <= end_date,
        Schedule.status.in_(['normal', 'vertretung']),
    ).count()

    if existing > 0:
        return float(existing)

    # Methode 2: Schau in vergangene Schedules welche Wochentage der MA arbeitet
    past_schedules = db.query(Schedule.weekday).filter(
        Schedule.employee_id == employee_id,
        Schedule.status.in_(['normal', 'vertretung']),
    ).distinct().all()

    if past_schedules:
        working_weekdays = set(wd[0] for wd in past_schedules)
    else:
        # Fallback: Mo-Fr (0-4 in Python)
        working_weekdays = {0, 1, 2, 3, 4}

    count = 0
    current = start_date
    while current <= end_date:
        if current.weekday() in working_weekdays:
            count += 1
        current += timedelta(days=1)

    return float(count)


@router.get("/my-vacation")
async def get_my_vacation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Urlaubsdaten des aktuellen Jahres."""
    current_year = date.today().year
    result = db.execute(text("""
        SELECT
            v.days_entitled,
            v.days_taken,
            v.days_remaining,
            v.vacation_rate,
            e.first_name,
            e.last_name
        FROM vacation_entitlements v
        JOIN employees e ON v.employee_id = e.id
        WHERE e.user_id = :user_id AND v.year = :year
    """), {"user_id": current_user.id, "year": current_year})

    vacation = result.fetchone()
    if not vacation:
        return {
            "days_entitled": 0,
            "days_taken": 0,
            "days_remaining": 0,
            "vacation_rate": 0
        }

    return {
        "days_entitled": vacation[0],
        "days_taken": vacation[1],
        "days_remaining": vacation[2],
        "vacation_rate": vacation[3],
        "name": f"{vacation[4]} {vacation[5]}"
    }


@router.post("/request")
def create_vacation_request(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """MA stellt Urlaubsantrag."""
    emp = _get_employee(db, current_user)
    start_str = data.get("start_date")
    end_str = data.get("end_date")

    if not start_str or not end_str:
        raise HTTPException(status_code=400, detail="start_date und end_date erforderlich")

    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)

    if end < start:
        raise HTTPException(status_code=400, detail="Enddatum muss nach Startdatum liegen")

    if start < date.today():
        raise HTTPException(status_code=400, detail="Urlaub kann nicht in der Vergangenheit beantragt werden")

    # Prüfe ob schon ein offener Antrag für den Zeitraum existiert
    overlap = db.query(VacationRequest).filter(
        VacationRequest.employee_id == emp.id,
        VacationRequest.status.in_(['pending', 'approved']),
        VacationRequest.start_date <= end,
        VacationRequest.end_date >= start,
    ).first()
    if overlap:
        raise HTTPException(status_code=400, detail="Es gibt bereits einen Antrag für diesen Zeitraum")

    working_days = _count_working_days(db, emp.id, start, end)

    # Resturlaub prüfen
    current_year = start.year
    entitlement = db.query(VacationEntitlement).filter(
        VacationEntitlement.employee_id == emp.id,
        VacationEntitlement.year == current_year,
    ).first()
    remaining = entitlement.days_remaining if entitlement else 30

    exceeds = working_days > remaining

    req = VacationRequest(
        employee_id=emp.id,
        start_date=start,
        end_date=end,
        working_days=working_days,
        status='pending',
    )
    db.add(req)
    db.flush()

    # Admin per Telegram benachrichtigen
    try:
        from app.services.telegram_bot import notify_admin
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        emp_name = f"{emp.first_name} {emp.last_name}"
        start_str_de = start.strftime("%d.%m.%Y")
        end_str_de = end.strftime("%d.%m.%Y")
        remaining_after = remaining - working_days

        warn_line = f"\n\u26a0\ufe0f <b>Uebersteigt Restanspruch: beantragt {working_days:.0f}, verfuegbar {remaining:.0f}</b>\n" if exceeds else ""
        msg = (
            f"\U0001f3d6\ufe0f <b>URLAUBSANTRAG</b>\n\n"
            f"\U0001f464 {emp_name} ({emp.personal_nr})\n"
            f"\U0001f4c5 {start_str_de} - {end_str_de}\n"
            f"\U0001f4ca {working_days:.0f} Arbeitstage\n"
            f"\U0001f4b0 Resturlaub danach: {remaining_after:.0f} Tage\n"
            f"{warn_line}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Genehmigen", callback_data=f"vac_ok:{req.id}"),
                InlineKeyboardButton("\u274c Ablehnen", callback_data=f"vac_no:{req.id}"),
            ]
        ])
        notify_admin(msg, reply_markup=keyboard)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Telegram Urlaubsantrag-Benachrichtigung: {e}")

    from app.services.booking_service import log_audit
    log_audit(db, current_user.id, emp.id, 'vacation_request_created',
        'vacation_request', req.id,
        details=f"Urlaubsantrag: {start.strftime('%d.%m.')} bis {end.strftime('%d.%m.%Y')}, {working_days:.0f} Tage")

    db.commit()

    warn_msg = f" HINWEIS: Uebersteigt Restanspruch ({remaining:.0f} Tage verfuegbar)." if exceeds else ""
    return {
        "status": "ok",
        "message": f"Urlaubsantrag gesendet! {working_days:.0f} Arbeitstage vom {start.strftime('%d.%m.')} bis {end.strftime('%d.%m.%Y')}.{warn_msg}",
        "request_id": req.id,
        "working_days": working_days,
        "remaining_after": remaining - working_days,
        "exceeds_entitlement": exceeds,
    }


@router.get("/my-requests")
def get_my_vacation_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Meine Urlaubsanträge."""
    emp = _get_employee(db, current_user)
    requests = db.query(VacationRequest).filter(
        VacationRequest.employee_id == emp.id,
    ).order_by(VacationRequest.requested_at.desc()).limit(20).all()

    return [{
        "id": r.id,
        "start_date": r.start_date.isoformat(),
        "end_date": r.end_date.isoformat(),
        "working_days": r.working_days,
        "status": r.status,
        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    } for r in requests]


@router.get("/calc-working-days")
def calc_working_days(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Arbeitstage berechnen für Urlaubsantrag-Vorschau."""
    emp = _get_employee(db, current_user)
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    working_days = _count_working_days(db, emp.id, start, end)

    current_year = start.year
    entitlement = db.query(VacationEntitlement).filter(
        VacationEntitlement.employee_id == emp.id,
        VacationEntitlement.year == current_year,
    ).first()
    remaining = entitlement.days_remaining if entitlement else 30

    return {
        "working_days": working_days,
        "remaining": remaining,
        "remaining_after": remaining - working_days,
    }


# ========== ADMIN ENDPOINTS ==========

@router.get("/admin/requests")
def get_all_vacation_requests(
    status: str = None,
    employee_id: int = None,
    year: int = None,
    month: int = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Alle Urlaubsanträge (Admin)."""
    query = db.query(VacationRequest).order_by(VacationRequest.start_date.desc())
    if status:
        query = query.filter(VacationRequest.status == status)
    if employee_id:
        query = query.filter(VacationRequest.employee_id == employee_id)
    if year:
        query = query.filter(
            extract('year', VacationRequest.start_date) == year
        )
    if month:
        query = query.filter(
            extract('month', VacationRequest.start_date) == month
        )
    requests = query.limit(500).all()

    # Entitlements vorladen fuer exceeds-Pruefung
    entitlement_map = {}
    for ent in db.query(VacationEntitlement).all():
        entitlement_map[(ent.employee_id, ent.year)] = ent

    result = []
    for r in requests:
        emp = db.query(Employee).filter(Employee.id == r.employee_id).first()
        req_type = getattr(r, 'type', 'urlaub') or 'urlaub'
        exceeds = False
        if r.status == 'pending' and req_type == 'urlaub':
            ent = entitlement_map.get((r.employee_id, r.start_date.year))
            remaining = ent.days_remaining if ent else 30
            exceeds = (r.working_days or 0) > remaining
        result.append({
            "id": r.id,
            "employee_id": r.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "personal_nr": emp.personal_nr if emp else "?",
            "start_date": r.start_date.isoformat(),
            "end_date": r.end_date.isoformat(),
            "working_days": r.working_days,
            "status": r.status,
            "type": req_type,
            "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            "exceeds_entitlement": exceeds,
        })
    return result


@router.get("/admin/calendar")
def get_vacation_calendar(
    year: int = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Jahreskalender: Alle genehmigten + offenen Urlaubstage pro MA."""
    if not year:
        year = date.today().year

    requests_list = db.query(VacationRequest).filter(
        VacationRequest.status.in_(['approved', 'pending']),
        extract('year', VacationRequest.start_date) == year,
    ).all()

    employees = db.query(Employee).filter(
        Employee.is_active == True,
        ~Employee.personal_nr.like('A%')
    ).order_by(Employee.last_name).all()

    result = []
    for emp in employees:
        emp_requests = [r for r in requests_list if r.employee_id == emp.id]
        days = []
        for r in emp_requests:
            d = r.start_date
            while d <= r.end_date:
                if d.weekday() < 5:  # Mo-Fr
                    days.append({
                        "date": d.isoformat(),
                        "status": r.status,
                        "type": getattr(r, 'type', 'urlaub') or 'urlaub',
                        "request_id": r.id,
                    })
                d += timedelta(days=1)
        result.append({
            "employee_id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}",
            "personal_nr": emp.personal_nr,
            "days": days,
        })
    return result


@router.put("/admin/requests/{request_id}")
def process_vacation_request(
    request_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Urlaubsantrag genehmigen, ablehnen oder nur Daten aktualisieren."""
    req = db.query(VacationRequest).filter(VacationRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Antrag nicht gefunden")

    new_status = data.get("status")  # Kann None sein = nur Daten speichern

    # Daten aendern wenn mitgeliefert
    new_start = data.get("start_date")
    new_end = data.get("end_date")
    old_start = req.start_date
    old_end = req.end_date
    if new_start:
        req.start_date = date.fromisoformat(new_start)
    if new_end:
        req.end_date = date.fromisoformat(new_end)
    if new_start or new_end:
        req.working_days = _count_working_days(db, req.employee_id, req.start_date, req.end_date)

    emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
    emp_name = f"{emp.first_name} {emp.last_name}" if emp else "?"
    req_type = getattr(req, 'type', 'urlaub') or 'urlaub'

    # Wenn kein Status mitgeschickt -> nur Daten aktualisieren ("Speichern")
    if new_status is None:
        if not (new_start or new_end):
            raise HTTPException(status_code=400, detail="Keine Aenderungen")

        dates_changed = (req.start_date != old_start or req.end_date != old_end)

        # Falls aktuell approved: Schedules revertieren + neu erstellen
        if req.status == 'approved':
            _revert_vacation_schedules(db, req)
            if req_type == 'urlaub':
                entitlement = db.query(VacationEntitlement).filter(
                    VacationEntitlement.employee_id == req.employee_id,
                    VacationEntitlement.year == old_start.year,
                ).first()
                if entitlement:
                    entitlement.days_taken = max(0, (entitlement.days_taken or 0) - _count_working_days(db, req.employee_id, old_start, old_end))
                    entitlement.days_remaining = (entitlement.days_entitled or 30) - entitlement.days_taken
            _create_vacation_schedules(db, req, emp)
            if req_type == 'urlaub':
                entitlement = db.query(VacationEntitlement).filter(
                    VacationEntitlement.employee_id == req.employee_id,
                    VacationEntitlement.year == req.start_date.year,
                ).first()
                if entitlement:
                    entitlement.days_taken = (entitlement.days_taken or 0) + req.working_days
                    entitlement.days_remaining = (entitlement.days_entitled or 30) - entitlement.days_taken

        # Telegram: Datumsaenderung mitteilen
        if dates_changed and emp and getattr(emp, 'telegram_chat_id', None):
            try:
                from app.services.telegram_bot import send_message_sync
                type_label = "Abwesenheit" if req_type == 'abwesenheit' else "Urlaub"
                send_message_sync(emp.telegram_chat_id,
                    f"\U0001f4c5 Dein {type_label} wurde geaendert: "
                    f"{req.start_date.strftime('%d.%m.')} - {req.end_date.strftime('%d.%m.%Y')} "
                    f"({req.working_days:.0f} Tage)")
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Telegram Datumsaenderung: {e}")

        from app.services.booking_service import log_audit
        log_audit(db, admin.id, req.employee_id, 'vacation_request_updated',
            'vacation_request', req.id,
            details=f"Urlaub geaendert: {req.start_date.strftime('%d.%m.')} bis {req.end_date.strftime('%d.%m.%Y')}, {req.working_days:.0f} Tage ({emp_name})")

        db.commit()
        return {"status": "ok", "new_status": req.status}

    # Status-Validierung NUR wenn Status mitgeschickt
    if new_status not in ("approved", "rejected", "shifted", "cancelled"):
        raise HTTPException(status_code=400, detail="Status muss 'approved', 'rejected', 'shifted' oder 'cancelled' sein")

    req.status = new_status
    req.decided_at = datetime.now()
    req.decided_by = admin.id

    if new_status == 'approved':
        # Schedule-Einträge erstellen
        _create_vacation_schedules(db, req, emp)

        # VacationEntitlement nur bei echtem Urlaub updaten (nicht bei Abwesenheit)
        if req_type == 'urlaub':
            current_year = req.start_date.year
            entitlement = db.query(VacationEntitlement).filter(
                VacationEntitlement.employee_id == req.employee_id,
                VacationEntitlement.year == current_year,
            ).first()
            if entitlement:
                entitlement.days_taken = (entitlement.days_taken or 0) + req.working_days
                entitlement.days_remaining = (entitlement.days_entitled or 30) - entitlement.days_taken

        # MA per Telegram benachrichtigen
        if emp and emp.telegram_chat_id:
            from app.services.telegram_bot import send_message_sync
            start_str = req.start_date.strftime("%d.%m.")
            end_str = req.end_date.strftime("%d.%m.%Y")
            type_label = "Abwesenheit" if req_type == 'abwesenheit' else "Urlaub"
            send_message_sync(
                emp.telegram_chat_id,
                f"\U0001f3d6\ufe0f Dein {type_label} vom {start_str} bis {end_str} wurde genehmigt!",
            )
    elif new_status == 'cancelled':
        # Stornierung: Urlaubs-Schedules zuruecksetzen
        _revert_vacation_schedules(db, req)
        # Urlaubstage zurueckgeben (nur bei echtem Urlaub)
        if req_type == 'urlaub':
            current_year = req.start_date.year
            entitlement = db.query(VacationEntitlement).filter(
                VacationEntitlement.employee_id == req.employee_id,
                VacationEntitlement.year == current_year,
            ).first()
            if entitlement and req.status == 'approved':
                entitlement.days_taken = max(0, (entitlement.days_taken or 0) - req.working_days)
                entitlement.days_remaining = (entitlement.days_entitled or 30) - entitlement.days_taken
        if emp and emp.telegram_chat_id:
            from app.services.telegram_bot import send_message_sync
            send_message_sync(emp.telegram_chat_id, f"Dein Urlaub vom {req.start_date.strftime('%d.%m.')} bis {req.end_date.strftime('%d.%m.%Y')} wurde storniert.")

    elif new_status == 'shifted':
        # Verschiebung: alte Schedules zuruecksetzen, neue erstellen
        if req.status == 'approved':
            _revert_vacation_schedules(db, req)
            # Urlaubstage zurueckgeben
            current_year = req.start_date.year
            entitlement = db.query(VacationEntitlement).filter(
                VacationEntitlement.employee_id == req.employee_id,
                VacationEntitlement.year == current_year,
            ).first()
            if entitlement:
                entitlement.days_taken = max(0, (entitlement.days_taken or 0) - req.working_days)
                entitlement.days_remaining = (entitlement.days_entitled or 30) - entitlement.days_taken
        # Status auf pending zuruecksetzen (muss erneut genehmigt werden)
        req.status = 'pending'
        new_status = 'pending'
        if emp and emp.telegram_chat_id:
            from app.services.telegram_bot import send_message_sync
            send_message_sync(emp.telegram_chat_id, f"Dein Urlaub wurde verschoben auf {req.start_date.strftime('%d.%m.')} - {req.end_date.strftime('%d.%m.%Y')}. Bitte warte auf Genehmigung.")

    else:
        # Ablehnung: MA benachrichtigen
        if emp and emp.telegram_chat_id:
            from app.services.telegram_bot import send_message_sync
            start_str = req.start_date.strftime("%d.%m.")
            end_str = req.end_date.strftime("%d.%m.%Y")
            send_message_sync(
                emp.telegram_chat_id,
                f"\u274c Dein Urlaubsantrag vom {start_str} bis {end_str} wurde leider abgelehnt. "
                f"Bitte sprich mit der Verwaltung.",
            )

    from app.services.booking_service import log_audit
    status_labels = {'approved': 'genehmigt', 'rejected': 'abgelehnt', 'cancelled': 'storniert', 'shifted': 'verschoben', 'pending': 'verschoben (wartet)'}
    log_audit(db, admin.id, req.employee_id, f'vacation_request_{new_status}',
        'vacation_request', req.id,
        details=f"Urlaub {req.start_date.strftime('%d.%m.')} bis {req.end_date.strftime('%d.%m.%Y')}: {status_labels.get(new_status, new_status)} ({emp_name})")

    db.commit()
    return {"status": "ok", "new_status": new_status}


@router.get("/admin/overview")
def get_vacation_overview(
    year: int = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Jahresübersicht: Pro MA Anspruch, Genommen, Rest."""
    if not year:
        year = date.today().year

    employees = db.query(Employee).filter(
        Employee.is_active == True,
    ).order_by(Employee.last_name).all()

    result = []
    for emp in employees:
        if emp.personal_nr and emp.personal_nr.startswith('A'):
            continue
        entitlement = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == emp.id,
            VacationEntitlement.year == year,
        ).first()

        pending_count = db.query(VacationRequest).filter(
            VacationRequest.employee_id == emp.id,
            VacationRequest.status == 'pending',
        ).count()

        result.append({
            "employee_id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}",
            "personal_nr": emp.personal_nr,
            "days_entitled": entitlement.days_entitled if entitlement else 30,
            "days_taken": entitlement.days_taken if entitlement else 0,
            "days_remaining": entitlement.days_remaining if entitlement else 30,
            "vacation_rate": entitlement.vacation_rate if entitlement else 0,
            "pending_requests": pending_count,
        })
    return result


@router.put("/admin/entitlement")
def update_vacation_entitlement(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Urlaubsanspruch fuer einen MA/Jahr setzen oder aktualisieren."""
    employee_id = data.get('employee_id')
    year_val = data.get('year', date.today().year)
    days_entitled = data.get('days_entitled')

    if not employee_id or days_entitled is None:
        raise HTTPException(status_code=400, detail="employee_id und days_entitled erforderlich")

    entitlement = db.query(VacationEntitlement).filter(
        VacationEntitlement.employee_id == employee_id,
        VacationEntitlement.year == year_val,
    ).first()

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    emp_name = f"{emp.first_name} {emp.last_name}" if emp else str(employee_id)

    if not entitlement:
        entitlement = VacationEntitlement(
            employee_id=employee_id,
            year=year_val,
            days_entitled=float(days_entitled),
            days_taken=0,
            days_remaining=float(days_entitled),
        )
        db.add(entitlement)
        from app.services.booking_service import log_audit
        log_audit(db, admin.id, employee_id, 'vacation_entitlement_updated',
            entity_type='vacation_entitlement',
            new_value={"anspruch_tage": float(days_entitled), "jahr": year_val},
            details=f"Urlaubsanspruch erstellt: {emp_name}, {year_val}: {days_entitled} Tage")
    else:
        old_entitled = entitlement.days_entitled or 0
        entitlement.days_entitled = float(days_entitled)
        entitlement.days_remaining = float(days_entitled) - (entitlement.days_taken or 0)
        from app.services.booking_service import log_audit
        log_audit(db, admin.id, employee_id, 'vacation_entitlement_updated',
            entity_type='vacation_entitlement',
            old_value={"anspruch_tage": old_entitled, "jahr": year_val},
            new_value={"anspruch_tage": float(days_entitled), "jahr": year_val},
            details=f"Urlaubsanspruch geaendert: {emp_name}, {year_val}: {old_entitled} -> {days_entitled} Tage")

    db.commit()
    return {
        "status": "ok",
        "days_entitled": entitlement.days_entitled,
        "days_taken": entitlement.days_taken,
        "days_remaining": entitlement.days_remaining,
    }


def _calc_vacation_rate(db: Session, employee_id: int, ref_date: date = None) -> dict:
    """
    Berechnet den Urlaubstagessatz nach § 11 BUrlG:
    Durchschnittsverdienst pro Arbeitstag der letzten 13 Wochen.
    """
    if not ref_date:
        ref_date = date.today()
    start_date = ref_date - timedelta(days=91)  # 13 Wochen

    # Alle Arbeitstage (ohne Urlaub/Krank)
    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee_id,
        TimeEntry.object_id != 999,
        func.date(TimeEntry.check_in) >= start_date,
        func.date(TimeEntry.check_in) < ref_date,
        TimeEntry.check_out != None,
    ).all()

    # Pro Tag gruppieren
    daily_earnings = {}
    for e in entries:
        day = e.check_in.date()
        earnings = (e.billed_hours or 0) * (e.hourly_rate or 0)
        daily_earnings[day] = daily_earnings.get(day, 0) + earnings

    worked_days = len(daily_earnings)
    total_earnings = sum(daily_earnings.values())
    rate = round(total_earnings / worked_days, 2) if worked_days > 0 else 0

    return {
        "worked_days": worked_days,
        "total_earnings": round(total_earnings, 2),
        "vacation_rate": rate,
        "period_start": start_date.isoformat(),
        "period_end": ref_date.isoformat(),
    }


@router.post("/admin/recalc-vacation-rates")
def recalculate_vacation_rates(
    data: dict = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """
    Berechnet vacation_rate fuer alle (oder einen) MA nach § 11 BUrlG neu.
    WICHTIG: Aktualisiert NUR den Referenzwert in vacation_entitlements.
    Bereits gebuchte Urlaubstage (time_entries) werden NICHT geaendert.
    Body: { "employee_id": 5 } fuer einzelnen MA, oder {} fuer alle.
    """
    if not data:
        data = {}
    year = data.get('year', date.today().year)
    single_id = data.get('employee_id')

    if single_id:
        employees = db.query(Employee).filter(Employee.id == single_id).all()
    else:
        employees = db.query(Employee).filter(
            Employee.is_active == True,
        ).all()

    results = []
    for emp in employees:
        if emp.personal_nr and emp.personal_nr.startswith('A'):
            continue

        # ref_date = naechster Urlaubsbeginn dieses MA, sonst today()
        next_vacation = db.query(VacationRequest).filter(
            VacationRequest.employee_id == emp.id,
            VacationRequest.status == 'approved',
            VacationRequest.start_date >= date.today(),
        ).order_by(VacationRequest.start_date).first()
        ref = next_vacation.start_date if next_vacation else date.today()

        calc = _calc_vacation_rate(db, emp.id, ref_date=ref)
        if calc['worked_days'] == 0:
            results.append({
                "employee_id": emp.id,
                "name": f"{emp.first_name} {emp.last_name}",
                "status": "skipped",
                "reason": "Keine Arbeitsdaten in den letzten 13 Wochen",
            })
            continue

        # Entitlement holen oder erstellen
        ent = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == emp.id,
            VacationEntitlement.year == year,
        ).first()

        if not ent:
            ent = VacationEntitlement(
                employee_id=emp.id, year=year,
                days_entitled=0, days_taken=0, days_remaining=0,
            )
            db.add(ent)

        old_rate = ent.vacation_rate
        ent.vacation_rate = calc['vacation_rate']

        # Info ueber bereits gebuchte Urlaubstage (werden NICHT geaendert)
        booked_vacation_days = db.query(TimeEntry).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.object_id == 999,
            func.extract('year', TimeEntry.check_in) == year,
        ).count()

        results.append({
            "employee_id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}",
            "status": "updated",
            "old_rate": old_rate,
            "new_rate": calc['vacation_rate'],
            "worked_days": calc['worked_days'],
            "total_earnings": calc['total_earnings'],
            "booked_days": booked_vacation_days,
        })

    db.commit()
    return {"status": "ok", "results": results}


@router.post("/admin/recalc-vacation-entries")
def recalc_vacation_entries(
    data: dict = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """
    Vorschau oder Update der Urlaubssaetze in time_entries.
    Body: { "preview": true/false, "year": 2026 }
    preview=true: Zeigt betroffene Eintraege mit alt/neu/Differenz
    preview=false: Schreibt die neuen Saetze + Audit-Log
    Schutz: Abgerechnete Monate (Zeitkonto status=abgeschlossen) werden uebersprungen.
    """
    from app.models.models import Zeitkonto
    from app.services.booking_service import log_audit

    if not data:
        data = {}
    preview = data.get('preview', True)
    year = data.get('year', date.today().year)

    # Abgerechnete Monate ermitteln (global, alle MA)
    closed_records = db.query(Zeitkonto.employee_id, Zeitkonto.year, Zeitkonto.month).filter(
        Zeitkonto.status == 'abgeschlossen',
    ).all()
    closed_set = {(z.employee_id, z.year, z.month) for z in closed_records}

    # Alle Urlaubs-TimeEntries des Jahres
    urlaub_entries = db.query(TimeEntry).filter(
        TimeEntry.object_id == 999,
        TimeEntry.service_type == 'Urlaub',
        func.extract('year', TimeEntry.check_in) == year,
    ).all()

    # Pro MA gruppieren
    from collections import defaultdict
    entries_by_emp = defaultdict(list)
    for e in urlaub_entries:
        entries_by_emp[e.employee_id].append(e)

    results = []
    total_diff = 0.0

    for emp_id, entries in entries_by_emp.items():
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if not emp or (emp.personal_nr and emp.personal_nr.startswith('A')):
            continue

        entries_sorted = sorted(entries, key=lambda e: e.check_in)

        # Pro VacationRequest gruppieren fuer gleichen ref_date
        request_rates = {}
        for entry in entries_sorted:
            entry_date = entry.check_in.date()
            # Request finden, zu dem dieser Eintrag gehoert
            req = db.query(VacationRequest).filter(
                VacationRequest.employee_id == emp_id,
                VacationRequest.start_date <= entry_date,
                VacationRequest.end_date >= entry_date,
                VacationRequest.status == 'approved',
            ).first()
            req_id = req.id if req else 0
            if req_id not in request_rates:
                ref = req.start_date if req else entry_date
                calc = _calc_vacation_rate(db, emp_id, ref_date=ref)
                request_rates[req_id] = calc['vacation_rate'] if calc['worked_days'] > 0 else 0

        changes = []
        for entry in entries_sorted:
            entry_date = entry.check_in.date()
            entry_month = (emp_id, entry_date.year, entry_date.month)

            # Abgerechneten Monat ueberspringen
            if entry_month in closed_set:
                continue

            # Rate aus dem Request-Cache
            req = db.query(VacationRequest).filter(
                VacationRequest.employee_id == emp_id,
                VacationRequest.start_date <= entry_date,
                VacationRequest.end_date >= entry_date,
                VacationRequest.status == 'approved',
            ).first()
            req_id = req.id if req else 0
            new_rate = request_rates.get(req_id, 0)

            if new_rate == 0:
                continue

            old_rate = float(entry.hourly_rate or 0)
            if abs(old_rate - new_rate) < 0.01:
                continue

            diff = new_rate - old_rate
            total_diff += diff
            changes.append({
                "entry_id": entry.id,
                "date": entry_date.isoformat(),
                "old_rate": round(old_rate, 2),
                "new_rate": round(new_rate, 2),
                "diff": round(diff, 2),
            })

            if not preview:
                log_audit(db, admin.id, emp_id, 'vacation_rate_corrected',
                          entity_type='time_entry', entity_id=entry.id,
                          old_value={"hourly_rate": old_rate, "date": entry_date.isoformat()},
                          new_value={"hourly_rate": new_rate},
                          details=f"Urlaubssatz korrigiert: {old_rate:.2f} -> {new_rate:.2f} EUR")
                entry.hourly_rate = new_rate

        if changes:
            emp_diff = sum(c['diff'] for c in changes)
            results.append({
                "employee_id": emp_id,
                "personal_nr": emp.personal_nr,
                "name": f"{emp.first_name} {emp.last_name}",
                "entries": changes,
                "count": len(changes),
                "total_diff": round(emp_diff, 2),
            })

    if not preview and results:
        # Auch vacation_entitlements aktualisieren
        for r in results:
            emp_id = r['employee_id']
            if r['entries']:
                latest_rate = r['entries'][-1]['new_rate']
                ent = db.query(VacationEntitlement).filter(
                    VacationEntitlement.employee_id == emp_id,
                    VacationEntitlement.year == year,
                ).first()
                if ent:
                    ent.vacation_rate = latest_rate
        db.commit()

    return {
        "status": "preview" if preview else "updated",
        "results": results,
        "total_diff": round(total_diff, 2),
        "total_entries": sum(r['count'] for r in results),
    }


@router.get("/admin/vacation-rate-preview/{employee_id}")
def preview_vacation_rate(
    employee_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Zeigt die Berechnung fuer einen MA ohne zu speichern."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="MA nicht gefunden")

    calc = _calc_vacation_rate(db, emp.id)
    calc["employee_id"] = emp.id
    calc["name"] = f"{emp.first_name} {emp.last_name}"

    # Aktueller Wert zum Vergleich
    ent = db.query(VacationEntitlement).filter(
        VacationEntitlement.employee_id == emp.id,
        VacationEntitlement.year == date.today().year,
    ).first()
    calc["current_rate"] = ent.vacation_rate if ent else 0

    return calc


@router.post("/admin/create-request")
def admin_create_request(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Admin erstellt Urlaub oder Abwesenheit direkt (auto-genehmigt)."""
    employee_id = data.get("employee_id")
    start_str = data.get("start_date")
    end_str = data.get("end_date")
    req_type = data.get("type", "urlaub")  # urlaub / abwesenheit

    if not employee_id or not start_str or not end_str:
        raise HTTPException(status_code=400, detail="employee_id, start_date und end_date erforderlich")
    if req_type not in ('urlaub', 'abwesenheit'):
        raise HTTPException(status_code=400, detail="type muss 'urlaub' oder 'abwesenheit' sein")

    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    if end < start:
        raise HTTPException(status_code=400, detail="Enddatum muss nach Startdatum liegen")

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    working_days = _count_working_days(db, emp.id, start, end)

    # Bei Urlaub: Resturlaub pruefen (Warnung statt Blockade)
    exceeds = False
    if req_type == 'urlaub':
        entitlement = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == emp.id,
            VacationEntitlement.year == start.year,
        ).first()
        remaining = entitlement.days_remaining if entitlement else 30
        exceeds = working_days > remaining

    req = VacationRequest(
        employee_id=emp.id,
        start_date=start,
        end_date=end,
        working_days=working_days,
        status='approved',
        type=req_type,
        decided_at=datetime.now(),
        decided_by=admin.id,
    )
    db.add(req)
    db.flush()

    # Schedules + TimeEntries erstellen
    _create_vacation_schedules(db, req, emp)

    # Urlaubskonto nur bei echtem Urlaub belasten
    if req_type == 'urlaub':
        entitlement = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == emp.id,
            VacationEntitlement.year == start.year,
        ).first()
        if entitlement:
            entitlement.days_taken = (entitlement.days_taken or 0) + working_days
            entitlement.days_remaining = (entitlement.days_entitled or 30) - entitlement.days_taken

    from app.services.booking_service import log_audit
    type_label = "Abwesenheit" if req_type == 'abwesenheit' else "Urlaub"
    log_audit(db, admin.id, emp.id, f'vacation_{req_type}_created',
        'vacation_request', req.id,
        details=f"{type_label}: {start.strftime('%d.%m.')} bis {end.strftime('%d.%m.%Y')}, {working_days:.0f} Tage")

    db.commit()

    warn_msg = f" (ACHTUNG: uebersteigt Restanspruch, verfuegbar: {remaining:.0f})" if exceeds else ""
    return {
        "status": "ok",
        "request_id": req.id,
        "type": req_type,
        "working_days": working_days,
        "message": f"{type_label} eingetragen: {working_days:.0f} Arbeitstage{warn_msg}",
        "exceeds_entitlement": exceeds,
    }


@router.post("/admin/carry-over")
def carry_over_vacation(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin_or_objektleiter)
):
    """Resturlaub vom Vorjahr uebertragen."""
    from_year = data.get('from_year', date.today().year - 1)
    to_year = data.get('to_year', date.today().year)

    employees = db.query(Employee).filter(Employee.is_active == True).all()
    carried = 0

    for emp in employees:
        if emp.personal_nr and emp.personal_nr.startswith('A'):
            continue

        prev = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == emp.id,
            VacationEntitlement.year == from_year,
        ).first()

        if not prev or (prev.days_remaining or 0) <= 0:
            continue

        carry_days = prev.days_remaining or 0

        current = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == emp.id,
            VacationEntitlement.year == to_year,
        ).first()

        if not current:
            current = VacationEntitlement(
                employee_id=emp.id,
                year=to_year,
                days_entitled=30 + carry_days,
                days_taken=0,
                days_remaining=30 + carry_days,
            )
            db.add(current)
        else:
            # Uebertrag zum Anspruch addieren (nur wenn noch nicht uebertragen)
            current.days_entitled = (current.days_entitled or 30) + carry_days
            current.days_remaining = current.days_entitled - (current.days_taken or 0)

        carried += 1

    db.commit()
    return {"status": "ok", "carried_employees": carried, "from_year": from_year, "to_year": to_year}


def _revert_vacation_schedules(db: Session, req: VacationRequest):
    """Urlaubs-Schedules zuruecksetzen oder loeschen."""
    vacation_schedules = db.query(Schedule).filter(
        Schedule.employee_id == req.employee_id,
        Schedule.date >= req.start_date,
        Schedule.date <= req.end_date,
        Schedule.status == 'urlaub',
        Schedule.notes.like(f"%Urlaubsantrag #{req.id}%"),
    ).all()

    for s in vacation_schedules:
        if s.planned_hours and s.planned_hours > 0:
            # Hatte vorher eine echte Schicht - zuruecksetzen
            s.status = 'normal'
            s.notes = None
        else:
            # Wurde nur fuer Urlaub erstellt - loeschen
            db.delete(s)


def _create_vacation_schedules(db: Session, req: VacationRequest, emp: Employee):
    """Erstellt Schedule-Einträge mit status='urlaub' UND TimeEntries mit fixem Urlaubssatz."""
    from datetime import time as time_cls

    # Finde die normalen Arbeitstage des MA
    past_schedules = db.query(Schedule.weekday).filter(
        Schedule.employee_id == emp.id,
        Schedule.status.in_(['normal', 'vertretung']),
    ).distinct().all()

    if past_schedules:
        working_weekdays = set(wd[0] for wd in past_schedules)
    else:
        working_weekdays = {0, 1, 2, 3, 4}

    # Finde ein typisches Objekt für diesen MA
    typical_schedule = db.query(Schedule).filter(
        Schedule.employee_id == emp.id,
        Schedule.status == 'normal',
    ).order_by(Schedule.date.desc()).first()

    object_id = typical_schedule.object_id if typical_schedule else None

    # § 11 BUrlG: Urlaubssatz berechnen am ERSTEN Tag des Urlaubszeitraums
    # Fuer alle Tage am Stueck den gleichen Satz verwenden
    calc = _calc_vacation_rate(db, emp.id, ref_date=req.start_date)
    fixed_rate = calc['vacation_rate'] if calc['worked_days'] > 0 else 0

    # Fallback: vacation_entitlements Wert nehmen wenn keine Arbeitsdaten
    if fixed_rate == 0:
        ent = db.query(VacationEntitlement).filter(
            VacationEntitlement.employee_id == emp.id,
            VacationEntitlement.year == req.start_date.year,
        ).first()
        fixed_rate = ent.vacation_rate if ent and ent.vacation_rate else 0

    # Existierende Schedules im Zeitraum auf 'urlaub' setzen
    existing = db.query(Schedule).filter(
        Schedule.employee_id == emp.id,
        Schedule.date >= req.start_date,
        Schedule.date <= req.end_date,
        Schedule.status.in_(['normal', 'vertretung']),
    ).all()

    updated_dates = set()
    for s in existing:
        s.status = 'urlaub'
        s.notes = f"Urlaubsantrag #{req.id}"
        updated_dates.add(s.date)

    # Urlaubs-Tage sammeln
    req_type_for_status = getattr(req, 'type', 'urlaub') or 'urlaub'
    schedule_status = 'abwesend' if req_type_for_status == 'abwesenheit' else 'urlaub'
    vacation_dates = []
    current = req.start_date
    while current <= req.end_date:
        if current.weekday() in working_weekdays:
            vacation_dates.append(current)
            if current not in updated_dates:
                vacation_schedule = Schedule(
                    employee_id=emp.id,
                    object_id=object_id,
                    weekday=current.weekday(),
                    date=current,
                    start_time=None,
                    end_time=None,
                    planned_hours=0,
                    status=schedule_status,
                    notes=f"{'Abwesenheit' if schedule_status == 'abwesend' else 'Urlaubsantrag'} #{req.id}",
                )
                db.add(vacation_schedule)
        current += timedelta(days=1)

    # TimeEntries erstellen
    req_type = getattr(req, 'type', 'urlaub') or 'urlaub'
    is_abwesenheit = req_type == 'abwesenheit'

    for vac_date in vacation_dates:
        from datetime import datetime as dt
        existing_entry = db.query(TimeEntry).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.object_id == 999,
            func.date(TimeEntry.check_in) == vac_date,
        ).first()
        if not existing_entry:
            if is_abwesenheit:
                entry_rate = 0
                entry_service = 'Abwesenheit'
                entry_notes = f"Abwesenheit (unbezahlt) - Antrag #{req.id}"
            else:
                entry_rate = fixed_rate
                entry_service = 'Urlaub'
                entry_notes = f"Urlaubstag - Urlaubsantrag #{req.id} - Tagessatz {fixed_rate:.2f}€ fixiert"
            entry = TimeEntry(
                employee_id=emp.id,
                object_id=999,
                check_in=dt.combine(vac_date, time_cls(0, 0)),
                check_out=dt.combine(vac_date, time_cls(0, 0)),
                hourly_rate=entry_rate,
                billed_hours=None,
                service_type=entry_service,
                is_manual_entry=True,
                notes=entry_notes,
            )
            db.add(entry)
