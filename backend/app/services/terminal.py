"""Terminal-Modus (Drazen 24.11.2026): festes Tablet je Objekt (erstes Objekt: Lidl Neu Bie2, ab Fr 27.11.).

- Admin/Objektleitung registriert das Geraet einmal fuer ein Objekt -> Geraete-Token (nur Hash in der DB),
  im Cockpit sichtbar und widerrufbar.
- MA tippt seinen Namen, gibt seine persoenliche 4-stellige PIN ein (bcrypt, im Cockpit je MA setzbar)
  und bekommt einen kurzen Stempel-Schein (90 Sek), mit dem genau ein Kommen/Gehen gebucht wird.
- Gestempelt wird nur online mit Server-Uhrzeit (kein client_timestamp, keine Warteschlange).
  Die Buchung laeuft ueber dieselbe Logik wie die App (time_entries.check_in/check_out) und bekommt quelle='terminal'.
"""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta

from jose import JWTError, jwt
from sqlalchemy import text

from app.core.security import get_password_hash, verify_password

SCHEIN_SEK = 90                       # PIN gilt fuer einen Knopfdruck innerhalb von 90 Sek
PIN_MAX_FEHLER_MA = 5                 # danach MA 10 Min gesperrt
PIN_MAX_FEHLER_GERAET = 15            # danach Geraet 10 Min gesperrt (Durchprobieren verschiedener Namen)
SPERRE = timedelta(minutes=10)
OBJ_URLAUB, OBJ_KRANK = 999, 19
TRIVIAL = {"0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999", "1234", "4321"}


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _q(db, sql, **p):
    return [dict(r) for r in db.execute(text(sql), p).mappings()]


# ------------------------------------------------------------------ Geraete

def objekte(db):
    return _q(db, f"""SELECT id, name, coalesce(is_test, false) AS test FROM objects
                       WHERE coalesce(is_active, true) AND id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK})
                       ORDER BY coalesce(is_test, false), name""")


def registrieren(db, object_id, name, user_id):
    o = _q(db, "SELECT id, name FROM objects WHERE id = :o AND coalesce(is_active, true)", o=object_id)
    if not o or object_id in (OBJ_URLAUB, OBJ_KRANK):
        raise LookupError("Objekt nicht gefunden")
    name = (name or "").strip()[:80] or f"Terminal {o[0]['name']}"
    token = secrets.token_urlsafe(32)
    gid = db.execute(text("""INSERT INTO terminal_geraete (object_id, name, token_hash, erstellt_von)
                             VALUES (:o, :n, :h, :u) RETURNING id"""),
                     {"o": object_id, "n": name, "h": _hash(token), "u": user_id}).scalar()
    from app.services.booking_service import log_audit
    log_audit(db, user_id, None, "terminal_registriert", entity_type="terminal_geraet", entity_id=gid,
              details=f"Terminal '{name}' fuer Objekt {o[0]['name']} registriert")
    db.commit()
    return {"id": gid, "token": token, "name": name, "object_id": object_id, "objekt": o[0]["name"]}


def geraet(db, token, ip=None):
    """Geraet zum Token (nicht widerrufen) oder None. Merkt 'zuletzt gesehen'."""
    if not token or len(token) > 100:
        return None
    r = _q(db, """SELECT g.*, o.name AS objekt, coalesce(o.is_test, false) AS test_objekt FROM terminal_geraete g JOIN objects o ON o.id = g.object_id
                   WHERE g.token_hash = :h AND g.widerrufen_am IS NULL""", h=_hash(token))
    if not r:
        return None
    db.execute(text("UPDATE terminal_geraete SET zuletzt_gesehen = now(), zuletzt_ip = :ip WHERE id = :i"),
               {"ip": ip, "i": r[0]["id"]})
    db.commit()
    return r[0]


