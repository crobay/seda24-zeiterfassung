"""Ablage der Monatsabschluss-Dokumente (Lohnabrechnungen aus Lexware, Zeitnachweis, KM-Journal) - Drazen 19.11.2026.

- Liegt unter backend/data/abschluss/JJJJ-MM/ (ausserhalb des Web-Ordners httpdocs, nicht im Git).
- Jede Datei verschluesselt (Fernet = AES-128-CBC + HMAC-SHA256), Endung .enc. Schluessel in
  backend/secrets/lohnablage_key (0600, wird beim ersten Gebrauch erzeugt, nie ausgegeben). Ohne Schluessel sind die
  Dateien unlesbar - der Schluessel gehoert deshalb in die Server-Sicherung wie backend/.env.
- Aufbewahrung: Einstellung app_settings "lohnablage" {"aufbewahrung_monate": N}; der taegliche Job loescht die Dateien
  N Monate nach Monatsende (Eintrag bleibt fuer das Protokoll, pfad = ''). Die Originale bleiben in Lexware/OneDrive.
"""
import json
import os
from calendar import monthrange
from datetime import date

from sqlalchemy import text

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KEY_FILE = os.path.join(BACKEND, "secrets", "lohnablage_key")
EINST_KEY = "lohnablage"
DEFAULT = {"aufbewahrung_monate": 3}


def _fernet():
    from cryptography.fernet import Fernet
    if not os.path.exists(KEY_FILE):
        os.makedirs(os.path.dirname(KEY_FILE), mode=0o700, exist_ok=True)
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(Fernet.generate_key())
    with open(KEY_FILE, "rb") as f:
        return Fernet(f.read().strip())


def schreiben(pfad: str, daten: bytes) -> str:
    """Speichert verschluesselt unter pfad + '.enc' und gibt diesen Pfad zurueck."""
    ziel = pfad if pfad.endswith(".enc") else pfad + ".enc"
    tmp = ziel + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(_fernet().encrypt(daten))
    os.replace(tmp, ziel)
    return ziel


def lesen(pfad: str) -> bytes:
    with open(pfad, "rb") as f:
        b = f.read()
    return _fernet().decrypt(b) if pfad.endswith(".enc") else b


def einstellungen(db) -> dict:
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": EINST_KEY}).fetchone()
    try:
        g = json.loads(r[0]) if r else {}
    except (TypeError, ValueError):
        g = {}
    return {k: g.get(k, v) for k, v in DEFAULT.items()}


def einstellungen_speichern(db, werte: dict, user_id):
    from app.services.booking_service import log_audit
    try:
        n = int(werte.get("aufbewahrung_monate"))
    except (TypeError, ValueError):
        raise ValueError("Aufbewahrung: Anzahl Monate angeben")
    if not 1 <= n <= 120:
        raise ValueError("Aufbewahrung: 1–120 Monate")
    alt = einstellungen(db)
    neu = {**alt, "aufbewahrung_monate": n}
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": EINST_KEY, "v": json.dumps(neu), "u": user_id})
    log_audit(db, user_id, None, "lohnablage_einstellung", entity_type="einstellung", old_value=alt, new_value=neu,
              details=f"Lohnablage: Dateien {n} Monate nach Monatsende löschen")
    db.commit()
    return neu


def loeschdatum(monat: str, monate: int) -> date:
    """Erster Tag, an dem die Dateien des Monats geloescht werden (Monatsende + N Monate)."""
    y, m = int(monat[:4]), int(monat[5:7])
    m2 = m + monate
    y2, m2 = y + (m2 - 1) // 12, (m2 - 1) % 12 + 1
    return date(y2, m2, monthrange(y2, m2)[1])


def aufraeumen(db, heute: date = None) -> dict:
    """Loescht Dateien abgelaufener Monate. Nur Dateien - die Eintraege bleiben (pfad = '')."""
    from app.services.booking_service import log_audit
    heute = heute or date.today()
    n = einstellungen(db)["aufbewahrung_monate"]
    weg = {}
    for r in db.execute(text("SELECT id, monat, pfad FROM monatsabschluss_dokument WHERE pfad <> ''")).mappings().all():
        if heute < loeschdatum(r["monat"], n):
            continue
        if os.path.exists(r["pfad"]):
            os.remove(r["pfad"])
        db.execute(text("UPDATE monatsabschluss_dokument SET pfad = '' WHERE id = :i"), {"i": r["id"]})
        weg[r["monat"]] = weg.get(r["monat"], 0) + 1
    for monat, k in sorted(weg.items()):
        log_audit(db, None, None, "lohnablage_geloescht", entity_type="monat", entity_id=int(monat.replace("-", "")),
                  details=f"Lohnablage {monat}: {k} Datei(en) nach Ablauf der Aufbewahrung ({n} Monate) gelöscht")
    db.commit()
    return weg
