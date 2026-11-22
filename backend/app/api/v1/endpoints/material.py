"""Materialmeldung (services/material.py). Schalter COCKPIT_MATERIAL=1 (services/features.py).

/api/v1/material/...           MA-App (eigener Login): Objekte heute/morgen, Artikel, melden, eigene Meldungen
/api/v1/cockpit/material/...   Admin + Objektleitung: Liste, Status, Mengen, Foto, Objekt-Einstellung, Mail an Kunden
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.v1.endpoints.admin import verify_admin_or_objektleiter
from app.api.v1.endpoints.auth import get_current_user
from app.db.database import get_db
from app.models.models import Employee, User
from app.services import material as mat

router = APIRouter()           # MA-App
cockpit_router = APIRouter()   # Cockpit


def _fehler(e):
    if isinstance(e, LookupError):
        raise HTTPException(404, str(e).strip("'\""))
    raise HTTPException(400, str(e))


def _mitarbeiter(db, user):
    e = db.query(Employee).filter(Employee.user_id == user.id, Employee.is_active == True).first()  # noqa: E712
    if not e:
        raise HTTPException(403, "Kein Mitarbeiter-Konto")
    return e


# ------------------------------------------------------------------ MA-App

@router.get("/meine")
def meine(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Objekte mit Dienst heute/morgen (mit Artikelliste) + eigene Meldungen der letzten 30 Tage."""
    e = _mitarbeiter(db, user)
    o = mat.ma_objekte(db, e.id)
    for x in o["objekte"]:
        x["artikel"] = [{"id": a["id"], "name": a["name"], "einheit": a["einheit"]} for a in mat.artikel(db, x["object_id"])]
    r = {**o, "meldungen": mat.ma_meldungen(db, e.id), "sonstiges_max": mat.SONSTIGES_MAX, "menge_max": mat.MENGE_MAX}
    db.commit()
    return r


@router.post("/meldung")
def melden(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    e = _mitarbeiter(db, user)
    try:
        m = mat.melden(db, e.id, int(data.get("object_id") or 0), data.get("positionen") or [],
                       data.get("sonstiges") or "", data.get("foto"))
    except (ValueError, LookupError) as x:
        db.rollback()
        _fehler(x)
    return {k: m[k] for k in ("id", "objekt", "erstellt_am", "status", "status_ma", "positionen", "sonstiges", "foto")}


# ------------------------------------------------------------------ Cockpit

@cockpit_router.get("/meldungen")
def meldungen(alle: bool = False, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    r = mat.liste(db, nur_offen=not alle)
    r["mail"] = {**mat.mail_einstellungen(db), "echt_erlaubt": mat.echt_erlaubt()}
    from app.services import lohnversand as lv
    r["mail"]["weg_test"] = lv.weg(True)
    db.commit()
    return r


@cockpit_router.put("/meldungen/{mid}/status")
def status(mid: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return mat.status_setzen(db, mid, data.get("status"), user.id)
    except (ValueError, LookupError) as x:
        db.rollback()
        _fehler(x)


@cockpit_router.put("/meldungen/{mid}/mengen")
def mengen(mid: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return mat.mengen_aendern(db, mid, data.get("positionen") or [], user.id)
    except (ValueError, LookupError) as x:
        db.rollback()
        _fehler(x)


@cockpit_router.get("/meldungen/{mid}/foto")
def foto(mid: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        b, typ = mat.foto(db, mid)
    except LookupError as x:
        _fehler(x)
    return Response(b, media_type=typ, headers={"Cache-Control": "private, no-store"})


@cockpit_router.post("/meldungen/{mid}/an-kunden")
def an_kunden(mid: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return mat.an_kunden_senden(db, mid, user.id)
    except (ValueError, LookupError) as x:
        db.rollback()
        _fehler(x)
    except Exception as x:
        db.rollback()
        raise HTTPException(502, f"Mail konnte nicht gesendet werden: {type(x).__name__} {str(x)[:150]}")


@cockpit_router.get("/meldungen/{mid}/testmail.eml")
def testmail(mid: int, user=Depends(verify_admin_or_objektleiter)):
    try:
        b, name = mat.testmail(mid)
    except LookupError as x:
        _fehler(x)
    return Response(b, media_type="message/rfc822", headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                               "Cache-Control": "private, no-store"})


@cockpit_router.get("/objekte/{object_id}")
def objekt(object_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    r = {"einstellung": mat.einstellung(db, object_id), "artikel": mat.artikel(db, object_id), "vorlage": mat.VORLAGE}
    db.commit()
    return r


@cockpit_router.put("/objekte/{object_id}/einstellung")
def objekt_einstellung(object_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return mat.einstellung_speichern(db, object_id, data, user.id)
    except ValueError as x:
        db.rollback()
        _fehler(x)


@cockpit_router.put("/objekte/{object_id}/artikel")
def objekt_artikel(object_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return {"artikel": mat.artikel_speichern(db, object_id, data.get("artikel"), user.id)}
    except ValueError as x:
        db.rollback()
        _fehler(x)


@cockpit_router.put("/mail-einstellungen")
def mail_einstellungen(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return mat.mail_einstellungen_speichern(db, data, user.id)
    except ValueError as x:
        db.rollback()
        _fehler(x)
