"""Cockpit-Dienstplan: Mitarbeiter-Liste mit Objektleitung, Kopieren (Vorschau/Konflikte/Rueckgaengig), Verschieben.

Nur gegen dev_cockpit, jeder Test in einer Transaktion mit Rollback (siehe test_cockpit_rechte.py).
Die Testschichten liegen in einer Woche ca. 10 Wochen in der Zukunft und werden im Test selbst angelegt.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token, ol_headers  # noqa: E402,F401  (Fixtures + Hilfen)

API = "/api/v1/cockpit"


def _montag(wochen=10):
    d = date.today() + timedelta(weeks=wochen)
    return d - timedelta(days=d.weekday())


def _zwei_ma(db):
    rows = q(db, """SELECT a.employee_id, a.object_id FROM employee_object_assignments a
                    JOIN employees e ON e.id = a.employee_id JOIN users u ON u.id = e.user_id
                    WHERE coalesce(a.is_active,true) AND e.is_active AND NOT coalesce(e.is_test,false) AND u.role = 'MITARBEITER'
                      AND a.object_id NOT IN (19, 999) ORDER BY a.employee_id""")
    seen, out = set(), []
    for e, o in rows:
        if e not in seen:
            seen.add(e); out.append((e, o))
    return out[0], out[1]


def _schicht(client, h, emp, obj, tag, b="08:00", e="10:00"):
    r = client.post(f"{API}/dienstplan", json={"employee_id": emp, "object_id": obj, "datum": tag.isoformat(), "beginn": b, "ende": e}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _urlaub(db, emp, tag):
    db.execute(__import__("sqlalchemy").text(
        "INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, status) VALUES (:e, 999, :d, :w, '00:00', '23:59', 'urlaub')"),
        {"e": emp, "d": tag, "w": tag.weekday()})


# ---------- 1) Mitarbeiter-Liste ----------

def test_objektleitung_in_liste_und_akte(client, db):
    h = ol_headers(db)
    liste = client.get(f"{API}/mitarbeiter", headers=h).json()
    ruz = [m for m in liste if m["personal_nr"] == "D0002"]
    assert ruz and ruz[0]["rolle"] == "objektleiter"
    assert all(m["rolle"] != "admin" for m in liste)               # Admin-Testbuchungen von 2025 zaehlen nicht
    assert any(m["rolle"] == "mitarbeiter" for m in liste)
    akte = client.get(f"{API}/mitarbeiter/{ruz[0]['id']}", headers=h).json()
    assert akte["stamm"]["rolle"] == "objektleiter"


# ---------- 2) Kopieren ----------

def test_woche_kopieren_vorschau_konflikte_und_rueckgaengig(client, db):
    h = token(db, "ADMIN")
    (m1, o1), (m2, o2) = _zwei_ma(db)
    mo = _montag()
    s_a = _schicht(client, h, m1, o1, mo)                        # Mo  m1 08-10
    s_b = _schicht(client, h, m2, o2, mo + timedelta(days=2))    # Mi  m2 08-10
    s_c = _schicht(client, h, m1, o1, mo + timedelta(days=4), "12:00", "14:00")  # Fr m1 12-14
    naechste = mo + timedelta(days=7)
    _urlaub(db, m2, naechste + timedelta(days=2))                # Ziel-Mi: m2 hat Urlaub
    _schicht(client, h, m1, o2, naechste + timedelta(days=4), "13:00", "15:00")  # Ziel-Fr: m1 schon belegt (ueberlappt)
    vor = q(db, "SELECT count(*) FROM schedules")[0][0]

    body = {"quelle_von": mo.isoformat(), "quelle_bis": (mo + timedelta(days=6)).isoformat(), "ziel_von": naechste.isoformat()}
    v = client.post(f"{API}/dienstplan/kopieren", json={**body, "vorschau": True}, headers=h).json()
    assert q(db, "SELECT count(*) FROM schedules")[0][0] == vor      # Vorschau speichert nichts
    eig = [e for e in v["eintraege"] if e["quelle_id"] in (s_a, s_b, s_c)]
    st = {e["quelle_id"]: e for e in eig}
    assert st[s_a]["status"] == "ok" and st[s_a]["datum"] == naechste.isoformat()
    assert st[s_b]["status"] == "abwesend" and st[s_b]["grund"] == "Urlaub"
    assert st[s_c]["status"] == "konflikt" and st[s_c]["grund"].startswith("Doppelbelegung")

    r = client.post(f"{API}/dienstplan/kopieren", json={**body, "vorschau": False}, headers=h).json()
    assert r["angelegt"] == v["anzulegen"] and r["kopie_id"]
    neu = q(db, "SELECT employee_id, date, start_time FROM schedules WHERE id = ANY(:i)", i=r["ids"])
    assert (m1, naechste) in {(a, b) for a, b, _ in neu}
    assert not any(a == m2 and b == naechste + timedelta(days=2) for a, b, _ in neu)   # Urlaub uebersprungen
    # zweites Mal: alles "bereits vorhanden" -> nichts doppelt
    v2 = client.post(f"{API}/dienstplan/kopieren", json={**body, "vorschau": True}, headers=h).json()
    assert {e["quelle_id"]: e["grund"] for e in v2["eintraege"]}[s_a] == "bereits vorhanden"

    u = client.delete(f"{API}/dienstplan/kopie/{r['kopie_id']}", headers=h).json()
    assert u["entfernt"] == r["angelegt"]
    assert not q(db, "SELECT 1 FROM schedules WHERE id = ANY(:i)", i=r["ids"])


def test_schicht_duplizieren_anderer_ma_und_tag_kopieren_zeitraum(client, db):
    h = ol_headers(db)
    (m1, o1), (m2, _) = _zwei_ma(db)
    mo = _montag(11)
    sid = _schicht(client, h, m1, o1, mo, "06:00", "07:30")
    r = client.post(f"{API}/dienstplan/kopieren", json={"schicht_ids": [sid], "ziel_von": (mo + timedelta(days=1)).isoformat(),
                                                        "employee_id": m2, "vorschau": False}, headers=h).json()
    assert r["angelegt"] == 1
    neu = q(db, "SELECT employee_id, date, start_time, end_time, object_id FROM schedules WHERE id = :i", i=r["ids"][0])[0]
    assert neu[0] == m2 and neu[1] == mo + timedelta(days=1) and neu[4] == o1
    # ganzen Tag auf Mi..Fr kopieren (taeglich wiederholt)
    r2 = client.post(f"{API}/dienstplan/kopieren", json={"quelle_von": mo.isoformat(), "ziel_von": (mo + timedelta(days=2)).isoformat(),
                                                         "ziel_bis": (mo + timedelta(days=4)).isoformat(), "vorschau": True}, headers=h).json()
    mine = [e for e in r2["eintraege"] if e["quelle_id"] == sid]
    assert [e["datum"] for e in mine] == [(mo + timedelta(days=i)).isoformat() for i in (2, 3, 4)]


def test_kopieren_grenzen(client, db):
    h = token(db, "ADMIN")
    mo = _montag()
    bad = [{"quelle_von": "x", "ziel_von": mo.isoformat()},
           {"quelle_von": mo.isoformat(), "quelle_bis": (mo + timedelta(days=40)).isoformat(), "ziel_von": (mo + timedelta(days=60)).isoformat()},
           {"quelle_von": mo.isoformat(), "quelle_bis": (mo + timedelta(days=6)).isoformat(), "ziel_von": (mo + timedelta(days=3)).isoformat()},
           {"quelle_von": mo.isoformat(), "ziel_von": (mo + timedelta(days=7)).isoformat(), "ziel_bis": (mo + timedelta(days=200)).isoformat()}]
    for b in bad:
        assert client.post(f"{API}/dienstplan/kopieren", json=b, headers=h).status_code == 400, b
    assert client.delete(f"{API}/dienstplan/kopie/zzz", headers=h).status_code == 400
    assert client.post(f"{API}/dienstplan/kopieren", json={"quelle_von": mo.isoformat(), "ziel_von": mo.isoformat()},
                       headers=token(db, "MITARBEITER")).status_code in (401, 403)


def test_vergangenheit_wird_uebersprungen(client, db):
    h = token(db, "ADMIN")
    alt = date.today() - timedelta(days=21)
    alt -= timedelta(days=alt.weekday())
    v = client.post(f"{API}/dienstplan/kopieren", json={"quelle_von": (alt - timedelta(days=7)).isoformat(),
                                                        "quelle_bis": (alt - timedelta(days=1)).isoformat(), "ziel_von": alt.isoformat()}, headers=h).json()
    assert v["anzulegen"] == 0 and all(e["grund"] == "liegt in der Vergangenheit" for e in v["eintraege"])


# ---------- 3) Verschieben (Drag & Drop) ----------

def test_verschieben_mit_pruefungen(client, db):
    h = ol_headers(db)
    (m1, o1), (m2, o2) = _zwei_ma(db)
    mo = _montag(12)
    sid = _schicht(client, h, m1, o1, mo)
    r = client.post(f"{API}/dienstplan/{sid}/verschieben", json={"datum": (mo + timedelta(days=1)).isoformat(), "employee_id": m2}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["neu"]["employee_id"] == m2 and r.json()["neu"]["datum"] == (mo + timedelta(days=1)).isoformat()
    assert r.json()["alt"]["employee_id"] == m1
    # Doppelbelegung
    _schicht(client, h, m1, o2, mo + timedelta(days=2), "09:00", "11:00")
    assert client.post(f"{API}/dienstplan/{sid}/verschieben", json={"datum": (mo + timedelta(days=2)).isoformat(), "employee_id": m1},
                       headers=h).status_code == 409
    # Urlaub am Ziel
    _urlaub(db, m1, mo + timedelta(days=3))
    r = client.post(f"{API}/dienstplan/{sid}/verschieben", json={"datum": (mo + timedelta(days=3)).isoformat(), "employee_id": m1}, headers=h)
    assert r.status_code == 409 and "Urlaub" in r.json()["detail"]
    # Vergangenheit
    assert client.post(f"{API}/dienstplan/{sid}/verschieben", json={"datum": "2026-01-05"}, headers=h).status_code == 409
    # schon gestempelt -> nicht verschiebbar
    db.execute(__import__("sqlalchemy").text("INSERT INTO time_entries (employee_id, object_id, check_in, schedule_id) VALUES (:e, :o, now(), :s)"),
               {"e": m2, "o": o1, "s": sid})
    assert client.post(f"{API}/dienstplan/{sid}/verschieben", json={"datum": (mo + timedelta(days=4)).isoformat()}, headers=h).status_code == 409


def test_rueckgaengig_laesst_gestempelte_stehen(client, db):
    h = token(db, "ADMIN")
    (m1, o1), _ = _zwei_ma(db)
    mo = _montag(13)
    sid = _schicht(client, h, m1, o1, mo)
    r = client.post(f"{API}/dienstplan/kopieren", json={"schicht_ids": [sid], "ziel_von": (mo + timedelta(days=1)).isoformat(),
                                                        "ziel_bis": (mo + timedelta(days=2)).isoformat(), "vorschau": False}, headers=h).json()
    assert r["angelegt"] == 2
    db.execute(__import__("sqlalchemy").text("INSERT INTO time_entries (employee_id, object_id, check_in, schedule_id) VALUES (:e, :o, now(), :s)"),
               {"e": m1, "o": o1, "s": r["ids"][0]})
    u = client.delete(f"{API}/dienstplan/kopie/{r['kopie_id']}", headers=h).json()
    assert u == {"entfernt": 1, "behalten_gestempelt": 1}
    assert q(db, "SELECT 1 FROM schedules WHERE id = :i", i=r["ids"][0])
