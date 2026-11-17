"""Plan aus Vorlage: Vorlage pflegen, Woche aus Vorlage (Urlaub/Krank/Absage -> offene Luecke), Kontingent Festgehalt,
"Plan naechste Woche" + Freitags-Erinnerung. Nur gegen dev_cockpit, jeder Test mit Rollback (siehe test_cockpit_rechte.py).
"""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token, ol_headers  # noqa: E402,F401  (Fixtures + Hilfen)

WOCHE = date(2027, 3, 1)          # Montag, weit genug in der Zukunft
API = "/api/v1/cockpit"


def ex(db, sql, **p):
    from sqlalchemy import text
    db.execute(text(sql), p)


def emp(db, nr):
    return q(db, "SELECT id FROM employees WHERE personal_nr = :n", n=nr)[0][0]


def leer(db, *eids, von=WOCHE, bis=WOCHE + timedelta(days=6)):
    """Testwoche frei machen (nur in der Transaktion) + Vorlage leeren."""
    ex(db, "UPDATE time_entries SET schedule_id = NULL WHERE schedule_id IN (SELECT id FROM schedules WHERE date BETWEEN :a AND :b)", a=von, b=bis)
    ex(db, "DELETE FROM push_notifications WHERE schedule_id IN (SELECT id FROM schedules WHERE date BETWEEN :a AND :b)", a=von, b=bis)
    ex(db, "DELETE FROM shift_change_requests WHERE schedule_id IN (SELECT id FROM schedules WHERE date BETWEEN :a AND :b)", a=von, b=bis)
    ex(db, "UPDATE schedules SET partner_schedule_id = NULL WHERE date BETWEEN :a AND :b", a=von, b=bis)
    ex(db, "DELETE FROM schedules WHERE date BETWEEN :a AND :b", a=von, b=bis)
    ex(db, "DELETE FROM master_schedule_entries")


