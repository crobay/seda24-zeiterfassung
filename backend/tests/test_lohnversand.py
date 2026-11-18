"""Lohnversand ueber Microsoft Graph (ohne Netz): Anmeldung, sendMail mit saveToSentItems (Kopie in "Gesendete
Elemente" von buchhaltung@seda.de), kein BCC, Fehlertexte ohne Geheimnisse, kein Versand ohne Zugangsdaten."""
import base64

import pytest

from app.services import lohnversand as lv


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
                 "LOHNMAIL_GRAPH_CLIENT_SECRET": "geheim-123", "LOHNMAIL_FROM": "buchhaltung@seda.de"}.items():
        monkeypatch.setenv(k, v)


def test_sendmail_mit_kopie_in_gesendete_elemente(env, monkeypatch, tmp_path):
    import requests
    fs = FakeSession()
    monkeypatch.setattr(requests, "Session", lambda: fs)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    v = lv.verbinden()
    v.senden(lv.nachricht("lara@example.org", "Betreff", "Liebe Lara,", [("Lohnabrechnung_2026_11_D0040_H_Lara.pdf", str(pdf))]))
    url, data, body = fs.calls[-1]
    assert url == "https://graph.microsoft.com/v1.0/users/buchhaltung@seda.de/sendMail"
    assert body["saveToSentItems"] is True
    m = body["message"]
    assert m["toRecipients"] == [{"emailAddress": {"address": "lara@example.org"}}]
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
    assert s["konfiguriert"] is False and s["absender"] == "buchhaltung@seda.de"


def test_status_zeigt_keine_geheimnisse(env):
    assert "geheim-123" not in str(lv.status_versand()) and "c-id" not in str(lv.status_versand())
