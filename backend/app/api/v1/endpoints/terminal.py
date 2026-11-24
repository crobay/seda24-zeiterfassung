"""Terminal-Modus (services/terminal.py). Schalter COCKPIT_TERMINAL=1 (services/features.py).

/api/v1/terminal/...            Tablet: Kopfzeile X-Terminal-Token (Registrierung: Admin/OL-Login)
/api/v1/cockpit/terminal/...    Cockpit: Terminals ansehen/widerrufen, PINs je MA setzen
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.endpoints.admin import verify_admin_or_objektleiter
from app.api.v1.endpoints.time_entries import check_in, check_out, get_client_ip
from app.db.database import get_db
from app.models.models import User
from app.services import terminal as tm
from app.services.bie2_logger import log_bie2

router = APIRouter()           # Tablet
cockpit_router = APIRouter()   # Cockpit


def _fehler(e):
    if isinstance(e, LookupError):
        raise HTTPException(404, str(e).strip("'\""))
    raise HTTPException(400, str(e))


def _geraet(request: Request, x_terminal_token: str = Header(None), db: Session = Depends(get_db)):
    g = tm.geraet(db, x_terminal_token, get_client_ip(request))
    if not g:
        raise HTTPException(401, "Terminal nicht (mehr) registriert")
    return g


# ------------------------------------------------------------------ Tablet

@router.get("/objekte")
def objekte(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """Objektauswahl bei der Einrichtung (Test-Objekte am Ende, fuer Probe-Terminals)."""
    return {"objekte": tm.objekte(db)}


@router.post("/registrieren")
def registrieren(data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return tm.registrieren(db, int(data.get("object_id") or 0), data.get("name"), user.id)
    except (ValueError, LookupError) as x:
        db.rollback()
        _fehler(x)


@router.get("/start")
def start(g=Depends(_geraet), db: Session = Depends(get_db)):
    return tm.start(db, g)


@router.get("/suche")
def suche(q: str = "", g=Depends(_geraet), db: Session = Depends(get_db)):
    return {"treffer": tm.suche(db, g, q)}


@router.post("/pin")
def pin(data: dict, g=Depends(_geraet), db: Session = Depends(get_db)):
    """PIN pruefen -> Stempel-Schein (90 Sek) + was der grosse Knopf anbietet (kommen/gehen)."""
    eid = int(data.get("employee_id") or 0)
    ma = tm.mitarbeiter(db, g, eid)
    if not ma:
        raise HTTPException(404, "Mitarbeiter nicht gefunden")
    try:
        ok = tm.pin_pruefen(db, g, eid, data.get("pin"))
    except (ValueError, LookupError) as x:
        _fehler(x)
    if not ok:
        raise HTTPException(403, "PIN falsch – bitte noch einmal")
    st = tm.status(db, eid)
    return {"schein": tm.schein(g["id"], eid), "gueltig_sek": tm.SCHEIN_SEK,
            "name": f"{ma['first_name']} {ma['last_name']}", "vorname": ma["first_name"],
            "aktion": "gehen" if st else "kommen",
            "da_seit": st["check_in"].strftime("%H:%M") if st else None,
            "da_objekt": st["objekt"] if st and st["object_id"] != g["object_id"] else None,
            "auto": tm.ist_auto(db, eid, g["object_id"])}


@router.post("/stempeln")
async def stempeln(data: dict, request: Request, g=Depends(_geraet), db: Session = Depends(get_db)):
    """Kommen/Gehen mit Server-Uhrzeit ueber die normale Stempel-Logik; Buchung bekommt quelle='terminal'."""
    eid = tm.schein_pruefen(data.get("schein"), g["id"])
    if not eid:
        raise HTTPException(401, "Zeit abgelaufen – bitte Namen und PIN noch einmal")
    ma = tm.mitarbeiter(db, g, eid)
    user = db.query(User).filter(User.id == ma["user_id"]).first() if ma else None
    if not user:
        raise HTTPException(404, "Mitarbeiter nicht gefunden")
    aktion = data.get("aktion")
    st = tm.status(db, eid)
    if aktion == "kommen" and st and st["object_id"] == g["object_id"]:
        raise HTTPException(409, f"Du bist hier schon eingestempelt seit {st['check_in']:%H:%M}")
    if aktion == "gehen" and not st:
        raise HTTPException(409, "Du bist nicht eingestempelt")
    if aktion not in ("kommen", "gehen"):
        raise HTTPException(400, "Kommen oder Gehen?")
    if aktion == "kommen" and tm.ist_auto(db, eid, g["object_id"]):
        raise HTTPException(409, "Du wirst hier automatisch gebucht – Stempeln ist nicht nötig")

    ip = get_client_ip(request)
    name = f"{ma['first_name']} {ma['last_name']}"
    # Kein client_timestamp / client_id: Server-Uhrzeit zaehlt, nichts wird nachgereicht
    if aktion == "kommen":
        e = await check_in({"object_id": g["object_id"]}, db, user, client_ip=ip)
        entry_id, zeit = e.id, e.check_in
    else:
        r = check_out(request, {}, user, db)
        r = jsonable_encoder(r)
        entry_id, zeit = r["id"], datetime.fromisoformat(r["check_out"])
    db.execute(text("UPDATE time_entries SET quelle = 'terminal' WHERE id = :i"), {"i": entry_id})
    from app.services.booking_service import log_audit
    log_audit(db, user.id, eid, f"terminal_{aktion}", entity_type="time_entry", entity_id=entry_id,
              details=f"{'Kommen' if aktion == 'kommen' else 'Gehen'} {zeit:%d.%m. %H:%M} am Terminal '{g['name']}' "
                      f"({g['objekt']}, IP {ip})")
    db.commit()
    log_bie2("TERMINAL", name, g["objekt"], f"{aktion.upper()} {zeit:%H:%M:%S} Eintrag={entry_id} Terminal={g['id']}")
    return {"ok": True, "aktion": aktion, "zeit": zeit.strftime("%H:%M"), "name": name, "vorname": ma["first_name"],
            "entry_id": entry_id, "objekt": g["objekt"]}


# ------------------------------------------------------------------ Cockpit

@cockpit_router.get("")
def uebersicht(db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    return {"geraete": tm.geraete(db), "pins": tm.pins(db)}


@cockpit_router.delete("/geraete/{gid}")
def widerrufen(gid: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    try:
        return tm.widerrufen(db, gid, user.id)
    except LookupError as x:
        _fehler(x)


@cockpit_router.put("/pins/{employee_id}")
def pin_setzen(employee_id: int, data: dict, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    """{pin: '4711'} setzt die PIN, {zufall: true} erzeugt eine (wird einmal angezeigt)."""
    try:
        return tm.pin_setzen(db, employee_id, None if data.get("zufall") else data.get("pin"), user.id)
    except (ValueError, LookupError) as x:
        db.rollback()
        _fehler(x)


@cockpit_router.delete("/pins/{employee_id}")
def pin_loeschen(employee_id: int, db: Session = Depends(get_db), user=Depends(verify_admin_or_objektleiter)):
    return tm.pin_loeschen(db, employee_id, user.id)
