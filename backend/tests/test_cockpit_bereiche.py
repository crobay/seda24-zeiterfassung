"""Cockpit-Bereiche: Journal bearbeiten, Dienstplan bearbeiten, Objekt-Detail, KM-Strecken, Abrechnung, Leitstelle.

Nur gegen dev_cockpit, jeder Test in einer Transaktion mit Rollback (siehe test_cockpit_rechte.py).
"""
import os

import pytest
from sqlalchemy import text
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token, ol_headers  # noqa: E402,F401  (Fixtures + Hilfen)


def _ma_obj(db):
    return q(db, """SELECT a.employee_id, a.object_id FROM employee_object_assignments a JOIN employees e ON e.id = a.employee_id
                    WHERE coalesce(a.is_active,true) AND e.is_active AND a.object_id NOT IN (19, 999) ORDER BY a.id LIMIT 1""")[0]


# ---------- Journal ----------

def test_zeit_aendern_repariert_gehen_vor_kommen(client, db):
    row = q(db, "SELECT id, check_out FROM time_entries WHERE check_out < check_in ORDER BY id LIMIT 1")
    assert row, "DEV-Kopie sollte die bekannten Faelle enthalten"
    eid, co = row[0]
    r = client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": co.date().isoformat(), "kommen": "08:00", "gehen": "11:30"},
                   headers=ol_headers(db))
    assert r.status_code == 200, r.text
    ci, co2 = q(db, "SELECT check_in, check_out FROM time_entries WHERE id = :i", i=eid)[0]
    assert ci.date() == co2.date() == co.date() and co2 > ci
    assert q(db, "SELECT count(*) FROM audit_log WHERE action = 'booking_updated' AND entity_id = :i", i=eid)[0][0] >= 1


def test_zeit_pruefung(client, db):
    eid = q(db, """SELECT id FROM time_entries t WHERE check_out IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM km_daily_entries k WHERE k.time_entry_id = t.id) ORDER BY id DESC LIMIT 1""")[0][0]
    h = token(db, "ADMIN")
    assert client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "2026-11-10", "kommen": "06:00", "gehen": "05:00"}, headers=h).status_code == 400  # 23 h
    assert client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "2099-01-01", "kommen": "06:00", "gehen": "08:00"}, headers=h).status_code == 400
    assert client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "kaputt"}, headers=h).status_code == 400
    # Nachtschicht: Gehen vor Kommen = naechster Tag
    r = client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "2026-11-10", "kommen": "22:00", "gehen": "02:00"}, headers=h)
    assert r.status_code == 200 and r.json()["gehen_datum"] == "2026-11-11"


def test_zeit_verschieben_km_konflikt(client, db):
    """Tiefentest: Eintrag mit KM auf einen Tag, an dem MA/Objekt schon KM hat -> 409 mit Klartext statt 500."""
    r = q(db, """SELECT k.time_entry_id, k.employee_id, k.object_id FROM km_daily_entries k WHERE k.time_entry_id IS NOT NULL
                 AND k.object_id IS NOT NULL ORDER BY k.id DESC LIMIT 1""")
    if not r:
        pytest.skip("keine KM-Daten")
    te, emp, obj = r[0]
    db.execute(text("DELETE FROM km_daily_entries WHERE employee_id = :e AND object_id = :o AND date = '2026-09-07'"), {"e": emp, "o": obj})
    db.execute(text("""INSERT INTO km_daily_entries (employee_id, date, object_id, distance_km, amount, is_billable)
                       VALUES (:e, '2026-09-07', :o, 1, 0.3, true)"""), {"e": emp, "o": obj})
    h = token(db, "ADMIN")
    x = client.put(f"/api/v1/cockpit/zeiten/{te}", json={"datum": "2026-09-07", "kommen": "08:00", "gehen": "09:00"}, headers=h)
    assert x.status_code == 409 and "KM-Buchung" in x.json()["detail"]


def test_zeit_anlegen_und_loeschen(client, db):
    emp, obj = _ma_obj(db)
    h = ol_headers(db)
    r = client.post("/api/v1/cockpit/zeiten", json={"employee_id": emp, "object_id": obj, "datum": "2026-11-10",
                                                    "kommen": "09:00", "gehen": "11:00"}, headers=h)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    assert r.json()["kommen"] == "09:00" and r.json()["gehen"] == "11:00"
    d = client.delete(f"/api/v1/cockpit/zeiten/{eid}", headers=h)
    assert d.status_code == 200 and d.json()["alt"]["id"] == eid
    assert not q(db, "SELECT 1 FROM time_entries WHERE id = :i", i=eid)


