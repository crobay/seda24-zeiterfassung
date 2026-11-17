"""Objekt-Marge (NUR Admin): Personalkosten je Objekt gegen Kundenumsatz, mit Hochrechnung fuer den laufenden Monat.

Daten, die schon da sind:
  - Umsatz: customer_revenues (je Objekt/Monat, gepflegt in der BWA), sonst objects.monthly_amount_netto (Vertrag)
  - Stunden: time_entries.billed_hours x time_entries.hourly_rate (gleiche Rechnung wie die Mini-BWA)
  - Lohnnebenkosten: finance_settings lohnnebenkosten_pct[_JJJJ_MM] (Standard 30 %), wie in der BWA
  - KM-Geld: km_daily_entries (is_billable, is_longest_trip) je Objekt
Hochrechnung: Ist bis jetzt + noch geplante Schichten bis Monatsende x Stundenlohn des MA x (1 + LNK).
Ziel-Marge (Standard 25 %) in app_settings 'objekt_marge' {"ziel_prozent": 25}.
"""
import json
from calendar import monthrange
from datetime import date, datetime, time

from sqlalchemy import text

KEY = "objekt_marge"
DEFAULT = {"ziel_prozent": 25}
OBJ_URLAUB, OBJ_KRANK = 999, 19


def einstellung(db) -> dict:
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": KEY}).fetchone()
    return {**DEFAULT, **(json.loads(r[0]) if r else {})}


def speichern(db, ziel: float, user_id: int) -> dict:
    from app.services.booking_service import log_audit
    ziel = float(ziel)
    if not 0 <= ziel <= 80:
        raise ValueError("Ziel-Marge 0–80 %")
    alt = einstellung(db)
    wert = {**alt, "ziel_prozent": round(ziel, 1)}
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": KEY, "v": json.dumps(wert), "u": user_id})
    log_audit(db, user_id, None, "objekt_marge_ziel", entity_type="setting", old_value=alt, new_value=wert,
              details=f"Ziel-Marge je Objekt auf {wert['ziel_prozent']:g} % gesetzt")
    db.commit()
    return wert


def _lnk_pct(db, jahr, monat):
    s = {r[0]: r[1] for r in db.execute(text("SELECT setting_key, setting_value FROM finance_settings")).fetchall()}
    return float(s.get(f"lohnnebenkosten_pct_{jahr}_{monat:02d}", s.get("lohnnebenkosten_pct", "30")))


