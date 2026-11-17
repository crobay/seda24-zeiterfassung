"""Mitarbeiter-Texte per Telegram: Kommen fehlt, Gehen fehlt, Mehrzeit genehmigt.

Laeuft NUR gegen die DEV-Datenbank dev_cockpit, jeder Test in einer Transaktion mit Rollback - es bleibt
nichts in der DB. Telegram wird abgefangen (nichts wird verschickt).
Aufruf: cd backend && ./venv/bin/python -m pytest tests/test_ma_texte.py -q
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

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.database import engine  # noqa: E402
from app.services import scheduler as sch  # noqa: E402
from app.services import pending_booking_service as pbs  # noqa: E402
import app.services.telegram_bot as tb  # noqa: E402

HEUTE = date.today()
JETZT = datetime.combine(HEUTE, datetime.min.time()).replace(hour=14)  # im 6-21-Uhr-Fenster
CHAT = "999000111"  # nur in der Transaktion


class FesteZeit(datetime):
    @classmethod
    def now(cls, tz=None):
        return JETZT


@pytest.fixture()
def db(monkeypatch):
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    monkeypatch.setattr(session, "close", lambda: None)  # Jobs schliessen ihre Session selbst
    monkeypatch.setattr(sch, "SessionLocal", lambda: session)
    monkeypatch.setattr(sch, "datetime", FesteZeit)
    monkeypatch.setattr(sch, "finalize_due_vacation_rates", lambda *a, **k: None)
    monkeypatch.setattr(sch, "run_due_catchup_jobs", lambda *a, **k: None)
    try:
        yield session
    finally:
        Session.close(session)
        trans.rollback()
        conn.close()


@pytest.fixture()
def tg(monkeypatch):
    an_ma, an_admin = [], []
    monkeypatch.setattr(tb, "send_message_sync", lambda chat, txt, markup=None, **kw: an_ma.append((str(chat), txt, markup)) or True)
    monkeypatch.setattr(tb, "notify_admin", lambda txt, **kw: an_admin.append(txt))
    return an_ma, an_admin


def q(db, sql, **p):
    r = db.execute(text(sql), p)
    return r.fetchall() if r.returns_rows else None


def ma(db, nr="D0040"):
    """MA mit Test-Chat-ID, ohne Eintraege/Schichten heute und ohne offene Eintraege (nur in der Transaktion)."""
    eid = q(db, "SELECT id FROM employees WHERE personal_nr = :n", n=nr)[0][0]
    q(db, "UPDATE employees SET telegram_chat_id = :c WHERE id = :e", c=CHAT, e=eid)
    alt = "SELECT id FROM time_entries WHERE employee_id = :e AND (check_out IS NULL OR check_in::date = :d)"
    q(db, f"DELETE FROM break_entries WHERE time_entry_id IN ({alt})", e=eid, d=HEUTE)
    q(db, f"UPDATE km_daily_entries SET time_entry_id = NULL WHERE time_entry_id IN ({alt})", e=eid, d=HEUTE)
    q(db, f"UPDATE pending_bookings SET related_time_entry_id = NULL WHERE related_time_entry_id IN ({alt})", e=eid, d=HEUTE)
    q(db, "DELETE FROM time_entries WHERE employee_id = :e AND (check_out IS NULL OR check_in::date = :d)", e=eid, d=HEUTE)
    q(db, "UPDATE time_entries SET schedule_id = NULL WHERE schedule_id IN (SELECT id FROM schedules WHERE employee_id = :e AND date = :d)", e=eid, d=HEUTE)
    q(db, "UPDATE push_notifications SET schedule_id = NULL WHERE schedule_id IN (SELECT id FROM schedules WHERE employee_id = :e AND date = :d)", e=eid, d=HEUTE)
    q(db, "DELETE FROM schedules WHERE employee_id = :e AND date = :d", e=eid, d=HEUTE)
    return eid


def schicht(db, eid, beginn, ende, obj=20):
    return q(db, """INSERT INTO schedules (employee_id, object_id, date, start_time, end_time, planned_hours, status)
                    VALUES (:e, :o, :d, :b, :x, 3, 'normal') RETURNING id""", e=eid, o=obj, d=HEUTE, b=beginn, x=ende)[0][0]


def an(tg_ma):
    return [(t, m) for c, t, m in tg_ma if c == CHAT]


def link_knopf(markup):
    zeilen = markup.inline_keyboard
    assert len(zeilen) == 1 and len(zeilen[0]) == 1, "genau ein Knopf"
    k = zeilen[0][0]
    assert (k.text, k.url, k.callback_data) == ("App öffnen", "https://app.seda.de", None)


def test_kommen_fehlt_text_und_knopf(db, tg):
    eid = ma(db)
    sid = schicht(db, eid, "13:00", "16:00")  # 14:00 -> 60 Min nach Beginn: MA- und Admin-Meldung faellig
    sch.check_missing_stamps()
    nachrichten = an(tg[0])
    assert len(nachrichten) == 1
    txt, markup = nachrichten[0]
    assert txt == "Du hast heute bei Lidl Neu Bie2 noch kein Kommen gestempelt. Bitte jetzt in der App auf KOMMEN tippen."
    assert "http" not in txt and "?" not in txt
    link_knopf(markup)
    # Admin-Text unveraendert
    assert any(a == sch.missing_stamp_admin_text(*q(db, "SELECT first_name || ' ' || last_name, personal_nr FROM employees WHERE id = :e", e=eid)[0],
                                                  "13:00", "16:00", "Lidl Neu Bie2") for a in tg[1])
    # Protokoll wie bisher, gleiche Flags
    pn = q(db, "SELECT body, status FROM push_notifications WHERE schedule_id = :s AND notification_type = 'missing_stamp_ma'", s=sid)
    assert pn == [(txt, "sent")]
    assert q(db, "SELECT no_stamp_ma_notified FROM schedules WHERE id = :s", s=sid)[0][0] is True
    # kein zweites Mal
    sch.check_missing_stamps()
    assert len(an(tg[0])) == 1


def test_kommen_fehlt_nicht_vor_30_min(db, tg):
    eid = ma(db)
    schicht(db, eid, "13:45", "16:00")  # erst 15 Min
    sch.check_missing_stamps()
    assert an(tg[0]) == []


def test_gehen_fehlt_text_und_knopf(db, tg):
    eid = ma(db)
    schicht(db, eid, "09:00", "12:30")  # 14:00 -> 90 Min nach Ende
    te = q(db, """INSERT INTO time_entries (employee_id, object_id, check_in, created_at)
                  VALUES (:e, 20, :ci, :ci) RETURNING id""", e=eid, ci=JETZT.replace(hour=8, minute=55))[0][0]
    sch.check_overdue_entries()
    nachrichten = an(tg[0])
    assert len(nachrichten) == 1
    txt, markup = nachrichten[0]
    assert txt == ("Du hast heute bei Lidl Neu Bie2 noch kein Gehen gestempelt. Bitte jetzt in der App auf GEHEN tippen. "
                   "Schon weg? Dann in der App unter Nachtrag ‚Gehen vergessen‘ mit deiner Uhrzeit eintragen.")
    assert "http" not in txt
    link_knopf(markup)
    # Admin-Text unveraendert
    assert any(a.startswith("⚠️ Ueberfaellig: ") and "Schichtende war 12:30. Bitte pruefen." in a for a in tg[1])
    assert q(db, "SELECT overdue_notified, check_out FROM time_entries WHERE id = :t", t=te)[0] == (True, None)
    assert q(db, "SELECT body FROM push_notifications WHERE employee_id = :e AND notification_type = 'overdue_ma' ORDER BY id DESC LIMIT 1", e=eid)[0][0] == txt
    sch.check_overdue_entries()  # kein zweites Mal
    assert len(an(tg[0])) == 1


def test_gehen_fehlt_vom_vortag_nennt_datum():
    gestern = HEUTE - timedelta(days=1)
    txt = sch.gehen_fehlt_text("Lidl Neu Bie2", gestern, HEUTE)
    assert txt.startswith(f"Du hast am {gestern.strftime('%d.%m.')} bei Lidl Neu Bie2 noch kein Gehen gestempelt.")


def test_objektname_html_sicher():
    assert sch.kommen_fehlt_text("A & B <Halle>") == ("Du hast heute bei A &amp; B &lt;Halle&gt; noch kein Kommen gestempelt. "
                                                       "Bitte jetzt in der App auf KOMMEN tippen.")


def _antrag(db, eid, reason, typ, te_id):
    return q(db, """INSERT INTO pending_bookings (employee_id, object_id, date, start_time, end_time, service_type, requested_hours,
                                                 status, notes, created_at, reason, catch_up_type, related_time_entry_id, correction_field)
                    VALUES (:e, 20, :d, '13:00', '16:00', 'Unterhaltsreinigung', :h, 'offen', 'Test', NOW(), :r, :t, :te, :cf)
                    RETURNING id""", e=eid, d=HEUTE, h=0.42 if reason == 'mehrzeit_dienstplan' else 3,
             r=reason, t=typ, te=te_id, cf='beides' if typ == 'zeit_korrektur' else None)[0][0]


def _eintrag(db, eid):
    return q(db, """INSERT INTO time_entries (employee_id, object_id, check_in, check_out, billed_hours, created_at)
                    VALUES (:e, 20, :ci, :co, 3, :ci) RETURNING id""",
             e=eid, ci=JETZT.replace(hour=13), co=JETZT.replace(hour=16, minute=25))[0][0]


def test_mehrzeit_genehmigt_text(db, tg):
    eid = ma(db)
    pb = _antrag(db, eid, "mehrzeit_dienstplan", None, _eintrag(db, eid))
    pbs.approve_pending_booking_core(db, pb, {}, 1)
    nachrichten = an(tg[0])
    assert nachrichten == [(f"Deine Mehrzeit vom {HEUTE.strftime('%d.%m.%Y')} (Lidl Neu Bie2) wurde genehmigt: 0,42 Std.", None)]


def test_nachtrag_und_korrektur_texte_unveraendert(db, tg):
    eid = ma(db)
    pbs.approve_pending_booking_core(db, _antrag(db, eid, "vergessen", "beides_vergessen", None), {}, 1)
    pbs.approve_pending_booking_core(db, _antrag(db, eid, "sonstiges", "zeit_korrektur", _eintrag(db, eid)), {}, 1)
    d = HEUTE.strftime('%d.%m.%Y')
    assert [t for t, _ in an(tg[0])] == [
        f"Deine nachgetragene Zeit vom {d} wurde eingetragen:\nObjekt: Lidl Neu Bie2\n13:00–16:00, 3.0 Std.",
        f"Deine Zeitkorrektur vom {d} wurde übernommen:\nObjekt: Lidl Neu Bie2\n13:00–16:00, 3.0 Std.",
    ]


def test_kat_b_warst_du_da_unveraendert():
    import inspect
    src = inspect.getsource(tb.send_shift_confirmation_telegram)
    assert 'f"Warst du da?"' in src and "Ja, ich war anwesend" in src and "Nein, ich war nicht da" in src
