"""Sichtbereich der Objektleitung.

Admin sieht alles (None = keine Einschraenkung). Objektleitung sieht nur die Objekte aus
user_object_assignments (aktiv) und die Mitarbeiter dieser Objekte: aktive MA-Objekt-Zuweisung
oder Schicht an einem dieser Objekte im Fenster heute-45 .. heute+60 Tage.
Ohne zugewiesene Objekte sieht die Objektleitung nichts (sichere Voreinstellung).

ol_guard() haengt als Router-Abhaengigkeit an den alten Admin-Endpunkten: Fuer die Objektleitung
werden IDs aus Pfad und JSON-Body geprueft; fremde Objekte/MA/Schichten/Buchungen -> 403.
"""
import json
from datetime import date, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.database import get_db

FORBIDDEN = "Kein Zugriff: gehoert nicht zu Ihren Objekten"


def role_of(user) -> str:
    r = user.role
    return (r.value if hasattr(r, "value") else str(r)).lower()


def is_admin(user) -> bool:
    return role_of(user) == "admin"


def scope_object_ids(db: Session, user):
    if is_admin(user):
        return None
    rows = db.execute(text("""SELECT object_id FROM user_object_assignments
                              WHERE user_id = :u AND coalesce(is_active, true)"""), {"u": user.id}).fetchall()
    return {r[0] for r in rows}


def scope_employee_ids(db: Session, user, obj_ids=None):
    if is_admin(user):
        return None
    if obj_ids is None:
        obj_ids = scope_object_ids(db, user)
    if not obj_ids:
        return set()
    today = date.today()
    rows = db.execute(text("""
        SELECT employee_id FROM employee_object_assignments
         WHERE object_id = ANY(:o) AND coalesce(is_active, true)
        UNION
        SELECT employee_id FROM schedules
         WHERE object_id = ANY(:o) AND date BETWEEN :a AND :b"""),
        {"o": list(obj_ids), "a": today - timedelta(days=45), "b": today + timedelta(days=60)}).fetchall()
    return {r[0] for r in rows if r[0] is not None}


def require_object(db: Session, user, object_id):
    ids = scope_object_ids(db, user)
    if ids is not None and (object_id is None or int(object_id) not in ids):
        raise HTTPException(status_code=403, detail=FORBIDDEN)


def require_employee(db: Session, user, employee_id):
    ids = scope_employee_ids(db, user)
    if ids is not None and (employee_id is None or int(employee_id) not in ids):
        raise HTTPException(status_code=403, detail=FORBIDDEN)


# Pfad-Segment -> SQL, das (employee_id, object_id) des Datensatzes liefert
_PATH_LOOKUP = {
    "schedules": "SELECT employee_id, object_id FROM schedules WHERE id = :i",
    "schedule": "SELECT employee_id, object_id FROM schedules WHERE id = :i",
    "bookings": "SELECT employee_id, object_id FROM time_entries WHERE id = :i",
    "pending-bookings": "SELECT employee_id, object_id FROM pending_bookings WHERE id = :i",
    "assignments": "SELECT employee_id, object_id FROM employee_object_assignments WHERE id = :i",
    "km-distances": "SELECT employee_id, object_id FROM km_distances WHERE id = :i",
    "km-journal": "SELECT employee_id, object_id FROM km_daily_entries WHERE id = :i",
    "shift-requests": "SELECT employee_id, NULL FROM shift_change_requests WHERE id = :i",
    "requests": "SELECT employee_id, NULL FROM vacation_requests WHERE id = :i",
    "employees": "SELECT :i, NULL",
    "objects": "SELECT NULL, :i",
}
_BODY_KEYS = {"employee_id": "e", "object_id": "o", "new_employee_id": "e", "swap_employee_id": "e",
              "replacement_employee_id": "e"}


def _walk(node, found):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _BODY_KEYS and isinstance(v, (int, str)) and str(v).isdigit():
                found.append((_BODY_KEYS[k], int(v)))
            elif k in ("employee_ids", "object_ids") and isinstance(v, list):
                found += [(k[0], int(x)) for x in v if str(x).isdigit()]
            else:
                _walk(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk(v, found)


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
    """Fuer Objektleitung: IDs in Pfad und Body gegen den Sichtbereich pruefen (403)."""
    user = _current_user(request, db)
    if user is None or role_of(user) != "objektleiter":
        return  # Admin/MA/ungueltig: eigene Pruefung der Endpunkte greift
    obj_ids = scope_object_ids(db, user)
    emp_ids = scope_employee_ids(db, user, obj_ids)

    def check(kind, val):
        if val is None:
            return
        if (kind == "o" and val not in obj_ids) or (kind == "e" and val not in emp_ids):
            raise HTTPException(status_code=403, detail=FORBIDDEN)

    parts = [p for p in request.url.path.split("/") if p]
    for i, seg in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if seg in _PATH_LOOKUP and nxt.isdigit():
            row = db.execute(text(_PATH_LOOKUP[seg]), {"i": int(nxt)}).fetchone()
            if row:
                check("e", row[0])
                check("o", row[1])
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except ValueError:
                body = None
            found = []
            _walk(body, found)
            for kind, val in found:
                check(kind, val)
