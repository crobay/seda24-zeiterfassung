"""Lohnabrechnungen vom PC (Drazen 19.11.2026): verschluesselte Ablage, Zuordnung aus Dateiname/PDF-Text,
Sammel-PDF je MA aufteilen, Upload-Endpunkt mit Pruefsumme/Quittung, x von y da, Loeschfrist, Testversand als .eml.
Nur dev_cockpit, Transaktion mit Rollback, Dateien in tmp_path."""
import hashlib
import io
import os
import sys
import zipfile
from datetime import date

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db, client, q, token  # noqa: E402,F401

from app.services import lohnablage as la  # noqa: E402
from app.services import monatsabschluss as ma  # noqa: E402


def pdf_mit_text(*seiten):
    """Minimales PDF, je Seite eine Textzeile (Helvetica) - pypdf liest den Text wieder aus."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for t in seiten:
        stream = f"BT /F1 12 Tf 50 750 Td ({t}) Tj ET".encode("latin-1")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
        kids.append(len(objs) + 1)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {len(objs)} 0 R >>")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, xref = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        xref.append(len(out))
        out += f"{i} 0 obj\n".encode() + (o if isinstance(o, bytes) else o.encode("latin-1")) + b"\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{p:010d} 00000 n \n".encode() for p in xref)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return out


@pytest.fixture(autouse=True)
def tmp_daten(tmp_path, monkeypatch, db):
    monkeypatch.setattr(ma, "DATEN", str(tmp_path / "abschluss"))
    monkeypatch.setattr(la, "KEY_FILE", str(tmp_path / "secrets" / "lohnablage_key"))
    monkeypatch.setenv("COCKPIT_ABSCHLUSS", "1")
    ma.tabellen(db)
    for t in ("monatsabschluss_versand", "monatsabschluss_dokument", "monatsabschluss"):
        db.execute(text(f"DELETE FROM {t} WHERE monat = '2026-10'"))


def ma_id(db, pnr):
    return q(db, "SELECT id FROM employees WHERE personal_nr = :p", p=pnr)[0][0]


def test_ablage_verschluesselt(tmp_path):
    p = la.schreiben(str(tmp_path / "x.pdf"), b"%PDF-1.4 geheim Lohn")
    assert p.endswith(".enc") and b"geheim" not in open(p, "rb").read()
    assert la.lesen(p) == b"%PDF-1.4 geheim Lohn"
    assert oct(os.stat(p).st_mode & 0o777) == "0o600" and oct(os.stat(la.KEY_FILE).st_mode & 0o777) == "0o600"


def test_sammel_pdf_wird_je_ma_aufgeteilt(db):
    lara, helena = ma_id(db, "D0040"), ma_id(db, "D0039")
    b = pdf_mit_text("Abrechnung Oktober 2026 Lara Hardt-Fabrizis", "Seite 2 ohne Namen",
                     "Abrechnung Oktober 2026 Helena Martin", "Firma ohne Personenbezug")
    qt = ma.lohnabrechnungen_aufnehmen(db, 2026, 10, [("Lohnabrechnung_Oktober.pdf", b)], None)[0]
    assert qt["status"] == "gespeichert" and qt["sha256"] == hashlib.sha256(b).hexdigest()
    assert [(t["employee_id"], t["seiten"]) for t in qt["teile"]] == [(lara, [1, 2]), (helena, [3, 4])]
    docs = {d["employee_id"]: d for d in ma.dokumente(db, 2026, 10)["dokumente"]}
    assert docs[lara]["dateiname"] == "Lohnabrechnung_2026_10_D0040_Hardt-Fabrizis_Lara.pdf"
    pfad = q(db, "SELECT pfad FROM monatsabschluss_dokument WHERE employee_id = :e AND monat = '2026-10'", e=lara)[0][0]
    from pypdf import PdfReader
    assert len(PdfReader(io.BytesIO(la.lesen(pfad))).pages) == 2


def test_zuordnung_einzeln_und_widerspruch(db):
    lara = ma_id(db, "D0040")
    a = ma.lohnabrechnungen_aufnehmen(db, 2026, 10, [("Lohnabrechnung_2026_10_D0040.pdf", pdf_mit_text("Brutto/Netto"))], None)[0]
    assert a["teile"][0]["employee_id"] == lara and a["teile"][0]["zuordnung"] == "persnr"
    b = ma.lohnabrechnungen_aufnehmen(db, 2026, 10, [("Lohnabrechnung_x.pdf", pdf_mit_text("Abrechnung Lara Hardt-Fabrizis"))], None)[0]
    assert b["teile"][0]["employee_id"] == lara and b["teile"][0]["zuordnung"] == "PDF-Text"
    c = ma.lohnabrechnungen_aufnehmen(db, 2026, 10, [("Lohnabrechnung_D0040.pdf", pdf_mit_text("Abrechnung Helena Martin"))], None)[0]
    assert c["teile"][0]["employee_id"] is None and c["teile"][0]["zuordnung"].startswith("Widerspruch")


def test_stand_x_von_y(db):
    st = ma.lohnabrechnungen_stand(db, 2026, 10)
    assert st["da"] == 0 and st["erwartet"] > 0 and not st["komplett"]
    ma.lohnabrechnungen_aufnehmen(db, 2026, 10, [("Lohnabrechnung_D0040.pdf", pdf_mit_text("Lara Hardt-Fabrizis"))], None)
    st2 = ma.lohnabrechnungen_stand(db, 2026, 10)
    assert st2["da"] == 1 and len(st2["fehlen"]) == st["erwartet"] - 1


def test_pc_upload_endpunkt(client, db, monkeypatch):
    from app.api.v1.endpoints import export
    monkeypatch.setattr(export, "_check", lambda *a, **k: None)     # Schluessel/HTTPS-Pruefung: eigene Tests
    b = pdf_mit_text("Lohnabrechnung Lara Hardt-Fabrizis")
    sha = hashlib.sha256(b).hexdigest()
    h = {"X-Dateiname": "Lohnabrechnung_2026_10_D0040.pdf", "X-SHA256": sha, "X-Rechner": "SEDA2026", "Content-Type": "application/pdf"}
    U = "/api/v1/export/lohnabrechnungen/2026-10"
    assert client.post(U, content=b, headers={**h, "X-SHA256": "0" * 64}).status_code == 422          # Pruefsumme
    r = client.post(U, content=b, headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["quittung"]["status"] == "gespeichert" and j["quittung"]["sha256"] == sha and j["stand"]["da"] == 1
    assert client.post(U, content=b, headers=h).json()["quittung"]["status"] == "doppelt"
    st = client.get(U).json()
    assert sha in st["sha256"] and st["da"] == 1
    assert client.post("/api/v1/export/lohnabrechnungen/2025-01", content=b, headers=h).status_code == 400
    assert q(db, "SELECT count(*) FROM audit_log WHERE action = 'lohnabrechnung_upload' AND details LIKE '%SEDA2026%'")[0][0] >= 2
    monkeypatch.delenv("COCKPIT_ABSCHLUSS")
    assert client.get(U).status_code == 404
    # gesperrter Monat: keine Uploads mehr
    monkeypatch.setenv("COCKPIT_ABSCHLUSS", "1")
    db.execute(text("INSERT INTO monatsabschluss (monat, status) VALUES ('2026-10', 'abgeschlossen') "
                    "ON CONFLICT (monat) DO UPDATE SET status = 'abgeschlossen'"))
    b2 = pdf_mit_text("anderer Inhalt")
    assert client.post(U, content=b2, headers={**h, "X-SHA256": hashlib.sha256(b2).hexdigest()}).status_code == 409


def test_loeschfrist(db):
    assert la.loeschdatum("2026-10", 3) == date(2027, 1, 31) and la.loeschdatum("2026-11", 2) == date(2027, 1, 31)
    ma.lohnabrechnungen_aufnehmen(db, 2026, 10, [("Lohnabrechnung_D0040.pdf", pdf_mit_text("Lara Hardt-Fabrizis"))], None)
    pfad = q(db, "SELECT pfad FROM monatsabschluss_dokument WHERE monat = '2026-10'")[0][0]
    la.einstellungen_speichern(db, {"aufbewahrung_monate": 1}, None)
    assert la.aufraeumen(db, heute=date(2026, 11, 29)) == {} and os.path.exists(pfad)
    assert la.aufraeumen(db, heute=date(2026, 11, 30)) == {"2026-10": 1} and not os.path.exists(pfad)
    assert q(db, "SELECT pfad FROM monatsabschluss_dokument WHERE monat = '2026-10'")[0][0] == ""
    with pytest.raises(ValueError):
        la.einstellungen_speichern(db, {"aufbewahrung_monate": 0}, None)


def test_testversand_als_eml_ohne_zugang(monkeypatch, tmp_path):
    from app.services import lohnversand as lv
    for k in ("LOHNMAIL_GRAPH_TENANT_ID", "LOHNMAIL_GRAPH_CLIENT_ID", "LOHNMAIL_GRAPH_CLIENT_SECRET", "SMTP_HOST", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    assert lv.weg(True) == "datei_test" and lv.weg(False) == "keiner"
    with pytest.raises(RuntimeError, match="nicht eingerichtet"):
        lv.verbinden(False, str(tmp_path))                     # echter Versand nie ohne Graph
    anh = la.schreiben(str(tmp_path / "a.pdf"), b"%PDF-1.4 anhang")
    v = lv.verbinden(True, os.path.join(ma.DATEN, "2026-10"), "dsertic@seda.de")
    v.senden(lv.nachricht("dsertic@seda.de", "[TEST – an Lara H <l@x.de>] Lohn", "Text", [("Lohnabrechnung_x.pdf", anh)]))
    z = zipfile.ZipFile(io.BytesIO(ma.testversand_zip(2026, 10)))
    (name,) = z.namelist()
    assert name.endswith(".eml") and b"Lohnabrechnung_x.pdf" in z.read(name)


def test_smtp_testweg_nur_an_test_adresse(monkeypatch):
    from app.services import lohnversand as lv
    import smtplib
    gesendet = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, m): gesendet.append(m["To"])
        def quit(self): pass
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for k in ("LOHNMAIL_GRAPH_TENANT_ID", "LOHNMAIL_GRAPH_CLIENT_ID", "LOHNMAIL_GRAPH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example"); monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    v = lv.verbinden(True, None, "test@seda.de")
    v.senden(lv.nachricht("test@seda.de", "B", "T", []))
    with pytest.raises(RuntimeError, match="nur an die Test-Adresse"):
        v.senden(lv.nachricht("lara@example.org", "B", "T", []))
    assert gesendet == ["test@seda.de"]
