"""Lohnversand per Mail (Monatsabschluss Schritt 5) - ersetzt den Versand aus dem PC-Skript seda_lohn_email.py.

Versand ueber Microsoft Graph sendMail aus dem freigegebenen Postfach lohn@seda.de ("SEDA24 Lohnbuchhaltung", Drazen
19.11.2026; buchhaltung@ bleibt fuer Kundenrechnungen) mit saveToSentItems=true: jede Lohn-Mail liegt danach in
"Gesendete Elemente" des Absender-Postfachs (Drazen 18.11.2026: KEIN BCC). Antworten der MA gehen an dasselbe Postfach. Reines SMTP ueber
Office 365 legt keine Kopie ab und braucht Basic Auth, die Microsoft abschaltet - deshalb Graph.

Zugangsdaten NUR aus dem Server-Secret (backend/.env, nicht im Git), App-Registrierung in Entra ID mit
Anwendungsberechtigung Mail.Send, per Application Access Policy auf lohn@seda.de beschraenkt:
    LOHNMAIL_GRAPH_TENANT_ID, LOHNMAIL_GRAPH_CLIENT_ID, LOHNMAIL_GRAPH_CLIENT_SECRET
    LOHNMAIL_ECHT=1 -> nur auf LIVE setzen: erst dann darf an die Mitarbeiter selbst verschickt werden.
                       Ohne diesen Schalter geht hoechstens der Testmodus ("alles an Drazen").
Einstellungen (app_settings "lohnversand", im Cockpit aenderbar): testmodus, test_an, absender (nur @seda.de),
absender_name, antwort_an (leer = Absender).
Geheimnis und Token werden nie ausgegeben, geloggt oder an das Frontend geliefert.
"""
import base64
import json
import os
import re
import time

from sqlalchemy import text

KEY = "lohnversand"
DEFAULT = {"testmodus": True, "test_an": "dsertic@seda.de", "absender": "lohn@seda.de",
           "absender_name": "SEDA24 Lohnbuchhaltung", "antwort_an": ""}
ABSENDER_DOMAIN = "@seda.de"
MAIL_RE = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[a-z]{2,}", re.I)
PAUSE_S = 1.0          # schonend fuer das Postfach (Exchange Online: max. 30 Mails/Minute)
GRAPH = "https://graph.microsoft.com/v1.0"


SECRET_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "secrets", "lohnmail_graph.json")


def _datei():
    try:
        with open(SECRET_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def config():
    """Zugang aus backend/.env (LOHNMAIL_GRAPH_*) oder - im Cockpit eingetragen - aus backend/secrets/lohnmail_graph.json."""
    d = _datei()
    return {"tenant": (os.getenv("LOHNMAIL_GRAPH_TENANT_ID", "") or d.get("tenant", "")).strip(),
            "client_id": (os.getenv("LOHNMAIL_GRAPH_CLIENT_ID", "") or d.get("client_id", "")).strip(),
            "secret": os.getenv("LOHNMAIL_GRAPH_CLIENT_SECRET", "") or d.get("secret", "")}


def absender_von(einst=None):
    """{adresse, name, antwort_an} aus den Einstellungen (Standard lohn@seda.de, "SEDA24 Lohnbuchhaltung")."""
    e = {**DEFAULT, **(einst or {})}
    return {"adresse": e["absender"], "name": e["absender_name"], "antwort_an": e["antwort_an"] or e["absender"]}


GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def zugang_speichern(db, werte: dict, user_id):
    """Nur schreiben, nie zuruecklesen: Tenant-ID, Client-ID, Geheimnis (Wert). Datei 0600, Audit ohne Werte."""
    from app.services.booking_service import log_audit
    t, c, g = (str(werte.get(k) or "").strip() for k in ("tenant", "client_id", "secret"))
    if not GUID_RE.fullmatch(t) or not GUID_RE.fullmatch(c):
        raise ValueError("Verzeichnis-ID (Tenant) und Anwendungs-ID (Client) sind je eine GUID (xxxxxxxx-xxxx-…)")
    if len(g) < 20 or GUID_RE.fullmatch(g):
        raise ValueError("Geheimnis: den WERT des geheimen Clientschlüssels eintragen, nicht die Geheimnis-ID")
    os.makedirs(os.path.dirname(SECRET_FILE), mode=0o700, exist_ok=True)
    tmp = SECRET_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"tenant": t, "client_id": c, "secret": g, "am": time.strftime("%Y-%m-%d %H:%M")}, f)
    os.replace(tmp, SECRET_FILE)
    log_audit(db, user_id, None, "lohnversand_zugang", entity_type="einstellung",
              details=f"Microsoft-Zugang für den Lohnversand eingetragen (Anwendungs-ID …{c[-4:]})")
    db.commit()
    return status_versand(db)