def vl(client, h, nr_id, wt, b, e, obj=20, **kw):
    r = client.post(f"{API}/vorlage", json={"employee_id": nr_id, "object_id": obj, "wochentag": wt, "beginn": b, "ende": e, **kw}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Vorlage pflegen ----------

def test_vorlage_anlegen_aendern_loeschen(client, db):
    leer(db)
    h = ol_headers(db)
    lara = emp(db, "D0040")
    a = vl(client, h, lara, 0, "12:55", "15:55")
    assert a["tag"] == "Mo" and a["stunden"] == 3.0 and a["rhythmus"] == "weekly"
    assert client.post(f"{API}/vorlage", json={"employee_id": lara, "object_id": 20, "wochentag": 0, "beginn": "08:00", "ende": "09:00"},
                       headers=h).status_code == 409                                  # gleicher MA/Objekt/Tag/Rhythmus
    assert client.post(f"{API}/vorlage", json={"employee_id": lara, "object_id": 1, "wochentag": 0, "beginn": "15:00", "ende": "17:00"},
                       headers=h).status_code == 409                                  # Doppelbelegung in der Vorlage
    assert client.post(f"{API}/vorlage", json={"employee_id": lara, "object_id": 20, "wochentag": 9, "beginn": "08:00", "ende": "09:00"},
                       headers=h).status_code == 400
    u = client.put(f"{API}/vorlage/{a['id']}", json={"wochentag": 2}, headers=h)       # Ziehen auf Mittwoch
    assert u.status_code == 200 and u.json()["neu"]["tag"] == "Mi" and u.json()["neu"]["beginn"] == "12:55"
    lst = client.get(f"{API}/vorlage", headers=h).json()
    assert lst["wochenstunden"][str(lara)] == 3.0 and len(lst["eintraege"]) == 1
    assert client.delete(f"{API}/vorlage/{a['id']}", headers=h).json()["alt"]["tag"] == "Mi"
    assert q(db, "SELECT count(*) FROM audit_log WHERE entity_type = 'master_schedule' AND entity_id = :i", i=a["id"])[0][0] == 3
    assert client.get(f"{API}/vorlage", headers=token(db, "MITARBEITER")).status_code in (401, 403)


def test_vorlage_aus_woche(client, db):
    ex(db, "DELETE FROM master_schedule_entries")
    h = ol_headers(db)
    r = client.post(f"{API}/vorlage/aus-woche", json={"woche": "2026-11-18", "object_id": 20}, headers=h).json()
    assert r["vorschau"] and r["woche"] == "2026-11-16" and r["anzulegen"] > 0
    assert all(e["objekt"] for e in r["eintraege"])
    s = client.post(f"{API}/vorlage/aus-woche", json={"woche": "2026-11-16", "object_id": 20, "vorschau": False}, headers=h).json()
    assert len(s["ids"]) == r["anzulegen"]
    r2 = client.post(f"{API}/vorlage/aus-woche", json={"woche": "2026-11-16", "object_id": 20}, headers=h).json()
    assert r2["anzulegen"] == 0 and all(e["grund"] == "schon in der Vorlage" for e in r2["eintraege"])


# ---------- Woche aus Vorlage ----------

def test_woche_aus_vorlage_luecken_und_rueckgaengig(client, db):
    lara, helena, azra, sumi = emp(db, "D0040"), emp(db, "D0039"), emp(db, "D0036"), emp(db, "D0038")
    leer(db)
    h = ol_headers(db)
    assert client.post(f"{API}/dienstplan/aus-vorlage", json={"woche": WOCHE.isoformat()}, headers=h).status_code == 400  # Vorlage leer
    for wt in range(5):
        vl(client, h, lara, wt, "12:55", "15:55")
    vl(client, h, helena, 1, "12:55", "16:25")
    vl(client, h, azra, 5, "10:30", "13:00")
    vl(client, h, sumi, 2, "13:00", "16:00", rhythmus="biweekly_odd")   # KW 9 (01.03.2027) ist ungerade -> dabei
    # Lara Montag Urlaub, Helena hat Dienstag abgesagt
    ex(db, "INSERT INTO schedules (employee_id, object_id, date, start_time, end_time, status) VALUES (:e, 999, :d, '00:00', '23:59', 'urlaub')",
      e=lara, d=WOCHE)
    ex(db, "INSERT INTO shift_change_requests (employee_id, request_type, requested_date, reason, status, created_at) VALUES (:e, 'absage', :d, 'Test', 'offen', now())",
      e=helena, d=WOCHE + timedelta(days=1))
    v = client.post(f"{API}/dienstplan/aus-vorlage", json={"woche": (WOCHE + timedelta(days=3)).isoformat()}, headers=h).json()
    assert v["vorschau"] and v["woche"] == WOCHE.isoformat()
    st = {(e["name"].split()[0], e["tag"]): (e["status"], e["grund"]) for e in v["eintraege"]}
    assert st[("Lara", "Mo")] == ("abwesend", "Urlaub") and st[("Helena", "Di")] == ("abwesend", "Absage")
    assert v["anzulegen"] == 4 + 1 + 1 and v["luecken"] == 2                       # Lara Di-Fr, Azra Sa, Suemi Mi
    assert not q(db, "SELECT 1 FROM schedules WHERE date BETWEEN :a AND :b AND object_id = 20", a=WOCHE, b=WOCHE + timedelta(days=6))
    r = client.post(f"{API}/dienstplan/aus-vorlage", json={"woche": WOCHE.isoformat(), "vorschau": False}, headers=h).json()
    assert r["angelegt"] == 6 and r["kopie_id"]
    # Wochenansicht: 2 offene Luecken mit Grund; Plan-Status
    w = client.get(f"{API}/dienstplan?start={WOCHE.isoformat()}", headers=h).json()
    lu = [x for d in w["tage"] for x in d.get("luecken", [])]
    assert sorted((x["tag"], x["grund"]) for x in lu) == [("Di", "Absage"), ("Mo", "Urlaub")]
    assert w["plan"]["luecken"] == 2 and not w["plan"]["fertig"] and w["plan"]["abgabe"] == "2027-02-26T12:00"
    # Spontan eingeplant (Suemi springt Montag ein) -> Luecke weg
    assert client.post(f"{API}/dienstplan", json={"employee_id": sumi, "object_id": 20, "datum": WOCHE.isoformat(), "beginn": "13:00",
                                                  "ende": "16:00"}, headers=h).status_code == 200
    w = client.get(f"{API}/dienstplan?start={WOCHE.isoformat()}", headers=h).json()
    assert [x["grund"] for d in w["tage"] for x in d.get("luecken", [])] == ["Absage"]
    # Nochmal erzeugen: alles schon da; Rueckgaengig nimmt nur die Vorlage-Schichten weg
    assert client.post(f"{API}/dienstplan/aus-vorlage", json={"woche": WOCHE.isoformat()}, headers=h).json()["anzulegen"] == 0
    u = client.delete(f"{API}/dienstplan/kopie/{r['kopie_id']}", headers=h).json()
    assert u["entfernt"] == 6
    assert q(db, "SELECT count(*) FROM schedules WHERE date BETWEEN :a AND :b AND object_id = 20", a=WOCHE, b=WOCHE + timedelta(days=6))[0][0] == 1


def test_vorlage_sonntag_ruzica_bleibt_automatik(client, db):
    ruz = emp(db, "D0002")
    leer(db)
    h = ol_headers(db)
    vl(client, h, ruz, 6, "10:30", "19:00", obj=1)
    vl(client, h, ruz, 0, "12:45", "14:45")
    v = client.post(f"{API}/dienstplan/aus-vorlage", json={"woche": WOCHE.isoformat()}, headers=h).json()
    assert [e["tag"] for e in v["eintraege"]] == ["Mo"]    # Sonntag legt die Sonntagsautomatik an, nicht die Vorlage


# ---------- Plan naechste Woche / Erinnerung ----------

def test_plan_fertig_und_freitags_erinnerung(client, db, monkeypatch):
    from app.services import plan_vorlage as pv
    leer(db, von=date(2027, 3, 8), bis=date(2027, 3, 14))
    h = ol_headers(db)
    vl(client, h, emp(db, "D0040"), 0, "12:55", "15:55")
    ex(db, "UPDATE employees SET telegram_chat_id = '111' WHERE id = 4")                    # nur in der Transaktion
    gesendet = []
    monkeypatch.setattr(pv, "SEND", lambda chat, txt, knopf=None: gesendet.append((chat, txt, knopf)) or 1)
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "999")                                     # Drazen (Admin-Chat)
    fr = datetime(2027, 3, 5, 9, 0)                                                         # Freitag vor der Woche 08.03.
    r = pv.erinnerung_freitag(db, now=fr)
    assert r["status"] == "erinnert" and r["gesendet"] == 2 and r["luecken"] == 1           # Objektleitung UND Drazen
    assert {g[0] for g in gesendet} == {"111", "999"}
    txt, knopf = gesendet[0][1], gesendet[0][2]
    assert "Plan nächste Woche" in txt and "1 Lücke (Mo Lidl Neu Bie2 12:55)" in txt and "12:00" in txt
    assert knopf.inline_keyboard[0][0].text == "Plan öffnen" and knopf.inline_keyboard[0][0].url.endswith("/cockpit/dienstplan?start=2027-03-08&luecken=1")
    assert pv.erinnerung_freitag(db, now=fr)["status"] == "bereits_erinnert" and len(gesendet) == 2
    f = client.post(f"{API}/dienstplan/fertig", json={"woche": "2027-03-10"}, headers=h).json()
    assert f["fertig"] and f["woche"] == "2027-03-08" and f["gemeldet_von"]
    ex(db, "DELETE FROM audit_log WHERE action = 'plan_erinnerung'")
    r = pv.erinnerung_freitag(db, now=fr)                                                   # fertig, aber noch eine Luecke -> Meldung
    assert r["status"] == "erinnert" and "fertig gemeldet" in gesendet[-1][1]
    ex(db, "DELETE FROM audit_log WHERE action = 'plan_erinnerung'")
    ex(db, "DELETE FROM master_schedule_entries")
    assert pv.erinnerung_freitag(db, now=fr)["status"] == "fertig" and len(gesendet) == 4   # fertig, keine Luecke -> still
    assert client.post(f"{API}/dienstplan/fertig", json={"woche": "2027-03-08", "fertig": False}, headers=h).json()["fertig"] is False
    ls = client.get(f"{API}/leitstelle", headers=h).json()["plan_naechste_woche"]
    assert set(ls) >= {"woche", "fertig", "luecken", "schichten", "abgabe"}


