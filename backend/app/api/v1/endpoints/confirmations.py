"""
Monatsbestaetigung-Endpoints fuer SEDA24 V3.0 (S9)
"""
import json
from datetime import datetime, date
from calendar import monthrange
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func, or_
from app.db.database import get_db
from app.core.security import get_current_active_user
from app.models.models import (
    User, Employee, MonthlyConfirmation, TimeEntry, PushNotification,
    Schedule, KmDailyEntry
)
from app.services.booking_service import log_audit

router = APIRouter()


def get_employee_for_user(db: Session, user: User) -> Employee:
    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    return employee


def verify_admin(current_user: User = Depends(get_current_active_user)):
    if current_user.role.value != 'admin':
        raise HTTPException(status_code=403, detail="Nur fuer Admins")
    return current_user


def verify_admin_or_objektleiter(current_user: User = Depends(get_current_active_user)):
    if current_user.role.value not in ('admin', 'objektleiter'):
        raise HTTPException(status_code=403, detail="Kein Zugriff")
    return current_user


@router.get("/my-month/{year}/{month}")
def get_my_month_overview(
    year: int,
    month: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Monatsansicht fuer Mitarbeiter: Alle Buchungen + Zusammenfassung."""
    employee = get_employee_for_user(db, current_user)

    _, last_day = monthrange(year, month)
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    # Alle TimeEntries des Monats (inkl. Urlaub)
    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee.id,
        TimeEntry.check_in >= start_date,
        TimeEntry.check_in <= end_date,
    ).order_by(TimeEntry.check_in).all()

    # KM-Eintraege
    km_result = db.execute(text("""
        SELECT COALESCE(SUM(distance_km), 0), COALESCE(SUM(amount), 0)
        FROM km_daily_entries
        WHERE employee_id = :emp_id
        AND date >= :start_date AND date <= :end_date
        AND is_billable = TRUE
    """), {
        "emp_id": employee.id,
        "start_date": date(year, month, 1),
        "end_date": date(year, month, last_day),
    }).fetchone()

    total_km = km_result[0] if km_result else 0
    total_km_amount = km_result[1] if km_result else 0

    total_hours = sum(e.billed_hours or 0 for e in entries if e.object_id != 999 and e.service_type != 'Urlaub')
    vacation_entries_list = [e for e in entries if e.object_id == 999 or e.service_type == 'Urlaub']
    total_vacation_hours = len(vacation_entries_list)  # 1 Tag pro Urlaubseintrag

    # Bestaetigungsstatus
    confirmation = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee.id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
    ).first()

    entries_data = []
    for e in entries:
        if e.object_id == 999 or e.service_type == 'Urlaub':
            obj_name = "Urlaub"
            hours = 1.0
        else:
            obj_name = e.object.name if e.object else (e.custom_object_name or "?")
            hours = e.billed_hours
        entries_data.append({
            "id": e.id,
            "date": e.check_in.strftime("%Y-%m-%d") if e.check_in else None,
            "object_name": obj_name,
            "check_in": e.check_in.isoformat() if e.check_in else None,
            "check_out": e.check_out.isoformat() if e.check_out else None,
            "hours": hours,
            "service_type": e.service_type,
            "hourly_rate": e.hourly_rate,
        })

    return {
        "year": year,
        "month": month,
        "entries": entries_data,
        "total_hours": round(total_hours, 2),
        "total_vacation_hours": round(total_vacation_hours, 2),
        "total_km": round(total_km, 2),
        "total_km_amount": round(total_km_amount, 2),
        "confirmation_status": confirmation.status if confirmation else "pending",
        "confirmed_at": confirmation.confirmed_at.isoformat() if confirmation and confirmation.confirmed_at else None,
    }


@router.post("/confirm/{year}/{month}")
def confirm_month(
    year: int,
    month: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Mitarbeiter bestaetigt Monat."""
    employee = get_employee_for_user(db, current_user)

    # Pruefen ob bereits bestaetigt
    existing = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee.id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
    ).first()

    if existing and existing.status == 'confirmed':
        return {"status": "already_confirmed", "confirmed_at": existing.confirmed_at.isoformat()}

    # Gesamtstunden berechnen
    _, last_day = monthrange(year, month)
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month, last_day, 23, 59, 59)

    total_hours = db.query(func.sum(TimeEntry.billed_hours)).filter(
        TimeEntry.employee_id == employee.id,
        TimeEntry.check_in >= start_date,
        TimeEntry.check_in <= end_date,
        TimeEntry.object_id != 999,
    ).scalar() or 0

    km_result = db.execute(text("""
        SELECT COALESCE(SUM(distance_km), 0)
        FROM km_daily_entries
        WHERE employee_id = :emp_id
        AND date >= :start_date AND date <= :end_date
        AND is_billable = TRUE
    """), {
        "emp_id": employee.id,
        "start_date": date(year, month, 1),
        "end_date": date(year, month, last_day),
    }).scalar() or 0

    if existing:
        existing.status = 'confirmed'
        existing.confirmed_at = datetime.now()
        existing.confirmed_by = 'employee'
        existing.total_hours = total_hours
        existing.total_km = km_result
        existing.dispute_reason = None
    else:
        confirmation = MonthlyConfirmation(
            employee_id=employee.id,
            year=year,
            month=month,
            status='confirmed',
            confirmed_by='employee',
            total_hours=total_hours,
            total_km=km_result,
            confirmed_at=datetime.now(),
        )
        db.add(confirmation)

    log_audit(
        db, current_user.id, employee.id, 'month_confirmed',
        'monthly_confirmation', None,
        details=f"Monat {month}/{year} bestaetigt: {total_hours}h, {km_result}km"
    )

    db.commit()
    return {"status": "confirmed", "total_hours": total_hours, "total_km": km_result}