def geraete(db):
    return _q(db, """SELECT g.id, g.name, g.object_id, o.name AS objekt, g.erstellt_am, g.zuletzt_gesehen, g.zuletzt_ip,
                            g.widerrufen_am, g.gesperrt_bis,
                            coalesce(e.first_name || ' ' || e.last_name, u.email) AS erstellt_von
                       FROM terminal_geraete g JOIN objects o ON o.id = g.object_id
                       LEFT JOIN users u ON u.id = g.erstellt_von LEFT JOIN employees e ON e.user_id = u.id
                      ORDER BY g.widerrufen_am IS NOT NULL, g.erstellt_am DESC""")


def widerrufen(db, gid, user_id):
    r = _q(db, "SELECT name, widerrufen_am FROM terminal_geraete WHERE id = :i", i=gid)
    if not r:
        raise LookupError("Terminal nicht gefunden")
    if r[0]["widerrufen_am"] is None:
        db.execute(text("UPDATE terminal_geraete SET widerrufen_am = now(), widerrufen_von = :u WHERE id = :i"),
                   {"u": user_id, "i": gid})
        from app.services.booking_service import log_audit
        log_audit(db, user_id, None, "terminal_widerrufen", entity_type="terminal_geraet", entity_id=gid,
                  details=f"Terminal '{r[0]['name']}' widerrufen")
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ PINs

def pins(db):
    """Aktive MA mit PIN-Status fuer das Cockpit (Test-MA am Ende, fuer Test-Terminals)."""
    return _q(db, """SELECT e.id, e.first_name || ' ' || e.last_name AS name, e.personal_nr, coalesce(e.is_test, false) AS test,
                            p.gesetzt_am, (p.employee_id IS NOT NULL) AS hat_pin,
                            (p.gesperrt_bis IS NOT NULL AND p.gesperrt_bis > now()) AS gesperrt
                       FROM employees e LEFT JOIN terminal_pin p ON p.employee_id = e.id
                      WHERE coalesce(e.is_active, true)
                      ORDER BY coalesce(e.is_test, false), e.last_name, e.first_name""")


def pin_setzen(db, employee_id, pin, user_id):
    """pin=None -> zufaellige PIN erzeugen (wird einmal zurueckgegeben, damit die OL sie dem MA sagen kann)."""
    e = _q(db, "SELECT id, first_name || ' ' || last_name AS name FROM employees WHERE id = :e", e=employee_id)
    if not e:
        raise LookupError("Mitarbeiter nicht gefunden")
    if pin is None:
        while True:
            pin = f"{secrets.randbelow(10000):04d}"
            if pin not in TRIVIAL:
                break
    pin = str(pin).strip()
    if not re.fullmatch(r"\d{4}", pin):
        raise ValueError("Die PIN muss genau 4 Ziffern haben")
    if pin in TRIVIAL:
        raise ValueError("Diese PIN ist zu leicht zu erraten (z. B. 1234 oder 0000) – bitte eine andere wählen")
    db.execute(text("""INSERT INTO terminal_pin (employee_id, pin_hash, gesetzt_am, gesetzt_von, fehler, gesperrt_bis)
                       VALUES (:e, :h, now(), :u, 0, NULL)
                       ON CONFLICT (employee_id) DO UPDATE SET pin_hash = :h, gesetzt_am = now(), gesetzt_von = :u,
                                                             fehler = 0, gesperrt_bis = NULL"""),
               {"e": employee_id, "h": get_password_hash(pin), "u": user_id})
    from app.services.booking_service import log_audit
    log_audit(db, user_id, employee_id, "terminal_pin_gesetzt", entity_type="terminal_pin", entity_id=employee_id,
              details=f"Terminal-PIN fuer {e[0]['name']} gesetzt")   # PIN selbst nie ins Protokoll
    db.commit()
    return {"employee_id": employee_id, "name": e[0]["name"], "pin": pin}


def pin_loeschen(db, employee_id, user_id):
    n = db.execute(text("DELETE FROM terminal_pin WHERE employee_id = :e"), {"e": employee_id}).rowcount
    if n:
        from app.services.booking_service import log_audit
        log_audit(db, user_id, employee_id, "terminal_pin_geloescht", entity_type="terminal_pin", entity_id=employee_id,
                  details="Terminal-PIN geloescht")
    db.commit()
    return {"ok": True}


