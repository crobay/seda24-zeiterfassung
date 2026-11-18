"""Lohnversand per Mail (Monatsabschluss Schritt 5) - ersetzt den Versand aus dem PC-Skript seda_lohn_email.py.

Versand ueber Microsoft Graph sendMail aus dem Postfach buchhaltung@seda.de mit saveToSentItems=true: jede Lohn-Mail
liegt danach in "Gesendete Elemente" von buchhaltung@seda.de (Drazen 18.11.2026: KEIN BCC). Reines SMTP ueber
Office 365 legt keine Kopie ab und braucht Basic Auth, die Microsoft abschaltet - deshalb Graph.

Zugangsdaten NUR aus dem Server-Secret (backend/.env, nicht im Git), App-Registrierung in Entra ID mit
Anwendungsberechtigung Mail.Send, per Application Access Policy auf buchhaltung@seda.de beschraenkt:
    LOHNMAIL_GRAPH_TENANT_ID, LOHNMAIL_GRAPH_CLIENT_ID, LOHNMAIL_GRAPH_CLIENT_SECRET
    LOHNMAIL_FROM   (Standard buchhaltung@seda.de)
    LOHNMAIL_ECHT=1 -> nur auf LIVE setzen: erst dann darf an die Mitarbeiter selbst verschickt werden.
                       Ohne diesen Schalter geht hoechstens der Testmodus ("alles an Drazen").
Einstellungen (app_settings "lohnversand", im Cockpit aenderbar): testmodus, test_an.
Geheimnis und Token werden nie ausgegeben, geloggt oder an das Frontend geliefert.
"""
import base64
import json
import os
import re
import time

from sqlalchemy import text

KEY = "lohnversand"
DEFAULT = {"testmodus": True, "test_an": "dsertic@seda.de"}
MAIL_RE = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[a-z]{2,}", re.I)
PAUSE_S = 1.0          # schonend fuer das Postfach (Exchange Online: max. 30 Mails/Minute)
GRAPH = "https://graph.microsoft.com/v1.0"


def config():
    return {"tenant": os.getenv("LOHNMAIL_GRAPH_TENANT_ID", "").strip(),
            "client_id": os.getenv("LOHNMAIL_GRAPH_CLIENT_ID", "").strip(),
            "secret": os.getenv("LOHNMAIL_GRAPH_CLIENT_SECRET", ""),
            "from": os.getenv("LOHNMAIL_FROM", "buchhaltung@seda.de").strip() or "buchhaltung@seda.de"}


def echt_erlaubt() -> bool:
    return os.getenv("LOHNMAIL_ECHT", "") == "1"


def status_versand():
    """Fuer das Cockpit: nur ob eingerichtet, nie Geheimnisse."""
    c = config()
    return {"konfiguriert": bool(c["tenant"] and c["client_id"] and c["secret"]), "absender": c["from"],
            "weg": "Microsoft Graph (Kopie in „Gesendete Elemente“)", "echt_erlaubt": echt_erlaubt()}


def einstellungen(db):
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": KEY}).fetchone()
    try:
        gespeichert = json.loads(r[0]) if r else {}
    except (TypeError, ValueError):
        gespeichert = {}
    return {k: gespeichert.get(k, v) for k, v in DEFAULT.items()}


def einstellungen_speichern(db, werte: dict, user_id):
    from app.services.booking_service import log_audit
    alt = einstellungen(db)
    neu = dict(alt)
    if "testmodus" in werte:
        neu["testmodus"] = bool(werte["testmodus"])
    if "test_an" in werte:
        v = (werte["test_an"] or "").strip()
        if not MAIL_RE.fullmatch(v):
            raise ValueError("Test-Adresse: keine gültige Mail-Adresse")
        neu["test_an"] = v
    if not neu["testmodus"] and not echt_erlaubt():
        raise ValueError("Echter Versand an die Mitarbeiter ist auf diesem Server nicht freigeschaltet (nur Testmodus)")
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": KEY, "v": json.dumps(neu), "u": user_id})
    log_audit(db, user_id, None, "lohnversand_einstellung", entity_type="einstellung", old_value=alt, new_value=neu,
              details="Lohnversand: " + ("Testmodus (alles an " + neu["test_an"] + ")" if neu["testmodus"] else "ECHTER Versand an die Mitarbeiter"))
    db.commit()
    return neu


def nachricht(an, betreff, textkoerper, anhaenge):
    """Graph-Message (JSON). anhaenge: [(dateiname, pfad)]"""
    files = []
    for name, pfad in anhaenge:
        with open(pfad, "rb") as f:
            files.append({"@odata.type": "#microsoft.graph.fileAttachment", "name": name, "contentType": "application/pdf",
                          "contentBytes": base64.b64encode(f.read()).decode()})
    return {"subject": betreff, "body": {"contentType": "Text", "content": textkoerper},
            "toRecipients": [{"emailAddress": {"address": an}}], "attachments": files}


class Versand:
    """Ein Token fuer den ganzen Lauf. In Tests ueber verbinden() durch eine Attrappe ersetzbar."""

    def __init__(self):
        import requests
        c = config()
        if not (c["tenant"] and c["client_id"] and c["secret"]):
            raise RuntimeError("Mail-Zugang (LOHNMAIL_GRAPH_*) ist auf diesem Server nicht eingerichtet")
        self.absender = c["from"]
        self._http = requests.Session()
        r = self._http.post(f"https://login.microsoftonline.com/{c['tenant']}/oauth2/v2.0/token", timeout=20,
                            data={"grant_type": "client_credentials", "client_id": c["client_id"],
                                  "client_secret": c["secret"], "scope": "https://graph.microsoft.com/.default"})
        if r.status_code != 200:
            raise RuntimeError(f"Anmeldung bei Microsoft fehlgeschlagen (HTTP {r.status_code}: {_fehlertext(r)})")
        self._http.headers["Authorization"] = "Bearer " + r.json()["access_token"]

    def senden(self, msg):
        r = self._http.post(f"{GRAPH}/users/{self.absender}/sendMail", json={"message": msg, "saveToSentItems": True}, timeout=60)
        if r.status_code != 202:
            raise RuntimeError(f"Microsoft Graph HTTP {r.status_code}: {_fehlertext(r)}")

    def schliessen(self):
        self._http.close()


def _fehlertext(r):
    try:
        j = r.json()
        e = j.get("error")
        return (e.get("message") if isinstance(e, dict) else j.get("error_description") or e or "")[:200]
    except Exception:
        return r.text[:200]


def verbinden():
    return Versand()