def test_luecken_text_kurz():
    from app.services import plan_vorlage as pv
    lu = [{"datum": f"2027-03-{8 + i % 5:02d}", "tag": pv.WT[i % 5], "objekt": "Obj", "beginn": f"{8 + i:02d}:00"} for i in range(10)]
    t = pv.luecken_text(lu)
    assert t.startswith("Mo Obj 08:00") and t.endswith("+ 2 weitere") and t.count(",") == 8


def test_telegram_aus_auf_dev(monkeypatch):
    from app.services import plan_vorlage as pv
    monkeypatch.setenv("DISABLE_TELEGRAM", "1")
    assert pv._send("1", "x") is False


def test_fixum_donnerstag_entwurf(client, db, monkeypatch):
    """Do 18:00: nur feste Leute aus der Vorlage, Urlaub -> Luecke, nichts doppelt, Vorhandenes bleibt, einmal je Woche."""
    from app.services import plan_vorlage as pv
    mo = date(2027, 3, 8)
    leer(db, von=mo, bis=mo + timedelta(days=6))
    ex(db, "DELETE FROM app_settings WHERE key IN ('dienstplan_fixum', 'dienstplan_fertig')")
    h = ol_headers(db)
    lara, sumi = emp(db, "D0040"), emp(db, "D0038")
    vl(client, h, lara, 0, "12:55", "15:55")                                  # Mo
    vl(client, h, lara, 2, "12:55", "15:55")                                  # Mi: Urlaub -> Luecke
    vl(client, h, lara, 3, "12:55", "15:55")                                  # Do: schon jemand anders (Vertretung) eingeplant
    vl(client, h, sumi, 0, "06:00", "09:00", obj=20)
    ex(db, """INSERT INTO schedules (employee_id, object_id, date, weekday, start_time, end_time, planned_hours, status, is_driver, created_at, updated_at)
              VALUES (:e, 999, '2027-03-10', 2, '00:00', '23:59', 0, 'urlaub', false, now(), now()),
                     (:s, 20, '2027-03-11', 3, '12:55', '15:55', 3, 'normal', false, now(), now())""", e=lara, s=sumi)
    r = pv.fixum_entwurf(db, now=datetime(2027, 3, 4, 18, 0))                 # Donnerstag davor
    assert r["status"] == "erstellt" and r["angelegt"] == 2 and r["luecken"] == 1, r
    plan = q(db, "SELECT employee_id, date FROM schedules WHERE date BETWEEN '2027-03-08' AND '2027-03-14' AND status = 'normal' ORDER BY date, start_time")
    assert [(e, str(d)) for e, d in plan] == [(sumi, "2027-03-08"), (lara, "2027-03-08"), (sumi, "2027-03-11")]
    st = client.get(f"{API}/dienstplan?start=2027-03-08", headers=h).json()["plan"]
    assert st["fixum"]["angelegt"] == 2 and st["fixum"]["kopie_id"] and not st["fertig"] and st["luecken"] == 1
    assert pv.fixum_entwurf(db, now=datetime(2027, 3, 4, 18, 5))["status"] == "bereits_erstellt"
    assert q(db, "SELECT count(*) FROM schedules WHERE date BETWEEN '2027-03-08' AND '2027-03-14' AND status = 'normal'")[0][0] == 3
    u = client.delete(f"{API}/dienstplan/kopie/{st['fixum']['kopie_id']}", headers=h).json()   # Entwurf ganz zuruecknehmen
    assert u["entfernt"] == 2
    st = client.get(f"{API}/dienstplan?start=2027-03-08", headers=h).json()["plan"]
    assert st["fixum"]["zurueckgenommen"]                                      # kein zweiter Rueckgaengig-Knopf
    assert pv.fixum_entwurf(db, now=datetime(2027, 3, 4, 18, 30))["status"] == "bereits_erstellt"


