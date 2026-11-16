"""Cockpit-Bereiche: Journal bearbeiten, Dienstplan bearbeiten, Objekt-Detail, KM-Strecken, Abrechnung, Leitstelle.

Nur gegen dev_cockpit, jeder Test in einer Transaktion mit Rollback (siehe test_cockpit_rechte.py).
"""
import os
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
    eid = q(db, "SELECT id FROM time_entries WHERE check_out IS NOT NULL ORDER BY id DESC LIMIT 1")[0][0]
    h = token(db, "ADMIN")
    assert client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "2026-11-10", "kommen": "06:00", "gehen": "05:00"}, headers=h).status_code == 400  # 23 h
    assert client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "2099-01-01", "kommen": "06:00", "gehen": "08:00"}, headers=h).status_code == 400
    assert client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "kaputt"}, headers=h).status_code == 400
    # Nachtschicht: Gehen vor Kommen = naechster Tag
    r = client.put(f"/api/v1/cockpit/zeiten/{eid}", json={"datum": "2026-11-10", "kommen": "22:00", "gehen": "02:00"}, headers=h)
    assert r.status_code == 200 and r.json()["gehen_datum"] == "2026-11-11"


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