@router.post("/dispute/{year}/{month}")
def dispute_month(
    year: int,
    month: int,
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Mitarbeiter widerspricht Monat."""
    employee = get_employee_for_user(db, current_user)
    reason = data.get("reason", "")

    existing = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee.id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
    ).first()

    if existing:
        existing.status = 'disputed'
        existing.dispute_reason = reason
    else:
        confirmation = MonthlyConfirmation(
            employee_id=employee.id,
            year=year,
            month=month,
            status='disputed',
            dispute_reason=reason,
        )
        db.add(confirmation)

    log_audit(
        db, current_user.id, employee.id, 'month_disputed',
        'monthly_confirmation', None,
        details=f"Monat {month}/{year} angefochten: {reason}"
    )

    db.commit()
    return {"status": "disputed", "message": "Widerspruch eingereicht"}


@router.get("/admin/pending-confirmations")
def get_pending_confirmations(
    year: int = None,
    month: int = None,
    admin: User = Depends(verify_admin_or_objektleiter),
    db: Session = Depends(get_db)
):
    """Admin: Monatsbestaetigungen-Uebersicht mit letzter Schicht, Stunden, Status."""
    if not year:
        year = datetime.now().year
    if not month:
        month = datetime.now().month

    _, last_day_num = monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, last_day_num)
    start_dt = datetime(year, month, 1)
    end_dt = datetime(year, month, last_day_num, 23, 59, 59)

    # Alle aktiven Kat-B/C Mitarbeiter
    employees = db.query(Employee).filter(
        Employee.is_active == True,
        Employee.tracking_mode.in_(['B', 'C']),
    ).order_by(Employee.personal_nr).all()

    result = []
    for emp in employees:
        conf = db.query(MonthlyConfirmation).filter(
            MonthlyConfirmation.employee_id == emp.id,
            MonthlyConfirmation.year == year,
            MonthlyConfirmation.month == month,
        ).first()

        # Letzte Schicht im Monat
        last_shift_date = db.query(func.max(Schedule.date)).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= first_day,
            Schedule.date <= last_day,
            Schedule.status.in_(['normal', 'vertretung']),
        ).scalar()

        # Gesamtstunden aus TimeEntry
        total_hours = db.query(func.sum(TimeEntry.billed_hours)).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.check_in >= start_dt,
            TimeEntry.check_in <= end_dt,
            TimeEntry.object_id != 999,
        ).scalar() or 0

        # Schichtanzahl
        shift_count = db.query(func.count(Schedule.id)).filter(
            Schedule.employee_id == emp.id,
            Schedule.date >= first_day,
            Schedule.date <= last_day,
            Schedule.status.in_(['normal', 'vertretung']),
        ).scalar() or 0

        # Urlaubstage im Monat
        vacation_days = db.query(func.count(TimeEntry.id)).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.check_in >= start_dt,
            TimeEntry.check_in <= end_dt,
            or_(TimeEntry.object_id == 999, TimeEntry.service_type == 'Urlaub'),
        ).scalar() or 0

        # Kranktage im Monat
        sick_days = db.query(func.count(TimeEntry.id)).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.check_in >= start_dt,
            TimeEntry.check_in <= end_dt,
            TimeEntry.service_type == 'Krank',
        ).scalar() or 0

        # Status-Logik: pending ohne sent_at = not_sent
        status = "not_sent"
        if conf:
            if conf.status == 'confirmed':
                status = 'confirmed'
            elif conf.status == 'disputed':
                status = 'disputed'
            elif conf.sent_at:
                status = 'sent'
            else:
                status = 'not_sent'

        result.append({
            "employee_id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}",
            "personal_nr": emp.personal_nr,
            "tracking_mode": emp.tracking_mode,
            "status": status,
            "sent_at": conf.sent_at.isoformat() if conf and conf.sent_at else None,
            "confirmed_at": conf.confirmed_at.isoformat() if conf and conf.confirmed_at else None,
            "dispute_reason": conf.dispute_reason if conf else None,
            "last_shift_date": last_shift_date.isoformat() if last_shift_date else None,
            "last_shift_override": conf.last_shift_override.isoformat() if conf and conf.last_shift_override else None,
            "total_hours": round(total_hours, 2),
            "shift_count": shift_count,
            "has_telegram": bool(emp.telegram_chat_id),
            "confirmed_by": conf.confirmed_by if conf else None,
            "vacation_days": vacation_days,
            "sick_days": sick_days,
        })

    return {"year": year, "month": month, "confirmations": result}


@router.post("/admin/trigger-confirmations/{year}/{month}")
def trigger_monthly_confirmations(
    year: int,
    month: int,
    admin: User = Depends(verify_admin_or_objektleiter),
    db: Session = Depends(get_db)
):
    """Admin: Push an alle MA fuer Monatsbestaetigung ausloesen."""
    from app.services.push_service import send_monthly_confirmation_request

    employees = db.query(Employee).filter(
        Employee.is_active == True,
        Employee.tracking_mode.in_(['B', 'C']),
    ).all()

    sent_count = 0
    for emp in employees:
        # Pruefen ob schon bestaetigt
        conf = db.query(MonthlyConfirmation).filter(
            MonthlyConfirmation.employee_id == emp.id,
            MonthlyConfirmation.year == year,
            MonthlyConfirmation.month == month,
            MonthlyConfirmation.status == 'confirmed',
        ).first()

        if conf:
            continue

        # Stunden, Schichtanzahl und Betrag berechnen
        from calendar import monthrange
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])

        entries = db.query(TimeEntry).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.check_in >= datetime.combine(first_day, datetime.min.time()),
            TimeEntry.check_in <= datetime.combine(last_day, datetime.max.time()),
        ).all()

        total_hours = sum(e.billed_hours or 0 for e in entries)
        shift_count = len(entries)
        total_amount = sum((e.billed_hours or 0) * (e.hourly_rate or 15.0) for e in entries)

        # KM berechnen
        from app.models.models import KmDailyEntry
        km_entries = db.query(KmDailyEntry).filter(
            KmDailyEntry.employee_id == emp.id,
            KmDailyEntry.date >= first_day,
            KmDailyEntry.date <= last_day,
        ).all()
        total_km = sum(e.distance_km or 0 for e in km_entries)

        # Telegram-Nachricht mit Details senden
        if emp.telegram_chat_id:
            from app.services.telegram_bot import send_monthly_confirmation
            send_monthly_confirmation(
                emp.id, year, month,
                total_hours, total_km,
                shift_count=shift_count,
                total_amount=total_amount,
            )
            sent_count += 1
            # sent_at setzen
            mc = db.query(MonthlyConfirmation).filter(
                MonthlyConfirmation.employee_id == emp.id,
                MonthlyConfirmation.year == year,
                MonthlyConfirmation.month == month,
            ).first()
            if not mc:
                mc = MonthlyConfirmation(
                    employee_id=emp.id, year=year, month=month,
                    status='pending', sent_at=datetime.now(),
                )
                db.add(mc)
            else:
                mc.sent_at = datetime.now()
            db.commit()
        else:
            # Kein Telegram -> nur Push
            notif = send_monthly_confirmation_request(db, emp.id, year, month)
            if notif:
                sent_count += 1

    log_audit(
        db, admin.id, None, 'monthly_confirmations_triggered',
        details=f"Monatsbestaetigung {month}/{year} an {sent_count} MA ausgeloest"
    )

    return {"status": "triggered", "sent_count": sent_count}


@router.post("/admin/confirmation-reset/{employee_id}/{year}/{month}")
def reset_confirmation(
    employee_id: int,
    year: int,
    month: int,
    admin: User = Depends(verify_admin_or_objektleiter),
    db: Session = Depends(get_db)
):
    """Admin: Monatsbestaetigung zuruecksetzen."""
    conf = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee_id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
    ).first()

    if conf:
        conf.status = 'pending'
        conf.sent_at = None
        conf.confirmed_at = None
        conf.dispute_reason = None

    # PushNotification-Duplikatschutz entfernen
    first_day = date(year, month, 1)
    db.query(PushNotification).filter(
        PushNotification.employee_id == employee_id,
        PushNotification.notification_type == 'monthly_confirmation',
        PushNotification.created_at >= datetime.combine(first_day, datetime.min.time()),
    ).delete()

    db.commit()

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    log_audit(
        db, admin.id, employee_id, 'confirmation_reset',
        'monthly_confirmation', None,
        details=f"Monatsbestaetigung {month}/{year} zurueckgesetzt fuer {emp.first_name} {emp.last_name}" if emp else ""
    )
    db.commit()

    return {"status": "reset"}


@router.post("/admin/confirmation-remind/{employee_id}/{year}/{month}")
def remind_confirmation(
    employee_id: int,
    year: int,
    month: int,
    admin: User = Depends(verify_admin_or_objektleiter),
    db: Session = Depends(get_db)
):
    """Admin: Erinnerung an einzelnen MA senden."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    if not emp.telegram_chat_id:
        raise HTTPException(status_code=400, detail="MA hat kein Telegram")

    # Schon bestaetigt?
    conf = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee_id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
        MonthlyConfirmation.status == 'confirmed',
    ).first()
    if conf:
        raise HTTPException(status_code=400, detail="MA hat bereits bestaetigt")

    # Stunden/KM berechnen
    _, last_day_num = monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, last_day_num)

    entries = db.query(TimeEntry).filter(
        TimeEntry.employee_id == employee_id,
        TimeEntry.check_in >= datetime.combine(first_day, datetime.min.time()),
        TimeEntry.check_in <= datetime.combine(last_day, datetime.max.time()),
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

    # Telegram senden
    from app.services.telegram_bot import send_monthly_confirmation
    send_monthly_confirmation(
        employee_id, year, month,
        total_hours, total_km,
        shift_count=shift_count,
        total_amount=total_amount,
    )

    # sent_at setzen
    mc = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee_id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
    ).first()
    if not mc:
        mc = MonthlyConfirmation(
            employee_id=employee_id, year=year, month=month,
            status='pending', sent_at=datetime.now(),
        )
        db.add(mc)
    else:
        mc.sent_at = datetime.now()
        if mc.status not in ('confirmed', 'disputed'):
            mc.status = 'pending'
    db.commit()

    return {"status": "sent", "total_hours": total_hours, "shift_count": shift_count}


