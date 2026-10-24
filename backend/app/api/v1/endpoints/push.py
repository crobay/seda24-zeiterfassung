"""
Push-Notification-Endpoints fuer SEDA24 V3.0
- Browser Push Subscription Management
- Push Response Handling
- Pending Notifications Query
"""
import os
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.security import get_current_active_user
from app.models.models import (
    User, Employee, PushSubscription, PushNotification
)
from app.services import push_service

router = APIRouter()


def get_employee_for_user(db: Session, user: User) -> Employee:
    """Hilfsfunktion: Employee fuer den aktuellen User finden."""
    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    return employee


@router.get("/vapid-public-key")
def get_vapid_public_key():
    """VAPID Public Key fuer Frontend Push-Subscription."""
    public_key = os.getenv("VAPID_PUBLIC_KEY", "")
    if not public_key:
        raise HTTPException(status_code=500, detail="VAPID Key nicht konfiguriert")
    return {"public_key": public_key}


@router.post("/subscribe")
def subscribe_push(
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Browser-Push-Subscription registrieren."""
    employee = get_employee_for_user(db, current_user)

    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not all([endpoint, p256dh, auth]):
        raise HTTPException(status_code=400, detail="Unvollstaendige Subscription-Daten")

    user_agent = data.get("user_agent", "")

    # Bestehende Subscription mit gleichem Endpoint aktualisieren
    existing = db.query(PushSubscription).filter(
        PushSubscription.employee_id == employee.id,
        PushSubscription.endpoint == endpoint
    ).first()

    if existing:
        existing.p256dh_key = p256dh
        existing.auth_key = auth
        existing.is_active = True
        existing.user_agent = user_agent
        existing.last_used_at = datetime.now()
    else:
        # Alte Subscriptions vom gleichen Geraet deaktivieren (gleicher user_agent)
        if user_agent:
            old_subs = db.query(PushSubscription).filter(
                PushSubscription.employee_id == employee.id,
                PushSubscription.user_agent == user_agent,
                PushSubscription.is_active == True,
                PushSubscription.endpoint != endpoint,
            ).all()
            for old in old_subs:
                old.is_active = False

        sub = PushSubscription(
            employee_id=employee.id,
            endpoint=endpoint,
            p256dh_key=p256dh,
            auth_key=auth,
            user_agent=user_agent,
            is_active=True,
        )
        db.add(sub)

    db.commit()
    return {"status": "subscribed", "device": "mobile" if "Mobile" in user_agent else "desktop"}


@router.delete("/unsubscribe")
def unsubscribe_push(
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Push-Subscription entfernen."""
    employee = get_employee_for_user(db, current_user)
    endpoint = data.get("endpoint")

    if endpoint:
        sub = db.query(PushSubscription).filter(
            PushSubscription.employee_id == employee.id,
            PushSubscription.endpoint == endpoint
        ).first()
        if sub:
            sub.is_active = False
            db.commit()

    return {"status": "unsubscribed"}


@router.get("/pending")
def get_pending_notifications(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Offene Benachrichtigungen fuer den aktuellen Mitarbeiter."""
    employee = get_employee_for_user(db, current_user)

    notifications = db.query(PushNotification).filter(
        PushNotification.employee_id == employee.id,
        PushNotification.status.in_(['pending', 'sent', 'failed']),
        PushNotification.response_status.is_(None),
        PushNotification.notification_type.in_(['shift_confirm', 'monthly_confirm', 'correction_request']),
    ).order_by(PushNotification.created_at.desc()).all()

    result = []
    for n in notifications:
        item = {
            "id": n.id,
            "type": n.notification_type,
            "title": n.title,
            "body": n.body,
            "schedule_id": n.schedule_id,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "expires_at": n.expires_at.isoformat() if n.expires_at else None,
        }
        if n.payload:
            try:
                item["data"] = json.loads(n.payload)
            except json.JSONDecodeError:
                item["data"] = {}
        result.append(item)

    return result


@router.post("/respond/{notification_id}")
def respond_to_push(
    notification_id: int,
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Auf eine Push-Nachricht antworten.
    data.response: "confirmed" | "not_present" | "correction"
    data.reason: Optional (fuer not_present)
    data.correction_type: Optional (fuer correction)
    """
    employee = get_employee_for_user(db, current_user)

    notification = db.query(PushNotification).filter(
        PushNotification.id == notification_id,
        PushNotification.employee_id == employee.id,
    ).first()

    if not notification:
        raise HTTPException(status_code=404, detail="Benachrichtigung nicht gefunden")

    if notification.response_status:
        raise HTTPException(status_code=400, detail="Bereits beantwortet")

    response = data.get("response")
    if response not in ("confirmed", "not_present", "correction"):
        raise HTTPException(status_code=400, detail="Ungueltiger Response-Typ")

    # Import hier um zirkulaere Imports zu vermeiden
    from app.services.booking_service import BookingService
    booking_svc = BookingService(db)

    result = booking_svc.process_push_response(notification_id, response, data)
    return result


@router.get("/admin/expired")
def get_expired_notifications(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Admin: Alle abgelaufenen/unbearbeiteten Notifications."""
    if current_user.role.value != 'admin':
        raise HTTPException(status_code=403, detail="Nur fuer Admins")

    expired = db.query(PushNotification).filter(
        PushNotification.status == 'expired',
        PushNotification.response_status.is_(None),
    ).order_by(PushNotification.created_at.desc()).limit(50).all()

    result = []
    for n in expired:
        emp = db.query(Employee).filter(Employee.id == n.employee_id).first()
        result.append({
            "id": n.id,
            "employee_id": n.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "type": n.notification_type,
            "title": n.title,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "expires_at": n.expires_at.isoformat() if n.expires_at else None,
            "schedule_id": n.schedule_id,
        })

    return result
