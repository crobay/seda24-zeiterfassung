"""Stempel-Toleranz 10 Min (Kommen/Gehen mit Dienstplan).

Laeuft NUR gegen die DEV-Datenbank dev_cockpit, jeder Test in einer Transaktion mit Rollback
(commit() in den Endpunkten wird zum Savepoint) - es bleibt nichts in der DB. Telegram wird abgefangen.
Aufruf: cd backend && ./venv/bin/python -m pytest tests/test_stempel_toleranz.py -q
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

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.main import app  # noqa: E402
from app.db.database import engine, get_db  # noqa: E402
from app.api.v1.endpoints import time_entries as te  # noqa: E402

TAG = date.today() - timedelta(days=1)  # Stempel kommen wie aus der Offline-Queue (Handy-Zeit von gestern)


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
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def telegram(monkeypatch):
    gesendet = []
    import app.services.telegram_bot as tb
    monkeypatch.setattr(tb, "notify_admin", lambda text, **kw: gesendet.append((text, kw)))
    return gesendet


def q(db, sql, **p):
    r = db.execute(text(sql), p)
    return r.fetchall() if r.returns_rows else None


def ma(db, nr):
    """MA vorbereiten: offene Eintraege und Schichten am Testtag weg (nur in der Transaktion)."""
    eid, email = q(db, "SELECT e.id, u.email FROM employees e JOIN users u ON u.id = e.user_id WHERE e.personal_nr = :n", n=nr)[0]
    q(db, "DELETE FROM break_entries WHERE time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = :e AND (check_out IS NULL OR check_in::date = :d))", e=eid, d=TAG)
    q(db, "UPDATE km_daily_entries SET time_entry_id = NULL WHERE time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = :e AND (check_out IS NULL OR check_in::date = :d))", e=eid, d=TAG)
    q(db, "UPDATE pending_bookings SET related_time_entry_id = NULL WHERE related_time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = :e AND (check_out IS NULL OR check_in::date = :d))", e=eid, d=TAG)
    q(db, "DELETE FROM time_entries WHERE employee_id = :e AND (check_out IS NULL OR check_in::date = :d)", e=eid, d=TAG)
    q(db, "UPDATE time_entries SET schedule_id = NULL WHERE schedule_id IN (SELECT id FROM schedules WHERE employee_id = :e AND date = :d)", e=eid, d=TAG)
    q(db, "DELETE FROM schedules WHERE employee_id = :e AND date = :d", e=eid, d=TAG)
    tk = jwt.encode({"sub": email, "exp": datetime.utcnow() + timedelta(hours=1)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    return eid, {"Authorization": f"Bearer {tk}"}


def schicht(db, eid, beginn, ende, obj=20):
    q(db, """INSERT INTO schedules (employee_id, object_id, date, start_time, end_time, planned_hours, status)
             VALUES (:e, :o, :d, :b, :x, 3, 'normal')""", e=eid, o=obj, d=TAG, b=beginn, x=ende)


def ts(hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(TAG, datetime.min.time()).replace(hour=h, minute=m).isoformat()


def stempeln(client, h, kommen, gehen, obj=20):
    r = client.post("/api/v1/time-entries/check-in", headers=h, json={"object_id": obj, "client_id": f"t-{kommen}-{gehen}-in",
                                                                      "client_timestamp": ts(kommen)})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/time-entries/check-out", headers=h, json={"client_id": f"t-{kommen}-{gehen}-out",
                                                                       "client_timestamp": ts(gehen)})
    assert r.status_code == 200, r.text
    return r.json()


def antraege(db, entry_id):
    return q(db, "SELECT id, requested_hours, notes FROM pending_bookings WHERE related_time_entry_id = :i AND reason = 'mehrzeit_dienstplan'", i=entry_id)


# ---------- Regel ----------

def test_gezaehltes_fenster_beispiele():
    d = datetime(2026, 11, 17)
    b, e = d.replace(hour=13), d.replace(hour=16)
    t = lambda hh, mm: d.replace(hour=hh, minute=mm)  # noqa: E731
    assert te.gezaehltes_fenster(t(12, 55), t(15, 50), b, e) == (b, t(15, 50), 0)  # frueh kommen, frueh gehen
    assert te.gezaehltes_fenster(t(12, 55), t(16, 10), b, e) == (b, e, 0)          # 10 Min nach Ende: noch Toleranz
    assert te.gezaehltes_fenster(t(13, 5), t(16, 11), b, e) == (t(13, 5), e, 11)   # 11 Min nach Ende: Mehrzeit
    assert te.gezaehltes_fenster(t(12, 0), t(12, 30), b, e) == (b, b, 0)           # ganz vor Schichtbeginn: 0


def test_kommen_sperre_ab_beginn_minus_10(db):
    eid, _ = ma(db, "D0039")  # enforce_min_duration
    schicht(db, eid, "13:00", "16:30")
    stamp = lambda hh, mm: datetime.combine(TAG, datetime.min.time()).replace(hour=hh, minute=mm)  # noqa: E731
    with pytest.raises(HTTPException) as ex:
        te.check_start_not_before_schedule_bie2(eid, 20, stamp(12, 48), db)
    assert ex.value.status_code == 422 and "ab 12:50" in ex.value.detail
    assert te.check_start_not_before_schedule_bie2(eid, 20, stamp(12, 50), db) is None
    assert te.check_start_not_before_schedule_bie2(eid, 20, stamp(12, 48), db, offline=True) is None  # Offline geht nie verloren


# ---------- Stempeln ueber die API (wie Offline-Queue mit client_timestamp) ----------

def test_frueh_kommen_zaehlt_ab_beginn(client, db, telegram):
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:55", "15:50")
    assert r["check_in"].startswith(ts("12:55")[:16]) and r["check_out"].startswith(ts("15:50")[:16])  # echte Zeit gespeichert
    assert r["billed_hours"] == pytest.approx(170 / 60, abs=1e-3)  # 13:00-15:50
    assert "Gezaehlt 13:00-15:50" in r["notes"] and not antraege(db, r["id"]) and not telegram


def test_gehen_bis_10_min_nach_ende(client, db, telegram):
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:55", "16:10")
    assert r["billed_hours"] == pytest.approx(3.0) and "mehrzeit_antrag" not in r
    assert not antraege(db, r["id"]) and not telegram


def test_gehen_spaeter_mehrzeit_antrag(client, db, telegram):
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:58", "16:25")
    assert r["check_out"].startswith(ts("16:25")[:16]) and r["billed_hours"] == pytest.approx(3.0)
    a = antraege(db, r["id"])
    assert len(a) == 1 and float(a[0].requested_hours) == pytest.approx(0.42) and "Mehrzeit 25 Min" in a[0].notes
    assert r["mehrzeit_antrag"] == {"id": a[0].id, "minuten": 25} and "Genehmigung" in r["cap_message"]
    assert len(telegram) == 1 and telegram[0][1]["category"] == "genehmigungen" and telegram[0][1]["reply_markup"]
    # Gehen doppelt gesendet (Offline-Queue): kein zweiter Antrag
    client.post("/api/v1/time-entries/check-out", headers=h, json={"client_id": "t-12:58-16:25-out", "client_timestamp": ts("16:25")})
    assert len(antraege(db, r["id"])) == 1
    # Genehmigen ueber die vorhandene Mehrzeit-Logik: Stunden werden addiert
    from app.services.pending_booking_service import approve_pending_booking_core
    approve_pending_booking_core(db, a[0].id, {}, None)
    assert float(q(db, "SELECT billed_hours FROM time_entries WHERE id = :i", i=r["id"])[0][0]) == pytest.approx(3.42, abs=0.01)


def test_ohne_dienstplan_wie_bisher(client, db, telegram):
    eid, h = ma(db, "D0040")
    r = stempeln(client, h, "12:55", "16:25")
    assert r["billed_hours"] == pytest.approx(3.5) and not antraege(db, r["id"]) and "Gezaehlt" not in (r["notes"] or "")


def test_mindestdauer_zaehlt_ab_beginn(client, db, telegram):
    eid, h = ma(db, "D0039")  # enforce_min_duration: 80 % von 3,5 h = 2:48
    schicht(db, eid, "13:00", "16:30")
    r = client.post("/api/v1/time-entries/check-in", headers=h, json={"object_id": 20, "client_id": "m-in", "client_timestamp": ts("12:50")})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/time-entries/check-out", headers=h, json={"client_id": "m-out", "client_timestamp": ts("15:40")})
    assert r.status_code == 422  # ab 12:50 waeren es 2:50, ab Schichtbeginn erst 2:40
    r = client.post("/api/v1/time-entries/check-out", headers=h, json={"client_id": "m-out2", "client_timestamp": ts("16:35")})
    assert r.status_code == 200 and r.json()["billed_hours"] == pytest.approx(3.5)
    assert not r.json().get("cap_decision_needed") and not antraege(db, r.json()["id"])
