"""Super-PIN + unveraenderbares Protokoll im wieder geoeffneten Monat (Drazen 19.11.2026, GoBD).

Oeffnen nur mit Super-PIN (nur Inhaber, nicht Login-Passwort, gehasht, Fehlversuche begrenzt) und Grund. Jede
Aenderung im geoeffneten Monat - ueber die App UND direkt per SQL - steht mit alt/neu, wer, wann im Protokoll;
das Protokoll laesst sich vom App-Benutzer weder aendern noch loeschen; Sperren schliesst die Oeffnung.
Nur dev_cockpit, Transaktion mit Rollback."""
import os
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token, ol_headers  # noqa: E402,F401
from test_monatssperre import sperren, eintrag  # noqa: E402

from app.core.security import pwd_context  # noqa: E402
from app.services import monatsabschluss as ma, superpin  # noqa: E402

API = "/api/v1/cockpit/abschluss"
PIN = "740213"


def admin(db):
    return SimpleNamespace(**q(db, "SELECT u.* FROM users u JOIN superpin s ON s.user_id = u.id")[0]._mapping)


def pin_setzen(db, pin=PIN):
    db.execute(text("UPDATE superpin SET pin_hash = :h, fehlversuche = 0, gesperrt_bis = NULL, dauerhaft_gesperrt = false"),
               {"h": pwd_context.hash(pin)})


def fehlt_db(db, sql, **p):
    db.execute(text("SAVEPOINT t"))
    try:
        with pytest.raises(DBAPIError):
            db.execute(text(sql), p)
    finally:
        db.execute(text("ROLLBACK TO SAVEPOINT t"))


def test_pin_einrichten_regeln(db):
    u = admin(db)
    db.execute(text("UPDATE superpin SET pin_hash = NULL"))
    db.execute(text("UPDATE users SET password_hash = :h WHERE id = :i"), {"h": pwd_context.hash("13579864"), "i": u.id})
    u = admin(db)
    with pytest.raises(PermissionError):
        superpin.setzen(db, u, "740213", passwort="falsch")                      # erstes Mal nur mit Login-Passwort
    for schlecht in ("12345", "abcdef12", "111111", "123456", "987654", "13579864"):   # zu kurz/Buchstaben/einfach/= Passwort
        with pytest.raises(ValueError):
            superpin.setzen(db, u, schlecht, passwort="13579864")
    st = superpin.setzen(db, u, PIN, passwort="13579864")
    assert st["eingerichtet"] and st["inhaber"] and "hash" not in str(st).lower()
    h = q(db, "SELECT pin_hash FROM superpin")[0][0]
    assert h.startswith("$2") and PIN not in h                                    # bcrypt, nicht im Klartext
    with pytest.raises(PermissionError):
        superpin.setzen(db, u, "602418", pin_alt="999999")                         # aendern nur mit alter PIN
    superpin.setzen(db, u, "602418", pin_alt=PIN)
    # anderer Benutzer ist nie Inhaber
    fremd = SimpleNamespace(id=q(db, "SELECT id FROM users WHERE role = 'OBJEKTLEITER' LIMIT 1")[0][0], password_hash=None)
    with pytest.raises(PermissionError):
        superpin.pruefen(db, fremd, "602418")
    assert not superpin.status(db, fremd)["inhaber"]


def test_fehlversuche_begrenzt(db):
    u = admin(db)
    pin_setzen(db)
    for i in range(4):
        with pytest.raises(PermissionError, match="noch"):
            superpin.pruefen(db, u, "000001")
    with pytest.raises(PermissionError, match="15 Minuten"):
        superpin.pruefen(db, u, "000001")
    with pytest.raises(PermissionError, match="gesperrt bis"):
        superpin.pruefen(db, u, PIN)                                               # auch die richtige PIN nicht
    db.execute(text("UPDATE superpin SET gesperrt_bis = now() - interval '1 minute'"))
    for i in range(4):
        with pytest.raises(PermissionError):
            superpin.pruefen(db, u, "000001")
    with pytest.raises(PermissionError, match="Server"):
        superpin.pruefen(db, u, "000001")                                          # 10. Fehlversuch -> dauerhaft
    with pytest.raises(PermissionError, match="Server"):
        superpin.pruefen(db, u, PIN)
    assert q(db, "SELECT dauerhaft_gesperrt FROM superpin")[0][0]
    assert q(db, "SELECT count(*) FROM audit_log WHERE action = 'superpin_fehlversuch' AND created_at > now() - interval '1 minute'")[0][0] >= 10


