"""Schutz gegen doppelt nachgereichte Stempel (GO Drazen 23.11.2026, Anlass: Lara 17.11. / Eintrag 2507).

Ein Offline-Stempel (Handy-Zeit > 2 Min vor Eingang), der in eine vorhandene Buchung desselben MA faellt, wird NICHT
angelegt. Stattdessen:
  - Hinweis im Cockpit ("Offene Punkte" auf Heute, Typ "doppelt", Knopf "Erledigt"),
  - Telegram "Doppelt nachgereicht, nicht übernommen" (Kategorie sonstiges; Folge-Gehen ohne eigene Meldung),
  - die MA-App bekommt trotzdem eine Bestaetigung (client_id), damit die Warteschlange nicht endlos wiederholt.
Gleiche client_id ein zweites Mal = dieselbe Bestaetigung, keine zweite Meldung.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

OFFLINE_SEK = 120                    # wie [OFFLINE]-Markierung im Stempel-Log
KOMMEN_VORLAUF = timedelta(minutes=30)  # Kommen bis 30 Min vor einer vorhandenen Buchung zaehlt als doppelt

_DDL = """
CREATE TABLE IF NOT EXISTS stempel_verworfen (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    art VARCHAR(10) NOT NULL,                 -- kommen | gehen
    stempel_zeit TIMESTAMP NOT NULL,          -- Handy-Zeit
    empfangen_am TIMESTAMP NOT NULL DEFAULT now(),
    client_id VARCHAR(80) UNIQUE,
    object_id INTEGER,
    buchung_id INTEGER,                       -- vorhandene Buchung (keine FK: darf spaeter geloescht werden)
    buchung_text TEXT,
    status VARCHAR(12) NOT NULL DEFAULT 'offen',   -- offen | erledigt | vermerkt (Folge-Gehen, kein eigener Hinweis)
    erledigt_am TIMESTAMP,
    erledigt_von INTEGER
)"""


def tabelle(db):
    db.execute(text(_DDL))


def ist_offline(client_ts_str, stamp_time):
    return bool(client_ts_str) and (datetime.now() - stamp_time).total_seconds() > OFFLINE_SEK


def _hm(d):
    return d.strftime("%H:%M") if d else "offen"


def _buchung_text(r):
    if r["check_out"] is None:
        return f"laufender Buchung {r['id']} seit {r['check_in']:%d.%m. %H:%M}" + (f" {r['objekt']}" if r["objekt"] else "")
    return f"Buchung {r['id']} {r['check_in']:%d.%m.} {_hm(r['check_in'])}–{_hm(r['check_out'])}" + (f" {r['objekt']}" if r["objekt"] else "")


def konflikt_kommen(db, employee_id, stamp_time):
    """Vorhandene Buchung, mit der sich ein nachgereichtes Kommen ueberschneidet (oder None):
    abgeschlossene Buchung mit Kommen-30Min <= Stempel < Gehen, oder offene Buchung, die erst NACH dem Stempel beginnt
    (sonst wuerde sie mit einem Gehen vor ihrem Kommen geschlossen)."""
    r = db.execute(text("""
        SELECT t.id, t.check_in, t.check_out, o.name AS objekt FROM time_entries t LEFT JOIN objects o ON o.id = t.object_id
         WHERE t.employee_id = :e AND (
               (t.check_out IS NOT NULL AND t.check_in - :v <= :s AND :s < t.check_out)
            OR (t.check_out IS NULL AND t.check_in > :s))
         ORDER BY t.check_in LIMIT 1"""), {"e": employee_id, "s": stamp_time, "v": KOMMEN_VORLAUF}).mappings().first()
    return dict(r) if r else None


def konflikt_gehen(db, employee_id, stamp_time, offene):
    """Nachgereichtes Gehen: offene Buchung beginnt erst nach dem Stempel -> nicht schliessen (Gehen vor Kommen).
    Ohne offene Buchung: abgeschlossene Buchung, in die der Stempel faellt (dann nur bestaetigen + vermerken)."""
    if offene is not None:
        if offene.check_in and offene.check_in > stamp_time:
            r = db.execute(text("SELECT t.id, t.check_in, t.check_out, o.name AS objekt FROM time_entries t "
                                "LEFT JOIN objects o ON o.id = t.object_id WHERE t.id = :i"), {"i": offene.id}).mappings().first()
            return dict(r)
        return None
    r = db.execute(text("""
        SELECT t.id, t.check_in, t.check_out, o.name AS objekt FROM time_entries t LEFT JOIN objects o ON o.id = t.object_id
         WHERE t.employee_id = :e AND t.check_out IS NOT NULL AND t.check_in <= :s AND :s <= t.check_out + interval '30 minutes'
         ORDER BY t.check_in DESC LIMIT 1"""), {"e": employee_id, "s": stamp_time}).mappings().first()
    if r and abs((r["check_out"] - stamp_time).total_seconds()) < 2:
        return None      # dasselbe Gehen noch einmal (Antwort ging verloren) -> bisherige Bestaetigung
    return dict(r) if r else None


def schon_verworfen(db, client_id):
    if not client_id:
        return None
    tabelle(db)
    r = db.execute(text("SELECT * FROM stempel_verworfen WHERE client_id = :c"), {"c": client_id}).mappings().first()
    return dict(r) if r else None


def verwerfen(db, employee, art, stamp_time, client_id, object_id, buchung, melden=True):
    """Stempel vermerken (nicht buchen), Protokoll + Telegram. Gibt die Bestaetigung fuer die App zurueck."""
    from app.services.booking_service import log_audit
    tabelle(db)
    name = f"{employee.first_name} {employee.last_name}"
    btext = _buchung_text(buchung)
    jetzt = datetime.now()
    vid = db.execute(text("""
        INSERT INTO stempel_verworfen (employee_id, art, stempel_zeit, empfangen_am, client_id, object_id, buchung_id, buchung_text, status)
        VALUES (:e, :a, :s, :j, :c, :o, :b, :bt, :st) ON CONFLICT (client_id) DO NOTHING RETURNING id"""),
        {"e": employee.id, "a": art, "s": stamp_time, "j": jetzt, "c": client_id, "o": object_id,
         "b": buchung["id"], "bt": btext, "st": "offen" if melden else "vermerkt"}).scalar()
    was = "Kommen" if art == "kommen" else "Gehen"
    meldung = (f"Doppelt nachgereicht, nicht übernommen: {name}, {was} {stamp_time:%d.%m. %H:%M} "
               f"(offline, übertragen {jetzt:%d.%m. %H:%M}) – überschneidet sich mit {btext}.")
    if vid:
        log_audit(db, employee.user_id, employee.id, "stempel_doppelt_verworfen", entity_type="time_entry", entity_id=buchung["id"],
                  details=meldung)
    db.commit()
    logger.info(meldung)
    if vid and melden:
        try:
            from app.services.telegram_bot import notify_admin
            notify_admin("⚠️ " + meldung, category="sonstiges", ref_type="stempel_doppelt", ref_id=vid,
                         employee_id=employee.id)
        except Exception as x:   # Telegram darf den Stempel nie scheitern lassen
            logger.warning(f"Telegram stempel_doppelt: {x}")
    return antwort(client_id, art, stamp_time, btext)


def antwort(client_id, art, stamp_time, btext):
    was = "Kommen" if art == "kommen" else "Gehen"
    return {"id": None, "client_id": client_id, "nicht_uebernommen": True,
            "check_in": stamp_time.isoformat() if art == "kommen" else None,
            "check_out": stamp_time.isoformat() if art == "gehen" else None,
            "meldung": f"{was} {stamp_time:%d.%m. %H:%M} nicht übernommen – überschneidet sich mit {btext}. Die Objektleitung ist informiert."}


def offene(db, employee_ids=None):
    """Fuer die Cockpit-Liste "Offene Punkte" (Heute)."""
    tabelle(db)
    sql = """SELECT v.*, e.first_name || ' ' || e.last_name AS name FROM stempel_verworfen v
               JOIN employees e ON e.id = v.employee_id WHERE v.status = 'offen'"""
    p = {}
    if employee_ids is not None:
        sql += " AND v.employee_id = ANY(:ids)"
        p["ids"] = list(employee_ids) or [-1]
    return [dict(r) for r in db.execute(text(sql + " ORDER BY v.empfangen_am"), p).mappings()]


def erledigen(db, vid, user_id, zurueck=False):
    from app.services.booking_service import log_audit
    tabelle(db)
    r = db.execute(text("SELECT employee_id, status FROM stempel_verworfen WHERE id = :i"), {"i": vid}).mappings().first()
    if not r:
        raise LookupError("Hinweis nicht gefunden")
    neu = "offen" if zurueck else "erledigt"
    db.execute(text("UPDATE stempel_verworfen SET status = :s, erledigt_am = :a, erledigt_von = :u WHERE id = :i"),
               {"s": neu, "a": None if zurueck else datetime.now(), "u": None if zurueck else user_id, "i": vid})
    log_audit(db, user_id, r["employee_id"], "stempel_doppelt_erledigt", entity_type="stempel_verworfen", entity_id=vid,
              old_value={"status": r["status"]}, new_value={"status": neu},
              details=f"Hinweis 'Doppelt nachgereicht' {vid} im Cockpit {'wieder offen' if zurueck else 'erledigt'}")
    db.commit()
    return {"status": neu}
