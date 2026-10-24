from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import os
import random
import secrets
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

from app.db.database import get_db
from app.models.models import User, Employee, PasswordResetToken
from app.schemas import user_schema as schemas
from app.core.security import verify_password, get_password_hash, create_access_token, get_current_user
from app.models.models import Schedule

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# In-Memory Store fuer Passwort-Reset Codes {email: {"code": "847291", "expires": datetime}}
_password_reset_codes = {}

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    db_user = User(email=user.email, password_hash=hashed_password, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login", response_model=schemas.Token)
def login(user_credentials: schemas.UserLogin, request: Request, db: Session = Depends(get_db)):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    user = db.query(User).filter(User.email == user_credentials.email).first()
    if not user or not verify_password(user_credentials.password, user.password_hash):
        logger.warning(f"Login fehlgeschlagen: email={user_credentials.email}, ip={ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    access_token = create_access_token(data={"sub": user.email})
    user_name = f"{employee.first_name} {employee.last_name}" if employee else user.email.split('@')[0]
    personal_nr = employee.personal_nr if employee else "N/A"

    logger.info(f"Login erfolgreich: email={user.email}, name={user_name}, personal_nr={personal_nr}, role={user.role.value}, ip={ip}")

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_name": user_name,
        "personal_nr": personal_nr,
        "must_change_password": user.must_change_password,
        "role": user.role
    }


# get_current_user Funktion bleibt wie sie war
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token ungültig",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    
    return user

@router.get("/time-entries/my-objects-this-week")
async def get_my_scheduled_objects_this_week(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Gibt alle geplanten Objekte für den aktuellen Mitarbeiter für heute zurück.
    """
    # Hole Employee über User
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []
    
    # Aktueller Wochentag
    today = datetime.now().date()
    
    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.date == today
    ).all()
    
    return schedules if schedules else []

@router.post("/change-password")
def change_password(
    new_password_data: schemas.NewPassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Wenn old_password mitgeschickt: pruefen (Self-Service Aenderung)
    if new_password_data.old_password:
        if not verify_password(new_password_data.old_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Altes Passwort ist falsch")

    hashed_password = get_password_hash(new_password_data.new_password)
    current_user.password_hash = hashed_password
    current_user.must_change_password = False

    db.add(current_user)
    db.commit()
    return {"status": "ok", "message": "Passwort wurde geaendert"}


@router.post("/request-password-reset")
def request_password_reset(
    data: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Sendet einen 6-stelligen Reset-Code per Telegram."""
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="E-Mail nicht gefunden")

    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    chat_id = employee.telegram_chat_id
    if not chat_id or str(chat_id) == '0':
        raise HTTPException(
            status_code=400,
            detail="Kein Telegram verknuepft. Bitte Admin kontaktieren."
        )

    code = str(random.randint(100000, 999999))
    _password_reset_codes[data.email] = {
        "code": code,
        "expires": datetime.now() + timedelta(minutes=15),
    }

    try:
        from app.services.telegram_bot import send_message_sync
        send_message_sync(
            int(chat_id),
            f"🔐 <b>Passwort-Reset Code</b>\n\n"
            f"Dein Code: <code>{code}</code>\n\n"
            f"Gib diesen Code auf der Login-Seite ein.\n"
            f"Gueltig fuer 15 Minuten."
        )
    except Exception as e:
        logger.error(f"Telegram Reset-Code Versand fehlgeschlagen: {e}")
        raise HTTPException(status_code=500, detail="Telegram-Nachricht konnte nicht gesendet werden")

    logger.info(f"Password reset code sent to {data.email}")
    return {"status": "ok", "message": "Code wurde per Telegram gesendet"}


@router.post("/reset-password")
def reset_password(
    data: schemas.PasswordReset,
    db: Session = Depends(get_db)
):
    """Setzt Passwort mit gueltigem Reset-Code zurueck."""
    stored = _password_reset_codes.get(data.email)
    if not stored:
        raise HTTPException(status_code=400, detail="Kein Reset-Code angefordert")

    if datetime.now() > stored["expires"]:
        del _password_reset_codes[data.email]
        raise HTTPException(status_code=400, detail="Code abgelaufen. Bitte neuen Code anfordern.")

    if stored["code"] != data.code:
        raise HTTPException(status_code=400, detail="Falscher Code")

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.password_hash = get_password_hash(data.new_password)
    user.must_change_password = False
    db.add(user)
    db.commit()

    del _password_reset_codes[data.email]
    logger.info(f"Password reset successful for {data.email}")
    return {"status": "ok", "message": "Passwort wurde zurueckgesetzt"}


@router.post("/request-password-reset-email")
def request_password_reset_email(
    data: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Sendet einen Reset-Link per E-Mail (60 Min gueltig)."""
    # Immer gleiche Antwort, egal ob E-Mail existiert (Sicherheit)
    success_msg = {"status": "ok", "message": "Falls die Adresse bekannt ist, wurde eine E-Mail verschickt."}

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        logger.info(f"Password reset requested for unknown email: {data.email}")
        return success_msg

    # Alte unbenutzte Tokens fuer diesen User invalidieren
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False
    ).update({"used": True})

    # Neuen Token generieren
    token = secrets.token_urlsafe(48)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=datetime.now() + timedelta(minutes=60),
    )
    db.add(reset_token)
    db.commit()

    # Reset-Link bauen
    base_url = os.getenv("FRONTEND_URL", "https://app.seda.de")
    reset_link = f"{base_url}/reset-password/{token}"

    # E-Mail senden
    from app.core.email_service import EmailService
    sent = EmailService.send_password_reset_email(user.email, reset_link)
    if not sent:
        logger.error(f"Password reset email could not be sent to {data.email}")

    logger.info(f"Password reset email requested for {data.email}")
    return success_msg


@router.post("/reset-password-by-token")
def reset_password_by_token(
    data: schemas.PasswordResetByToken,
    db: Session = Depends(get_db)
):
    """Setzt Passwort mit gueltigem E-Mail-Token zurueck."""
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == data.token,
        PasswordResetToken.used == False,
    ).first()

    if not reset_token:
        raise HTTPException(status_code=400, detail="Ungueltiger oder bereits verwendeter Link.")

    if datetime.now() > reset_token.expires_at:
        reset_token.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Link abgelaufen. Bitte fordere einen neuen an.")

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    user.password_hash = get_password_hash(data.new_password)
    user.must_change_password = False
    reset_token.used = True

    db.add(user)
    db.commit()

    logger.info(f"Password reset by email token successful for user {user.email}")
    return {"status": "ok", "message": "Passwort wurde erfolgreich zurueckgesetzt."}


@router.get("/verify-reset-token/{token}")
def verify_reset_token(token: str, db: Session = Depends(get_db)):
    """Prueft ob ein Reset-Token gueltig ist (fuer Frontend-Validierung)."""
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.used == False,
    ).first()

    if not reset_token or datetime.now() > reset_token.expires_at:
        raise HTTPException(status_code=400, detail="Link ungueltig oder abgelaufen.")

    return {"status": "ok", "valid": True}

