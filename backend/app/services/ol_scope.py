"""Rechte der Objektleitung (Betriebsleitung).

Objektleitung = Admin-Rechte minus Kunden-Umsaetze. Sie sieht und bearbeitet alle Objekte, Mitarbeiter,
Dienstplan, Journal, Abrechnung und Einstellungen. Gesperrt (403) sind nur die Kunden-Umsaetze und die
BWA, weil die BWA den Umsatz je Objekt aus denselben Daten zeigt.

ol_guard() haengt als Router-Abhaengigkeit an /api/v1/admin und erzwingt die Sperre im Backend.
"""
import re

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db

MANAGER_ROLES = ("admin", "objektleiter")
FORBIDDEN_UMSATZ = "Kein Zugriff: Kunden-Umsaetze nur fuer Administration"
# Pfade unter /api/v1/admin, die Kunden-Umsaetze enthalten
_UMSATZ_PATHS = re.compile(r"^/api/v1/admin/(customer-revenues|bwa)(/|$)")


def role_of(user) -> str:
    r = user.role
    return (r.value if hasattr(r, "value") else str(r)).lower()


def is_admin(user) -> bool:
    return role_of(user) == "admin"


def is_manager(user) -> bool:
    """Admin oder Objektleitung (volle Verwaltungsrechte)."""
    return role_of(user) in MANAGER_ROLES


def can_see_revenue(user) -> bool:
    return is_admin(user)


def rights(user) -> dict:
    from app.services import features
    return {"verwalten": is_manager(user), "kunden_umsaetze": can_see_revenue(user),
            "abschluss": _ist_admin(user) and features.an("ABSCHLUSS"), "objekt_logo": features.an("OBJEKT_LOGO"),
            "material": is_manager(user) and features.an("MATERIAL"),
            "terminal": is_manager(user) and features.an("TERMINAL")}


def require_revenue(user):
    if not can_see_revenue(user):
        raise HTTPException(status_code=403, detail=FORBIDDEN_UMSATZ)


# Sichtbereich: Admin und Objektleitung sehen alles (None = keine Einschraenkung).
def scope_object_ids(db: Session, user):
    return None


def scope_employee_ids(db: Session, user, obj_ids=None):
    return None


def require_object(db: Session, user, object_id):
    return None


def require_employee(db: Session, user, employee_id):
    return None


def _current_user(request: Request, db: Session):
    from jose import jwt, JWTError
    import os
    from app.models.models import User
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:], os.getenv("SECRET_KEY"), algorithms=["HS256"])
    except JWTError:
        return None
    return db.query(User).filter(User.email == payload.get("sub")).first()


async def ol_guard(request: Request, db: Session = Depends(get_db)):
    """Kunden-Umsaetze/BWA fuer alle ausser Admin sperren (403)."""
    if not _UMSATZ_PATHS.match(request.url.path):
        return
    user = _current_user(request, db)
    if user is not None and not can_see_revenue(user):
        raise HTTPException(status_code=403, detail=FORBIDDEN_UMSATZ)


def _ist_admin(user) -> bool:
    r = getattr(user, "role", None)
    return (r.value if hasattr(r, "value") else str(r or "")).lower() == "admin"
