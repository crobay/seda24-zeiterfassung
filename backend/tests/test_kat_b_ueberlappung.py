"""Kat-B-Bestaetigung: Kommen/Gehen gegen andere Buchungen des Tages abgrenzen (Fehler D0036 03.10.2026:
fruehe Schicht 07:30-10:30 erst NACH der spaeteren 10:30-13:00 bestaetigt -> Kommen 13:01, Gehen 10:29)."""
from datetime import datetime

from app.services.booking_service import zeiten_ohne_ueberlappung


def d(hm):
    return datetime(2026, 10, 3, int(hm[:2]), int(hm[3:]))


def test_fruehe_schicht_nach_spaeterer_bestaetigt():
    k, g = zeiten_ohne_ueberlappung(d("07:29"), d("10:32"), d("07:30"), [(d("10:30"), d("13:00"))])
    assert (k, g) == (d("07:29"), d("10:29"))


def test_spaetere_schicht_nach_frueherer_wie_bisher():
    # bisheriger Fall: vorherige Schicht endet 10:31 (Zufall), neue beginnt 10:29 -> Kommen 10:32
    k, g = zeiten_ohne_ueberlappung(d("10:29"), d("13:01"), d("10:30"), [(d("07:29"), d("10:31"))])
    assert (k, g) == (d("10:32"), d("13:01"))


def test_ohne_andere_buchungen_unveraendert():
    assert zeiten_ohne_ueberlappung(d("07:31"), d("10:30"), d("07:30"), []) == (d("07:31"), d("10:30"))


def test_beide_seiten_und_nie_umgedreht():
    k, g = zeiten_ohne_ueberlappung(d("10:28"), d("13:02"), d("10:30"),
                                    [(d("07:30"), d("10:31")), (d("13:00"), d("16:00"))])
    assert (k, g) == (d("10:32"), d("12:59")) and k < g
    # Grenzfall: andere Buchung ueberdeckt die ganze Schicht -> Kommen bleibt vor Gehen
    k, g = zeiten_ohne_ueberlappung(d("10:29"), d("13:00"), d("10:30"), [(d("09:00"), d("14:00"))])
    assert k < g


def test_bestaetigung_echt_in_db():
    """Ganzer Weg ueber BookingService (dev_cockpit, Transaktion mit Rollback): spaetere Schicht schon gebucht,
    dann fruehere per Push bestaetigt -> Kommen ~07:30, Gehen spaetestens 10:30 (keine Ueberlappung), 3 Std."""
    from sqlalchemy import text
    from test_stempel_toleranz import engine, Session
    from app.services.booking_service import BookingService
    conn = engine.connect(); trans = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        tag = "2026-01-10"
        x = lambda sql, **p: db.execute(text(sql), p)
        eid = x("SELECT id FROM employees WHERE personal_nr = 'D0040'").scalar()
        x("UPDATE km_daily_entries SET time_entry_id = NULL WHERE time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = :e AND check_in::date = :d)", e=eid, d=tag)
        x("DELETE FROM break_entries WHERE time_entry_id IN (SELECT id FROM time_entries WHERE employee_id = :e AND check_in::date = :d)", e=eid, d=tag)
        x("DELETE FROM time_entries WHERE employee_id = :e AND check_in::date = :d", e=eid, d=tag)
        frueh = x("""INSERT INTO schedules (employee_id, object_id, date, start_time, end_time, planned_hours, status)
                     VALUES (:e, 15, :d, '07:30', '10:30', 3, 'normal') RETURNING id""", e=eid, d=tag).scalar()
        x(f"""INSERT INTO time_entries (employee_id, object_id, check_in, check_out, billed_hours, hourly_rate, is_manual_entry)
              VALUES (:e, 20, '{tag} 10:30', '{tag} 13:00', 2.5, 15.5, true)""", e=eid)
        nid = x("""INSERT INTO push_notifications (employee_id, notification_type, title, status, schedule_id)
                   VALUES (:e, 'shift_confirm', 'Test', 'sent', :s) RETURNING id""", e=eid, s=frueh).scalar()
        for _ in range(5):   # Zufallsminuten: mehrfach pruefen
            r = BookingService(db).process_push_response(nid, "confirmed")
            assert r["status"] == "booked", r
            k, g = datetime.fromisoformat(r["check_in"]), datetime.fromisoformat(r["check_out"])
            assert d("07:28") <= k.replace(year=2026, month=10, day=3) <= d("07:32"), r
            assert k < g and g.strftime("%H:%M") <= "10:30" and r["hours"] == 3, r
            x("DELETE FROM km_daily_entries WHERE time_entry_id = :t", t=r["time_entry_id"])
            x("DELETE FROM time_entries WHERE id = :t", t=r["time_entry_id"])
    finally:
        db.close(); trans.rollback(); conn.close()
