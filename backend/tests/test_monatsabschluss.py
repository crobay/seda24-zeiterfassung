"""Monatsabschluss (Prototyp): Rechte, Pruefliste/Haken, Lexware-Datei, Zuordnung der Lohnabrechnungen, Vorschau,
Versand (Graph-Attrappe, Testmodus/echt, erneut senden) + Sperre. Nur gegen dev_cockpit, jeder Test in einer Transaktion mit Rollback; Dateien in tmp_path.
"""
import io
import os
import re
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token, ol_headers  # noqa: E402,F401

from app.services import monatsabschluss as ma  # noqa: E402

API = "/api/v1/cockpit/abschluss"
PDF = b"%PDF-1.4\n% Muster\n"


def admin_h(db):
    return token(db, "ADMIN")


@pytest.fixture(autouse=True)
def tmp_daten(tmp_path, monkeypatch, db):
    """Dateien in tmp_path; Oktober in der Transaktion auf Anfang (unabhaengig vom DEV-Demo-Stand)."""
    from sqlalchemy import text
    monkeypatch.setattr(ma, "DATEN", str(tmp_path))
    ma.tabellen(db)
    for t in ("monatsabschluss_versand", "monatsabschluss_dokument", "monatsabschluss"):
        db.execute(text(f"DELETE FROM {t} WHERE monat = '2026-10'"))


def test_nur_admin(client, db):
    assert client.get(f"{API}/2026-10", headers=ol_headers(db)).status_code == 403      # Objektleitung nicht
    assert client.get(f"{API}/2026-10").status_code in (401, 422)
    r = client.get(f"{API}/2026-10", headers=admin_h(db))
    assert r.status_code == 200 and r.json()["status"] == "offen"
    assert client.get(f"{API}/2026-13", headers=admin_h(db)).status_code == 400


def test_ueberspringen_und_anrede():
    assert ma.ueberspringen("A0001", False) and ma.ueberspringen("TEST01", False) and ma.ueberspringen("D0040", True)
    assert not ma.ueberspringen("D0040", False)
    assert ma.anrede("Lara", "W") == "Liebe Lara" and ma.anrede("Ruzica", "F") == "Liebe Ruzica"
    assert ma.anrede("Matej", "M") == "Lieber Matej" and ma.anrede("Kim", None) == "Hallo Kim"


def test_haken_erst_wenn_gruen(client, db, monkeypatch):
    h = admin_h(db)
    p = client.get(f"{API}/2026-10", headers=h).json()["pruefliste"]
    assert "bestaetigt" not in {x["key"] for x in p["punkte"]}  # Monatsbestaetigung wird nicht genutzt (Drazen 18.11.)
    rot = [x for x in p["punkte"] if x["auto"] is False]
    if rot:
        r = client.post(f"{API}/2026-10/haken", json={"key": rot[0]["key"]}, headers=h)
        assert r.status_code == 409 and "Erst erledigen" in r.json()["detail"]
    hand = [x for x in p["punkte"] if x["auto"] is None][0]
    r = client.post(f"{API}/2026-10/haken", json={"key": hand["key"]}, headers=h).json()
    assert next(x for x in r["punkte"] if x["key"] == hand["key"])["gruen"]
    r = client.post(f"{API}/2026-10/haken", json={"key": hand["key"], "wert": False}, headers=h).json()
    assert not next(x for x in r["punkte"] if x["key"] == hand["key"])["gruen"] and not r["alle_gruen"]
    assert client.post(f"{API}/2026-10/haken", json={"key": "gibtsnicht"}, headers=h).status_code == 404
    assert client.post(f"{API}/2026-10/erzeugen", headers=h).status_code == 409             # Pruefliste nicht gruen