def test_zeiten_pruef_filter(client, db):
    r = client.get("/api/v1/cockpit/zeiten?pruef=gehen_vor_kommen", headers=token(db, "ADMIN")).json()
    assert all("Gehen vor Kommen" in e["hinweis"] for e in r["eintraege"])


# ---------- Dienstplan ----------

def test_schicht_anlegen_aendern_loeschen(client, db):
    emp, obj = _ma_obj(db)
    h = ol_headers(db)
    tag = (date.today() + timedelta(days=30)).isoformat()
    r = client.post("/api/v1/cockpit/dienstplan", json={"employee_id": emp, "object_id": obj, "datum": tag, "beginn": "08:00", "ende": "10:00"}, headers=h)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert client.post("/api/v1/cockpit/dienstplan", json={"employee_id": emp, "object_id": obj, "datum": tag, "beginn": "10:00", "ende": "09:00"}, headers=h).status_code == 400
    u = client.put(f"/api/v1/cockpit/dienstplan/{sid}", json={"employee_id": emp, "object_id": obj, "datum": tag, "beginn": "09:00", "ende": "12:30", "fahrer": False}, headers=h)
    assert u.status_code == 200 and u.json()["beginn"] == "09:00" and u.json()["fahrer"] is False
    assert client.delete(f"/api/v1/cockpit/dienstplan/{sid}", headers=h).status_code == 200
    assert not q(db, "SELECT 1 FROM schedules WHERE id = :i", i=sid)


# ---------- Objekt ----------

def test_objekt_detail_umsatz_nur_admin(client, db):
    oid = _ma_obj(db)[1]
    a = client.get(f"/api/v1/cockpit/objekte/{oid}", headers=token(db, "ADMIN")).json()
    o = client.get(f"/api/v1/cockpit/objekte/{oid}", headers=ol_headers(db)).json()
    assert "umsatz" in a["stamm"] and "umsatz" not in o["stamm"]
    assert o["mitarbeiter"] and "monat" in o


def test_objekt_aendern(client, db):
    oid = _ma_obj(db)[1]
    h = ol_headers(db)
    assert client.put(f"/api/v1/cockpit/objekte/{oid}", json={"name": "  "}, headers=h).status_code == 400
    r = client.put(f"/api/v1/cockpit/objekte/{oid}", json={"key_location": "Testschluessel", "monthly_amount": 999}, headers=h)
    assert r.status_code == 200
    kl, ma = q(db, "SELECT key_location, monthly_amount FROM objects WHERE id = :i", i=oid)[0]
    assert kl == "Testschluessel" and ma != 999  # Umsatzfelder sind nicht ueber das Cockpit aenderbar


# ---------- KM ----------

def test_km_strecke_setzen_und_aendern(client, db):
    emp, obj = q(db, """SELECT a.employee_id, a.object_id FROM employee_object_assignments a
                        WHERE NOT EXISTS (SELECT 1 FROM km_distances k WHERE k.employee_id = a.employee_id AND k.object_id = a.object_id)
                        LIMIT 1""")[0] if q(db, """SELECT 1 FROM employee_object_assignments a WHERE NOT EXISTS
                        (SELECT 1 FROM km_distances k WHERE k.employee_id = a.employee_id AND k.object_id = a.object_id)""") else _ma_obj(db)
    h = ol_headers(db)
    r = client.put("/api/v1/cockpit/km-strecken", json={"employee_id": emp, "object_id": obj, "distance_km": "8,4"}, headers=h)
    assert r.status_code == 200 and r.json()["distance_km"] == 8.4
    r2 = client.put("/api/v1/cockpit/km-strecken", json={"employee_id": emp, "object_id": obj, "distance_km": 9}, headers=h)
    assert r2.json()["id"] == r.json()["id"] and r2.json()["alt"] == {"distance_km": 8.4}
    assert client.put("/api/v1/cockpit/km-strecken", json={"employee_id": emp, "object_id": obj, "distance_km": 999}, headers=h).status_code == 400


# ---------- Abrechnung / Leitstelle ----------

def test_abrechnung_und_leitstelle(client, db):
    r = client.get("/api/v1/cockpit/abrechnung?year=2026&month=10", headers=ol_headers(db))
    assert r.status_code == 200 and r.json()["zeilen"] and "summe" in r.json()
    assert client.get("/api/v1/cockpit/abrechnung?year=2026&month=10", headers=token(db, "MITARBEITER")).status_code == 403
    ls = client.get("/api/v1/cockpit/leitstelle", headers=ol_headers(db))
    assert ls.status_code == 200 and len(ls.json()["woche"]) == 7 and ls.json()["abschluss"]["pruefpunkte"]


