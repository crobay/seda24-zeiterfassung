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


def smtp_config():
    """Vorhandener Office-365-SMTP-Zugang des Servers (Passwort-Reset-Mails). Fuer die Lohnmails NUR im Testmodus."""
    return {"host": os.getenv("SMTP_HOST", "").strip(), "port": int(os.getenv("SMTP_PORT", "587") or 587),
            "user": os.getenv("SMTP_USER", "").strip(), "password": os.getenv("SMTP_PASSWORD", ""),
            "from": os.getenv("SMTP_FROM", "").strip()}


def weg(test: bool) -> str:
    """graph | smtp_test | datei_test | keiner - Reihenfolge: Graph, sonst (nur Test) SMTP, sonst (nur Test) .eml-Datei."""
    c = config()
    if c["tenant"] and c["client_id"] and c["secret"]:
        return "graph"
    if not test:
        return "keiner"
    s = smtp_config()
    return "smtp_test" if (s["host"] and s["user"] and s["password"]) else "datei_test"


WEG_TEXT = {"graph": "Microsoft Graph (Kopie in „Gesendete Elemente“)",
            "smtp_test": "Test über den SMTP-Zugang des Servers (nur an die Test-Adresse)",
            "datei_test": "Test als .eml-Dateien zum Herunterladen – nichts verlässt den Server",
            "keiner": "nicht eingerichtet"}


def status_versand():
    """Fuer das Cockpit: nur ob eingerichtet, nie Geheimnisse."""
    c = config()
    w = weg(True)
    return {"konfiguriert": w == "graph", "absender": c["from"], "weg": WEG_TEXT[w], "weg_test": w,
            "echt_erlaubt": echt_erlaubt()}


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
    from app.services.lohnablage import lesen
    for name, pfad in anhaenge:
        files.append({"@odata.type": "#microsoft.graph.fileAttachment", "name": name, "contentType": "application/pdf",
                      "contentBytes": base64.b64encode(lesen(pfad)).decode()})
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


class SmtpTestVersand:
    """Nur Testmodus: an die Test-Adresse ueber den vorhandenen SMTP-Zugang (STARTTLS). Absender = SMTP_FROM."""

    def __init__(self, test_an):
        import smtplib
        c = smtp_config()
        self.test_an = test_an.lower()
        self.absender = c["from"] or c["user"]
        self._s = smtplib.SMTP(c["host"], c["port"], timeout=30)
        self._s.starttls()
        self._s.login(c["user"], c["password"])

    def senden(self, msg):
        an = msg["toRecipients"][0]["emailAddress"]["address"]
        if an.lower() != self.test_an:       # Sicherung: dieser Weg schickt nie an Mitarbeiter
            raise RuntimeError("SMTP-Testweg: nur an die Test-Adresse")
        self._s.send_message(eml(msg, self.absender))

    def schliessen(self):
        try:
            self._s.quit()
        except Exception:
            pass


class DateiVersand:
    """Nur Testmodus: jede Mail als .eml (verschluesselt) im Monatsordner - zum Herunterladen und in Outlook oeffnen."""

    def __init__(self, ordner):
        import shutil
        self.absender = config()["from"]
        self.ordner = os.path.join(ordner, "testversand")
        shutil.rmtree(self.ordner, ignore_errors=True)      # nur der letzte Testlauf
        os.makedirs(self.ordner)
        self.n = 0

    def senden(self, msg):
        from app.services.lohnablage import schreiben
        self.n += 1
        an = re.sub(r"[^A-Za-z0-9.@_-]", "_", msg["toRecipients"][0]["emailAddress"]["address"])
        name = re.sub(r"[^A-Za-z0-9_-]", "_", msg["subject"].split("] ")[0].replace("[TEST – an ", ""))[:60]
        schreiben(os.path.join(self.ordner, f"{self.n:02d}_{name}_{an}.eml"), eml(msg, self.absender).as_bytes())

    def schliessen(self):
        pass


def eml(msg, absender):
    """Graph-Message -> E-Mail (fuer SMTP-Test und .eml-Datei)."""
    from email.message import EmailMessage
    from email.utils import formatdate
    e = EmailMessage()
    e["From"] = absender
    e["To"] = msg["toRecipients"][0]["emailAddress"]["address"]
    e["Subject"] = msg["subject"]
    e["Date"] = formatdate(localtime=True)
    e.set_content(msg["body"]["content"])
    for a in msg.get("attachments", []):
        e.add_attachment(base64.b64decode(a["contentBytes"]), maintype="application", subtype="pdf", filename=a["name"])
    return e


def verbinden(test=False, ordner=None, test_an=None):
    """Graph, wenn eingerichtet. Ohne Graph nur im Testmodus: SMTP-Zugang des Servers, sonst .eml-Dateien."""
    w = weg(test)
    if w == "smtp_test":
        return SmtpTestVersand(test_an)
    if w == "datei_test" and ordner:
        return DateiVersand(ordner)
    return Versand()
