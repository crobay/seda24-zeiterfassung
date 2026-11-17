"""Server-Bestaetigung fuer die Stempeluhr: Kennung X-Seda24 an jeder Antwort, client_id kommt bei Kommen und
Gehen zurueck (auch bei Wiederholung aus der Warteschlange).

Laeuft NUR gegen dev_cockpit, Transaktion mit Rollback (Fixtures aus test_stempel_toleranz).
Aufruf: cd backend && ./venv/bin/python -m pytest tests/test_server_bestaetigung.py -q
"""
from test_stempel_toleranz import db, client, telegram, ma, schicht, ts  # noqa: F401


def test_kommen_gehen_bestaetigt_mit_client_id(client, db, telegram):
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = client.post("/api/v1/time-entries/check-in", headers=h,
                    json={"object_id": 20, "client_id": "sb-in-1", "client_timestamp": ts("12:58")})
    assert r.status_code == 200 and r.headers["x-seda24"] == "1"
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["client_id"] == "sb-in-1"
    r = client.post("/api/v1/time-entries/check-out", headers=h, json={"client_id": "sb-out-1", "client_timestamp": ts("15:58")})
    assert r.status_code == 200 and r.headers["x-seda24"] == "1"
    assert r.json()["client_id"] == "sb-out-1"


def test_wiederholung_aus_warteschlange_wird_bestaetigt(client, db, telegram):
    """Antwort ging verloren (Timeout), Handy sendet erneut: Kommen per Dedup, Gehen per Idempotenz bestaetigt."""
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    k = {"object_id": 20, "client_id": "sb-in-2", "client_timestamp": ts("12:58")}
    g = {"client_id": "sb-out-2", "client_timestamp": ts("15:58")}
    a = client.post("/api/v1/time-entries/check-in", headers=h, json=k).json()
    b = client.post("/api/v1/time-entries/check-in", headers=h, json=k)
    assert b.status_code == 200 and b.json()["client_id"] == "sb-in-2" and b.json()["id"] == a["id"]
    client.post("/api/v1/time-entries/check-out", headers=h, json=g)
    c = client.post("/api/v1/time-entries/check-out", headers=h, json=g)
    assert c.status_code == 200 and c.json()["client_id"] == "sb-out-2" and c.json()["id"] == a["id"]
    assert c.json()["check_out"].startswith(ts("15:58")[:16])


def test_echte_fehlermeldung_ist_json_mit_kennung(client, db, telegram):
    eid, h = ma(db, "D0040")
    r = client.post("/api/v1/time-entries/check-out", headers=h, json={"client_timestamp": ts("15:58")})
    assert r.status_code == 400 and r.headers["x-seda24"] == "1"
    assert r.headers["content-type"].startswith("application/json") and "detail" in r.json()


def test_kennung_auch_bei_401(client):
    r = client.post("/api/v1/time-entries/check-in", json={"object_id": 20})
    assert r.status_code == 401 and r.headers["x-seda24"] == "1"