def test_pruefpunkte_fuer_abrechnungsmonat(client, db):
    h = token(db, "ADMIN")
    r = client.get("/api/v1/cockpit/zeiten?pruef=alle&monat=2026-10", headers=h).json()
    assert r["monat"] == "2026-10" and r["von"] == "2026-10-01" and r["bis"] == "2026-10-31"
    ab = client.get("/api/v1/cockpit/abrechnung?year=2026&month=10", headers=h).json()
    assert sum(z["pruefpunkte"] for z in ab["zeilen"]) == len(r["eintraege"])  # Zahl in der Abrechnung = Liste hinter dem Link
    assert client.get("/api/v1/cockpit/zeiten?pruef=alle&monat=kaputt", headers=h).status_code == 400


# ---------- Branding ----------

def test_branding_felder_und_pruefung(client, db):
    h = token(db, "ADMIN")
    gut = {"akzent": "#1E537C", "cta": "#F9B233", "cta_text": "#0E2A40", "leiste": "#1E537C", "leiste_text": "#FFFFFF",
           "logo_url": "/brand/seda24/logo-seda24-weiss.svg", "schrift_css": "/brand/seda24/fonts/fonts.css",
           "schrift_titel": "Poppins", "schrift_text": "Open Sans"}
    r = client.put("/api/v1/cockpit/branding", json=gut, headers=h)
    assert r.status_code == 200, r.text
    assert {k: r.json()[k] for k in gut} == gut
    assert client.get("/api/v1/cockpit/branding").json()["cta"] == "#F9B233"
    for k, v in [("cta", "gold"), ("leiste", "#12345"), ("schrift_css", "https://fonts.example.com/x.css"),
                 ("schrift_css", "/x.js"), ("schrift_titel", "Poppins'; }"), ("logo_url", "javascript:alert(1)")]:
        assert client.put("/api/v1/cockpit/branding", json={k: v}, headers=h).status_code == 400, (k, v)
    assert client.put("/api/v1/cockpit/branding", json={"cta": ""}, headers=h).json()["cta"] == ""  # leer = Standard
    assert client.put("/api/v1/cockpit/branding", json={"cta": "#000000"}, headers=token(db, "MITARBEITER")).status_code in (401, 403)


def test_pruefpunkt_geplant_nicht_gestempelt(client, db):
    """Tiefentest: Schicht geplant, kein Stempel, nicht abwesend -> Pruefpunkt 'ohne_stempel' (Leitstelle + Zeiten)."""
    from app.api.v1.endpoints.cockpit import ohne_stempel
    emp, obj = _ma_obj(db)
    d = date.today() - timedelta(days=1) if date.today().day > 1 else date.today()
    db.execute(text("""INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, planned_hours, status, created_at, updated_at)
                       VALUES (:e, :o, :d, :w, '04:01', '04:59', 1, 'normal', now(), now())"""), {"e": emp, "o": obj, "d": d, "w": d.weekday()})
    db.execute(text("DELETE FROM time_entries WHERE employee_id = :e AND check_in::date = :d"), {"e": emp, "d": d})
    if d == date.today():
        return                                                                    # am 1. des Monats gibt es noch kein "gestern"
    m0 = d.replace(day=1)
    z = [x for x in ohne_stempel(db, m0, d) if x["employee_id"] == emp and x["kommen"] == "04:01"]
    assert z and z[0]["fehlt"] and z[0]["hinweis"] == "geplant, nicht gestempelt"
    r = client.get(f"/api/v1/cockpit/zeiten?pruef=ohne_stempel&monat={d:%Y-%m}", headers=ol_headers(db)).json()
    assert any(x["schicht_id"] == z[0]["schicht_id"] for x in r["eintraege"])
    ls = client.get("/api/v1/cockpit/leitstelle", headers=ol_headers(db)).json()
    assert any(p["key"] == "ohne_stempel" and p["n"] >= 1 for p in ls["abschluss"]["pruefpunkte"])


