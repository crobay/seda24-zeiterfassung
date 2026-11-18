"""Minijob-Grenze und Mindestlohn: datumsabhaengige Einstellung + fruehe Warnung mit Hochrechnung bis Monatsende.

Die Werte stehen in app_settings (key 'lohn_grenzen') als Liste [{"ab": "JJJJ-MM-TT", "minijob_grenze": 603,
"mindestlohn": 13.90}, ...] und sind im Cockpit (Einstellungen, nur Admin) aenderbar. Es gilt der Eintrag mit dem
letzten "ab" <= Stichtag. DEFAULT wird nur beim ersten Lesen einmal in die Datenbank geschrieben.

Nur lesen/hochrechnen: an der Lohnberechnung aendert sich nichts. Ist-Betrag wie in der Lohn-Uebersicht
(normale + Feiertags-Stunden x Stundenlohn, Sonder-Betraege, Urlaubsgeld); KM-Geld zaehlt nicht mit
(steuerfreier Fahrtkostenersatz). Hochrechnung = Ist + noch geplante Schichten bis Monatsende x Stundenlohn.
"""
import json
from calendar import monthrange
from math import floor
from datetime import date, datetime, timedelta

from sqlalchemy import text

KEY = "lohn_grenzen"
DEFAULT = {"warn_ab_prozent": 90,
           "stufen": [{"ab": "2026-01-01", "minijob_grenze": 603.0, "mindestlohn": 13.90},
                      {"ab": "2027-01-01", "minijob_grenze": 633.0, "mindestlohn": 14.60}]}
OBJ_URLAUB, OBJ_KRANK = 999, 19