def test_lexware_datei_format(db):
    from sqlalchemy import text
    db.execute(text("DELETE FROM app_settings WHERE key = 'lexware_lohnarten'"))
    with pytest.raises(ValueError, match="Lohnart-Nummer fehlt"):        # Platzhalter: Drazen traegt normal/sonder/km ein
        ma.lexware_datei(db, 2026, 10)
    assert "Stunden" in ma.fehlende_lohnarten(db, 2026, 10)
    ma.lohnarten_speichern(db, {"normal": 1000, "sonder": 1001, "km": 1002}, 1)
    assert ma.fehlende_lohnarten(db, 2026, 10) == []
    zeilen = ma.lexware_zeilen(db, 2026, 10)
    assert zeilen and all(not ma.ueberspringen(p, False) for p, *_ in zeilen)
    lohn = {r["personal_nr"]: r for r in ma.lohnzeilen(db, 2026, 10)}
    la = ma.lohnarten(db)
    for p, _n, nr, wert, _s, _b in zeilen:                                               # Werte 1:1 aus der Lohnuebersicht
        if nr == la["km"]:
            assert wert == round(lohn[p]["km_amount"], 2)
    txt = ma.lexware_datei(db, 2026, 10).decode("cp1252")
    z = txt.split("\r\n")
    assert z[0] == "Jahr;Monat;Personalnummer;Lohnart;Wert;Stundensatz"
    assert all(len(x.split(";")) == 6 for x in z[1:-1]) and z[-1] == ""
    assert all(x.startswith("2026;10;D") for x in z[1:-1]) and "." not in "".join(x.split(";")[4] for x in z[1:-1])
    ma.lohnarten_speichern(db, {"persnr": "nur_ziffern", "kopfzeile": False}, 1)
    z2 = ma.lexware_datei(db, 2026, 10).decode("cp1252").split("\r\n")
    assert not z2[0].startswith("Jahr") and z2[0].split(";")[2].isdigit()
    with pytest.raises(ValueError):
        ma.lohnarten_speichern(db, {"km": 0}, 1)
    assert ma.lohnarten_speichern(db, {"km": ""}, 1)["km"] is None                        # wieder leer = Platzhalter


def test_summen_je_lohnart_d0002_ohne_km(db):
    """Je MA hoechstens eine Zeile je Lohnart (Summen, keine Tageswerte); D0002 nie mit KM-Geld (Dienstwagen)."""
    from collections import Counter
    ma.lohnarten_speichern(db, {"normal": 1000, "sonder": 1001, "km": 1002}, 1)
    for y, m in ((2026, 9), (2026, 10)):
        zeilen = ma.lexware_zeilen(db, y, m)
        c = Counter((p, nr, b) for p, _n, nr, *_x, b in zeilen)
        assert c and max(c.values()) == 1
        assert not [z for z in zeilen if z[0] == "D0002" and z[2] == 1002]


def test_anhang_namen_v25():
    assert ma.anhang_name("lohnabrechnung", 2026, 11, "D0040", "Hardt-Fabrizis", "Lara") == \
        "Lohnabrechnung_2026_11_D0040_Hardt-Fabrizis_Lara.pdf"
    assert ma.anhang_name("km", 2026, 3, "D0038", "Müller Öz", "Zyumbyul") == "KM-Journal_2026_03_D0038_Mueller-Oez_Zyumbyul.pdf"
    assert ma.anhang_name("zeitnachweis", 2026, 11, "D0002", "Sertic", "Ruzica").startswith("Zeitnachweis_2026_11_D0002_")


def test_zuordnung_dateiname(db):
    lara = q(db, "SELECT id FROM employees WHERE personal_nr = 'D0040'")[0][0]
    for name, wie in [("D0040_Lohnabrechnung_10_2026.pdf", "persnr"), ("Lohnabrechnung Lara Hardt-Fabrizis Oktober.pdf", "name"),
                      ("hardt-fabrizis_10.pdf", "nachname"), ("00040_Abrechnung.pdf", "persnr")]:
        assert ma.zuordnen_name(db, name) == (lara, wie), name
    assert ma.zuordnen_name(db, "Abrechnung_Oktober.pdf") == (None, None)