def verbindung_testen():
    """Nur Anmeldung bei Microsoft (Token holen) - es wird KEINE Mail geschickt."""
    try:
        Versand().schliessen()
        return {"ok": True, "text": "Anmeldung bei Microsoft erfolgreich – Versand ist eingerichtet (es wurde keine Mail geschickt)."}
    except Exception as e:
        return {"ok": False, "text": str(e)[:300]}


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


def status_versand(db=None):
    """Fuer das Cockpit: nur ob eingerichtet, nie Geheimnisse."""
    c = config()
    w = weg(True)
    d = _datei()
    a = absender_von(einstellungen(db) if db is not None else None)
    return {"konfiguriert": w == "graph", "absender": a["adresse"], "absender_name": a["name"], "antwort_an": a["antwort_an"], "weg": WEG_TEXT[w], "weg_test": w,
            "echt_erlaubt": echt_erlaubt(), "zugang_am": d.get("am"),
            "client_ende": c["client_id"][-4:] if len(c["client_id"]) > 12 else None}


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
    if "absender" in werte:
        v = (werte["absender"] or "").strip().lower()
        if not MAIL_RE.fullmatch(v) or not v.endswith(ABSENDER_DOMAIN):
            raise ValueError(f"Absender: eine Adresse {ABSENDER_DOMAIN} (z. B. lohn@seda.de)")
        neu["absender"] = v
    if "absender_name" in werte:
        v = re.sub(r"\s+", " ", str(werte["absender_name"] or "")).strip()
        if not 2 <= len(v) <= 80 or re.search(r'[<>"@]', v):
            raise ValueError("Anzeigename: 2 bis 80 Zeichen, ohne < > \" @")
        neu["absender_name"] = v
    if "antwort_an" in werte:
        v = (werte["antwort_an"] or "").strip().lower()
        if v and not MAIL_RE.fullmatch(v):
            raise ValueError("Antworten an: keine gültige Mail-Adresse (leer = Absender)")
        neu["antwort_an"] = v
    if not neu["testmodus"] and not echt_erlaubt():
        raise ValueError("Echter Versand an die Mitarbeiter ist auf diesem Server nicht freigeschaltet (nur Testmodus)")
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": KEY, "v": json.dumps(neu), "u": user_id})
    log_audit(db, user_id, None, "lohnversand_einstellung", entity_type="einstellung", old_value=alt, new_value=neu,
              details=f"Lohnversand (Absender {neu['absender_name']} <{neu['absender']}>): " + ("Testmodus (alles an " + neu["test_an"] + ")" if neu["testmodus"] else "ECHTER Versand an die Mitarbeiter"))
    db.commit()
    return neu


def nachricht(an, betreff, textkoerper, anhaenge, absender=None, html=None):
    """Graph-Message (JSON). anhaenge: [(dateiname, pfad)]; absender = absender_von(...) -> From + Antworten-an.
    Mit html: Graph bekommt den HTML-Teil, die .eml/SMTP-Mail beide Teile (Text + HTML, "_text" wird vor Graph entfernt)."""
    files = []
    from app.services.lohnablage import lesen
    for name, pfad in anhaenge:
        files.append({"@odata.type": "#microsoft.graph.fileAttachment", "name": name, "contentType": "application/pdf",
                      "contentBytes": base64.b64encode(lesen(pfad)).decode()})
    return {"subject": betreff, "body": {"contentType": "HTML", "content": html} if html else {"contentType": "Text", "content": textkoerper},
            **({"_text": textkoerper} if html else {}),
            "toRecipients": [{"emailAddress": {"address": an}}], "attachments": files,
            **({"from": {"emailAddress": {"address": absender["adresse"], "name": absender["name"]}},
                "replyTo": [{"emailAddress": {"address": absender["antwort_an"]}}]} if absender else {})}


