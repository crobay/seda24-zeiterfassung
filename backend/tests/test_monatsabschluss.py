"""Monatsabschluss (Prototyp): Rechte, Pruefliste/Haken, Lexware-Datei, Zuordnung der Lohnabrechnungen, Vorschau,
Trockenlauf-Versand + Sperre. Nur gegen dev_cockpit, jeder Test in einer Transaktion mit Rollback; Dateien in tmp_path.
"""
import io
import os
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
    docs = {d["dateiname"]: d for d in r["dokumente"]}
    assert docs["D0040_Lohnabrechnung.pdf"]["employee_id"] == lara and docs["unbekannt.pdf"]["employee_id"] is None
    r = client.post(f"{API}/2026-10/lohnabrechnungen", files=[("dateien", ("D0040.pdf", PDF + b"lara", "application/pdf"))], headers=h).json()
    assert r["neu"] == 0 and r["doppelt"] == 1                                             # gleicher Inhalt nicht doppelt
    v = client.get(f"{API}/2026-10/vorschau", headers=h).json()
    lv = next(x for x in v["mitarbeiter"] if x["employee_id"] == lara)
    assert lv["anrede"] == "Liebe Lara" and "Oktober 2026" in lv["betreff"] and "Zeitnachweis" in lv["fehlt"]
    assert len(v["nicht_zugeordnet"]) == 1 and all(not x["personal_nr"].startswith("A") for x in v["mitarbeiter"])
    assert next((x for x in v["mitarbeiter"] if x["personal_nr"] == "D0002"), {"ohne_km": True})["ohne_km"]
    # Versand: nur wenn alles gruen und bereit -> sonst 409; mit allem bereit: Trockenlauf + Sperre
    assert client.post(f"{API}/2026-10/versenden", headers=h).status_code == 409
    monkeypatch.setattr(ma, "pruefliste", lambda db, y, m: {"alle_gruen": True, "punkte": []})
    monkeypatch.setattr(ma, "vorschau", lambda db, y, m: {"bereit": 1, "gesamt": 1, "nicht_zugeordnet": [], "mitarbeiter": [
        {"employee_id": lara, "email": "x@example.org", "betreff": "B", "anhaenge": [{"datei": "a.pdf"}]}]})
    p = client.post(f"{API}/2026-10/versenden", headers=h).json()
    assert p["status"] == "abgeschlossen" and p["versand"][0]["status"] == "simuliert" and p["gesperrt_am"]
    assert ma.gesperrt(db, 2026, 10)
    assert client.post(f"{API}/2026-10/versenden", headers=h).status_code == 423
    assert client.post(f"{API}/2026-10/lohnabrechnungen", files=[("dateien", ("n.pdf", PDF + b"n", "application/pdf"))], headers=h).status_code == 423
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": ""}, headers=h).status_code == 409
    assert client.post(f"{API}/2026-10/wieder-oeffnen", json={"grund": "Korrektur Lara"}, headers=h).json()["status"] == "erzeugt"
    assert q(db, "SELECT count(*) FROM audit_log WHERE action LIKE 'abschluss_%' AND created_at > now() - interval '1 minute'")[0][0] >= 3


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
    r = ma.erzeugen(db, 2026, 10, 1)
    assert gesehen and all(g.startswith(str(tmp_path)) and "seda24_pdfs" not in g for g in gesehen)
    assert not r["fehler"] and r["dokumente"]
    assert not os.path.exists(os.path.join(str(tmp_path), "2026-10", ".erzeugen"))
