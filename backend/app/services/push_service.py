"""
Push-Notification-Service fuer SEDA24 V3.0
Sendet Browser-Push und (spaeter) Telegram-Nachrichten an Mitarbeiter.
"""
import json
import os
import logging
from datetime import datetime, timedelta
from pywebpush import webpush, WebPushException
from sqlalchemy.orm import Session
from app.models.models import (
    PushSubscription, PushNotification, Employee, Schedule, TelegramConfig
)

logger = logging.getLogger(__name__)

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS = {"sub": os.getenv("VAPID_CLAIM_EMAIL", "mailto:admin@seda24.de")}


def send_to_employee(db: Session, employee_id: int, notification_type: str,
                     title: str, body: str, data: dict = None,
                     schedule_id: int = None) -> PushNotification:
    """Sendet Push an einen Mitarbeiter ueber seinen bevorzugten Kanal."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        logger.error(f"Employee {employee_id} nicht gefunden")
        return None

    # PushNotification-Eintrag erstellen
    payload = json.dumps(data) if data else None
    notification = PushNotification(
        employee_id=employee_id,
        notification_type=notification_type,
        title=title,
        body=body,
        payload=payload,
        channel=employee.push_channel or 'browser',
        status='pending',
        schedule_id=schedule_id,
        expires_at=datetime.now() + timedelta(hours=24),
    )
    db.add(notification)
    db.flush()

    # Push-Payload zusammenstellen
    push_data = {
        "type": notification_type,
        "title": title,
        "body": body,
        "notification_id": notification.id,
        "schedule_id": schedule_id,
    }
    if data:
        push_data.update(data)

    channel = employee.push_channel or 'browser'

    if channel in ('browser', 'both'):
        success = _send_browser_push(db, employee_id, push_data)
        if success:
            notification.status = 'sent'
            notification.sent_at = datetime.now()

    if channel in ('telegram', 'both'):
        # Telegram-Integration spaeter
        pass

    if notification.status == 'pending':
        notification.status = 'pending_telegram'
        logger.info(f"Push an Employee {employee_id} wartet auf Telegram-Zustellung")

    db.commit()
    return notification


def _send_browser_push(db: Session, employee_id: int, payload: dict) -> bool:
    """Browser-Push deaktiviert - wird durch Telegram ersetzt."""
    return False
    # --- Alter Code (deaktiviert) ---
    subscriptions = db.query(PushSubscription).filter(
        PushSubscription.employee_id == employee_id,
        PushSubscription.is_active == True
    ).all()

    if not subscriptions:
        logger.info(f"Keine aktiven Push-Subscriptions fuer Employee {employee_id}")
        return False

    success = False
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh_key,
                        "auth": sub.auth_key
                    }
                },
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            sub.last_used_at = datetime.now()
            success = True
            logger.info(f"Push gesendet an Employee {employee_id} (Sub {sub.id})")
        except WebPushException as e:
            logger.error(f"WebPush-Fehler fuer Sub {sub.id}: {e}")
            if e.response and e.response.status_code in (404, 410):
                # Subscription abgelaufen - sofort deaktivieren und flushen
                sub.is_active = False
                db.flush()
                logger.info(f"Subscription {sub.id} deaktiviert (Status {e.response.status_code})")
        except Exception as e:
            logger.error(f"Push-Fehler fuer Sub {sub.id}: {e}")

    return success


def send_shift_confirmation(db: Session, employee_id: int, schedule_id: int):
    """S1: Push nach Schichtende - Bestaetigung anfordern."""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        return None

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        return None

    obj_name = schedule.object.name if schedule.object else "Unbekannt"
    start_str = schedule.start_time.strftime("%H:%M") if schedule.start_time else ""
    end_str = schedule.end_time.strftime("%H:%M") if schedule.end_time else ""

    title = "Schicht beendet"
    body = f"Deine Schicht bei {obj_name} ({start_str}-{end_str}) ist beendet. Alles korrekt?"

    data = {
        "object_name": obj_name,
        "start_time": start_str,
        "end_time": end_str,
        "planned_hours": schedule.planned_hours,
        "date": str(schedule.date),
    }

    return send_to_employee(
        db, employee_id, 'shift_confirm', title, body, data, schedule_id
    )


def send_monthly_confirmation_request(db: Session, employee_id: int,
                                       year: int, month: int):
    """S9: Monatsbestaetigung anfordern."""
    MONATSNAMEN = [
        "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ]
    monat = MONATSNAMEN[month] if 1 <= month <= 12 else str(month)

    title = "Monatsbestaetigung"
    body = f"Bitte pruefe und bestaetige deine Buchungen fuer {monat} {year}."
    data = {"year": year, "month": month}

    return send_to_employee(
        db, employee_id, 'monthly_confirm', title, body, data
    )


def check_and_send_reminders(db: Session):
    """
    Erinnerungen fuer unbearbeitete Pushes pruefen.
    Nur im Fenster 09:00-21:00.

    HINWEIS: Tatsaechliche Telegram-Erinnerungen werden von
    send_telegram_reminders() in telegram_bot.py gesendet (Job 6).
    Diese Funktion markiert nur Notifications als erledigt,
    wenn bereits ein TimeEntry existiert.
    """
    from app.models.models import TimeEntry

    now = datetime.now()
    if now.hour < 9 or now.hour >= 21:
        return

    pending = db.query(PushNotification).filter(
        PushNotification.status.in_(['sent', 'pending_telegram']),
        PushNotification.response_status.is_(None),
        PushNotification.expires_at > now,
        PushNotification.notification_type == 'shift_confirm',
    ).all()

    for notif in pending:
        # Pruefe ob Schicht schon gebucht wurde
        if notif.schedule_id:
            existing_entry = db.query(TimeEntry).filter(
                TimeEntry.schedule_id == notif.schedule_id,
            ).first()
            if existing_entry:
                notif.status = 'responded'
                notif.response_status = 'confirmed'
                notif.responded_at = now
                logger.info(f"check_and_send_reminders: Notification {notif.id} als erledigt markiert "
                           f"(TimeEntry {existing_entry.id} existiert)")

    db.commit()


def expire_old_notifications(db: Session):
    """24h abgelaufene Pushes markieren und Admin informieren."""
    now = datetime.now()
    expired = db.query(PushNotification).filter(
        PushNotification.status.in_(['pending', 'sent']),
        PushNotification.response_status.is_(None),
        PushNotification.expires_at <= now,
        PushNotification.notification_type == 'shift_confirm',
    ).all()

    for notif in expired:
        notif.status = 'expired'
        logger.info(f"Push {notif.id} fuer Employee {notif.employee_id} abgelaufen")

    if expired:
        db.commit()
