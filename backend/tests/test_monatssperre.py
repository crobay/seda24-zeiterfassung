"""Monatssperre (DB-Trigger migrations/monatssperre.sql): abgeschlossener Monat ist ueber JEDEN Weg gesperrt -
Admin, Cockpit, MA-App, direkt per SQL (Scheduler/Skripte). API liefert 423 mit Klartext. Wieder oeffnen hebt die
Sperre auf. Nur dev_cockpit, Transaktion mit Rollback."""
import os
import sys
from datetime import datetime, timedelta

import pytest
from jose import jwt
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token  # noqa: E402,F401


def sperren(db, monat="2026-10", status="abgeschlossen"):
    db.execute(text("""INSERT INTO monatsabschluss (monat, status) VALUES (:m, :s)
                       ON CONFLICT (monat) DO UPDATE SET status = :s"""), {"m": monat, "s": status})


def eintrag(db, monat="2026-10"):
    r = q(db, """SELECT t.id, t.employee_id, u.email FROM time_entries t JOIN employees e ON e.id = t.employee_id
                 JOIN users u ON u.id = e.user_id WHERE to_char(t.check_in, 'YYYY-MM') = :m AND t.check_out IS NOT NULL
                 AND t.object_id <> 999 ORDER BY t.id LIMIT 1""", m=monat)
    return r[0]


def ma_header(email):
    tk = jwt.encode({"sub": email, "exp": datetime.utcnow() + timedelta(hours=1)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    return {"Authorization": f"Bearer {tk}"}


def gesperrt_sql(db, sql, **p):
    db.execute(text("SAVEPOINT t"))
    try:
        with pytest.raises(DBAPIError) as e:
            db.execute(text(sql), p)
        assert e.value.orig.pgcode == "SD423", (sql, e.value.orig)
        assert "10/2026 ist abgeschlossen" in str(e.value)
    finally:
        db.execute(text("ROLLBACK TO SAVEPOINT t"))


def test_trigger_auf_allen_lohndaten(db):
    tid, eid, _ = eintrag(db)
    sperren(db)
    gesperrt_sql(db, "UPDATE time_entries SET notes = coalesce(notes, '') || 'x' WHERE id = :i", i=tid)
    gesperrt_sql(db, "DELETE FROM time_entries WHERE id = :i", i=tid)
    gesperrt_sql(db, """INSERT INTO time_entries (employee_id, object_id, check_in, check_out) VALUES (:e, 15, '2026-10-31 08:00', '2026-10-31 09:00')""", e=eid)
    gesperrt_sql(db, """INSERT INTO km_daily_entries (employee_id, date, distance_km, amount) VALUES (:e, '2026-10-05', 1, 0.3)""", e=eid)
    gesperrt_sql(db, """INSERT INTO sick_notes (employee_id, start_date, end_date) VALUES (:e, '2026-09-28', '2026-10-02')""", e=eid)
    gesperrt_sql(db, """INSERT INTO vacation_requests (employee_id, start_date, end_date, type, status) VALUES (:e, '2026-10-30', '2026-11-03', 'urlaub', 'pending')""", e=eid)
    gesperrt_sql(db, """INSERT INTO pending_bookings (employee_id, object_id, date, start_time, end_time, status) VALUES (:e, 15, '2026-10-30', '08:00', '09:00', 'offen')""", e=eid)
    gesperrt_sql(db, """INSERT INTO correction_requests (employee_id, time_entry_id, correction_type, status) VALUES (:e, :t, 'delete', 'pending')""", e=eid, t=tid)
    gesperrt_sql(db, "INSERT INTO zeitkonto (employee_id, year, month) VALUES (:e, 2026, 10)", e=eid)
    # Planung, andere Monate und No-op-Updates bleiben frei
    db.execute(text("UPDATE time_entries SET notes = notes WHERE id = :i"), {"i": tid})
    db.execute(text("""INSERT INTO time_entries (employee_id, object_id, check_in, check_out) VALUES (:e, 15, '2026-11-02 08:00', '2026-11-02 09:00')"""), {"e": eid})
    # wieder geoeffnet -> erlaubt
    sperren(db, status="erzeugt")
    db.execute(text("UPDATE time_entries SET notes = coalesce(notes, '') || 'x' WHERE id = :i"), {"i": tid})


def test_api_liefert_423_mit_klartext(client, db):
    tid, eid, email = eintrag(db)
    sperren(db)
    h = token(db, "ADMIN")
    ci, co = q(db, "SELECT check_in, check_out FROM time_entries WHERE id = :i", i=tid)[0]
    zeiten = {"datum": ci.date().isoformat(), "kommen": ci.strftime("%H:%M"), "gehen": co.strftime("%H:%M"), "notes": "geaendert"}
    for methode, pfad, body in (("put", f"/api/v1/admin/bookings/{tid}", {"notes": "geaendert"}),
                                ("put", f"/api/v1/cockpit/zeiten/{tid}", zeiten),
                                ("delete", f"/api/v1/admin/bookings/{tid}", None)):
        sperren(db)          # nach jedem rollback neu (DEV-Kopie hat keinen echt gesperrten Monat)
        r = getattr(client, methode)(pfad, headers=h, **({"json": body} if body else {}))
        assert r.status_code == 423, (pfad, r.status_code, r.text)
        assert "Monat 10/2026 ist abgeschlossen" in r.json()["detail"]
        db.rollback()
    # MA-App: Korrekturantrag fuer einen Eintrag im gesperrten Monat
    sperren(db)
    r = client.post("/api/v1/corrections/", headers=ma_header(email), json={
        "time_entry_id": tid, "correction_type": "delete", "old_value": "-", "new_value": "-", "reason": "Test Monatssperre"})
    assert r.status_code == 423, r.text
    db.rollback()
    assert q(db, "SELECT count(*) FROM time_entries WHERE id = :i", i=tid)[0][0] == 1