def test_upload_vorschau_versand_sperre(client, db, monkeypatch):
    h = admin_h(db)
    lara = q(db, "SELECT id FROM employees WHERE personal_nr = 'D0040'")[0][0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Lexware/D0040_Lohnabrechnung.pdf", PDF + b"lara")
        zf.writestr("Lexware/unbekannt.pdf", PDF + b"x")
        zf.writestr("liesmich.txt", "kein pdf")
    r = client.post(f"{API}/2026-10/lohnabrechnungen", files=[("dateien", ("lohn.zip", buf.getvalue(), "application/zip"))], headers=h).json()
    assert r["neu"] == 2
    docs = {d["dateiname"]: d for d in r["dokumente"] if d["art"] == "lohnabrechnung"}
    assert docs["Lohnabrechnung_2026_10_D0040_Hardt-Fabrizis_Lara.pdf"]["employee_id"] == lara      # v2.5-Name
    assert docs["unbekannt.pdf"]["employee_id"] is None
    r = client.post(f"{API}/2026-10/lohnabrechnungen", files=[("dateien", ("D0040.pdf", PDF + b"lara", "application/pdf"))], headers=h).json()
    assert r["neu"] == 0 and r["doppelt"] == 1                                             # gleicher Inhalt nicht doppelt
    v = client.get(f"{API}/2026-10/vorschau", headers=h).json()
    lv = next(x for x in v["mitarbeiter"] if x["employee_id"] == lara)
    assert lv["anrede"] == "Liebe Lara" and "Oktober 2026" in lv["betreff"] and "Zeitnachweis" in lv["fehlt"]
    assert len(v["nicht_zugeordnet"]) == 1 and all(not x["personal_nr"].startswith("A") for x in v["mitarbeiter"])
    assert next((x for x in v["mitarbeiter"] if x["personal_nr"] == "D0002"), {"ohne_km": True})["ohne_km"]
    # Versand: nur wenn alles gruen und bereit -> sonst 409
    assert client.post(f"{API}/2026-10/versenden", headers=h).status_code == 409
    gesendet = attrappe(monkeypatch)
    monkeypatch.setattr(ma, "pruefliste", lambda db, y, m: {"alle_gruen": True, "punkte": []})
    ma_eintrag = {"employee_id": lara, "personal_nr": "D0040", "name": "Lara H", "email": "lara@example.org", "betreff": "B",
                  "text": "Liebe Lara,", "anhaenge": [], "fehlt": [], "bereit": True}
    monkeypatch.setattr(ma, "vorschau", lambda db, y, m: {"bereit": 1, "gesamt": 1, "nicht_zugeordnet": [], "mitarbeiter": [ma_eintrag]})
    # 1) Testmodus (Standard): alles an Drazen, Betreff mit echtem Empfaenger, Monat bleibt offen
    p = client.post(f"{API}/2026-10/versenden", headers=h).json()
    assert {k: v for k, v in p["ergebnis"].items() if k != "weg"} == {"gesendet": 1, "fehler": 0, "testmodus": True} and p["status"] != "abgeschlossen"
    msg = gesendet[-1]
    assert msg["toRecipients"] == [{"emailAddress": {"address": "dsertic@seda.de"}}] and "lara@example.org" in msg["subject"]
    assert [a["name"] for a in msg["attachments"]] == ["Lohnabrechnung_2026_10_D0040_Hardt-Fabrizis_Lara.pdf"]
    assert "ccRecipients" not in msg and "bccRecipients" not in msg                         # kein BCC (Drazen 18.11.)
    assert p["je_ma"][0]["status"] == "test"
    # 2) echter Versand ohne Freischaltung (LOHNMAIL_ECHT) nicht einstellbar
    monkeypatch.delenv("LOHNMAIL_ECHT", raising=False)
    assert client.put(f"{API}/einstellungen/lohnversand", json={"testmodus": False}, headers=h).status_code == 409
    monkeypatch.setenv("LOHNMAIL_ECHT", "1")
    r = client.put(f"{API}/einstellungen/lohnversand", json={"testmodus": False}, headers=h).json()
    assert r["einstellungen"] == {"testmodus": False, "test_an": "dsertic@seda.de"} and "secret" not in str(r).lower()
    p = client.post(f"{API}/2026-10/versenden", headers=h).json()
    assert p["status"] == "abgeschlossen" and p["gesperrt_am"] and p["je_ma"][0]["status"] == "gesendet"
    assert gesendet[-1]["toRecipients"][0]["emailAddress"]["address"] == "lara@example.org"
    assert ma.gesperrt(db, 2026, 10)
    assert client.post(f"{API}/2026-10/versenden", headers=h).status_code == 423
    assert client.post(f"{API}/2026-10/lohnabrechnungen", files=[("dateien", ("n.pdf", PDF + b"n", "application/pdf"))], headers=h).status_code == 423
    # 3) einzelnen MA erneut senden (auch im gesperrten Monat); Fehler wird je MA protokolliert
    attrappe(monkeypatch, fehler=True)
    p = client.post(f"{API}/2026-10/versenden/{lara}", headers=h).json()
    assert p["ergebnis"]["fehler"] == 1 and p["je_ma"][0]["status"] == "fehler" and "Graph" in p["je_ma"][0]["fehler"]
    attrappe(monkeypatch)
    p = client.post(f"{API}/2026-10/versenden/{lara}", headers=h).json()
    assert p["je_ma"][0]["status"] == "gesendet" and len(p["versand"]) == 4
    assert client.post(f"{API}/2026-10/versenden/999999", headers=h).status_code == 409
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": ""}, headers=h).status_code == 409
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": "Korrektur Lara"}, headers=h).json()["status"] == "erzeugt"
    assert client.post(f"{API}/2026-10/sperren", headers=h).json()["status"] == "abgeschlossen"
    assert q(db, "SELECT count(*) FROM audit_log WHERE action LIKE 'abschluss_%' AND created_at > now() - interval '1 minute'")[0][0] >= 5


def attrappe(monkeypatch, fehler=False):
    """Ersetzt Microsoft Graph: merkt sich die Nachrichten statt sie zu verschicken."""
    from app.services import lohnversand as lv
    gesendet = []

    class Fake:
        absender = "buchhaltung@seda.de"

        def senden(self, msg):
            if fehler:
                raise RuntimeError("Microsoft Graph HTTP 503: Service unavailable")
            gesendet.append(msg)

        def schliessen(self):
            pass
    monkeypatch.setattr(lv, "verbinden", lambda *a, **k: Fake())
    monkeypatch.setattr(lv, "PAUSE_S", 0)
    return gesendet


def test_pdfs_frisch_im_eigenen_ordner(db, monkeypatch, tmp_path):
    """Nie Dateien aus dem gemeinsamen /tmp/seda24_pdfs nehmen (dort liegen ggf. alte LIVE-PDFs)."""
    from app.core import pdf_generator
    gesehen = []

    def fake(self, eid, y, m):
        gesehen.append(self.output_dir)
        p = os.path.join(self.output_dir, f"Zeitnachweis_{eid}.pdf")
        open(p, "wb").write(PDF)
        return p
    monkeypatch.setattr(pdf_generator.PDFGenerator, "generate_zeitnachweis", fake)
    monkeypatch.setattr(pdf_generator.PDFGenerator, "generate_kilometer", fake)
    monkeypatch.setattr(ma, "pruefliste", lambda db, y, m: {"alle_gruen": True, "punkte": []})
    ma.lohnarten_speichern(db, {"normal": 1000, "sonder": 1001, "km": 1002}, 1)
    r = ma.erzeugen(db, 2026, 10, 1)
    namen = [d["dateiname"] for d in r["dokumente"]]
    assert all(re.fullmatch(r"(Zeitnachweis|KM-Journal)_2026_10_D\d{4}_[A-Za-z-]+_[A-Za-z-]+\.pdf", x) for x in namen), namen
    assert not [x for x in namen if x.startswith("KM-Journal_2026_10_D0002_")]
    assert gesehen and all(g.startswith(str(tmp_path)) and "seda24_pdfs" not in g for g in gesehen)
    assert not r["fehler"] and r["dokumente"]
    assert not os.path.exists(os.path.join(str(tmp_path), "2026-10", ".erzeugen"))