def test_feiertag_kein_soll_keine_luecke(client, db):
    """Tiefentest: Vorlage/Fixum planen an Feiertagen (25./26.12.) nichts ein und melden dort keine Luecke."""
    from app.services import plan_vorlage as pv
    mo = date(2027, 12, 20)
    leer(db, von=mo, bis=mo + timedelta(days=6))
    ex(db, "DELETE FROM app_settings WHERE key IN ('dienstplan_fixum', 'dienstplan_fertig')")
    h = ol_headers(db)
    lara = emp(db, "D0040")
    vl(client, h, lara, 3, "12:55", "15:55")                                  # Do 23.12. normal
    vl(client, h, lara, 5, "09:00", "11:00")                                  # Sa 25.12. = 1. Weihnachtstag
    assert [str(d) for _, d in pv.soll(db, mo, mo + timedelta(days=6))] == ["2027-12-23"]
    r = pv.fixum_entwurf(db, now=datetime(2027, 12, 16, 18, 0))
    assert r["angelegt"] == 1 and r["luecken"] == 0


def test_fixum_nicht_wenn_fertig(client, db):
    from app.services import plan_vorlage as pv
    mo = date(2027, 3, 8)
    leer(db, von=mo, bis=mo + timedelta(days=6))
    ex(db, "DELETE FROM app_settings WHERE key IN ('dienstplan_fixum', 'dienstplan_fertig')")
    h = ol_headers(db)
    vl(client, h, emp(db, "D0040"), 0, "12:55", "15:55")
    client.post(f"{API}/dienstplan/fertig", json={"woche": "2027-03-08"}, headers=h)
    assert pv.fixum_entwurf(db, now=datetime(2027, 3, 4, 18, 0))["status"] == "fertig"


