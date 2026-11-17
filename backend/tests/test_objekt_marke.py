"""Objekt-Logo / farbiges Kuerzel (Cockpit + Stempeluhr).

Laeuft NUR gegen dev_cockpit, Transaktion mit Rollback (Fixtures aus test_stempel_toleranz).
Aufruf: cd backend && ./venv/bin/python -m pytest tests/test_objekt_marke.py -q
"""
import base64
import struct
import zlib
from datetime import datetime, timedelta

import pytest
from jose import jwt
import os

from test_stempel_toleranz import db, client, telegram, q  # noqa: F401
from app.services import objekt_marke as om


def png(w, h):
    """Kleines gueltiges PNG (einfarbig) ohne Pillow."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    roh = b"".join(b"\x00" + b"\x1e\x53\x7c" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(roh)) + chunk(b"IEND", b""))


def data_url(b):
    return "data:image/png;base64," + base64.b64encode(b).decode()


def admin(db):
    email = q(db, "SELECT email FROM users WHERE role::text = 'ADMIN' AND is_active ORDER BY id LIMIT 1")[0][0]
    tk = jwt.encode({"sub": email, "exp": datetime.utcnow() + timedelta(hours=1)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    return {"Authorization": f"Bearer {tk}"}


def test_kuerzel_automatisch():
    assert om.kuerzel_auto("Lidl Neu Bie2") == "LI"
    assert om.kuerzel_auto("Gemeinde Musterstadt") == "GE"
    assert om.kuerzel_auto("A Bau GmbH") == "AB"
    assert om.kuerzel_auto("") == "?"


def test_farbe_aus_palette_und_lesbar():
    assert len(set(om.PALETTE)) == 8
    for f in om.PALETTE:
        assert om.text_farbe(f) in ("#000000", "#FFFFFF")
    assert om.text_farbe("#F0E442") == "#000000" and om.text_farbe("#0072B2") == "#FFFFFF"
    assert om.farbe_auto(20) in om.PALETTE


def test_logo_pruefung():
    assert om.pruefe_logo(data_url(png(160, 80))).startswith("data:image/png;base64,")
    for falsch in ["data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode(),
                   "https://example.com/logo.png", data_url(b"<html>kein png</html>"), data_url(png(400, 100))]:
        with pytest.raises(ValueError):
            om.pruefe_logo(falsch)


def test_cockpit_marke_logo_und_stempeluhr(client, db, telegram):
    h = admin(db)
    r = client.get("/api/v1/cockpit/objekt-marken", headers=h)
    assert r.status_code == 200 and r.json()["palette"] == om.PALETTE
    auto = r.json()["marken"]["20"]
    assert auto["auto"] and auto["kuerzel"] == om.kuerzel_auto("Lidl Neu Bie2") and auto["logo"] is None
    # Kuerzel/Farbe aendern, ungueltige Werte ablehnen
    assert client.put("/api/v1/cockpit/objekte/20/marke", headers=h, json={"farbe": "#123456"}).status_code == 400
    assert client.put("/api/v1/cockpit/objekte/20/marke", headers=h, json={"kuerzel": "LIDL"}).status_code == 400
    r = client.put("/api/v1/cockpit/objekte/20/marke", headers=h, json={"kuerzel": "lb", "farbe": "#009E73"})
    assert r.status_code == 200 and r.json()["kuerzel"] == "LB" and r.json()["farbe"] == "#009E73" and r.json()["text"] == "#000000"
    # Logo hochladen / ablehnen / entfernen
    assert client.put("/api/v1/cockpit/objekte/20/logo", headers=h, json={"logo": "https://example.com/x.png"}).status_code == 400
    r = client.put("/api/v1/cockpit/objekte/20/logo", headers=h, json={"logo": data_url(png(120, 60))})
    assert r.status_code == 200 and r.json()["logo"].startswith("data:image/png")
    assert q(db, "SELECT count(*) FROM audit_log WHERE action = 'objekt_marke_geaendert' AND entity_id = 20 AND created_at > now() - interval '1 minute'")[0][0] >= 2
    # Stempeluhr: Objektliste liefert die Marke mit (fuer den Offline-Cache)
    ma = q(db, "SELECT u.email FROM employees e JOIN users u ON u.id = e.user_id WHERE e.personal_nr = 'D0040'")[0][0]
    tk = jwt.encode({"sub": ma, "exp": datetime.utcnow() + timedelta(hours=1)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    objs = client.get("/api/v1/time-entries/my-c-objects", headers={"Authorization": f"Bearer {tk}"}).json()
    bie2 = [o for o in objs if o["id"] == 20][0]
    assert bie2["marke"]["kuerzel"] == "LB" and bie2["marke"]["logo"].startswith("data:image/png")
    r = client.delete("/api/v1/cockpit/objekte/20/logo", headers=h)
    assert r.status_code == 200 and r.json()["logo"] is None
    # zurueck auf automatisch
    r = client.put("/api/v1/cockpit/objekte/20/marke", headers=h, json={"kuerzel": "", "farbe": ""})
    assert r.json()["auto"] and r.json()["kuerzel"] == auto["kuerzel"]


def test_mitarbeiter_darf_nicht_aendern(client, db):
    ma = q(db, "SELECT u.email FROM employees e JOIN users u ON u.id = e.user_id WHERE e.personal_nr = 'D0040'")[0][0]
    tk = jwt.encode({"sub": ma, "exp": datetime.utcnow() + timedelta(hours=1)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    r = client.put("/api/v1/cockpit/objekte/20/marke", headers={"Authorization": f"Bearer {tk}"}, json={"kuerzel": "XX"})
    assert r.status_code in (401, 403)
