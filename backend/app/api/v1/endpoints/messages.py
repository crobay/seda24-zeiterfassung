"""
Nachrichten/Kommunikation Endpoints fuer SEDA24
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.models import User, Employee, Message
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'uploads', 'message_photos'
)


def _get_employee(db: Session, user: User) -> Employee:
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    return emp


def _verify_admin(current_user: User = Depends(get_current_user)):
    if current_user.role.value != 'admin':
        raise HTTPException(status_code=403, detail="Nur Admin")
    return current_user


# ========== MA ENDPOINTS ==========

@router.post("/send")
def send_message(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """MA sendet Nachricht an Verwaltung."""
    emp = _get_employee(db, current_user)

    category = data.get("category", "sonstiges")
    body = data.get("body", "")

    if not body.strip():
        raise HTTPException(status_code=400, detail="Nachricht darf nicht leer sein")

    if category not in ("material", "reklamation", "problem", "sonstiges"):
        category = "sonstiges"

    msg = Message(
        sender_employee_id=emp.id,
        category=category,
        subject=data.get("subject", ""),
        body=body,
        status='neu',
    )
    db.add(msg)
    db.flush()

    # Admin per Telegram benachrichtigen
    try:
        from app.services.telegram_bot import notify_admin
        category_labels = {
            "material": "Material fehlt",
            "reklamation": "Reklamation",
            "problem": "Problem",
            "sonstiges": "Sonstiges",
        }
        cat_label = category_labels.get(category, category)
        emp_name = f"{emp.first_name} {emp.last_name}"
        notify_admin(
            f"\U0001f4e8 <b>NEUE NACHRICHT</b>\n\n"
            f"\U0001f464 {emp_name} ({emp.personal_nr})\n"
            f"\U0001f4cb {cat_label}\n"
            f"\U0001f4dd {body[:200]}"
        )
    except Exception as e:
        logger.error(f"Telegram-Benachrichtigung: {e}")

    db.commit()
    return {"status": "ok", "message_id": msg.id}


@router.post("/send-with-photo")
async def send_message_with_photo(
    category: str = Form("sonstiges"),
    body: str = Form(""),
    subject: str = Form(""),
    photo: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """MA sendet Nachricht mit Foto."""
    emp = _get_employee(db, current_user)

    if not body.strip():
        raise HTTPException(status_code=400, detail="Nachricht darf nicht leer sein")

    photo_path = None
    if photo:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        ext = photo.filename.split('.')[-1] if '.' in photo.filename else 'jpg'
        filename = f"msg_{emp.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        photo_path = os.path.join(UPLOAD_DIR, filename)
        with open(photo_path, "wb") as f:
            content = await photo.read()
            f.write(content)

    msg = Message(
        sender_employee_id=emp.id,
        category=category,
        subject=subject,
        body=body,
        photo_path=photo_path,
        status='neu',
    )
    db.add(msg)
    db.commit()

    try:
        from app.services.telegram_bot import notify_admin
        category_labels = {
            "material": "Material fehlt",
            "reklamation": "Reklamation",
            "problem": "Problem",
            "sonstiges": "Sonstiges",
        }
        cat_label = category_labels.get(category, category)
        emp_name = f"{emp.first_name} {emp.last_name}"
        photo_hint = " (mit Foto)" if photo_path else ""
        notify_admin(
            f"\U0001f4e8 <b>NEUE NACHRICHT{photo_hint}</b>\n\n"
            f"\U0001f464 {emp_name} ({emp.personal_nr})\n"
            f"\U0001f4cb {cat_label}\n"
            f"\U0001f4dd {body[:200]}"
        )
    except Exception as e:
        logger.error(f"Telegram-Benachrichtigung: {e}")

    return {"status": "ok", "message_id": msg.id}


@router.get("/my-messages")
def get_my_messages(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """MA sieht seine Nachrichten + Antworten."""
    emp = _get_employee(db, current_user)

    messages = db.query(Message).filter(
        Message.sender_employee_id == emp.id,
        Message.parent_id.is_(None),
    ).order_by(Message.created_at.desc()).limit(50).all()

    result = []
    for msg in messages:
        # Antworten laden
        replies = db.query(Message).filter(
            Message.parent_id == msg.id,
        ).order_by(Message.created_at.asc()).all()

        result.append({
            "id": msg.id,
            "category": msg.category,
            "subject": msg.subject,
            "body": msg.body,
            "has_photo": bool(msg.photo_path),
            "status": msg.status,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "replies": [{
                "id": r.id,
                "body": r.body,
                "is_admin": bool(r.sender_admin_id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in replies],
        })
    return result


# ========== ADMIN ENDPOINTS ==========

@router.get("/admin/inbox")
def get_admin_inbox(
    status: str = None,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin)
):
    """Admin-Posteingang: Alle MA-Nachrichten."""
    query = db.query(Message).filter(
        Message.sender_employee_id.isnot(None),
        Message.parent_id.is_(None),
    ).order_by(Message.created_at.desc())

    if status:
        query = query.filter(Message.status == status)

    messages = query.limit(100).all()

    result = []
    for msg in messages:
        emp = db.query(Employee).filter(Employee.id == msg.sender_employee_id).first()
        replies_count = db.query(Message).filter(Message.parent_id == msg.id).count()
        result.append({
            "id": msg.id,
            "employee_id": msg.sender_employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
            "personal_nr": emp.personal_nr if emp else "?",
            "category": msg.category,
            "subject": msg.subject,
            "body": msg.body,
            "has_photo": bool(msg.photo_path),
            "status": msg.status,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
            "replies_count": replies_count,
        })
    return result


@router.get("/admin/message/{message_id}")
def get_message_detail(
    message_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin)
):
    """Nachricht-Details mit Antworten."""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")

    # Status auf 'gelesen' setzen
    if msg.status == 'neu':
        msg.status = 'gelesen'
        db.commit()

    emp = db.query(Employee).filter(Employee.id == msg.sender_employee_id).first()

    replies = db.query(Message).filter(
        Message.parent_id == msg.id,
    ).order_by(Message.created_at.asc()).all()

    return {
        "id": msg.id,
        "employee_id": msg.sender_employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "?",
        "personal_nr": emp.personal_nr if emp else "?",
        "category": msg.category,
        "subject": msg.subject,
        "body": msg.body,
        "has_photo": bool(msg.photo_path),
        "status": msg.status,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "replies": [{
            "id": r.id,
            "body": r.body,
            "is_admin": bool(r.sender_admin_id),
            "sender_name": "Admin" if r.sender_admin_id else "Mitarbeiter",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in replies],
    }


@router.get("/admin/message/{message_id}/photo")
def get_message_photo(
    message_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin)
):
    """Nachrichtenfoto herunterladen."""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg or not msg.photo_path:
        raise HTTPException(status_code=404, detail="Kein Foto vorhanden")
    if not os.path.exists(msg.photo_path):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    return FileResponse(msg.photo_path)


@router.post("/admin/reply/{message_id}")
def reply_to_message(
    message_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin)
):
    """Admin antwortet auf MA-Nachricht."""
    original = db.query(Message).filter(Message.id == message_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Nachricht nicht gefunden")

    body = data.get("body", "")
    if not body.strip():
        raise HTTPException(status_code=400, detail="Antwort darf nicht leer sein")

    reply = Message(
        sender_admin_id=admin.id,
        category=original.category,
        body=body,
        parent_id=message_id,
        status='neu',
    )
    db.add(reply)

    # Original auf 'beantwortet' setzen
    original.status = 'beantwortet'

    db.flush()

    # MA per Telegram benachrichtigen
    emp = db.query(Employee).filter(Employee.id == original.sender_employee_id).first()
    if emp and emp.telegram_chat_id:
        try:
            from app.services.telegram_bot import send_message_sync
            send_message_sync(
                emp.telegram_chat_id,
                f"\U0001f4e8 <b>Antwort auf deine Nachricht</b>\n\n"
                f"\U0001f4dd {body[:300]}"
            )
        except Exception as e:
            logger.error(f"Telegram-Antwort: {e}")

    db.commit()
    return {"status": "ok", "reply_id": reply.id}


@router.post("/admin/broadcast")
def send_broadcast(
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(_verify_admin)
):
    """Admin sendet Firmen-Mitteilung an ausgewaehlte MAs."""
    body = data.get("body", "")
    subject = data.get("subject", "Firmen-Mitteilung")
    recipient_ids = data.get("recipient_employee_ids", [])

    if not body.strip():
        raise HTTPException(status_code=400, detail="Nachricht darf nicht leer sein")

    # Wenn keine Empfaenger: An alle aktiven MAs
    if not recipient_ids:
        employees = db.query(Employee).filter(Employee.is_active == True).all()
        recipient_ids = [emp.id for emp in employees if not (emp.personal_nr and emp.personal_nr.startswith('A'))]

    msg = Message(
        sender_admin_id=admin.id,
        category='firmen_mitteilung',
        subject=subject,
        body=body,
        recipient_employee_ids=json.dumps(recipient_ids),
        status='gesendet',
    )
    db.add(msg)
    db.flush()

    # Per Telegram senden
    sent_count = 0
    for emp_id in recipient_ids:
        emp = db.query(Employee).filter(Employee.id == emp_id).first()
        if emp and emp.telegram_chat_id:
            try:
                from app.services.telegram_bot import send_message_sync
                send_message_sync(
                    emp.telegram_chat_id,
                    f"\U0001f4e2 <b>{subject}</b>\n\n{body}"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Broadcast an {emp.first_name}: {e}")

    db.commit()
    return {
        "status": "ok",
        "message_id": msg.id,
        "sent_count": sent_count,
        "total_recipients": len(recipient_ids),
    }