def test_nachtrag_fahrer_bekommt_km(client, db):
    """Tiefentest: Nachtrag im Cockpit fuer eine Fahrer-Schicht legt KM-Geld an (wie beim Stempeln), sonst nicht."""
    r = q(db, """SELECT k.employee_id, k.object_id FROM km_distances k JOIN employees e ON e.id = k.employee_id
                 WHERE e.is_active AND NOT coalesce(e.is_test, false) AND k.distance_km > 0 ORDER BY k.employee_id LIMIT 1""")
    if not r:
        pytest.skip("keine KM-Strecken")
    emp, obj = r[0]
    d = date.today() - timedelta(days=2)
    db.execute(text("DELETE FROM km_daily_entries WHERE employee_id = :e AND date = :d"), {"e": emp, "d": d})
    db.execute(text("DELETE FROM time_entries WHERE employee_id = :e AND check_in::date = :d"), {"e": emp, "d": d})
    sid = db.execute(text("""INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, planned_hours, status, is_driver, created_at, updated_at)
                             VALUES (:e, :o, :d, :w, '04:00', '05:00', 1, 'normal', true, now(), now()) RETURNING id"""),
                     {"e": emp, "o": obj, "d": d, "w": d.weekday()}).scalar()
    x = client.post("/api/v1/cockpit/zeiten", json={"employee_id": emp, "object_id": obj, "datum": d.isoformat(), "kommen": "04:00",
                                                    "gehen": "05:00", "schedule_id": sid}, headers=ol_headers(db))
    assert x.status_code == 200, x.text
    km = q(db, "SELECT distance_km, is_billable FROM km_daily_entries WHERE employee_id = :e AND date = :d", e=emp, d=d)
    assert km and float(km[0][0]) > 0 and km[0][1]


def test_lohnfortzahlung_ist_kein_stempel(client, db):
    """Tiefentest: Krank-Lohnfortzahlung (Zeiteintrag am Objekt, service_type 'Krank') erscheint in 'Heute' nicht als Stempel."""
    emp, obj = _ma_obj(db)
    tid = db.execute(text("""INSERT INTO time_entries (employee_id, object_id, check_in, check_out, billed_hours, hourly_rate, service_type, notes)
                             VALUES (:e, :o, date_trunc('day', now()) + interval '4 hours', date_trunc('day', now()) + interval '5 hours', 1, 15,
                                     'Krank', 'Lohnfortzahlung - Test') RETURNING id"""), {"e": emp, "o": obj}).scalar()
    h = client.get("/api/v1/cockpit/heute", headers=ol_headers(db)).json()
    assert all(x["eintrag_id"] != tid for x in h["ohne_schicht"]) and all(x.get("eintrag_id") != tid for x in h["schichten"])


def test_abschluss_karte_zeigt_vormonat_bis_exporttag(client, db, monkeypatch):
    """Tiefentest: am 04.01. (Exporttag Dezember) zeigt die Leitstelle den Abschluss Dezember, am 05.01. den Januar."""
    import app.api.v1.endpoints.cockpit as ck
    from datetime import date as _date

    class D(_date):
        heute = _date(2027, 1, 4)

        @classmethod
        def today(cls):
            return cls.heute
    monkeypatch.setattr(ck, "date", D)
    assert client.get("/api/v1/cockpit/leitstelle", headers=ol_headers(db)).json()["abschluss"]["monat"] == "2026-12"
    D.heute = _date(2027, 1, 5)
    a = client.get("/api/v1/cockpit/leitstelle", headers=ol_headers(db)).json()["abschluss"]
    assert a["monat"] == "2027-01" and a["pruefpunkte"][0]["link"].endswith("&monat=2027-01")


def test_protokoll_mit_systemeintrag_ohne_benutzer(client, db):
    """Tiefentest/QA: Audit-Eintrag ohne user_id (Deploy-Test raeumt auf) liess das Aenderungsprotokoll mit 500 abbrechen."""
    db.execute(text("INSERT INTO audit_log (user_id, action, details, created_at) VALUES (NULL, 'test_entries_deleted', 'Test', now())"))
    r = client.get("/api/v1/admin/audit-log?limit=50", headers=token(db, "ADMIN"))
    assert r.status_code == 200, r.text



def test_protokoll_mit_altem_textformat(client, db):
    """LIVE 18.11.: aeltere Eintraege speichern 'feld=wert' statt JSON -> Satzbildung brach mit 500 ab."""
    db.execute(text("""INSERT INTO audit_log (user_id, action, old_value, new_value, created_at)
                       VALUES (NULL, 'booking_updated', 'check_out=2026-10-26 16:37:45', 'check_out=2026-10-26 16:38:00', now())"""))
    r = client.get("/api/v1/admin/audit-log?limit=500&action=booking_updated", headers=token(db, "ADMIN"))
    assert r.status_code == 200, r.text
    e = next(x for x in r.json() if x["action"] == "booking_updated" and x["old_value"] == "check_out=2026-10-26 16:37:45")
    assert "hat die Buchung" in e["message"]