def _tabelle(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS app_settings (key varchar(50) PRIMARY KEY, value text NOT NULL,
                       updated_at timestamp DEFAULT now(), updated_by integer)"""))


def einstellung(db) -> dict:
    _tabelle(db)
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": KEY}).fetchone()
    if r:
        return json.loads(r[0])
    db.execute(text("INSERT INTO app_settings (key, value, updated_at) VALUES (:k, :v, now()) ON CONFLICT (key) DO NOTHING"),
               {"k": KEY, "v": json.dumps(DEFAULT)})
    return json.loads(json.dumps(DEFAULT))


def pruefe(neu: dict) -> dict:
    """Eingabe pruefen und normalisieren (sortiert nach 'ab')."""
    try:
        warn = int(neu.get("warn_ab_prozent", 90))
        stufen = sorted(({"ab": date.fromisoformat(str(s["ab"])).isoformat(), "minijob_grenze": round(float(s["minijob_grenze"]), 2),
                          "mindestlohn": round(float(s["mindestlohn"]), 2)} for s in neu.get("stufen") or []), key=lambda s: s["ab"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Bitte je Stufe 'gültig ab' (Datum), Minijob-Grenze und Mindestlohn angeben")
    if not stufen:
        raise ValueError("Mindestens eine Stufe nötig")
    if not 50 <= warn <= 100:
        raise ValueError("Warnung ab 50–100 %")
    if any(not (100 <= s["minijob_grenze"] <= 2000 and 5 <= s["mindestlohn"] <= 50) for s in stufen):
        raise ValueError("Werte unplausibel (Grenze 100–2000 €, Mindestlohn 5–50 €)")
    if len({s["ab"] for s in stufen}) != len(stufen):
        raise ValueError("Jedes 'gültig ab' nur einmal")
    return {"warn_ab_prozent": warn, "stufen": stufen}


def speichern(db, neu: dict, user_id: int) -> dict:
    from app.services.booking_service import log_audit
    alt = einstellung(db)
    wert = pruefe(neu)
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": KEY, "v": json.dumps(wert), "u": user_id})
    log_audit(db, user_id, None, "lohn_grenzen_geaendert", entity_type="setting", old_value=alt, new_value=wert,
              details="Minijob-Grenze/Mindestlohn geändert: " + ", ".join(
                  f"ab {s['ab']}: {s['minijob_grenze']:.0f} €, {s['mindestlohn']:.2f} €/h" for s in wert["stufen"]))
    db.commit()
    return wert


def stufe_am(db, tag: date, cfg=None) -> dict:
    cfg = cfg or einstellung(db)
    gilt = [s for s in cfg["stufen"] if s["ab"] <= tag.isoformat()]
    return gilt[-1] if gilt else cfg["stufen"][0]


def _std(s):
    if s["planned_hours"]:
        return float(s["planned_hours"])
    a, b = s["start_time"], s["end_time"]
    m = (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)
    return (m if m > 0 else m + 1440) / 60


def hochrechnung(db, jahr: int, monat: int, jetzt: datetime = None, employee_ids=None) -> list:
    """Je Minijobber: Ist (bis jetzt), noch geplant, Hochrechnung, Grenze, Quote, Stufe (ok/warnung/ueber),
    Reststunden bis zur Grenze; dazu Hinweis, wenn der Stundenlohn unter dem Mindestlohn des Monats liegt."""
    from app.api.v1.endpoints.admin import _berechne_stunden_split
    jetzt = jetzt or datetime.now()
    m0 = date(jahr, monat, 1)
    m1 = date(jahr, monat, monthrange(jahr, monat)[1])
    cfg = einstellung(db)
    st = stufe_am(db, m0, cfg)
    grenze, warn = st["minijob_grenze"], cfg["warn_ab_prozent"]
    flt = "" if employee_ids is None else "AND e.id = ANY(:ids)"
    emps = db.execute(text(f"""SELECT e.id, e.personal_nr, e.first_name || ' ' || e.last_name AS name, e.hourly_rate
                               FROM employees e WHERE e.is_active AND NOT coalesce(e.is_test, false)
                                 AND e.employment_type = 'minijob' {flt} ORDER BY e.last_name"""),
                      {"ids": list(employee_ids or [])}).mappings().all()
    out = []
    for e in emps:
        rate = float(e["hourly_rate"] or 0)
        sp = _berechne_stunden_split(db, e["id"], m0, m1)
        # Urlaubsgeld: Tagessatz -1 = "Satz offen" (wird erst am Urlaubsbeginn bestimmt) -> bis dahin mit 0 zaehlen
        urlaub = float(db.execute(text("""SELECT coalesce(sum(greatest(hourly_rate, 0)), 0) FROM time_entries
                                         WHERE employee_id = :e AND service_type = 'Urlaub' AND check_in::date BETWEEN :a AND :b"""),
                                  {"e": e["id"], "a": m0, "b": m1}).scalar())
        ist = (sp["normal_hours"] + sp["feiertag_hours"]) * rate + sp["sonder_amount"] + urlaub
        # noch geplant: Schichten ab jetzt (heute nur, wenn noch nicht begonnen und nicht gestempelt)
        rest_h = 0.0
        for s in db.execute(text(f"""SELECT s.id, s.date, s.start_time, s.end_time, s.planned_hours FROM schedules s
                                     WHERE s.employee_id = :e AND s.date BETWEEN :a AND :b AND s.status IN ('normal', 'vertretung')
                                       AND s.start_time IS NOT NULL AND s.end_time IS NOT NULL
                                       AND s.object_id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK})
                                       AND NOT EXISTS (SELECT 1 FROM time_entries t WHERE t.schedule_id = s.id)"""),
                              {"e": e["id"], "a": max(m0, jetzt.date()), "b": m1}).mappings():
            if s["date"] > jetzt.date() or s["start_time"] > jetzt.time():
                rest_h += _std(s)
        geplant = rest_h * rate
        hoch = ist + geplant
        quote = round(hoch / grenze * 100) if grenze else 0
        stufe = "ueber" if hoch > grenze else ("warnung" if quote >= warn else "ok")
        ml = stufe_am(db, m1, cfg)["mindestlohn"]
        out.append({"employee_id": e["id"], "personal_nr": e["personal_nr"], "name": e["name"], "stundenlohn": rate,
                    "ist": round(ist, 2), "geplant": round(geplant, 2), "hochrechnung": round(hoch, 2), "grenze": grenze,
                    "quote": quote, "stufe": stufe,
                    "rest_stunden": rest_stunden(grenze, hoch, rate),
                    "unter_mindestlohn": bool(rate) and rate < ml, "mindestlohn": ml})
    out.sort(key=lambda r: -r["quote"])
    return out


def rest_stunden(grenze: float, hochrechnung: float, stundenlohn: float):
    """Stunden bis zur Grenze, auf 0,1 ABgerundet - wer die angezeigten Stunden arbeitet, bleibt sicher darunter."""
    if not stundenlohn:
        return None
    return floor(max(0.0, grenze - hochrechnung) / stundenlohn * 10 + 1e-9) / 10


def naechste_aenderung(db, heute: date = None):
    """Naechste kuenftige Stufe (fuer den Hinweis 'ab 01.01.2027: 633 €, Mindestlohn 14,60 €')."""
    heute = heute or date.today()
    k = [s for s in einstellung(db)["stufen"] if s["ab"] > heute.isoformat()]
    return k[0] if k else None


def grenze(db, stichtag: date) -> float:
    """Minijob-Grenze in €/Monat am Stichtag (aus app_settings 'lohn_grenzen')."""
    return float(stufe_am(db, stichtag)["minijob_grenze"])


def mindestlohn(db, stichtag: date) -> float:
    """Gesetzlicher Mindestlohn in €/h am Stichtag (aus app_settings 'lohn_grenzen')."""
    return float(stufe_am(db, stichtag)["mindestlohn"])
