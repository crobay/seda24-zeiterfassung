"""Cockpit: Sichtbereich Objektleitung (Backend erzwungen) und KM-Pruefung beim Zuteilen.

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


@pytest.fixture()
def ol(db):
    """Objektleitung mit genau einem Objekt (das mit den meisten Schichten), unabhaengig vom DB-Stand."""
    uid = q(db, "SELECT id FROM users WHERE role = 'OBJEKTLEITER' ORDER BY id LIMIT 1")[0][0]
    obj = q(db, """SELECT object_id FROM schedules WHERE object_id NOT IN (19, 999) AND date >= current_date - 30
                   GROUP BY 1 ORDER BY count(*) DESC LIMIT 1""")[0][0]
    db.execute(text("DELETE FROM user_object_assignments WHERE user_id = :u"), {"u": uid})
    db.execute(text("INSERT INTO user_object_assignments (user_id, object_id, is_active) VALUES (:u, :o, true)"), {"u": uid, "o": obj})
    db.flush()
    return {"headers": token(db, "OBJEKTLEITER"), "object_id": obj, "user_id": uid}


def foreign_object(db, own):
    return q(db, "SELECT id FROM objects WHERE id NOT IN (19, 999, :o) AND NOT coalesce(is_test,false) ORDER BY id LIMIT 1", o=own)[0][0]


def foreign_employee(db, own_obj):
    """MA ohne Zuweisung/Schicht am eigenen Objekt."""
    return q(db, """SELECT e.id FROM employees e JOIN users u ON u.id = e.user_id WHERE u.role = 'MITARBEITER'
                    AND e.id NOT IN (SELECT employee_id FROM employee_object_assignments WHERE object_id = :o)
                    AND e.id NOT IN (SELECT employee_id FROM schedules WHERE object_id = :o
                                     AND date BETWEEN current_date - 45 AND current_date + 60)
                    ORDER BY e.id LIMIT 1""", o=own_obj)[0][0]


def own_employee(db, own_obj):
    return q(db, """SELECT employee_id FROM employee_object_assignments WHERE object_id = :o AND coalesce(is_active,true)
                    UNION SELECT employee_id FROM schedules WHERE object_id = :o
                    AND date BETWEEN current_date - 45 AND current_date + 60 LIMIT 1""", o=own_obj)[0][0]


# ---------- Lesen: Objektleitung sieht nur ihren Bereich ----------

def test_ol_objekte_nur_eigene(client, db, ol):
    r = client.get("/api/v1/cockpit/objekte", headers=ol["headers"])
    assert r.status_code == 200
    assert {o["id"] for o in r.json()} == {ol["object_id"]}


def test_admin_sieht_alle_objekte(client, db):
    r = client.get("/api/v1/cockpit/objekte", headers=token(db, "ADMIN"))
    assert r.status_code == 200 and len(r.json()) > 1


def test_ol_heute_dienstplan_zeiten_nur_eigene_objekte(client, db, ol):
    name = q(db, "SELECT name FROM objects WHERE id = :o", o=ol["object_id"])[0][0]
    h = client.get("/api/v1/cockpit/heute", headers=ol["headers"]).json()
    assert all(s["object_id"] == ol["object_id"] for s in h["schichten"])
    d = client.get("/api/v1/cockpit/dienstplan", headers=ol["headers"]).json()
    assert all(s["objekt"] == name for tag in d["tage"] for s in tag["schichten"])
    z = client.get(f"/api/v1/cockpit/zeiten?von={date.today() - timedelta(days=60)}", headers=ol["headers"]).json()
    assert all(e["objekt"] == name for e in z["eintraege"])


def test_ol_mitarbeiterliste_ohne_fremde(client, db, ol):
    ids = {m["id"] for m in client.get("/api/v1/cockpit/mitarbeiter", headers=ol["headers"]).json()}
    assert own_employee(db, ol["object_id"]) in ids
    assert foreign_employee(db, ol["object_id"]) not in ids


def test_ol_fremde_akte_403_eigene_200(client, db, ol):
    assert client.get(f"/api/v1/cockpit/mitarbeiter/{foreign_employee(db, ol['object_id'])}", headers=ol["headers"]).status_code == 403
    assert client.get(f"/api/v1/cockpit/mitarbeiter/{own_employee(db, ol['object_id'])}", headers=ol["headers"]).status_code == 200


def test_ol_ohne_objekte_sieht_nichts(client, db, ol):
    db.execute(text("DELETE FROM user_object_assignments WHERE user_id = :u"), {"u": ol["user_id"]})
    db.flush()
    assert client.get("/api/v1/cockpit/objekte", headers=ol["headers"]).json() == []
    assert client.get("/api/v1/cockpit/mitarbeiter", headers=ol["headers"]).json() == []
    assert client.get("/api/v1/cockpit/heute", headers=ol["headers"]).json()["schichten"] == []


# ---------- Schreiben: alte Admin-Endpunkte, 403 bei fremden Objekten/MA ----------

def test_ol_fremde_schicht_aendern_403(client, db, ol):
    sid = q(db, "SELECT id FROM schedules WHERE object_id NOT IN (:o, 19, 999) ORDER BY id DESC LIMIT 1", o=ol["object_id"])[0][0]
    r = client.put(f"/api/v1/admin/schedules/{sid}", json={"notes": "x"}, headers=ol["headers"])
    assert r.status_code == 403
    r = client.delete(f"/api/v1/admin/schedules/{sid}", headers=ol["headers"])
    assert r.status_code == 403


def test_ol_eigene_schicht_aendern_erlaubt(client, db, ol):
    sid = q(db, "SELECT id FROM schedules WHERE object_id = :o ORDER BY id DESC LIMIT 1", o=ol["object_id"])[0][0]
    r = client.put(f"/api/v1/admin/schedules/{sid}", json={"notes": "Test Cockpit"}, headers=ol["headers"])
    assert r.status_code != 403


def test_ol_buchung_fuer_fremdes_objekt_403(client, db, ol):
    body = {"employee_id": own_employee(db, ol["object_id"]), "object_id": foreign_object(db, ol["object_id"]),
            "check_in": "2026-11-10T08:00:00", "check_out": "2026-11-10T10:00:00"}
    assert client.post("/api/v1/admin/bookings/manual", json=body, headers=ol["headers"]).status_code == 403


def test_ol_fremde_buchung_aendern_403(client, db, ol):
    bid = q(db, "SELECT id FROM time_entries WHERE object_id NOT IN (:o, 19, 999) ORDER BY id DESC LIMIT 1", o=ol["object_id"])[0][0]
    assert client.put(f"/api/v1/admin/bookings/{bid}", json={"notes": "x"}, headers=ol["headers"]).status_code == 403


def test_ol_zuweisung_fremder_ma_403(client, db, ol):
    body = {"employee_id": foreign_employee(db, ol["object_id"]), "object_id": ol["object_id"]}
    assert client.post("/api/v1/admin/assignments", json=body, headers=ol["headers"]).status_code == 403


def test_ol_cockpit_zuteilen_fremdes_objekt_403(client, db, ol):
    emp = own_employee(db, ol["object_id"])
    r = client.post(f"/api/v1/cockpit/mitarbeiter/{emp}/objekte", json={"object_id": foreign_object(db, ol["object_id"])}, headers=ol["headers"])
    assert r.status_code == 403


def test_ol_urlaubsantrag_fremder_ma_403(client, db, ol):
    fe = foreign_employee(db, ol["object_id"])
    rid = db.execute(text("""INSERT INTO vacation_requests (employee_id, start_date, end_date, working_days, status, requested_at)
                             VALUES (:e, '2027-03-01', '2027-03-02', 2, 'pending', now()) RETURNING id"""), {"e": fe}).scalar()
    db.flush()
    assert client.post(f"/api/v1/cockpit/aktion/urlaub/{rid}", json={"aktion": "genehmigen"}, headers=ol["headers"]).status_code == 403
    assert client.put(f"/api/v1/vacation/admin/requests/{rid}", json={"status": "approved"}, headers=ol["headers"]).status_code == 403
    assert q(db, "SELECT status FROM vacation_requests WHERE id = :i", i=rid)[0][0] == "pending"


def test_ol_branding_403(client, db, ol):
    assert client.put("/api/v1/cockpit/branding", json={"firma": "X"}, headers=ol["headers"]).status_code == 403


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
