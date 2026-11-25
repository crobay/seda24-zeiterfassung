"""Art / Satz / Fahrt mit KM fuer "Buchung nachtragen" und "Buchung bearbeiten" im Cockpit (Drazen 25.11.2026).

Nichts Neues: Art = time_entries.service_type, Satz = time_entries.hourly_rate, Lohnart ueber service_type
(Lohnsplit admin._berechne_stunden_split: Fenster-/Sonder-/Grundreinigung -> "sonder", sonst "normal"; Nummern aus
den Lexware-Lohnarten im Monatsabschluss). KM ueber time_entries.calculate_and_save_km (weiteste Fahrt des Tages).
Arten wie in der alten Ansicht/App; Satz je Art vorbelegt, im Dialog ueberschreibbar (Drazen 25.11.2026 12:20).
"""
from sqlalchemy import text

UNTERHALT = "Unterhaltsreinigung"
SONDER = "Sonderreinigung"
SONDER_ARTEN = ("Grundreinigung", "Sonderreinigung", "Fensterreinigung")   # wie der Lohnsplit
ARTEN = (UNTERHALT,) + SONDER_ARTEN                                          # Auswahl wie alte Ansicht
ART_FEHLER = "Art: Unterhalts-, Grund-, Sonder- oder Fensterreinigung"
SONDERSATZ_STANDARD = 20.0


def ist_sonder(service_type):
    return service_type in SONDER_ARTEN


def satz_pruefen(v):
    """Eigener Stundensatz aus dem Dialog ('15,50' oder 15.5) -> float, 1 bis 100 €."""
    try:
        f = round(float(str(v).replace(",", ".").strip()), 2)
    except (TypeError, ValueError):
        raise ValueError("Stundensatz ist keine Zahl")
    if not 1 <= f <= 100:
        raise ValueError("Stundensatz muss zwischen 1 und 100 € liegen")
    return f


def satz(db, employee_id, object_id, service_type):
    """Vorbelegung: Grund/Sonder/Fenster = MA-Sondersatz (hourly_rate_basic, Standard 20 €);
    Unterhalt = Satz der Objekt-Zuweisung (wie beim App-Stempel), sonst MA-Satz."""
    e = db.execute(text("""SELECT hourly_rate, hourly_rate_standard, hourly_rate_window, hourly_rate_basic
                             FROM employees WHERE id = :e"""), {"e": employee_id}).mappings().first()
    if not e:
        raise LookupError("Mitarbeiter nicht gefunden")
    if ist_sonder(service_type):
        return float(e["hourly_rate_basic"] or SONDERSATZ_STANDARD)
    a = db.execute(text("""SELECT custom_hourly_rate, custom_service_type FROM employee_object_assignments
                            WHERE employee_id = :e AND object_id = :o AND is_active ORDER BY id LIMIT 1"""),
                   {"e": employee_id, "o": object_id}).mappings().first() if object_id else None
    # Zuweisungen fuer Sondereinsaetze (z. B. Zentrale "Sonderreinigung") gelten nicht fuer die Unterhaltsreinigung
    if a and a["custom_hourly_rate"] and not (a["custom_service_type"] or "").lower().startswith(("son", "fen", "grund")):
        return float(a["custom_hourly_rate"])
    return float(e["hourly_rate"] or e["hourly_rate_standard"] or 15.0)


def lohnart(db, service_type):
    """Lexware-Lohnart als Text ('0001' / '0030') aus den Einstellungen im Monatsabschluss, None wenn nicht gesetzt."""
    from app.services import monatsabschluss as ma
    nr = ma.lohnarten(db).get("sonder" if ist_sonder(service_type) else "normal")
    return f"{int(nr):04d}" if nr not in (None, "") else None


def fahrer_standard(db, employee_id, object_id, schedule_id=None):
    """Haken "Fahrt mit KM" vorbelegen: Fahrer laut Schicht, sonst laut Zuweisung MA -> Objekt (wie bisher beim Nachtragen)."""
    if schedule_id:
        r = db.execute(text("SELECT coalesce(is_driver, false) FROM schedules WHERE id = :s"), {"s": int(schedule_id)}).scalar()
        if r is not None:
            return bool(r)
    if not object_id:
        return False
    return bool(db.execute(text("""SELECT coalesce(bool_or(is_driver), false) FROM employee_object_assignments
                                    WHERE employee_id = :e AND object_id = :o AND coalesce(is_active, true)"""),
                           {"e": employee_id, "o": object_id}).scalar())


def km_berechtigt(db, employee_id):
    """KM-Geld ja/nein wie im Monatsabschluss: D0002 (Ruzica, E-Dienstwagen) bekommt kein KM-Geld."""
    from app.services import monatsabschluss as ma
    pnr = db.execute(text("SELECT personal_nr FROM employees WHERE id = :e"), {"e": employee_id}).scalar()
    return pnr not in ma.OHNE_KM_ANHANG


def _hm(t):
    return t.strftime("%H:%M") if t else None


