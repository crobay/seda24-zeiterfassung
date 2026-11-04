"""
Genehmigen / Ablehnen / still Erledigen von Antraegen (pending_bookings):
Mehrzeit, Nachtrag, Korrektur, Selbstbuchung.
Gemeinsame Logik fuer die App (admin.py) und die Telegram-Knoepfe.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)


class PendingBookingError(Exception):
    """Fachlicher Fehler (wird in der App zu HTTPException, in Telegram zu einer Meldung)."""
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _booking_snap(e):
    from app.api.v1.endpoints.admin import _booking_snap as snap
    return snap(e)


def approver_display_name(db, user_id) -> str:
    """Vorname des entscheidenden Benutzers fuer 'Genehmigt von ...'."""
    if user_id:
        row = db.execute(text(
            "SELECT e.first_name FROM employees e WHERE e.user_id = :uid ORDER BY e.id LIMIT 1"
        ), {"uid": user_id}).fetchone()
        if row and row.first_name:
            return row.first_name
    return "Admin"


def _mark_telegram(booking_id: int, label: str):
    """Telegram-Nachrichten zu diesem Antrag bei allen Empfaengern als entschieden markieren."""
    try:
        from app.services.telegram_bot import mark_admin_messages_decided
        mark_admin_messages_decided("pending_booking", booking_id, label)
    except Exception as e:
        logger.error(f"Telegram-Markierung pending_booking {booking_id} fehlgeschlagen: {e}")


def approve_pending_booking_core(db, booking_id: int, data: dict, approver_user_id):
    """Buchung genehmigen: Erstellt echten TimeEntry + optional KM."""

    import random

    pb = db.execute(text(
        "SELECT * FROM pending_bookings WHERE id = :id FOR UPDATE"
    ), {"id": booking_id}).fetchone()

    if not pb:
        raise PendingBookingError(404, "Buchung nicht gefunden")
    if pb.status != 'offen':
        raise PendingBookingError(400, "Buchung ist nicht mehr offen")

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
    # Alten Zustand der verknuepften Buchung fuer das Audit-Log sichern (vor Aenderung)
    from app.models.models import TimeEntry as _TE_snap
    old_te_snap = _booking_snap(db.query(_TE_snap).filter(_TE_snap.id == related_id).first()) if related_id else None
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

    elif related_id and getattr(pb, 'reason', None) == 'mehrzeit_dienstplan':
        # MEHRZEIT: genehmigte Stunden ADDIEREN statt ueberschreiben.
        # Die echte Arbeitszeit (check_in/check_out) der verknuepften Buchung bleibt
        # unveraendert, nur billed_hours wird um die genehmigte Mehrzeit erhoeht.
        db.execute(text("""
            UPDATE time_entries
            SET billed_hours = COALESCE(billed_hours, 0) + :add_hours,
                is_manual_entry = true,
                notes = COALESCE(notes, '') || :note_append
            WHERE id = :te_id
        """), {
            "add_hours": approved_hours,
            "note_append": f" [MEHRZEIT GENEHMIGT +{approved_hours}h] {admin_notes}".rstrip(),
            "te_id": related_id,
        })
        time_entry_id = related_id

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
        # Prüfe auf bestehende Buchungen am selben Tag
        force = data.get("force", False)
        existing_entries = db.execute(text("""
            SELECT id, check_in, check_out, billed_hours FROM time_entries
            WHERE employee_id = :emp_id AND object_id = :obj_id AND DATE(check_in) = :dt
        """), {"emp_id": pb.employee_id, "obj_id": pb.object_id, "dt": pb.date}).fetchall()

        if existing_entries and not force:
            details = "; ".join([
                f"{e.check_in.strftime('%H:%M') if hasattr(e.check_in, 'strftime') else str(e.check_in)[:5]}-"
                f"{e.check_out.strftime('%H:%M') if e.check_out and hasattr(e.check_out, 'strftime') else (str(e.check_out)[:5] if e.check_out else 'offen')} "
                f"({e.billed_hours}h)"
                for e in existing_entries
            ])
            raise PendingBookingError(409, f"Fuer diesen Tag existiert bereits eine Buchung: {details}. Trotzdem eintragen?")

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
        "admin_id": approver_user_id,
    })

    from app.services.booking_service import log_audit
    log_audit(db, approver_user_id, pb.employee_id, 'booking_approved',
        entity_type='pending_booking', entity_id=booking_id,
        old_value=old_te_snap,
        new_value={"datum": str(pb.date), "stunden": approved_hours, "stundensatz": hourly_rate, "typ": service_type},
        details=f"Selbstbuchung genehmigt: ID {booking_id}, {approved_hours}h, {hourly_rate} EUR/h")

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


def reject_pending_booking_core(db, booking_id: int, data: dict, approver_user_id):
    """Buchung ablehnen (Rueckfrage an MA)."""

    pb = db.execute(text(
        "SELECT * FROM pending_bookings WHERE id = :id FOR UPDATE"
    ), {"id": booking_id}).fetchone()

    if not pb:
        raise PendingBookingError(404, "Buchung nicht gefunden")
    if pb.status != 'offen':
        raise PendingBookingError(400, "Buchung ist nicht mehr offen")

    admin_notes = data.get("admin_notes", "")

    db.execute(text("""
        UPDATE pending_bookings
        SET status = 'abgelehnt', admin_notes = :notes, approved_at = NOW(), approved_by = :admin_id
        WHERE id = :id
    """), {
        "id": booking_id,
        "notes": admin_notes,
        "admin_id": approver_user_id,
    })

    from app.services.booking_service import log_audit
    log_audit(db, approver_user_id, pb.employee_id, 'booking_rejected',
        entity_type='pending_booking', entity_id=booking_id,
        details=f"Selbstbuchung abgelehnt: ID {booking_id}, Grund: {admin_notes}")

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


def close_pending_booking_core(db, booking_id: int, data: dict, approver_user_id):
    """Still erledigen: schliesst einen Antrag OHNE Benachrichtigung an den MA."""

    pb = db.execute(text(
        "SELECT * FROM pending_bookings WHERE id = :id FOR UPDATE"
    ), {"id": booking_id}).fetchone()

    if not pb:
        raise PendingBookingError(404, "Buchung nicht gefunden")
    if pb.status != 'offen':
        raise PendingBookingError(400, "Buchung ist nicht mehr offen")

    admin_notes = (data or {}).get("admin_notes", "")

    db.execute(text("""
        UPDATE pending_bookings
        SET status = 'erledigt', admin_notes = :notes, approved_at = NOW(), approved_by = :admin_id
        WHERE id = :id
    """), {"id": booking_id, "notes": admin_notes, "admin_id": approver_user_id})

    from app.services.booking_service import log_audit
    log_audit(db, approver_user_id, pb.employee_id, 'booking_closed_silently',
        entity_type='pending_booking', entity_id=booking_id,
        details=f"Antrag still erledigt (ohne Benachrichtigung): ID {booking_id}. {admin_notes}".rstrip())

    db.commit()
    # BEWUSST keine Telegram-/Mail-Benachrichtigung an den Mitarbeiter.
    return {"status": "ok", "message": "Still erledigt"}


# ─── Telegram-Log ────────────────────────────────────────────────────────────


def approve_pending_booking(db, booking_id: int, data: dict, approver_user_id, source: str = "App"):
    result = approve_pending_booking_core(db, booking_id, data or {}, approver_user_id)
    name = approver_display_name(db, approver_user_id)
    _mark_telegram(booking_id, f"\u2705 Genehmigt von {name}, {datetime.now().strftime('%H:%M')}"
                               + (" (App)" if source == "App" else ""))
    return result


def reject_pending_booking(db, booking_id: int, data: dict, approver_user_id, source: str = "App"):
    result = reject_pending_booking_core(db, booking_id, data or {}, approver_user_id)
    name = approver_display_name(db, approver_user_id)
    _mark_telegram(booking_id, f"\u274c Abgelehnt von {name}, {datetime.now().strftime('%H:%M')}"
                               + (" (App)" if source == "App" else ""))
    return result


def close_pending_booking(db, booking_id: int, data: dict, approver_user_id, source: str = "App"):
    result = close_pending_booking_core(db, booking_id, data or {}, approver_user_id)
    name = approver_display_name(db, approver_user_id)
    _mark_telegram(booking_id, f"\u2611\ufe0f Still erledigt von {name}, {datetime.now().strftime('%H:%M')}"
                               + (" (App)" if source == "App" else ""))
    return result
