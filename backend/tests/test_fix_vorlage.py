"""Haekchen "fix" im Dienstplan -> Vorlage (Fixum), 14-taeglich nach ISO-Woche. Nur dev_cockpit, Rollback."""
import os
import sys
from datetime import date

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token  # noqa: E402,F401

API = "/api/v1/cockpit"


def schicht(client, h, db, datum, beginn="07:30", ende="10:30", pnr="D0036", obj=15):
    eid = q(db, "SELECT id FROM employees WHERE personal_nr = :p", p=pnr)[0][0]
    db.execute(text("DELETE FROM schedules WHERE employee_id = :e AND date = :d"), {"e": eid, "d": datum})
    db.execute(text("DELETE FROM master_schedule_entries WHERE employee_id = :e AND object_id = :o"), {"e": eid, "o": obj})
    r = client.post(f"{API}/dienstplan", headers=h, json={"employee_id": eid, "object_id": obj, "datum": datum,
                                                          "beginn": beginn, "ende": ende, "fahrer": True})
    assert r.status_code == 200, r.text
    return r.json()["id"], eid


def tag(client, h, datum, sid):
    wo = client.get(f"{API}/dienstplan", headers=h, params={"start": datum}).json()
    return next(s for d in wo["tage"] for s in d["schichten"] if s["id"] == sid)


def test_fix_woechentlich_und_zurueck(client, db):
    h = token(db, "ADMIN")
    sid, eid = schicht(client, h, db, "2026-12-12")
    assert tag(client, h, "2026-12-12", sid)["fix"] is False
    r = client.put(f"{API}/dienstplan/{sid}/fix", headers=h, json={"fix": True}).json()
    assert r["rhythmus"] == "weekly"
    assert tag(client, h, "2026-12-12", sid)["fix"] is True
    m = q(db, "SELECT weekday, start_time::text, end_time::text, is_driver, planned_hours, is_active FROM master_schedule_entries WHERE id = :i", i=r["vorlage_id"])[0]
    assert tuple(m) == (5, "07:30:00", "10:30:00", True, 3.0, True)
    assert client.get(f"{API}/schicht/{sid}", headers=h).json()["fix"] is True
    client.put(f"{API}/dienstplan/{sid}/fix", headers=h, json={"fix": False})
    assert tag(client, h, "2026-12-12", sid)["fix"] is False
    assert q(db, "SELECT is_active FROM master_schedule_entries WHERE id = :i", i=r["vorlage_id"])[0][0] is False
    assert q(db, "SELECT count(*) FROM audit_log WHERE action IN ('vorlage_fix', 'vorlage_nicht_fix') AND entity_id = :i", i=r["vorlage_id"])[0][0] == 2


def test_fix_14_taeglich_lange_woche(client, db):
    """Matej/Ljubica: Sa 28.11.2026 (KW 48) ja, Sa 05.12. (KW 49) nein, Sa 12.12. (KW 50) ja."""
    h = token(db, "ADMIN")
    sid, eid = schicht(client, h, db, "2026-11-28", "09:00", "15:00", pnr="D0021", obj=14)
    r = client.put(f"{API}/dienstplan/{sid}/fix", headers=h, json={"fix": True, "alle_2_wochen": True}).json()
    assert r["rhythmus"] == "biweekly_even"
    from app.services import plan_vorlage as pv
    m = [dict(x) for x in pv.vorlage(db) if x["id"] == r["vorlage_id"]][0]
    assert [pv.rhythmus_passt(m["rhythm"], None, 5, date.fromisoformat(d)) for d in ("2026-11-28", "2026-12-05", "2026-12-12")] == [True, False, True]
    assert tag(client, h, "2026-11-28", sid)["fix_14"] is True
    # auf woechentlich umstellen: 14-taeglich wird abgeloest, nicht doppelt
    client.put(f"{API}/dienstplan/{sid}/fix", headers=h, json={"fix": True, "alle_2_wochen": False})
    aktiv = q(db, "SELECT rhythm FROM master_schedule_entries WHERE employee_id = :e AND object_id = 14 AND coalesce(is_active, true)", e=eid)
    assert [a[0] for a in aktiv] == ["weekly"]


def test_fix_rechte_und_abwesenheit(client, db):
    sid, _ = schicht(client, token(db, "ADMIN"), db, "2026-12-19")
    assert client.put(f"{API}/dienstplan/{sid}/fix", headers=token(db, "OBJEKTLEITER"), json={"fix": True}).status_code == 200
    assert client.put(f"{API}/dienstplan/999999/fix", headers=token(db, "ADMIN"), json={"fix": True}).status_code == 404