@router.post("/admin/confirm-by-admin/{employee_id}/{year}/{month}")
def admin_confirm_month(
    employee_id: int,
    year: int,
    month: int,
    admin: User = Depends(verify_admin_or_objektleiter),
    db: Session = Depends(get_db)
):
    """Admin bestaetigt Monat fuer einen Mitarbeiter."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    _, last_day_num = monthrange(year, month)
    first_day = date(year, month, 1)
    last_day = date(year, month, last_day_num)
    start_dt = datetime(year, month, 1)
    end_dt = datetime(year, month, last_day_num, 23, 59, 59)

    total_hours = db.query(func.sum(TimeEntry.billed_hours)).filter(
        TimeEntry.employee_id == employee_id,
        TimeEntry.check_in >= start_dt,
        TimeEntry.check_in <= end_dt,
        TimeEntry.object_id != 999,
    ).scalar() or 0

    km_total = db.execute(text("""
        SELECT COALESCE(SUM(distance_km), 0) FROM km_daily_entries
        WHERE employee_id = :emp_id AND date >= :s AND date <= :e AND is_billable = TRUE
    """), {"emp_id": employee_id, "s": first_day, "e": last_day}).scalar() or 0

    conf = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee_id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
    ).first()

    if not conf:
        conf = MonthlyConfirmation(
            employee_id=employee_id, year=year, month=month,
        )
        db.add(conf)

    conf.status = 'confirmed'
    conf.confirmed_at = datetime.now()
    conf.confirmed_by = 'admin'
    conf.total_hours = total_hours
    conf.total_km = km_total
    conf.dispute_reason = None

    log_audit(
        db, admin.id, employee_id, 'month_confirmed_by_admin',
        'monthly_confirmation', None,
        details=f"Monat {month}/{year} durch Admin bestaetigt: {total_hours}h"
    )

    db.commit()
    return {"status": "confirmed", "confirmed_by": "admin", "total_hours": round(total_hours, 2)}


@router.put("/admin/confirmation-override/{employee_id}/{year}/{month}")
def override_last_shift(
    employee_id: int,
    year: int,
    month: int,
    data: dict,
    admin: User = Depends(verify_admin_or_objektleiter),
    db: Session = Depends(get_db)
):
    """Admin: Letzte Schicht manuell ueberschreiben."""
    override_date_str = data.get("last_shift_override")
    override_date = None
    if override_date_str:
        override_date = datetime.strptime(override_date_str, "%Y-%m-%d").date()

    conf = db.query(MonthlyConfirmation).filter(
        MonthlyConfirmation.employee_id == employee_id,
        MonthlyConfirmation.year == year,
        MonthlyConfirmation.month == month,
    ).first()

    if not conf:
        conf = MonthlyConfirmation(
            employee_id=employee_id, year=year, month=month,
            status='pending',
        )
        db.add(conf)

    conf.last_shift_override = override_date
    db.commit()

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    log_audit(
        db, admin.id, employee_id, 'last_shift_override',
        'monthly_confirmation', None,
        details=f"Letzte Schicht Override {month}/{year}: {override_date} fuer {emp.first_name} {emp.last_name}" if emp else ""
    )
    db.commit()

    return {"status": "ok", "last_shift_override": override_date.isoformat() if override_date else None}