# ---------- Kontingent Festgehalt ----------

def test_kontingent_ruzica_januar_und_verteilen(client, db):
    ruz = emp(db, "D0002")
    leer(db, von=date(2027, 1, 1), bis=date(2027, 1, 31))
    h = ol_headers(db)
    k = client.get(f"{API}/kontingent?monat=2027-01", headers=h).json()
    p = [x for x in k["personen"] if x["employee_id"] == ruz][0]
    assert p["soll"] == 100 and p["sonntage_automatisch"]
    assert [s["datum"] for s in p["sonntage"]] == ["2027-01-03", "2027-01-10", "2027-01-17"] and p["sonntag_stunden"] == 24
    assert p["werktag_stunden"] == 0 and p["rest"] == 76
    assert client.get(f"{API}/kontingent?monat=2026-11", headers=h).json()["personen"] == []   # Festgehalt erst ab 2027
    v = client.post(f"{API}/kontingent/verteilen", json={"employee_id": ruz, "monat": "2027-01"}, headers=h).json()
    tage = [e["datum"] for e in v["eintraege"]]
    assert "2027-01-01" not in tage and "2027-01-06" not in tage                                  # Feiertage BW
    assert all(date.fromisoformat(d).weekday() < 5 for d in tage) and v["tage"] == 19
    std = sum((datetime.strptime(e["ende"], "%H:%M") - datetime.strptime(e["beginn"], "%H:%M")).seconds / 3600 for e in v["eintraege"])
    assert std == pytest.approx(76)
    s = client.post(f"{API}/kontingent/verteilen", json={"employee_id": ruz, "monat": "2027-01", "vorschau": False}, headers=h).json()
    assert s["angelegt"] == 19
    p = [x for x in client.get(f"{API}/kontingent?monat=2027-01", headers=h).json()["personen"] if x["employee_id"] == ruz][0]
    assert p["rest"] == pytest.approx(0, abs=0.01)
    assert client.post(f"{API}/kontingent/verteilen", json={"employee_id": ruz, "monat": "2027-01"}, headers=h).json()["hinweis"]
    client.delete(f"{API}/dienstplan/kopie/{s['kopie_id']}", headers=h)
    assert [x for x in client.get(f"{API}/kontingent?monat=2027-01", headers=h).json()["personen"] if x["employee_id"] == ruz][0]["rest"] == 76
