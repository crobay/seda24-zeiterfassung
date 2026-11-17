"""Cockpit: Objektleitung = Admin-Rechte minus Kunden-Umsaetze (Backend erzwungen), KM-Pruefung beim Zuteilen.

Laeuft NUR gegen die DEV-Datenbank dev_cockpit. Jeder Test laeuft in einer Transaktion, die am Ende
zurueckgerollt wird (commit() in den Endpunkten wird zum Savepoint) - es bleibt nichts in der DB.
Aufruf: cd backend && ./venv/bin/python -m pytest tests/test_cockpit_scope.py -q
"""
import os
import sys
from datetime import datetime, timedelta, date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
assert os.getenv("DATABASE_URL", "").endswith("/dev_cockpit"), "Tests nur gegen dev_cockpit!"

from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.main import app  # noqa: E402
from app.db.database import engine, get_db  # noqa: E402


@pytest.fixture()
def db():
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield session
    finally:
        app.dependency_overrides.clear()
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as c:  # Startup laeuft mit DISABLE_SCHEDULER=1 (DEV-.env)
        yield c


def q(db, sql, **p):
    return db.execute(text(sql), p).fetchall()


def token(db, role):
    email = q(db, "SELECT email FROM users WHERE role = :r ORDER BY id LIMIT 1", r=role)[0][0]
    tk = jwt.encode({"sub": email, "exp": datetime.utcnow() + timedelta(hours=1)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    return {"Authorization": f"Bearer {tk}"}


def ol_headers(db):
    return token(db, "OBJEKTLEITER")


def any_employee(db):
    return q(db, """SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id
                    WHERE u.role = 'MITARBEITER' ORDER BY e.id LIMIT 1""")[0][0]


# ---------- Objektleitung = Admin-Rechte ... ----------

def test_ol_sieht_alles_wie_admin(client, db):
    ol, admin = ol_headers(db), token(db, "ADMIN")
    for path in ("/api/v1/cockpit/objekte", "/api/v1/cockpit/mitarbeiter", "/api/v1/cockpit/dienstplan",
                 f"/api/v1/cockpit/zeiten?von={date.today() - timedelta(days=30)}"):
        a, o = client.get(path, headers=admin), client.get(path, headers=ol)
        assert a.status_code == o.status_code == 200, path
        assert a.json() == o.json(), path
    assert len(client.get("/api/v1/cockpit/objekte", headers=ol).json()) > 1
    h = client.get("/api/v1/cockpit/heute", headers=ol).json()
    assert len(h["schichten"]) == len(client.get("/api/v1/cockpit/heute", headers=admin).json()["schichten"])


def test_ol_akte_jedes_ma_mit_lohn(client, db):
    r = client.get(f"/api/v1/cockpit/mitarbeiter/{any_employee(db)}", headers=ol_headers(db))
    assert r.status_code == 200 and "stundenlohn" in r.json()["stamm"]


def test_ol_rechte_in_me(client, db):
    assert client.get("/api/v1/cockpit/me", headers=ol_headers(db)).json()["rechte"] == {"verwalten": True, "kunden_umsaetze": False, "abschluss": False}
    assert client.get("/api/v1/cockpit/me", headers=token(db, "ADMIN")).json()["rechte"] == {"verwalten": True, "kunden_umsaetze": True, "abschluss": True}


def test_ol_frueher_admin_only_endpunkte_erlaubt(client, db):
    ol = ol_headers(db)
    for path in ("/api/v1/admin/push-settings", "/api/v1/admin/km-distances/all", "/api/v1/messages/admin/inbox",
                 "/api/v1/admin/lohn-uebersicht?year=2026&month=10", "/api/v1/admin/finance-settings",
                 "/api/v1/confirmations/admin/pending-confirmations"):
        assert client.get(path, headers=ol).status_code == 200, path


def test_ol_schicht_und_buchung_bearbeiten_erlaubt(client, db):
    ol = ol_headers(db)
    sid = q(db, "SELECT id FROM schedules ORDER BY id DESC LIMIT 1")[0][0]
    assert client.put(f"/api/v1/admin/schedules/{sid}", json={"notes": "Test Cockpit"}, headers=ol).status_code == 200
    bid = q(db, "SELECT id FROM time_entries WHERE check_out IS NOT NULL ORDER BY id DESC LIMIT 1")[0][0]
    assert client.put(f"/api/v1/admin/bookings/{bid}", json={"notes": "Test Cockpit"}, headers=ol).status_code == 200


def test_ol_branding_erlaubt(client, db):
    assert client.put("/api/v1/cockpit/branding", json={"firma": "Test GmbH"}, headers=ol_headers(db)).status_code == 200


# ---------- ... minus Kunden-Umsaetze (Backend 403) ----------

def test_ol_kunden_umsaetze_403(client, db):
    ol = ol_headers(db)
    assert client.get("/api/v1/admin/customer-revenues?year=2026&month=10", headers=ol).status_code == 403
    assert client.post("/api/v1/admin/customer-revenues", json={"object_id": 1, "year": 2026, "month": 10, "amount": 1}, headers=ol).status_code == 403
    assert client.post("/api/v1/admin/customer-revenues/bulk", json={"year": 2026, "month": 10, "items": []}, headers=ol).status_code == 403


def test_ol_bwa_403(client, db):
    ol = ol_headers(db)
    assert client.get("/api/v1/admin/bwa?year=2026&month=10", headers=ol).status_code == 403
    assert client.put("/api/v1/admin/bwa/fixkosten", json={}, headers=ol).status_code == 403


def test_admin_kunden_umsaetze_und_bwa_200(client, db):
    admin = token(db, "ADMIN")
    assert client.get("/api/v1/admin/customer-revenues?year=2026&month=10", headers=admin).status_code == 200
    assert client.get("/api/v1/admin/bwa?year=2026&month=10", headers=admin).status_code == 200


def test_mitarbeiter_weiter_ohne_adminrechte(client, db):
    ma = token(db, "MITARBEITER")
    assert client.get("/api/v1/cockpit/heute", headers=ma).status_code == 403
    assert client.get("/api/v1/admin/push-settings", headers=ma).status_code == 403
    assert client.get("/api/v1/admin/customer-revenues?year=2026&month=10", headers=ma).status_code == 403


def test_lohnuebersicht_nicht_fuer_mitarbeiter(client, db):
    """Lohndaten aller MA: vorher reichte jeder Login (LIVE-Luecke), jetzt nur Verwaltung."""
    url = "/api/v1/admin/lohn-uebersicht?year=2026&month=10"
    assert client.get(url, headers=token(db, "MITARBEITER")).status_code == 403
    assert client.get(url, headers=ol_headers(db)).status_code == 200
    assert client.get(url, headers=token(db, "ADMIN")).status_code == 200


# ---------- KM-Pruefung beim Zuteilen ----------

def _emp_obj_ohne_km(db):
    return q(db, """SELECT e.id, o.id FROM employees e JOIN users u ON u.id = e.user_id, objects o
                    WHERE u.role = 'MITARBEITER' AND e.is_active AND o.is_active AND o.id NOT IN (19, 999)
                      AND NOT coalesce(o.is_test,false)
                      AND NOT EXISTS (SELECT 1 FROM km_distances k WHERE k.employee_id = e.id AND k.object_id = o.id)
                      AND NOT EXISTS (SELECT 1 FROM employee_object_assignments a WHERE a.employee_id = e.id AND a.object_id = o.id)
                    ORDER BY e.id, o.id LIMIT 1""")[0]


def test_zuteilen_ohne_km_fragt_nach_und_speichert(client, db):
    admin = token(db, "ADMIN")
    emp, obj = _emp_obj_ohne_km(db)
    url = f"/api/v1/cockpit/mitarbeiter/{emp}/objekte"
    r = client.post(url, json={"object_id": obj, "tracking_category": "B"}, headers=admin)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "km_fehlt"
    assert not q(db, "SELECT 1 FROM employee_object_assignments WHERE employee_id = :e AND object_id = :o", e=emp, o=obj)

    r = client.post(url, json={"object_id": obj, "tracking_category": "B", "distance_km": "12,5"}, headers=admin)
    assert r.status_code == 200, r.text
    assert float(q(db, "SELECT distance_km FROM km_distances WHERE employee_id = :e AND object_id = :o", e=emp, o=obj)[0][0]) == 12.5
    assert q(db, "SELECT is_active FROM employee_object_assignments WHERE id = :i", i=r.json()["assignment_id"])[0][0] is True
    assert q(db, "SELECT count(*) FROM audit_log WHERE action = 'km_distance_created' AND entity_id = :i", i=r.json()["km_distance_id"])[0][0] == 1

    # Rueckgaengig (Zuteilung beenden), KM-Strecke bleibt
    assert client.delete(f"{url}/{r.json()['assignment_id']}", headers=admin).status_code == 200
    assert q(db, "SELECT is_active FROM employee_object_assignments WHERE id = :i", i=r.json()["assignment_id"])[0][0] is False


def test_zuteilen_mit_vorhandener_km_ohne_nachfrage(client, db):
    admin = token(db, "ADMIN")
    emp, obj = _emp_obj_ohne_km(db)
    db.execute(text("INSERT INTO km_distances (employee_id, object_id, distance_km, rate_per_km) VALUES (:e, :o, 7, 0.30)"), {"e": emp, "o": obj})
    db.flush()
    r = client.post(f"/api/v1/cockpit/mitarbeiter/{emp}/objekte", json={"object_id": obj}, headers=admin)
    assert r.status_code == 200 and r.json()["km_distance_id"] is None


def test_zuteilen_km_ungueltig_400(client, db):
    emp, obj = _emp_obj_ohne_km(db)
    r = client.post(f"/api/v1/cockpit/mitarbeiter/{emp}/objekte", json={"object_id": obj, "distance_km": "abc"}, headers=token(db, "ADMIN"))
    assert r.status_code == 400