class Versand:
    """Ein Token fuer den ganzen Lauf. In Tests ueber verbinden() durch eine Attrappe ersetzbar."""

    def __init__(self, absender=None):
        import requests
        c = config()
        if not (c["tenant"] and c["client_id"] and c["secret"]):
            raise RuntimeError("Mail-Zugang (LOHNMAIL_GRAPH_*) ist auf diesem Server nicht eingerichtet")
        self.absender = (absender or absender_von())["adresse"]
        self._http = requests.Session()
        r = self._http.post(f"https://login.microsoftonline.com/{c['tenant']}/oauth2/v2.0/token", timeout=20,
                            data={"grant_type": "client_credentials", "client_id": c["client_id"],
                                  "client_secret": c["secret"], "scope": "https://graph.microsoft.com/.default"})
        if r.status_code != 200:
            raise RuntimeError(f"Anmeldung bei Microsoft fehlgeschlagen (HTTP {r.status_code}: {_fehlertext(r)})")
        self._http.headers["Authorization"] = "Bearer " + r.json()["access_token"]

    def senden(self, msg):
        msg = {k: v for k, v in msg.items() if not k.startswith("_")}
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
    """Nur Testmodus: an die Test-Adresse ueber den vorhandenen SMTP-Zugang (STARTTLS). Absender-Adresse = SMTP_FROM
    (Office 365 laesst ueber SMTP nur das eigene Konto zu), Anzeigename + Antworten-an wie beim echten Versand."""

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
        e = eml(msg, self.absender)
        from email.utils import formataddr
        name = (msg.get("from") or {}).get("emailAddress", {}).get("name")
        del e["From"]
        e["From"] = formataddr((f"{name} (Test über SMTP)" if name else "", self.absender))
        self._s.send_message(e)

    def schliessen(self):
        try:
            self._s.quit()
        except Exception:
            pass


class DateiVersand:
    """Nur Testmodus: jede Mail als .eml (verschluesselt) im Monatsordner - zum Herunterladen und in Outlook oeffnen."""

    def __init__(self, ordner, absender=None):
        import shutil
        self.absender = (absender or absender_von())["adresse"]
        self.ordner = os.path.join(ordner, "testversand")
        shutil.rmtree(self.ordner, ignore_errors=True)      # nur der letzte Testlauf
        os.makedirs(self.ordner)
        self.n = 0

    def senden(self, msg):
        from app.services.lohnablage import schreiben
        self.n += 1
        an = re.sub(r"[^A-Za-z0-9.@_-]", "_", msg["toRecipients"][0]["emailAddress"]["address"])
        name = re.sub(r"[^A-Za-z0-9_-]", "_", msg["subject"].split("] ")[0].replace("[TEST – an ", ""))[:60]
        from email import policy
        schreiben(os.path.join(self.ordner, f"{self.n:02d}_{name}_{an}.eml"), eml(msg, self.absender).as_bytes(policy=policy.SMTP))

    def schliessen(self):
        pass


def eml(msg, absender):
    """Graph-Message -> E-Mail (fuer SMTP-Test und .eml-Datei)."""
    from email.message import EmailMessage
    from email.utils import formataddr, formatdate
    e = EmailMessage()
    von = (msg.get("from") or {}).get("emailAddress") or {"address": absender}
    e["From"] = formataddr((von.get("name") or "", von["address"]))
    if msg.get("replyTo"):
        e["Reply-To"] = msg["replyTo"][0]["emailAddress"]["address"]
    e["To"] = msg["toRecipients"][0]["emailAddress"]["address"]
    e["Subject"] = msg["subject"]
    e["Date"] = formatdate(localtime=True)
    # Sauberes UTF-8 (Drazen 21.11.: "Kilome=er"): Text und HTML base64-kodiert statt quoted-printable,
    # .eml mit CRLF (policy.SMTP) - so bricht kein Mailprogramm Umlaute oder Zeilen falsch um.
    if msg["body"]["contentType"] == "HTML":
        e.set_content(msg.get("_text") or "", charset="utf-8", cte="base64")
        e.add_alternative(msg["body"]["content"], subtype="html", charset="utf-8", cte="base64")
    else:
        e.set_content(msg["body"]["content"], charset="utf-8", cte="base64")
    for a in msg.get("attachments", []):
        e.add_attachment(base64.b64decode(a["contentBytes"]), maintype="application", subtype="pdf", filename=a["name"])
    return e


def verbinden(test=False, ordner=None, test_an=None, absender=None):
    """Graph, wenn eingerichtet. Ohne Graph nur im Testmodus: SMTP-Zugang des Servers, sonst .eml-Dateien."""
    w = weg(test)
    if w == "smtp_test":
        return SmtpTestVersand(test_an)
    if w == "datei_test" and ordner:
        return DateiVersand(ordner, absender)
    return Versand(absender)
