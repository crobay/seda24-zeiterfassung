"""
Festgehalt je Mitarbeiter (Tabelle employee_festgehalt), gueltig ab einem Datum.

Bei aktivem Festgehalt (Monat ab gueltig_ab):
- Lexware: LA 1 fix Monatsstunden x Stundensatz, unabhaengig von Ist-Stunden.
  Dazu LA 13 Sonntagszuschlag (Sonntagsstunden x SONNTAG_ZUSCHLAG EUR), LA 11 Nacht,
  LA 15 Feiertagsstunden, LA 16 Feiertagszuschlag 125 %, LA 17 Feiertagszuschlag 150 %
  (25.12., 26.12., 01.05.). Kein LA 14 Urlaub, kein LA 7 Krank, kein LA 6005 Vorschuss.
- Kein Zeitkonto (kein Soll, kein Uebertrag), Werktags-Automatik aus,
  Stempeln erlaubt, aber nicht lohnrelevant.
Monate vor gueltig_ab laufen im alten Modell.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import text

SONNTAG_ZUSCHLAG = 10.00            # EUR pro Sonntagsstunde (LA 13)
FEIERTAG_150 = {(12, 25), (12, 26), (5, 1)}    # LA 17 (150 %), uebrige Feiertage LA 16 (125 %)


def get(db, employee_id):
    """Festgehalt-Eintrag (auch inaktiv) oder None."""
    return db.execute(text("""
        SELECT id, employee_id, aktiv, gueltig_ab, monatsstunden, stundensatz
        FROM employee_festgehalt WHERE employee_id = :e
    """), {"e": employee_id}).fetchone()


def active_on(db, employee_id, day):
    """Festgehalt-Eintrag, wenn am Tag aktiv, sonst None."""
    fg = get(db, employee_id)
    if fg and fg.aktiv and day >= fg.gueltig_ab:
        return fg
    return None


def active_in_month(db, employee_id, year, month):
    """Aktiv fuer den ganzen Monat? (Monatserster ab gueltig_ab)"""
    return active_on(db, employee_id, date(year, month, 1))


def active_employee_ids(db, year, month):
    rows = db.execute(text("""
        SELECT employee_id FROM employee_festgehalt
        WHERE aktiv = true AND gueltig_ab <= :d
    """), {"d": date(year, month, 1)}).fetchall()
    return {r.employee_id for r in rows}


def betrag(fg):
    return round(float(fg.monatsstunden) * float(fg.stundensatz), 2)


def _nacht_stunden(ci, co):
    """Nachtstunden 23-6 Uhr eines Eintrags (wie Zeitkonto: Beginn vor 6 / Ende nach 23)."""
    h = 0.0
    if ci.hour < 6:
        h += max(0.0, min((co - ci).total_seconds() / 3600, 6 - ci.hour - ci.minute / 60))
    if co.hour >= 23:
        h += co.hour - 23 + co.minute / 60
    return h


def lohn_split(db, employee_id, first_day, last_day):
    """Sonntags-, Feiertags- (125 % / 150 %) und Nachtstunden des Monats aus den Buchungen.
    Sonntagsstunden = gebuchte Stunden (billed_hours, also ohne Pause)."""
    from app.services.holidays_bw import is_feiertag_bw
    rows = db.execute(text("""
        SELECT check_in, check_out, billed_hours FROM time_entries
        WHERE employee_id = :e AND check_out IS NOT NULL
          AND check_in >= :f AND check_in < :l
          AND COALESCE(object_id, 0) <> 999
    """), {"e": employee_id, "f": first_day, "l": last_day + timedelta(days=1)}).fetchall()
    sonntag = feiertag125 = feiertag150 = nacht = 0.0
    for r in rows:
        h = float(r.billed_hours) if r.billed_hours is not None else (r.check_out - r.check_in).total_seconds() / 3600
        d = r.check_in.date()
        if is_feiertag_bw(d):
            if (d.month, d.day) in FEIERTAG_150:
                feiertag150 += h
            else:
                feiertag125 += h
        elif d.weekday() == 6:
            sonntag += h
        nacht += _nacht_stunden(r.check_in, r.check_out)
    return {
        "sonntag_hours": round(sonntag, 2),
        "feiertag125_hours": round(feiertag125, 2),
        "feiertag150_hours": round(feiertag150, 2),
        "feiertag_hours": round(feiertag125 + feiertag150, 2),
        "nacht_hours": round(nacht, 2),
    }


def lexware_lohnarten(db, emp, fg, year, month):
    from calendar import monthrange
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    s = lohn_split(db, emp.id, first, last)
    la = [{"lohnart": 1, "bezeichnung": "Gehalt (Festgehalt)",
           "stunden": float(fg.monatsstunden), "betrag": betrag(fg)}]
    if s["sonntag_hours"] > 0:
        la.append({"lohnart": 13, "bezeichnung": "Sonntagszuschlag", "stunden": s["sonntag_hours"],
                   "betrag": round(s["sonntag_hours"] * SONNTAG_ZUSCHLAG, 2)})
    if s["feiertag_hours"] > 0:
        la.append({"lohnart": 15, "bezeichnung": "Feiertagsstunden", "stunden": s["feiertag_hours"], "betrag": None})
    if s["feiertag125_hours"] > 0:
        la.append({"lohnart": 16, "bezeichnung": "Feiertagszuschlag 125 % stfr.",
                   "stunden": s["feiertag125_hours"], "betrag": None})
    if s["feiertag150_hours"] > 0:
        la.append({"lohnart": 17, "bezeichnung": "Feiertagszuschlag 150 % stfr.",
                   "stunden": s["feiertag150_hours"], "betrag": None})
    if s["nacht_hours"] > 0:
        la.append({"lohnart": 11, "bezeichnung": "Nachtzuschlag", "stunden": s["nacht_hours"], "betrag": None})
    return la


def save(db, employee_id, data, admin_id):
    """Festgehalt anlegen/aendern mit Audit. data: aktiv, gueltig_ab (YYYY-MM-DD), monatsstunden, stundensatz."""
    from app.services.booking_service import log_audit
    old = get(db, employee_id)
    aktiv = bool(data.get("aktiv", old.aktiv if old else False))
    ab = data.get("gueltig_ab") or (str(old.gueltig_ab) if old else None)
    if not ab:
        raise ValueError("Gültig ab fehlt")
    ab = datetime.strptime(str(ab)[:10], "%Y-%m-%d").date()
    if ab.day != 1:
        raise ValueError("Gültig ab muss ein Monatserster sein")
    std = float(data.get("monatsstunden", old.monatsstunden if old else 100))
    satz = float(data.get("stundensatz", old.stundensatz if old else 20))
    if std <= 0 or satz <= 0:
        raise ValueError("Monatsstunden und Stundensatz müssen größer 0 sein")
    new = {"aktiv": aktiv, "gueltig_ab": str(ab), "monatsstunden": std, "stundensatz": satz}
    oldv = ({"aktiv": old.aktiv, "gueltig_ab": str(old.gueltig_ab),
             "monatsstunden": old.monatsstunden, "stundensatz": old.stundensatz} if old else None)
    if oldv == new:
        return new
    if old:
        db.execute(text("""UPDATE employee_festgehalt SET aktiv=:a, gueltig_ab=:g, monatsstunden=:m,
                           stundensatz=:s, updated_at=now() WHERE employee_id=:e"""),
                   {"a": aktiv, "g": ab, "m": std, "s": satz, "e": employee_id})
        fid = old.id
    else:
        fid = db.execute(text("""INSERT INTO employee_festgehalt (employee_id, aktiv, gueltig_ab, monatsstunden, stundensatz)
                                 VALUES (:e, :a, :g, :m, :s) RETURNING id"""),
                         {"a": aktiv, "g": ab, "m": std, "s": satz, "e": employee_id}).scalar()
    emp = db.execute(text("SELECT first_name, last_name, personal_nr FROM employees WHERE id=:e"),
                     {"e": employee_id}).fetchone()
    log_audit(db, admin_id, employee_id, "festgehalt_changed", entity_type="employee_festgehalt",
              entity_id=fid, old_value=oldv, new_value=new,
              details=(f"Festgehalt {'aktiv' if aktiv else 'aus'}: {emp.first_name} {emp.last_name} "
                       f"({emp.personal_nr}), ab {ab.strftime('%d.%m.%Y')}, {std:g} h x {satz:.2f} EUR "
                       f"= {std * satz:.2f} EUR"))
    return new