def pin_pruefen(db, g, employee_id, pin):
    """True/False; Sperren werden als ValueError mit Klartext gemeldet."""
    jetzt = datetime.now()
    if g["gesperrt_bis"] and g["gesperrt_bis"] > jetzt:
        raise ValueError(f"Zu viele falsche PINs – Terminal bis {g['gesperrt_bis']:%H:%M} gesperrt")
    p = _q(db, "SELECT pin_hash, fehler, gesperrt_bis FROM terminal_pin WHERE employee_id = :e", e=employee_id)
    if not p:
        raise LookupError("Für dich ist noch keine PIN hinterlegt – bitte bei der Objektleitung melden")
    p = p[0]
    if p["gesperrt_bis"] and p["gesperrt_bis"] > jetzt:
        raise ValueError(f"Zu viele falsche PINs – bitte ab {p['gesperrt_bis']:%H:%M} wieder versuchen oder Objektleitung fragen")
    if verify_password(str(pin or ""), p["pin_hash"]):
        db.execute(text("UPDATE terminal_pin SET fehler = 0, gesperrt_bis = NULL WHERE employee_id = :e"), {"e": employee_id})
        db.execute(text("UPDATE terminal_geraete SET pin_fehler = 0 WHERE id = :i"), {"i": g["id"]})
        db.commit()
        return True
    f_ma, f_g = p["fehler"] + 1, g["pin_fehler"] + 1
    db.execute(text("UPDATE terminal_pin SET fehler = :f, gesperrt_bis = :s WHERE employee_id = :e"),
               {"f": 0 if f_ma >= PIN_MAX_FEHLER_MA else f_ma, "s": jetzt + SPERRE if f_ma >= PIN_MAX_FEHLER_MA else None,
                "e": employee_id})
    db.execute(text("UPDATE terminal_geraete SET pin_fehler = :f, gesperrt_bis = :s WHERE id = :i"),
               {"f": 0 if f_g >= PIN_MAX_FEHLER_GERAET else f_g,
                "s": jetzt + SPERRE if f_g >= PIN_MAX_FEHLER_GERAET else g["gesperrt_bis"], "i": g["id"]})
    db.commit()
    return False


# ------------------------------------------------------------------ Stempel-Schein (nach PIN, 90 Sek)

def _key():
    return os.getenv("SECRET_KEY")


def schein(gid, employee_id):
    exp = datetime.utcnow() + timedelta(seconds=SCHEIN_SEK)
    return jwt.encode({"typ": "terminal", "g": gid, "e": employee_id, "exp": exp}, _key(), algorithm="HS256")


def schein_pruefen(s, gid):
    try:
        d = jwt.decode(s or "", _key(), algorithms=["HS256"])
    except JWTError:
        return None
    if d.get("typ") != "terminal" or d.get("g") != gid:
        return None
    return d.get("e")


# ------------------------------------------------------------------ Startbildschirm

def _kat_sql():
    return """coalesce((SELECT a.tracking_category FROM employee_object_assignments a
                         WHERE a.employee_id = e.id AND a.object_id = :o AND coalesce(a.is_active, true) LIMIT 1),
                        u.category, 'C')"""


def status(db, employee_id):
    """Offene Buchung des MA (neueste) oder None."""
    r = _q(db, """SELECT t.id, t.check_in, t.object_id, o.name AS objekt FROM time_entries t
                   LEFT JOIN objects o ON o.id = t.object_id
                  WHERE t.employee_id = :e AND t.check_out IS NULL ORDER BY t.id DESC LIMIT 1""", e=employee_id)
    return r[0] if r else None


