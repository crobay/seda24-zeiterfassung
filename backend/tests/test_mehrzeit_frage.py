"""Mehrzeit nach Schichtende - neue Regel Drazen 19.11.2026 (services/mehrzeit.py).

Kein automatischer Antrag mehr: ab Schichtende + 15 Min (Einstellung) fragt die App, nur "Ja" + Grund
legt einen Antrag an (minutengenau ab Schichtende, nie mehr als gestempelt). Historie: 3 Tage lang.
Laeuft NUR gegen dev_cockpit, jeder Test in einer Transaktion mit Rollback. Telegram wird abgefangen.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from tests.test_stempel_toleranz import db, client, telegram, q, ma, schicht, ts, stempeln, antraege, TAG  # noqa: F401
from app.services import mehrzeit as mz

URL = "/api/v1/time-entries/{}/mehrzeit-antrag"


def test_regel_rechnung():
    d = datetime(2026, 11, 18)
    ende = d.replace(hour=16, minute=25)
    assert mz.minuten_nach_ende(d.replace(hour=12, minute=55), d.replace(hour=16, minute=43, second=50), ende) == 18
    assert mz.minuten_nach_ende(d.replace(hour=12, minute=55), d.replace(hour=16, minute=20), ende) == 0
    assert mz.minuten_nach_ende(d.replace(hour=16, minute=30), d.replace(hour=16, minute=50), ende) == 20  # ab Kommen
    assert mz.stunden(19) == 0.31 and mz.stunden(25) == 0.41 and mz.stunden(60) == 1.0  # abgerundet, nie mehr


def test_bis_14_min_keine_frage_kein_antrag(client, db, telegram):
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:58", "16:14")
    assert r["billed_hours"] == pytest.approx(3.0) and "mehrzeit_frage" not in r and not antraege(db, r["id"])
    x = client.post(URL.format(r["id"]), headers=h, json={"grund": "Kunde hat noch gegessen, Raum gesaugt"})
    assert x.status_code == 409 and "15" in x.json()["detail"] and not antraege(db, r["id"]) and not telegram


def test_ab_15_min_frage_aber_kein_automatischer_antrag(client, db, telegram):
    eid, h = ma(db, "D0039")
    schicht(db, eid, "12:55", "16:25")
    r = stempeln(client, h, "12:55", "16:43")
    assert r["billed_hours"] == pytest.approx(3.5)                     # gezaehlt nur bis Schichtende
    assert r["mehrzeit_frage"]["minuten"] == 18 and r["mehrzeit_frage"]["schicht_ende"] == "16:25"
    assert r["mehrzeit_frage"]["frage_ab"] == 15
    assert "mehrzeit_antrag" not in r and not antraege(db, r["id"]) and not telegram


def test_ja_mit_grund_antrag_ab_schichtende(client, db, telegram):
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:58", "16:25")
    x = client.post(URL.format(r["id"]), headers=h, json={"grund": "kurz"})
    assert x.status_code == 400 and not antraege(db, r["id"])           # Grund ist Pflicht
    x = client.post(URL.format(r["id"]), headers=h, json={"grund": "Konferenzraum nach Kundenessen gesaugt", "client_id": "mz-1"})
    assert x.status_code == 200 and x.json()["client_id"] == "mz-1" and x.json()["minuten"] == 25
    a = antraege(db, r["id"])
    assert len(a) == 1 and float(a[0].requested_hours) == 0.41 and "Mehrzeit 25 Min" in a[0].notes and "Konferenzraum" in a[0].notes
    assert len(telegram) == 1 and telegram[0][1]["category"] == "genehmigungen" and "Gehen 16:25" in telegram[0][0]
    # Wiederholung aus der Warteschlange: derselbe Antrag, keine zweite Meldung
    y = client.post(URL.format(r["id"]), headers=h, json={"grund": "Konferenzraum nach Kundenessen gesaugt", "client_id": "mz-1"})
    assert y.status_code == 200 and y.json()["id"] == a[0].id and len(antraege(db, r["id"])) == 1 and len(telegram) == 1
    # Spaeter nochmal aus der Historie: abgelehnt
    z = client.post(URL.format(r["id"]), headers=h, json={"grund": "nochmal derselbe Grund hier"})
    assert z.status_code == 409
    # Genehmigt: Stunden kommen dazu (nie mehr als gestempelt)
    from app.services.pending_booking_service import approve_pending_booking_core
    approve_pending_booking_core(db, a[0].id, {}, None)
    bh = float(q(db, "SELECT billed_hours FROM time_entries WHERE id = :i", i=r["id"])[0][0])
    assert bh == pytest.approx(3.41, abs=0.001) and bh * 60 <= (16 * 60 + 25) - 13 * 60


def test_fremder_eintrag_und_kein_gehen(client, db, telegram):
    eid, h = ma(db, "D0040")
    _, h2 = ma(db, "D0038")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:58", "16:30")
    assert client.post(URL.format(r["id"]), headers=h2, json={"grund": "fremder Eintrag geht nicht"}).status_code == 404
    assert not antraege(db, r["id"]) and not telegram


def test_historie_drei_tage_und_gesperrter_monat(client, db, telegram):
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:58", "16:30")
    hist = client.get(f"/api/v1/reports/my/history?date_from={TAG}&date_to={TAG}", headers=h).json()["entries"]
    e = [x for x in hist if x["id"] == r["id"]][0]
    assert e["mehrzeit"]["moeglich"] and e["mehrzeit"]["minuten"] == 30
    # 3 Tage nach dem Gehen: nicht mehr
    entry = type("E", (), {})()
    row = q(db, "SELECT id, employee_id, object_id, check_in, check_out FROM time_entries WHERE id = :i", i=r["id"])[0]
    for k in ("id", "employee_id", "object_id", "check_in", "check_out"):
        setattr(entry, k, getattr(row, k))
    assert "minuten" in mz.pruefen(db, entry, now=row.check_out + timedelta(days=3) - timedelta(minutes=1))
    assert "3 Tage" in mz.pruefen(db, entry, now=row.check_out + timedelta(days=3, minutes=1))["grund"]
    # Gesperrter Monat: nicht mehr (Sperre nur in dieser Transaktion)
    monat = TAG.strftime("%Y-%m")
    gesperrt = q(db, "SELECT status FROM monatsabschluss WHERE monat = :m", m=monat)
    if not gesperrt:
        q(db, "INSERT INTO monatsabschluss (monat, status) VALUES (:m, 'abgeschlossen')", m=monat)
    elif gesperrt[0][0] != "abgeschlossen":
        pytest.skip("Testmonat auf DEV gerade geoeffnet")
    assert mz.pruefen(db, entry)["grund"] == "Der Monat ist abgeschlossen"
    x = client.post(URL.format(r["id"]), headers=h, json={"grund": "im gesperrten Monat geht nichts"})
    assert x.status_code == 409 and not antraege(db, r["id"])


def test_einstellung_frage_ab(client, db, telegram):
    admin = q(db, "SELECT id FROM users WHERE email = 'admin@seda24.de'")[0][0]
    with pytest.raises(ValueError):
        mz.frage_ab_speichern(db, 3, admin)
    mz.frage_ab_speichern(db, 30, admin)
    assert mz.frage_ab(db) == 30
    eid, h = ma(db, "D0040")
    schicht(db, eid, "13:00", "16:00")
    r = stempeln(client, h, "12:58", "16:25")
    assert "mehrzeit_frage" not in r                                     # 25 < 30
    assert client.get("/api/v1/time-entries/mehrzeit-regel", headers=h).json()["frage_ab_min"] == 30

