"""
Zentrale Buchungslogik fuer SEDA24 V3.0 Kategorie B.
Verarbeitet alle Push-Antworten und erstellt Buchungen.
Implementiert Szenarien S1-S10.
"""
import json
import random
import logging
from datetime import datetime, timedelta, time
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.models import (
    PushNotification, Schedule, Employee, TimeEntry, AuditLog, Object
)

logger = logging.getLogger(__name__)


def log_audit(db: Session, user_id: int, employee_id: int, action: str,
              entity_type: str = None, entity_id: int = None,
              old_value=None, new_value=None, details: str = None):
    """Audit-Log-Eintrag erstellen."""
    entry = AuditLog(
        user_id=user_id,
        employee_id=employee_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        details=details,
    )
    db.add(entry)


class BookingService:
    """Zentrale Buchungslogik fuer alle Kategorie-B-Szenarien."""

    def __init__(self, db: Session):
        self.db = db

    def process_push_response(self, notification_id: int, response: str,
                               data: dict = None) -> dict:
        """
        Haupteinstiegspunkt fuer Push-Antworten.
        Implementiert S1-S10.
        """
        notification = self.db.query(PushNotification).get(notification_id)
        if not notification:
            return {"status": "error", "message": "Benachrichtigung nicht gefunden"}

        schedule = None
        if notification.schedule_id:
            schedule = self.db.query(Schedule).get(notification.schedule_id)

        employee = self.db.query(Employee).get(notification.employee_id)
        if not employee:
            return {"status": "error", "message": "Mitarbeiter nicht gefunden"}

        if response == 'confirmed':
            return self._handle_confirmed(notification, schedule, employee)
        elif response == 'not_present':
            return self._handle_not_present(notification, schedule, employee, data or {})
        elif response == 'correction':
            return self._handle_correction(notification, schedule, employee, data or {})
        else:
            return {"status": "error", "message": "Unbekannter Response-Typ"}

    def _handle_confirmed(self, notification, schedule, employee):
        """
        S1: Normalfall - Buchung mit +-2min Randomisierung
        S10: KM-Fahrerlogik
        """
        if not schedule:
            return {"status": "error", "message": "Kein Dienstplan gefunden"}

        # Zeitcheck: Bestätigung erst nach Schichtende erlauben
        now = datetime.now()
        sched_end = datetime.combine(schedule.date, schedule.end_time)
        if now < sched_end:
            return {"status": "error", "message": "Schicht hat noch nicht geendet. Bitte erst nach Schichtende bestätigen."}

        # planned_hours ist bereits pro MA korrekt berechnet.
        # Aufteilung nur bei partner_schedule_id (manuelle Teilung durch Admin).
        hours = schedule.planned_hours or 0

        # Randomisierung +-2min (GDPR)
        start_var = random.randint(-2, 2)
        end_var = random.randint(-1, 2)

        check_in = datetime.combine(schedule.date, schedule.start_time) + timedelta(minutes=start_var)
        check_out = datetime.combine(schedule.date, schedule.end_time) + timedelta(minutes=end_var)

        # Ueberlappung mit vorherigen Schichten verhindern:
        # Bei aufeinanderfolgenden Schichten (z.B. 10:30 Ende -> 10:30 Start)
        # koennen die Zufallszeiten Ueberlappungen erzeugen.
        # Fix: check_in muss nach dem letzten check_out des gleichen MA am selben Tag liegen.
        day_start = datetime.combine(schedule.date, time(0, 0))
        day_end = datetime.combine(schedule.date, time(23, 59, 59))
        prev_entries = self.db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee.id,
            TimeEntry.check_in >= day_start,
            TimeEntry.check_in <= day_end,
            TimeEntry.check_out.isnot(None),
        ).order_by(TimeEntry.check_out.desc()).all()

        for prev in prev_entries:
            if prev.check_out and check_in < prev.check_out:
                check_in = prev.check_out + timedelta(minutes=1)
                logger.info(
                    f"Overlap-Fix: check_in verschoben auf {check_in} "
                    f"(vorherige Schicht endet {prev.check_out})"
                )
                break

        # Stundensatz bestimmen
        hourly_rate = self._get_hourly_rate(employee, schedule)

        # Pruefe Doppelbuchung fuer genau DIESE Schicht (exakt per schedule_id)
        existing = self.db.query(TimeEntry).filter(
            TimeEntry.schedule_id == schedule.id,
        ).first()

        if existing:
            # Update Notification trotzdem
            notification.response_status = 'confirmed'
            notification.responded_at = datetime.now()
            notification.status = 'responded'
            self.db.commit()
            return {"status": "already_booked", "message": "Schicht bereits gebucht"}

        entry = TimeEntry(
            employee_id=employee.id,
            object_id=schedule.object_id,
            schedule_id=schedule.id,
            check_in=check_in,
            check_out=check_out,
            billed_hours=hours,
            hourly_rate=hourly_rate,
            is_manual_entry=True,
            service_type=self._get_service_type(schedule),
            notes="Push-Bestaetigung Kategorie B",
        )
        self.db.add(entry)
        self.db.flush()

        # S10: KM-Berechnung
        if self._should_book_km(schedule, employee):
            self._book_km(employee.id, schedule.object_id, schedule.date, entry.id)

        # Audit Log
        log_audit(
            self.db, employee.user_id, employee.id, 'push_confirmed',
            'time_entry', entry.id,
            details=f"Schicht bei {schedule.object.name if schedule.object else '?'}, "
                    f"{hours}h gebucht"
        )

        notification.response_status = 'confirmed'
        notification.responded_at = datetime.now()
        notification.status = 'responded'

        self.db.commit()

        obj_name = schedule.object.name if schedule.object else f"Objekt {schedule.object_id}"
        brutto = round(hours * hourly_rate, 2)

        return {
            "status": "booked",
            "hours": hours,
            "check_in": check_in.isoformat(),
            "check_out": check_out.isoformat(),
            "time_entry_id": entry.id,
            "object_name": obj_name,
            "date": schedule.date.strftime("%d.%m.%Y"),
            "start_time": check_in.strftime("%H:%M"),
            "end_time": check_out.strftime("%H:%M"),
            "brutto": brutto,
        }

    def _handle_not_present(self, notification, schedule, employee, data):
        """S4: Nicht anwesend mit Grund."""
        reason = data.get('reason', 'Keine Angabe')
        absence_type = data.get('absence_type', 'privat')  # krank / privat / anderes

        notification.response_status = 'not_present'
        notification.response_data = json.dumps({
            "reason": reason,
            "absence_type": absence_type,
        })
        notification.responded_at = datetime.now()
        notification.status = 'responded'

        # Audit Log
        log_audit(
            self.db, employee.user_id, employee.id, 'push_not_present',
            'schedule', schedule.id if schedule else None,
            details=f"Abwesend: {absence_type} - {reason}"
        )

        self.db.commit()
        return {
            "status": "noted",
            "message": "Abwesenheit notiert. Admin wird informiert."
        }

    def _handle_correction(self, notification, schedule, employee, data):
        """
        S7: War mit Kollege -> Stunden teilen, Kollege bestaetigen
        S8: Anderes Objekt/andere Zeit -> Admin-Genehmigung
        """
        correction_type = data.get('type')

        if correction_type == 'with_colleague':
            return self._handle_correction_colleague(notification, schedule, employee, data)
        elif correction_type == 'different_object_time':
            return self._handle_correction_different(notification, schedule, employee, data)
        else:
            notification.response_status = 'correction'
            notification.response_data = json.dumps(data)
            notification.responded_at = datetime.now()
            notification.status = 'responded'
            self.db.commit()
            return {"status": "correction_requested", "message": "Korrektur eingereicht"}

    def _handle_correction_colleague(self, notification, schedule, employee, data):
        """S7: War mit Kollege - Stunden 50/50 teilen."""
        colleague_id = data.get('colleague_id')
        if not colleague_id:
            return {"status": "error", "message": "Kollegen-ID fehlt"}

        colleague = self.db.query(Employee).get(colleague_id)
        if not colleague:
            return {"status": "error", "message": "Kollege nicht gefunden"}

        hours = (schedule.planned_hours or 0) / 2

        # Buchung fuer den Mitarbeiter
        start_var = random.randint(-2, 2)
        end_var = random.randint(-1, 2)
        check_in = datetime.combine(schedule.date, schedule.start_time) + timedelta(minutes=start_var)
        check_out = datetime.combine(schedule.date, schedule.end_time) + timedelta(minutes=end_var)

        entry1 = TimeEntry(
            employee_id=employee.id,
            object_id=schedule.object_id,
            schedule_id=schedule.id,
            check_in=check_in,
            check_out=check_out,
            billed_hours=hours,
            hourly_rate=self._get_hourly_rate(employee, schedule),
            is_manual_entry=True,
            service_type=self._get_service_type(schedule),
            notes=f"Push-Bestaetigung mit Kollege {colleague.first_name} {colleague.last_name}",
        )
        self.db.add(entry1)

        # Buchung fuer den Kollegen (andere Zufallszeiten!)
        start_var2 = random.randint(-2, 2)
        end_var2 = random.randint(-1, 2)
        check_in2 = datetime.combine(schedule.date, schedule.start_time) + timedelta(minutes=start_var2)
        check_out2 = datetime.combine(schedule.date, schedule.end_time) + timedelta(minutes=end_var2)

        entry2 = TimeEntry(
            employee_id=colleague.id,
            object_id=schedule.object_id,
            check_in=check_in2,
            check_out=check_out2,
            billed_hours=hours,
            hourly_rate=self._get_hourly_rate(colleague, schedule),
            is_manual_entry=True,
            service_type=self._get_service_type(schedule),
            notes=f"Push-Bestaetigung mit Kollege {employee.first_name} {employee.last_name}",
        )
        self.db.add(entry2)

        notification.response_status = 'confirmed'
        notification.response_data = json.dumps({
            "type": "with_colleague",
            "colleague_id": colleague_id,
            "hours_each": hours,
        })
        notification.responded_at = datetime.now()
        notification.status = 'responded'

        # Audit Log
        log_audit(
            self.db, employee.user_id, employee.id, 'push_confirmed_with_colleague',
            'time_entry', None,
            details=f"Stunden geteilt mit {colleague.first_name} {colleague.last_name}: je {hours}h"
        )

        self.db.commit()
        return {
            "status": "booked_shared",
            "hours_each": hours,
            "colleague_name": f"{colleague.first_name} {colleague.last_name}",
        }

    def _handle_correction_different(self, notification, schedule, employee, data):
        """S8: Anderes Objekt oder andere Zeiten - geht an Admin."""
        from app.models.models import CorrectionRequest

        new_object_id = data.get('object_id')
        new_start = data.get('start_time')
        new_end = data.get('end_time')
        reason = data.get('reason', '')

        correction = CorrectionRequest(
            employee_id=employee.id,
            time_entry_id=None,
            correction_type='different_object_time',
            old_value=json.dumps({
                "object_id": schedule.object_id if schedule else None,
                "start_time": str(schedule.start_time) if schedule else None,
                "end_time": str(schedule.end_time) if schedule else None,
            }),
            new_value=json.dumps({
                "object_id": new_object_id,
                "start_time": new_start,
                "end_time": new_end,
            }),
            reason=reason,
            status='pending',
        )
        self.db.add(correction)

        notification.response_status = 'correction'
        notification.response_data = json.dumps(data)
        notification.responded_at = datetime.now()
        notification.status = 'responded'

        log_audit(
            self.db, employee.user_id, employee.id, 'correction_requested',
            'correction_request', None,
            details=f"Anderes Objekt/Zeit beantragt"
        )

        self.db.commit()
        return {
            "status": "correction_pending",
            "message": "Korrekturantrag an Admin gesendet"
        }

    def _get_hourly_rate(self, employee, schedule):
        """Stundensatz basierend auf Objekt/Service-Type bestimmen."""
        if schedule and schedule.object:
            obj_name = schedule.object.name.upper() if schedule.object.name else ""
            if any(kw in obj_name for kw in ['FENSTER', 'WINDOW']):
                return employee.hourly_rate_window or 20.00
            elif any(kw in obj_name for kw in ['GRUND', 'BASIC']):
                return employee.hourly_rate_basic or 20.00
        return employee.hourly_rate or employee.hourly_rate_standard or 15.00

    def _get_service_type(self, schedule):
        """Service-Type basierend auf Objekt bestimmen."""
        if schedule and schedule.object:
            obj_name = schedule.object.name.upper() if schedule.object.name else ""
            if 'FENSTER' in obj_name:
                return 'Fensterreinigung'
            elif 'GRUND' in obj_name:
                return 'Grundreinigung'
        return 'Unterhaltsreinigung'

    def _should_book_km(self, schedule, employee):
        """
        Pruefe ob KM gebucht werden sollen.
        - Solo am Objekt -> immer KM
        - Mehrere MA am Objekt -> nur wenn is_driver=True im Schedule
        - is_driver=True -> immer KM
        """
        if not schedule:
            return False

        # Wenn is_driver explizit gesetzt -> immer KM
        try:
            if schedule.is_driver:
                return True
        except AttributeError:
            pass

        # Pruefe ob andere MA am gleichen Objekt/Tag/gleiche Schichtzeit
        other_schedules = self.db.query(Schedule).filter(
            Schedule.object_id == schedule.object_id,
            Schedule.date == schedule.date,
            Schedule.employee_id != employee.id,
            Schedule.status.in_(['normal', 'vertretung']),
        ).count()

        # Solo am Objekt -> automatisch KM buchen
        return other_schedules == 0

    def _book_km(self, employee_id: int, object_id: int, entry_date, time_entry_id: int):
        """KM-Eintrag erstellen wenn Distanz konfiguriert. Bei Duplikat updaten."""
        from app.models.models import KmDistance

        km_dist = self.db.query(KmDistance).filter(
            KmDistance.employee_id == employee_id,
            KmDistance.object_id == object_id,
        ).first()

        if not km_dist or km_dist.distance_km <= 0:
            logger.info(f"KM: Keine Distanz fuer emp={employee_id}, obj={object_id}")
            return

        amount = round(km_dist.distance_km * (km_dist.rate_per_km or 0.30), 2)

        # INSERT ON CONFLICT: Bei Duplikat (employee_id+date+object_id) updaten
        self.db.execute(text("""
            INSERT INTO km_daily_entries
            (employee_id, object_id, time_entry_id, date, distance_km, amount, is_billable, is_longest_trip)
            VALUES (:emp_id, :obj_id, :te_id, :entry_date, :dist, :amount, TRUE, FALSE)
            ON CONFLICT (employee_id, date, object_id)
            DO UPDATE SET time_entry_id = :te_id, distance_km = :dist, amount = :amount
        """), {
            "emp_id": employee_id,
            "obj_id": object_id,
            "te_id": time_entry_id,
            "entry_date": entry_date,
            "dist": km_dist.distance_km,
            "amount": amount,
        })
        logger.info(f"KM gebucht: emp={employee_id}, obj={object_id}, {km_dist.distance_km}km, {amount}EUR")