def marge(db, jahr: int, monat: int, jetzt: datetime = None) -> dict:
    jetzt = jetzt or datetime.now()
    m0 = date(jahr, monat, 1)
    m1 = date(jahr, monat, monthrange(jahr, monat)[1])
    lnk = _lnk_pct(db, jahr, monat)
    f = 1 + lnk / 100
    ziel = einstellung(db)["ziel_prozent"]
    objs = db.execute(text(f"""SELECT o.id, o.name, o.monthly_amount_netto, r.revenue FROM objects o
                               LEFT JOIN customer_revenues r ON r.object_id = o.id AND r.year = :y AND r.month = :m
                               WHERE coalesce(o.is_active, true) AND NOT coalesce(o.is_test, false)
                                 AND o.id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK})"""), {"y": jahr, "m": monat}).mappings().all()
    ist = {r["object_id"]: (float(r["kosten"]), float(r["std"])) for r in db.execute(text(f"""
        SELECT t.object_id, sum(coalesce(t.billed_hours, 0) * coalesce(t.hourly_rate, 15.0)) AS kosten, sum(coalesce(t.billed_hours, 0)) AS std
          FROM time_entries t JOIN employees e ON e.id = t.employee_id
         WHERE t.check_in BETWEEN :a AND :b AND t.object_id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK}) AND NOT coalesce(e.is_test, false)
         GROUP BY 1"""), {"a": datetime.combine(m0, time(0)), "b": datetime.combine(m1, time(23, 59, 59))}).mappings()}
    km = {r["object_id"]: float(r["eur"]) for r in db.execute(text("""
        SELECT object_id, sum(amount) AS eur FROM km_daily_entries
         WHERE date BETWEEN :a AND :b AND is_billable AND is_longest_trip AND object_id IS NOT NULL GROUP BY 1"""),
        {"a": m0, "b": m1}).mappings()}
    plan = {}
    for s in db.execute(text(f"""SELECT s.object_id, s.date, s.start_time, s.end_time, s.planned_hours, e.hourly_rate
                                 FROM schedules s JOIN employees e ON e.id = s.employee_id
                                 WHERE s.date BETWEEN :a AND :b AND s.status IN ('normal', 'vertretung') AND NOT coalesce(e.is_test, false)
                                   AND s.start_time IS NOT NULL AND s.end_time IS NOT NULL AND s.object_id NOT IN ({OBJ_URLAUB}, {OBJ_KRANK})
                                   AND NOT EXISTS (SELECT 1 FROM time_entries t WHERE t.schedule_id = s.id)"""),
                        {"a": max(m0, jetzt.date()), "b": m1}).mappings():
        if s["date"] > jetzt.date() or s["start_time"] > jetzt.time():
            if s["planned_hours"]:
                h = float(s["planned_hours"])
            else:
                mi = (s["end_time"].hour * 60 + s["end_time"].minute) - (s["start_time"].hour * 60 + s["start_time"].minute)
                h = (mi if mi > 0 else mi + 1440) / 60
            k = plan.setdefault(s["object_id"], [0.0, 0.0])
            k[0] += h * float(s["hourly_rate"] or 15.0)
            k[1] += h
    zeilen = []
    for o in objs:
        umsatz = o["revenue"] if o["revenue"] is not None else (float(o["monthly_amount_netto"]) if o["monthly_amount_netto"] else None)
        lohn_ist, std_ist = ist.get(o["id"], (0.0, 0.0))
        lohn_plan, std_plan = plan.get(o["id"], (0.0, 0.0))
        kosten_ist = lohn_ist * f + km.get(o["id"], 0.0)
        kosten = kosten_ist + lohn_plan * f
        if not umsatz and not kosten:
            continue
        m = round((umsatz - kosten) / umsatz * 100, 1) if umsatz else None
        zeilen.append({"object_id": o["id"], "objekt": o["name"], "umsatz": round(float(umsatz), 2) if umsatz else None,
                       "umsatz_quelle": "BWA" if o["revenue"] is not None else ("Vertrag" if umsatz else None),
                       "stunden_ist": round(std_ist, 1), "stunden_geplant": round(std_plan, 1),
                       "lohn_ist": round(lohn_ist, 2), "km": round(km.get(o["id"], 0.0), 2),
                       "kosten_ist": round(kosten_ist, 2), "kosten_hochrechnung": round(kosten, 2),
                       "marge_prozent": m, "ziel_prozent": ziel,
                       # Umsatz ohne jede Stunde = Objekt nicht geplant/gestempelt (sonst 100 % Marge, die es nicht gibt)
                       "status": "ohne_umsatz" if m is None else ("ohne_stunden" if not std_ist and not std_plan
                                                                    else ("unter_ziel" if m < ziel else "ok"))})
    zeilen.sort(key=lambda z: (z["marge_prozent"] is None, z["marge_prozent"] if z["marge_prozent"] is not None else 0))
    u = sum(z["umsatz"] or 0 for z in zeilen)
    k = sum(z["kosten_hochrechnung"] for z in zeilen if z["umsatz"])
    return {"monat": f"{jahr}-{monat:02d}", "lnk_prozent": lnk, "ziel_prozent": ziel, "objekte": zeilen,
            "gesamt": {"umsatz": round(u, 2), "kosten": round(k, 2), "marge_prozent": round((u - k) / u * 100, 1) if u else None}}


def warnungen(db, jetzt: datetime = None) -> list:
    """Leitstelle: 'Vorsicht: Objekt X liegt bei 18 % Marge (Ziel 25 %), wenn es so weitergeht'."""
    jetzt = jetzt or datetime.now()
    r = marge(db, jetzt.year, jetzt.month, jetzt)
    return [{"object_id": z["object_id"], "objekt": z["objekt"], "marge_prozent": z["marge_prozent"], "ziel_prozent": z["ziel_prozent"],
             "text": f"Vorsicht: {z['objekt']} liegt bei {z['marge_prozent']:.0f} % Marge (Ziel {z['ziel_prozent']:g} %), wenn es so weitergeht"}
            for z in r["objekte"] if z["status"] == "unter_ziel"]