def start(db, g):
    """Kacheln: MA mit Dienst heute an diesem Objekt + MA, die gerade hier eingestempelt sind (Test-MA nur am Test-Objekt)."""
    heute = datetime.now().date()
    rows = _q(db, f"""
        SELECT e.id, e.first_name, e.last_name, s.start_time, s.end_time, {_kat_sql()} AS kat
          FROM schedules s JOIN employees e ON e.id = s.employee_id JOIN users u ON u.id = e.user_id
         WHERE s.date = :d AND s.object_id = :o AND s.status IN ('normal', 'vertretung')
           AND coalesce(e.is_active, true) AND (NOT coalesce(e.is_test, false) OR :t)
         ORDER BY s.start_time, e.first_name""", d=heute, o=g["object_id"], t=g["test_objekt"])
    da = _q(db, f"""
        SELECT e.id, e.first_name, e.last_name, NULL::time AS start_time, NULL::time AS end_time, {_kat_sql()} AS kat
          FROM time_entries t JOIN employees e ON e.id = t.employee_id JOIN users u ON u.id = e.user_id
         WHERE t.object_id = :o AND t.check_out IS NULL AND t.check_in > now() - interval '16 hours'
           AND (NOT coalesce(e.is_test, false) OR :t)""", o=g["object_id"], t=g["test_objekt"])
    kacheln, gesehen = [], set()
    for r in rows + da:
        if r["id"] in gesehen:
            continue
        gesehen.add(r["id"])
        kacheln.append(_kachel(db, r, g["object_id"]))
    return {"objekt": g["objekt"], "object_id": g["object_id"], "terminal": g["name"],
            "jetzt": datetime.now().isoformat(timespec="seconds"), "kacheln": kacheln}


def _kachel(db, r, object_id):
    st = status(db, r["id"])
    heute_fertig = None
    if not st:
        f = _q(db, """SELECT check_in, check_out FROM time_entries WHERE employee_id = :e AND object_id = :o
                       AND check_in::date = current_date AND check_out IS NOT NULL ORDER BY check_out DESC LIMIT 1""",
               e=r["id"], o=object_id)
        heute_fertig = f[0] if f else None
    return {"employee_id": r["id"], "name": f"{r['first_name']} {r['last_name']}", "vorname": r["first_name"],
            "schicht": f"{r['start_time']:%H:%M}–{r['end_time']:%H:%M}" if r.get("start_time") and r.get("end_time") else None,
            "auto": (r.get("kat") or "C").upper() == "A",
            "da_seit": st["check_in"].strftime("%H:%M") if st else None,
            "da_objekt": st["objekt"] if st and st["object_id"] != object_id else None,
            "fertig": f"{heute_fertig['check_in']:%H:%M}–{heute_fertig['check_out']:%H:%M}" if heute_fertig else None}


def suche(db, g, q):
    q = (q or "").strip()
    if len(q) < 2:
        return []
    rows = _q(db, f"""
        SELECT e.id, e.first_name, e.last_name, NULL::time AS start_time, NULL::time AS end_time, {_kat_sql()} AS kat
          FROM employees e JOIN users u ON u.id = e.user_id
         WHERE coalesce(e.is_active, true) AND (NOT coalesce(e.is_test, false) OR :t)
           AND (e.first_name || ' ' || e.last_name ILIKE :q OR e.last_name || ' ' || e.first_name ILIKE :q)
         ORDER BY e.first_name, e.last_name LIMIT 12""", q=f"%{q}%", o=g["object_id"], t=g["test_objekt"])
    return [_kachel(db, r, g["object_id"]) for r in rows]


def ist_auto(db, employee_id, object_id):
    r = _q(db, f"SELECT {_kat_sql()} AS kat FROM employees e JOIN users u ON u.id = e.user_id WHERE e.id = :e",
           e=employee_id, o=object_id)
    return bool(r) and (r[0]["kat"] or "C").upper() == "A"


def mitarbeiter(db, g, employee_id):
    """Test-MA (is_test) nur an Terminals fuer Test-Objekte."""
    r = _q(db, """SELECT e.id, e.user_id, e.first_name, e.last_name FROM employees e
                   WHERE e.id = :e AND coalesce(e.is_active, true) AND (NOT coalesce(e.is_test, false) OR :t)""",
           e=employee_id, t=g["test_objekt"])
    return r[0] if r else None