def standardzeit(db, employee_id, object_id, tag):
    """Vorbelegung Kommen/Gehen beim Nachtragen (Drazen 25.11.2026 15:09). Quelle wie die klassische Ansicht
    (admin.get_schedule_for_booking: Dienstplan -> Objekt-Standardzeit je Wochentag -> Objekt-Zeit), dazwischen die
    feste Zuweisung MA -> Objekt aus der Vorlage (master_schedule_entries). None = nichts hinterlegt."""
    from app.services.plan_vorlage import rhythmus_passt
    if not object_id or not tag:
        return None
    s = db.execute(text("""SELECT id, start_time, end_time FROM schedules WHERE employee_id = :e AND object_id = :o AND date = :d
                             AND coalesce(status, 'normal') IN ('normal', 'vertretung') ORDER BY start_time LIMIT 1"""),
                   {"e": employee_id, "o": object_id, "d": tag}).mappings().first()
    if s and s["start_time"] and s["end_time"]:
        return {"kommen": _hm(s["start_time"]), "gehen": _hm(s["end_time"]), "quelle": "dienstplan", "schedule_id": s["id"]}
    v = db.execute(text("""SELECT start_time, end_time, rhythm, month_week, weekday FROM master_schedule_entries
                            WHERE employee_id = :e AND object_id = :o AND weekday = :w AND coalesce(is_active, true)
                            ORDER BY start_time"""), {"e": employee_id, "o": object_id, "w": tag.weekday()}).mappings().all()
    v = [m for m in v if m["start_time"] and m["end_time"]]
    if v:
        m = next((m for m in v if rhythmus_passt(m["rhythm"], m["month_week"], m["weekday"], tag)), v[0])
        return {"kommen": _hm(m["start_time"]), "gehen": _hm(m["end_time"]), "quelle": "zuweisung"}
    o = db.execute(text("""SELECT start_time, end_time FROM object_standard_times_v2 WHERE object_id = :o AND weekday = :w
                            ORDER BY id LIMIT 1"""), {"o": object_id, "w": tag.weekday()}).mappings().first()
    if o and o["start_time"]:
        return {"kommen": _hm(o["start_time"]), "gehen": _hm(o["end_time"]) or "17:00", "quelle": "objekt"}
    o = db.execute(text("SELECT start_time, end_time FROM objects WHERE id = :o"), {"o": object_id}).mappings().first()
    if o and o["start_time"]:
        return {"kommen": _hm(o["start_time"]), "gehen": _hm(o["end_time"]) or "17:00", "quelle": "objekt"}
    return None


def km_distanz(db, employee_id, object_id):
    r = db.execute(text("SELECT distance_km FROM km_distances WHERE employee_id = :e AND object_id = :o"),
                   {"e": employee_id, "o": object_id}).scalar() if object_id else None
    return float(r) if r is not None else None


def _km_zeilen(db, entry_id):
    return db.execute(text("SELECT id, employee_id, object_id, date, distance_km FROM km_daily_entries WHERE time_entry_id = :t"),
                      {"t": entry_id}).mappings().all()


def _weiteste_neu(db, employee_id, tag):
    """Wie calculate_and_save_km / delete_booking: nur die weiteste Fahrt des Tages ist abrechenbar."""
    db.execute(text("UPDATE km_daily_entries SET is_longest_trip = false, is_billable = false WHERE employee_id = :e AND date = :d"),
               {"e": employee_id, "d": tag})
    db.execute(text("""UPDATE km_daily_entries SET is_longest_trip = true, is_billable = true WHERE id = (
                         SELECT id FROM km_daily_entries WHERE employee_id = :e AND date = :d ORDER BY distance_km DESC LIMIT 1)"""),
               {"e": employee_id, "d": tag})


def km_setzen(db, entry_id, an, user_id):
    """Fahrt mit KM an/aus fuer eine Buchung. Gibt einen kurzen Text fuer das Protokoll zurueck (None = nichts geaendert)."""
    from app.api.v1.endpoints.time_entries import calculate_and_save_km
    from app.services.booking_service import log_audit
    t = db.execute(text("SELECT id, employee_id, object_id, check_in FROM time_entries WHERE id = :i"), {"i": entry_id}).mappings().first()
    if not t:
        raise LookupError("Buchung nicht gefunden")
    tag = t["check_in"].date()
    alt = _km_zeilen(db, entry_id)
    passt = [k for k in alt if k["object_id"] == t["object_id"] and k["date"] == tag]
    if an and passt:
        return None
    if not an and not alt:
        return None
    for k in alt:   # weg (aus) bzw. veraltet (anderes Objekt/Datum) -> neu berechnen
        db.execute(text("DELETE FROM km_daily_entries WHERE id = :k"), {"k": k["id"]})
        _weiteste_neu(db, k["employee_id"], k["date"])
    text_ = "Fahrt mit KM aus" + (f" ({float(alt[0]['distance_km']):g} km entfernt)" if alt else "")
    if an:
        if not t["object_id"]:
            raise ValueError("Fahrt mit KM geht nur mit Objekt")
        calculate_and_save_km(t["employee_id"], t["object_id"], tag, entry_id, db)
        neu = _km_zeilen(db, entry_id)
        text_ = f"Fahrt mit KM an ({float(neu[0]['distance_km']):g} km)" if neu else "Fahrt mit KM an"
    log_audit(db, user_id, t["employee_id"], "km_entry_changed", entity_type="time_entry", entity_id=entry_id,
              details=f"{text_} – Buchung {entry_id} vom {tag:%d.%m.%Y} (Cockpit)")
    db.commit()
    return text_
