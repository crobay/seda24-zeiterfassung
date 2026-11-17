"""Minijob-Grenze (datumsabhaengig, Hochrechnung bis Monatsende) und Objekt-Marge (nur Admin).
Nur gegen dev_cockpit, jeder Test in einer Transaktion mit Rollback (siehe test_cockpit_rechte.py).
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token, ol_headers  # noqa: E402,F401

API = "/api/v1/cockpit"
JETZT = datetime(2027, 2, 10, 12, 0)     # Februar 2027: Grenze 633 €


def ex(db, sql, **p):
    from sqlalchemy import text
    db.execute(text(sql), p)


def lara(db):
    return q(db, "SELECT id FROM employees WHERE personal_nr = 'D0040'")[0][0]


def februar(db):
    """Lara: 5 x 3 h gestempelt (01.–05.02.) + 12 x 3 h geplant (11.–26.02., Mo–Fr) in Lidl Neu Bie2. Objekt 20 sonst leer."""
    e = lara(db)
    zr = "BETWEEN '2027-02-01' AND '2027-02-28'"
    ex(db, f"UPDATE time_entries SET schedule_id = NULL WHERE schedule_id IN (SELECT id FROM schedules WHERE date {zr})")
    ex(db, f"DELETE FROM break_entries WHERE time_entry_id IN (SELECT id FROM time_entries WHERE check_in::date {zr})")
    ex(db, f"DELETE FROM time_entries WHERE check_in::date {zr}")
    ex(db, f"DELETE FROM km_daily_entries WHERE date {zr}")
    ex(db, f"DELETE FROM push_notifications WHERE schedule_id IN (SELECT id FROM schedules WHERE date {zr})")
    ex(db, f"DELETE FROM shift_change_requests WHERE schedule_id IN (SELECT id FROM schedules WHERE date {zr})")
    ex(db, f"UPDATE schedules SET partner_schedule_id = NULL WHERE date {zr}")
    ex(db, f"DELETE FROM schedules WHERE date {zr}")
    for d in range(1, 6):
        ex(db, """INSERT INTO time_entries (employee_id, object_id, check_in, check_out, billed_hours, hourly_rate)
                  VALUES (:e, 20, :a, :b, 3, 15.5)""", e=e, a=datetime(2027, 2, d, 12, 55), b=datetime(2027, 2, d, 15, 55))
    d = date(2027, 2, 11)
    while d <= date(2027, 2, 26):
        if d.weekday() < 5:
            ex(db, """INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, planned_hours, status)
                      VALUES (:e, 20, :d, :w, '12:55', '15:55', 3, 'normal')""", e=e, d=d, w=d.weekday())
        d += timedelta(days=1)
    ex(db, "DELETE FROM customer_revenues WHERE object_id = 20 AND year = 2027 AND month = 2")
    ex(db, "INSERT INTO customer_revenues (object_id, year, month, revenue) VALUES (20, 2027, 2, 1250)")
    ex(db, "DELETE FROM finance_settings WHERE setting_key LIKE 'lohnnebenkosten_pct%'")
    ex(db, "DELETE FROM app_settings WHERE key IN ('lohn_grenzen', 'objekt_marge')")
    return e


def test_grenze_datumsabhaengig(db):
    from app.services import minijob as mj
    ex(db, "DELETE FROM app_settings WHERE key = 'lohn_grenzen'")
    assert mj.stufe_am(db, date(2026, 12, 31))["minijob_grenze"] == 603
    s = mj.stufe_am(db, date(2027, 1, 1))
    assert s["minijob_grenze"] == 633 and s["mindestlohn"] == 14.60
    assert q(db, "SELECT count(*) FROM app_settings WHERE key = 'lohn_grenzen'")[0][0] == 1      # in der DB, nicht im Code
    assert mj.naechste_aenderung(db, date(2026, 11, 18))["ab"] == "2027-01-01"
    assert mj.grenze(db, date(2026, 11, 30)) == 603.0 and mj.grenze(db, date(2027, 3, 1)) == 633.0
    assert mj.mindestlohn(db, date(2027, 1, 1)) == 14.60


def test_hochrechnung_warnt_vor_monatsende(db):
    from app.services import minijob as mj
    e = februar(db)
    r = [x for x in mj.hochrechnung(db, 2027, 2, JETZT) if x["employee_id"] == e][0]
    ex(db, """INSERT INTO time_entries (employee_id, object_id, check_in, check_out, hourly_rate, service_type)
              VALUES (:e, 999, '2027-02-26', '2027-02-26', -1, 'Urlaub')""", e=e)          # Urlaub "Satz offen" zaehlt 0, nicht -1
    r = [x for x in mj.hochrechnung(db, 2027, 2, JETZT) if x["employee_id"] == e][0]
    assert r["ist"] == 232.5 and r["geplant"] == 558.0 and r["hochrechnung"] == 790.5
    assert r["grenze"] == 633 and r["stufe"] == "ueber" and r["quote"] == 125 and r["rest_stunden"] == 0
    # 5 geplante Schichten weniger -> 558 € = 88 % -> ok; +3 h und +2 h -> ueber; dann 604,50 € = 95 % -> Warnung (ab 90 %)
    ex(db, "DELETE FROM schedules WHERE employee_id = :e AND date BETWEEN '2027-02-22' AND '2027-02-26'", e=e)
    r = [x for x in mj.hochrechnung(db, 2027, 2, JETZT) if x["employee_id"] == e][0]
    assert r["hochrechnung"] == 558.0 and r["quote"] == 88 and r["stufe"] == "ok"
    ex(db, """INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, planned_hours, status)
              VALUES (:e, 20, '2027-02-22', 0, '12:55', '15:55', 3, 'normal'), (:e, 20, '2027-02-23', 1, '12:55', '15:55', 2, 'normal')""", e=e)
    r = [x for x in mj.hochrechnung(db, 2027, 2, JETZT) if x["employee_id"] == e][0]
    assert r["hochrechnung"] == 635.5 and r["stufe"] == "ueber"
    ex(db, "DELETE FROM schedules WHERE employee_id = :e AND date = '2027-02-23'", e=e)
    r = [x for x in mj.hochrechnung(db, 2027, 2, JETZT) if x["employee_id"] == e][0]
    assert r["hochrechnung"] == 604.5 and r["quote"] == 95 and r["stufe"] == "warnung" and r["rest_stunden"] == 1.8


def test_einstellung_aendern_nur_admin(client, db):
    ex(db, "DELETE FROM app_settings WHERE key = 'lohn_grenzen'")
    admin, ol = token(db, "ADMIN"), ol_headers(db)
    assert client.get(f"{API}/einstellungen/lohn-grenzen", headers=ol).status_code == 403
    neu = {"warn_ab_prozent": 85, "stufen": [{"ab": "2027-01-01", "minijob_grenze": 633, "mindestlohn": 14.6},
                                             {"ab": "2026-01-01", "minijob_grenze": 603, "mindestlohn": 13.9}]}
    assert client.put(f"{API}/einstellungen/lohn-grenzen", json=neu, headers=ol).status_code == 403
    r = client.put(f"{API}/einstellungen/lohn-grenzen", json=neu, headers=admin)
    assert r.status_code == 200 and r.json()["stufen"][0]["ab"] == "2026-01-01" and r.json()["warn_ab_prozent"] == 85
    assert client.put(f"{API}/einstellungen/lohn-grenzen", json={"stufen": [{"ab": "x"}]}, headers=admin).status_code == 400
    assert q(db, "SELECT count(*) FROM audit_log WHERE action = 'lohn_grenzen_geaendert' AND created_at > now() - interval '1 minute'")[0][0] == 1


def test_ol_sieht_keine_euro(client, db):
    februar(db)
    r = client.get(f"{API}/minijob?monat=2027-02", headers=ol_headers(db)).json()
    p = r["personen"][0]
    assert "quote" in p and "rest_stunden" in p and not ({"ist", "hochrechnung", "stundenlohn", "grenze"} & set(p))


def test_objekt_marge_hochrechnung_und_warnung(db):
    from app.services import objekt_marge as om
    februar(db)
    r = om.marge(db, 2027, 2, JETZT)
    z = [x for x in r["objekte"] if x["object_id"] == 20][0]
    # Ist 15 h x 15,50 x 1,3 = 302,25; geplant 36 h x 15,50 x 1,3 = 725,40; Umsatz 1250 -> 17,8 % (Ziel 25 %)
    assert z["kosten_ist"] == 302.25 and z["kosten_hochrechnung"] == 1027.65 and z["marge_prozent"] == 17.8
    assert z["umsatz_quelle"] == "BWA" and z["status"] == "unter_ziel"
    w = [x for x in om.warnungen(db, JETZT) if x["object_id"] == 20][0]
    assert w["text"] == "Vorsicht: Lidl Neu Bie2 liegt bei 18 % Marge (Ziel 25 %), wenn es so weitergeht"


def test_objekt_marge_nur_admin(client, db):
    admin, ol = token(db, "ADMIN"), ol_headers(db)
    assert client.get(f"{API}/objekt-marge", headers=ol).status_code == 403
    assert client.put(f"{API}/einstellungen/objekt-marge", json={"ziel_prozent": 20}, headers=ol).status_code == 403
    assert client.get(f"{API}/objekt-marge", headers=admin).status_code == 200
    assert client.put(f"{API}/einstellungen/objekt-marge", json={"ziel_prozent": 99}, headers=admin).status_code == 400
    assert client.put(f"{API}/einstellungen/objekt-marge", json={"ziel_prozent": 22}, headers=admin).json()["ziel_prozent"] == 22
    ls_ol = client.get(f"{API}/leitstelle", headers=ol).json()
    ls_ad = client.get(f"{API}/leitstelle", headers=admin).json()
    assert ls_ol["marge"] is None and isinstance(ls_ad["marge"], list) and "minijob" in ls_ol


def test_marge_umsatz_ohne_stunden(db):
    """Tiefentest: Objekt mit Umsatz, aber ohne Stunden im Monat -> 'ohne_stunden' statt 100 % Marge."""
    from app.services import objekt_marge as om
    februar(db)
    ex(db, "DELETE FROM customer_revenues WHERE object_id = 9 AND year = 2027 AND month = 2")
    ex(db, "INSERT INTO customer_revenues (object_id, year, month, revenue) VALUES (9, 2027, 2, 200)")
    z = [x for x in om.marge(db, 2027, 2, JETZT)["objekte"] if x["object_id"] == 9][0]
    assert z["status"] == "ohne_stunden"

