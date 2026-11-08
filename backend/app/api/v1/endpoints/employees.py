from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.database import get_db
from app.models.models import User
from app.core.security import get_current_user

router = APIRouter()

@router.get("/my-category")
def get_my_category(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = text("""
        SELECT e.id, e.personal_nr, e.first_name, e.last_name, e.tracking_mode, e.gps_required
        FROM employees e
        WHERE e.user_id = :user_id
    """)
    
    result = db.execute(query, {"user_id": current_user.id}).fetchone()
    
    if not result:
        return {
            "id": 0,
            "name": "Mitarbeiter",
            "personal_nr": "-",
            "tracking_mode": "C",
            "gps_required": False,
            "has_c_assignments": False,
        }

    # Prüfe ob MA C-Zuweisungen hat
    c_count_query = text("""
        SELECT COUNT(*) FROM employee_object_assignments
        WHERE employee_id = :emp_id AND tracking_category = 'C' AND is_active = true
    """)
    c_count = db.execute(c_count_query, {"emp_id": result[0]}).scalar() or 0

    # Festgehalt (ab gueltig_ab): Kategorie A sieht die Stempeluhr (Button) - Stempeln erlaubt,
    # aber nicht lohnrelevant. In der DB bleibt Kategorie A (keine Erinnerungen).
    mode = result[4] if result[4] else "C"
    if mode == "A":
        from datetime import date as _date
        from app.services import festgehalt
        if festgehalt.active_on(db, result[0], _date.today()):
            mode = "B"

    return {
        "id": result[0],
        "name": f"{result[2]} {result[3]}",
        "personal_nr": result[1],
        "tracking_mode": mode,
        "gps_required": bool(result[5]) if result[5] else False,
        "has_c_assignments": c_count > 0,
    }

@router.get("/my-colleagues-today")
def get_my_colleagues_today(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kollegen-Feature deaktiviert für v1.0"""
    return []


TELEGRAM_BOT_USERNAME = "seda24zeitbot"
TELEGRAM_LINK_CODE_MINUTES = 15
_LINK_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


@router.post("/telegram-link-code")
def create_telegram_link_code(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Einmal-Code fuer die Telegram-Verknuepfung (15 Min gueltig, einmal verwendbar).
    Der Bot verknuepft nur per /start <code> - nicht mehr per Personalnummer."""
    import secrets
    from datetime import datetime, timedelta
    from fastapi import HTTPException

    emp = db.execute(
        text("SELECT id FROM employees WHERE user_id = :uid AND is_active = true"),
        {"uid": current_user.id}
    ).fetchone()
    if not emp:
        raise HTTPException(status_code=404, detail="Kein aktiver Mitarbeiter zu diesem Login")

    now = datetime.now()
    # Aeltere, noch offene Codes dieses MA ungueltig machen
    db.execute(
        text("UPDATE telegram_link_codes SET expires_at = :now "
             "WHERE employee_id = :emp AND used_at IS NULL AND expires_at > :now"),
        {"emp": emp[0], "now": now}
    )
    code = "".join(secrets.choice(_LINK_CODE_ALPHABET) for _ in range(12))
    expires_at = now + timedelta(minutes=TELEGRAM_LINK_CODE_MINUTES)
    db.execute(
        text("INSERT INTO telegram_link_codes (employee_id, code, expires_at, created_at) "
             "VALUES (:emp, :code, :exp, :now)"),
        {"emp": emp[0], "code": code, "exp": expires_at, "now": now}
    )
    db.commit()
    return {
        "code": code,
        "url": f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={code}",
        "expires_at": expires_at.isoformat(),
        "valid_minutes": TELEGRAM_LINK_CODE_MINUTES,
    }
