"""Lohnversand ueber Microsoft Graph (ohne Netz): Anmeldung, sendMail mit saveToSentItems (Kopie in "Gesendete
Elemente" von lohn@seda.de, Absender einstellbar), kein BCC, Fehlertexte ohne Geheimnisse, kein Versand ohne Zugangsdaten."""
import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cockpit_rechte import db  # noqa: E402,F401

from app.services import lohnversand as lv  # noqa: E402


class Antwort:
    def __init__(self, code, j=None):
        self.status_code, self._j, self.text = code, j or {}, str(j)

    def json(self):
        return self._j


class FakeSession:
    def __init__(self, token_code=200, send_code=202):
        self.headers, self.calls, self.token_code, self.send_code = {}, [], token_code, send_code

    def post(self, url, data=None, json=None, timeout=None):
        self.calls.append((url, data, json))
        if "login.microsoftonline.com" in url:
            return Antwort(self.token_code, {"access_token": "tok"} if self.token_code == 200 else
                           {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret"})
        return Antwort(self.send_code, None if self.send_code == 202 else {"error": {"message": "Access is denied"}})

    def close(self):
        pass


@pytest.fixture
def env(monkeypatch):
    for k, v in {"LOHNMAIL_GRAPH_TENANT_ID": "t-id", "LOHNMAIL_GRAPH_CLIENT_ID": "c-id",
                 "LOHNMAIL_GRAPH_CLIENT_SECRET": "geheim-123"}.items():
        monkeypatch.setenv(k, v)


def test_sendmail_mit_kopie_in_gesendete_elemente(env, monkeypatch, tmp_path):
    import requests
    fs = FakeSession()
    monkeypatch.setattr(requests, "Session", lambda: fs)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    ab = lv.absender_von()                                   # Standard: lohn@seda.de, "SEDA24 Lohnbuchhaltung" (Drazen 19.11.)
    v = lv.verbinden(absender=ab)
    v.senden(lv.nachricht("lara@example.org", "Betreff", "Liebe Lara,", [("Lohnabrechnung_2026_11_D0040_H_Lara.pdf", str(pdf))], ab))
    url, data, body = fs.calls[-1]
    assert url == "https://graph.microsoft.com/v1.0/users/lohn@seda.de/sendMail"
    assert body["saveToSentItems"] is True
    m = body["message"]
    assert m["toRecipients"] == [{"emailAddress": {"address": "lara@example.org"}}]
    assert m["from"] == {"emailAddress": {"address": "lohn@seda.de", "name": "SEDA24 Lohnbuchhaltung"}}
    assert m["replyTo"] == [{"emailAddress": {"address": "lohn@seda.de"}}]           # Antworten der MA -> lohn@
    assert "bccRecipients" not in m and "ccRecipients" not in m
    a = m["attachments"][0]
    assert a["name"].startswith("Lohnabrechnung_") and base64.b64decode(a["contentBytes"]) == b"%PDF-1.4 test"
    assert fs.headers["Authorization"] == "Bearer tok"
    assert fs.calls[0][1]["scope"] == "https://graph.microsoft.com/.default"


def test_fehler_ohne_geheimnis(env, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "Session", lambda: FakeSession(token_code=401))
    with pytest.raises(RuntimeError) as e:
        lv.verbinden()
    assert "401" in str(e.value) and "geheim-123" not in str(e.value)
    fs = FakeSession(send_code=403)
    monkeypatch.setattr(requests, "Session", lambda: fs)
    with pytest.raises(RuntimeError, match="403: Access is denied"):
        lv.verbinden().senden(lv.nachricht("a@b.de", "B", "T", []))


def test_ohne_zugangsdaten_kein_versand(monkeypatch):
    for k in ("LOHNMAIL_GRAPH_TENANT_ID", "LOHNMAIL_GRAPH_CLIENT_ID", "LOHNMAIL_GRAPH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="nicht eingerichtet"):
        lv.verbinden()
    s = lv.status_versand()
    assert s["konfiguriert"] is False and s["absender"] == "lohn@seda.de"


def test_status_zeigt_keine_geheimnisse(env):
    assert "geheim-123" not in str(lv.status_versand()) and "c-id" not in str(lv.status_versand())


def test_zugang_im_cockpit_nur_schreiben(db, monkeypatch, tmp_path):
    for k in ("LOHNMAIL_GRAPH_TENANT_ID", "LOHNMAIL_GRAPH_CLIENT_ID", "LOHNMAIL_GRAPH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(lv, "SECRET_FILE", str(tmp_path / "s" / "lohnmail_graph.json"))

    g = "11111111-2222-3333-4444-555555555555"
    with pytest.raises(ValueError, match="WERT"):
        lv.zugang_speichern(db, {"tenant": g, "client_id": g, "secret": g}, 1)       # Geheimnis-ID statt Wert
    st = lv.zugang_speichern(db, {"tenant": g, "client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeee1234", "secret": "x" * 40}, 1)
    assert st["konfiguriert"] is True and st["client_ende"] == "1234" and "secret" not in json.dumps(st) and "x" * 10 not in json.dumps(st)
    assert oct(os.stat(lv.SECRET_FILE).st_mode & 0o777) == "0o600"
    assert lv.config()["secret"] == "x" * 40


def test_absender_einstellbar(db):
    """Absender im Cockpit einstellbar - nur @seda.de; Antworten-an leer = Absender; geht in Graph-Pfad und From."""
    e = lv.einstellungen_speichern(db, {"absender": "Buchhaltung@seda.de", "absender_name": "SEDA24 Buchhaltung"}, None)
    assert e["absender"] == "buchhaltung@seda.de" and lv.absender_von(e)["antwort_an"] == "buchhaltung@seda.de"
    e = lv.einstellungen_speichern(db, {"absender": "lohn@seda.de", "absender_name": "SEDA24 Lohnbuchhaltung", "antwort_an": "drazen@seda.de"}, None)
    assert lv.absender_von(e) == {"adresse": "lohn@seda.de", "name": "SEDA24 Lohnbuchhaltung", "antwort_an": "drazen@seda.de"}
    for falsch in ({"absender": "lohn@gmail.com"}, {"absender": "kaputt"}, {"absender_name": "x"}, {"absender_name": "A <b@c.de>"},
                   {"antwort_an": "nix"}):
        with pytest.raises(ValueError):
            lv.einstellungen_speichern(db, falsch, None)
    assert lv.status_versand(db)["antwort_an"] == "drazen@seda.de"
    m = lv.nachricht("a@b.de", "B", "T", [], lv.absender_von(e))
    em = lv.eml(m, "x@y.de")
    assert em["From"] == "SEDA24 Lohnbuchhaltung <lohn@seda.de>" and em["Reply-To"] == "drazen@seda.de"
