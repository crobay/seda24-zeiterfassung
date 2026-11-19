"""Super-PIN zum Wieder-Oeffnen eines abgeschlossenen Monats (Drazen 19.11.2026).

- Nur EIN Inhaber (Tabelle superpin, eine Zeile; Inhaber = Admin-Login von Drazen). Aendern des Inhabers und
  Zuruecksetzen nur auf dem Server: tools/superpin_reset.py.
- Eigene PIN, 6-10 Ziffern, nicht das Login-Passwort, bcrypt-gehasht. Erstes Setzen mit dem Login-Passwort, Aendern
  mit der alten PIN.
- Fehlversuche: nach 5 falschen 15 Min. gesperrt, nach 10 (insgesamt, ohne Treffer dazwischen) dauerhaft bis zum
  Zuruecksetzen auf dem Server. Jeder Fehlversuch steht im Aenderungsprotokoll (audit_log).
"""
from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.security import pwd_context

SPERRE_NACH, SPERRE_MIN, DAUERHAFT_NACH = 5, 15, 10


class PinFehler(PermissionError):
    pass


def _zeile(db):
    r = db.execute(text("SELECT * FROM superpin")).mappings().first()
    if not r:
        raise PinFehler("Super-PIN ist auf diesem Server nicht eingerichtet (migrations/monatssperre.sql)")
    return dict(r)


def status(db, user):
    try:
        z = _zeile(db)
    except PinFehler:
        return {"vorhanden": False, "inhaber": False, "eingerichtet": False}
    gesperrt_bis = z["gesperrt_bis"] if z["gesperrt_bis"] and z["gesperrt_bis"] > datetime.now() else None
    return {"vorhanden": True, "inhaber": z["user_id"] == user.id, "eingerichtet": bool(z["pin_hash"]),
            "gesperrt_bis": gesperrt_bis and gesperrt_bis.isoformat(timespec="minutes"),
            "dauerhaft_gesperrt": z["dauerhaft_gesperrt"], "gesetzt_am": z["gesetzt_am"] and z["gesetzt_am"].isoformat(timespec="minutes")}


def _audit(db, user, action, details):
    from app.services.booking_service import log_audit
    log_audit(db, user.id, None, action, entity_type="superpin", details=details)


def _gueltig(pin, user):
    pin = (pin or "").strip()
    if not pin.isdigit() or not 6 <= len(pin) <= 10:
        raise ValueError("Die PIN muss aus 6 bis 10 Ziffern bestehen")
    if len(set(pin)) == 1 or pin in "01234567890123456789" or pin in "98765432109876543210":
        raise ValueError("Die PIN ist zu einfach (gleiche Ziffern oder Zahlenreihe)")
    if user.password_hash and pwd_context.verify(pin, user.password_hash):
        raise ValueError("Die PIN darf nicht das Login-Passwort sein")
    return pin


def pruefen(db, user, pin):
    """PIN pruefen. Fehlversuche werden sofort gespeichert (auch wenn die Anfrage danach scheitert)."""
    z = _zeile(db)
    if z["user_id"] != user.id:
        _audit(db, user, "superpin_verweigert", "Super-PIN: Versuch von einem anderen Benutzer als dem Inhaber")
        db.commit()
        raise PinFehler("Nur der Inhaber der Super-PIN (Drazen) kann einen abgeschlossenen Monat öffnen")
    if not z["pin_hash"]:
        raise PinFehler("Super-PIN ist noch nicht gesetzt – zuerst unter Monatsabschluss › Super-PIN einrichten")
    if z["dauerhaft_gesperrt"]:
        raise PinFehler("Super-PIN nach zu vielen Fehlversuchen gesperrt – Zurücksetzen nur auf dem Server")
    if z["gesperrt_bis"] and z["gesperrt_bis"] > datetime.now():
        raise PinFehler(f"Super-PIN nach {SPERRE_NACH} Fehlversuchen gesperrt bis {z['gesperrt_bis']:%H:%M} Uhr")
    if pwd_context.verify((pin or "").strip(), z["pin_hash"]):
        if z["fehlversuche"]:
            db.execute(text("UPDATE superpin SET fehlversuche = 0, gesperrt_bis = NULL"))
        return True
    n = z["fehlversuche"] + 1
    dauerhaft = n >= DAUERHAFT_NACH
    bis = datetime.now() + timedelta(minutes=SPERRE_MIN) if n % SPERRE_NACH == 0 and not dauerhaft else None
    db.execute(text("UPDATE superpin SET fehlversuche = :n, gesperrt_bis = coalesce(:b, gesperrt_bis), dauerhaft_gesperrt = :d"),
               {"n": n, "b": bis, "d": dauerhaft})
    _audit(db, user, "superpin_fehlversuch", f"Super-PIN falsch ({n}. Fehlversuch)"
           + (" – DAUERHAFT gesperrt" if dauerhaft else f" – gesperrt bis {bis:%H:%M}" if bis else ""))
    db.commit()
    if dauerhaft:
        raise PinFehler("Super-PIN falsch – nach zu vielen Fehlversuchen jetzt gesperrt, Zurücksetzen nur auf dem Server")
    if bis:
        raise PinFehler(f"Super-PIN falsch – {SPERRE_MIN} Minuten gesperrt (bis {bis:%H:%M} Uhr)")
    raise PinFehler(f"Super-PIN falsch (noch {SPERRE_NACH - n % SPERRE_NACH} Versuch(e) bis zur Sperre)")


def setzen(db, user, pin_neu, passwort=None, pin_alt=None):
    """Erstes Setzen mit Login-Passwort, Aendern mit alter PIN."""
    z = _zeile(db)
    if z["user_id"] != user.id:
        raise PinFehler("Nur der Inhaber der Super-PIN (Drazen) kann sie setzen")
    if z["pin_hash"]:
        pruefen(db, user, pin_alt)
    elif not (passwort and user.password_hash and pwd_context.verify(passwort, user.password_hash)):
        _audit(db, user, "superpin_fehlversuch", "Super-PIN einrichten: Login-Passwort falsch")
        db.commit()
        raise PinFehler("Login-Passwort falsch")
    neu = _gueltig(pin_neu, user)
    db.execute(text("UPDATE superpin SET pin_hash = :h, fehlversuche = 0, gesperrt_bis = NULL, gesetzt_am = now()"),
               {"h": pwd_context.hash(neu)})
    _audit(db, user, "superpin_gesetzt", "Super-PIN " + ("geändert" if z["pin_hash"] else "eingerichtet"))
    db.commit()
    return status(db, user)