def test_oeffnen_aendern_protokoll_sperren(client, db):
    tid, eid, _ = eintrag(db)
    h = token(db, "ADMIN")
    email = q(db, "SELECT email FROM users WHERE role = 'ADMIN' ORDER BY id LIMIT 1")[0][0]
    pin_setzen(db)
    sperren(db)
    # ohne / mit falscher PIN, ohne Grund -> nein
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": "Korrektur Azra 03.10.", "pin": ""}, headers=h).status_code == 423
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": "Korrektur Azra 03.10.", "pin": "000001"}, headers=h).status_code == 423
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": "kurz", "pin": PIN}, headers=h).status_code == 409
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": "Korrektur Azra 03.10.", "pin": PIN},
                       headers=ol_headers(db)).status_code == 403                  # Objektleitung nie
    assert ma.gesperrt(db, 2026, 10)
    r = client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": "Korrektur Azra 03.10.", "pin": PIN}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "erzeugt", r.text
    assert q(db, "SELECT fehlversuche FROM superpin")[0][0] == 0                  # Treffer setzt Zaehler zurueck
    # 1) Aenderung ueber die App -> Protokoll mit App-Benutzer, alt/neu
    alt = q(db, "SELECT notes FROM time_entries WHERE id = :i", i=tid)[0][0]
    assert client.put(f"/api/v1/admin/bookings/{tid}", json={"notes": "korrigiert lt. Grund"}, headers=h).status_code == 200
    # 2) direkt per SQL (Skript/Scheduler) -> ebenfalls protokolliert, ohne App-Benutzer
    db.execute(text("SELECT set_config('seda.app_benutzer', '', true)"))          # wie eine eigene Skript-Sitzung
    db.execute(text("""INSERT INTO km_daily_entries (employee_id, date, distance_km, amount) VALUES (:e, '2026-10-05', 1, 0.3)"""), {"e": eid})
    # anderer Monat: nicht im Protokoll
    db.execute(text("""INSERT INTO km_daily_entries (employee_id, date, distance_km, amount) VALUES (:e, '2026-11-05', 1, 0.3)"""), {"e": eid})
    zeilen = q(db, "SELECT a.tabelle, a.aktion, a.app_benutzer, a.alt, a.neu, a.hash FROM monatsabschluss_aenderung a JOIN monatsabschluss_oeffnung o "
                   "ON o.id = a.oeffnung_id WHERE o.monat = '2026-10' AND o.gesperrt_am IS NULL ORDER BY a.id")
    assert [z[:2] for z in zeilen] == [("monatsabschluss", "GEOEFFNET"), ("time_entries", "UPDATE"), ("km_daily_entries", "INSERT")]
    assert zeilen[0][2] == email and zeilen[0][4]["grund"] == "Korrektur Azra 03.10."
    assert zeilen[1][2] == email and zeilen[1][3]["notes"] == alt and zeilen[1][4]["notes"] == "korrigiert lt. Grund"
    assert zeilen[2][2] is None and all(z[5] for z in zeilen)
    # Protokoll unveraenderbar: kein UPDATE/DELETE/TRUNCATE, Oeffnung nicht loeschbar, Grund nicht aenderbar
    fehlt_db(db, "UPDATE monatsabschluss_aenderung SET neu = NULL")
    fehlt_db(db, "DELETE FROM monatsabschluss_aenderung")
    fehlt_db(db, "TRUNCATE monatsabschluss_aenderung")
    fehlt_db(db, "DELETE FROM monatsabschluss_oeffnung")
    fehlt_db(db, "UPDATE monatsabschluss_oeffnung SET grund = 'anders egal was'")
    fehlt_db(db, "ALTER TABLE monatsabschluss_aenderung DISABLE TRIGGER ALL")
    fehlt_db(db, "UPDATE superpin SET user_id = -1")                               # Inhaber nur auf dem Server
    # 3) erneut sperren -> Oeffnung geschlossen, Zeile GESPERRT, danach wieder gesperrt
    assert client.post(f"{API}/2026-10/sperren", headers=h).json()["status"] == "abgeschlossen"
    assert q(db, "SELECT count(*) FROM monatsabschluss_oeffnung WHERE monat = '2026-10' AND gesperrt_am IS NULL")[0][0] == 0
    fehlt_db(db, "UPDATE time_entries SET notes = 'nach Sperre' WHERE id = :i", i=tid)
    # 4) Anzeige "Nachtraegliche Aenderungen" im Monatsabschluss
    n = client.get(f"{API}/2026-10", headers=h).json()["protokoll"]["nachtraege"]
    assert n["kette_ok"] is True
    o = n["oeffnungen"][-1]
    assert o["grund"] == "Korrektur Azra 03.10." and o["gesperrt_am"] and not o["offen"]
    assert [a["aktion"] for a in o["aenderungen"]] == ["geändert", "neu"]
    f = {x["feld"]: x for x in o["aenderungen"][0]["felder"]}
    assert f["Notiz"]["neu"] == "korrigiert lt. Grund" and o["aenderungen"][0]["wer"] != "" and "System/Skript" in o["aenderungen"][1]["wer"]
    assert q(db, "SELECT action FROM audit_log WHERE action = 'abschluss_wieder_offen' ORDER BY id DESC LIMIT 1")


def test_kette_erkennt_manipulation(db):
    """Selbst wer als Superuser eine Protokollzeile aendert, faellt an der Hash-Kette auf (hier simuliert ohne Trigger:
    der Pruefung wird eine geaenderte Zeile untergeschoben)."""
    sperren(db)
    db.execute(text("INSERT INTO monatsabschluss_oeffnung (monat, grund) VALUES ('2026-10', 'Test Hash-Kette pruefen')"))
    assert q(db, "SELECT erste_fehlerhafte FROM monatsabschluss_kette_pruefen()")[0][0] is None
    z = q(db, "SELECT * FROM monatsabschluss_aenderung ORDER BY id DESC LIMIT 1")[0]._mapping
    falsch = dict(z, neu=None)
    soll = q(db, "SELECT encode(sha256(convert_to(monatsabschluss_hash_text(jsonb_populate_record(NULL::monatsabschluss_aenderung, "
                 "CAST(:j AS jsonb))), 'UTF8')), 'hex')", j=__import__("json").dumps({**{k: (str(v) if k == "am" else v) for k, v in falsch.items()}}))[0][0]
    assert soll != z["hash"]


def test_ohne_superpin_tabelle_kein_absturz(db):
    assert ma.nachtraege(db, 2026, 10)["kette_ok"] in (True, None)
