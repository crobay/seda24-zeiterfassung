"""Upload-PC fuer Lohnabrechnungen (seda24_lohn_upload.ps1 auf Drazens Laptop) - Lebenszeichen, Fehler, Vollstaendigkeit
(Drazen 26.11.2026 00:41).

- Lebenszeichen: jeder Lauf des Skripts meldet sich (/export/lohn-pc/lebenszeichen, auch Stand-Abfrage, Upload und
  Fehlermeldung zaehlen). Der Server merkt sich Zeit, Rechner und was das Skript in den Lexware-Ordnern gesehen hat.
  Anzeige im Monatsabschluss, Schritt 3.
- Stille: Telegram, wenn sich der PC 24 Std. nicht gemeldet hat (nur Stunden an Werktagen zaehlen); zwischen Exporttag
  des Vormonats und dessen Abschluss schon nach 3 Std. (nur Werktage 07-22 Uhr, so lange laeuft das Skript).
  Hoechstens eine Erinnerung je 24 Std., erst wenn sich der PC schon einmal gemeldet hat.
- Fehler: Telegram "Lohnabrechnung-Upload fehlgeschlagen", gleicher Text hoechstens einmal in 6 Std. (Protokoll immer).
- Vollstaendig: Telegram "📄 Lohnabrechnungen <Monat>: x von y da", einmal je Monat.
Alles in app_settings (Schluessel lohn_upload_pc, JSON). Telegram ueber notify_admin, Meldungsart Sonstiges.
"""
import hashlib
import json
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from app.services.export_termine import exporttag, ist_werktag, vormonat

logger = logging.getLogger(__name__)
KEY = "lohn_upload_pc"
STILL_STD = 24            # Werktagsstunden ohne Meldung
STILL_STD_PHASE = 3       # Betriebsstunden (Werktag 07-22) zwischen Exporttag und Abschluss
BETRIEB = (time(7, 0), time(22, 0))
FEHLER_PAUSE = timedelta(hours=6)
ERINNERUNG_PAUSE = timedelta(hours=24)


def _jetzt():
    return datetime.now()


def lesen(db) -> dict:
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": KEY}).fetchone()
    try:
        return json.loads(r[0]) if r else {}
    except (TypeError, ValueError):
        return {}


def _schreiben(db, z: dict):
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at) VALUES (:k, :v, now())
                       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"""),
               {"k": KEY, "v": json.dumps(z, ensure_ascii=False)})
    db.commit()


def _melden(text_):
    from app.services.telegram_bot import notify_admin
    notify_admin(text_, category="sonstiges")


def _ts(dt):
    return dt.isoformat(timespec="seconds")


def _dt(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


# ------------------------------------------------------------------ Lebenszeichen

def gemeldet(db, rechner: str, ordner=None, version=None, jetzt=None):
    """Der PC hat sich gemeldet. ordner: {'2026-10': '12 Dateien'} (was das Skript gesehen hat), nur beim Lebenszeichen."""
    z = lesen(db)
    z["zuletzt"] = _ts(jetzt or _jetzt())
    z["rechner"] = (rechner or "PC")[:40]
    if ordner is not None:
        z["ordner"] = {str(k)[:7]: str(v)[:80] for k, v in list(ordner.items())[:4]}
    if version:
        z["version"] = str(version)[:20]
    z.pop("still_gemeldet", None)
    _schreiben(db, z)


def betriebsstunden(von: datetime, bis: datetime, nur_betrieb: bool) -> float:
    """Stunden zwischen von und bis, die zaehlen: nur Werktage (Mo-Fr ohne Feiertage BW); nur_betrieb: nur 07-22 Uhr."""
    if bis <= von:
        return 0.0
    s, d = 0.0, von.date()
    while d <= bis.date():
        if ist_werktag(d):
            a = datetime.combine(d, BETRIEB[0] if nur_betrieb else time(0))
            b = datetime.combine(d, BETRIEB[1]) if nur_betrieb else datetime.combine(d + timedelta(days=1), time(0))
            a, b = max(a, von), min(b, bis)
            if b > a:
                s += (b - a).total_seconds() / 3600
        d += timedelta(days=1)
    return s


def lohnphase(db, heute: date = None):
    """Monat 'JJJJ-MM', wenn heute zwischen Exporttag des Vormonats und dessen Abschluss liegt, sonst None."""
    heute = heute or date.today()
    vm = vormonat(heute)
    if heute < exporttag(vm):
        return None
    st = db.execute(text("SELECT status FROM monatsabschluss WHERE monat = :k"), {"k": vm}).scalar() \
        if db.execute(text("SELECT to_regclass('monatsabschluss') IS NOT NULL")).scalar() else None
    return None if st == "abgeschlossen" else vm


def status(db, jetzt=None) -> dict:
    """Fuer Schritt 3 und die Stille-Pruefung."""
    jetzt = jetzt or _jetzt()
    z = lesen(db)
    zuletzt = _dt(z.get("zuletzt"))
    phase = lohnphase(db, jetzt.date())
    grenze, nur_betrieb = (STILL_STD_PHASE, True) if phase else (STILL_STD, False)
    still = betriebsstunden(zuletzt, jetzt, nur_betrieb) if zuletzt else None
    return {"zuletzt": z.get("zuletzt"), "rechner": z.get("rechner"), "ordner": z.get("ordner") or {},
            "version": z.get("version"), "letzter_fehler": z.get("letzter_fehler"),
            "phase": phase, "grenze_std": grenze, "nur_betrieb": nur_betrieb,
            "still_std": None if still is None else round(still, 1),
            "ueberfaellig": bool(still is not None and still >= grenze)}


def stille_pruefen(db, jetzt=None):
    """Stuendlich (Scheduler): zu lange keine Meldung -> Telegram, hoechstens einmal je 24 Std."""
    jetzt = jetzt or _jetzt()
    st = status(db, jetzt)
    if not st["ueberfaellig"]:
        return None
    z = lesen(db)
    letzte = _dt(z.get("still_gemeldet"))
    if letzte and jetzt - letzte < ERINNERUNG_PAUSE:
        return None
    zl = _dt(st["zuletzt"])
    wann = f"{zl:%d.%m. %H:%M}"
    if st["phase"]:
        y, m = map(int, st["phase"].split("-"))
        from app.services.monatsabschluss import MONATE
        grund = f"Lohnabrechnungen {MONATE[m]} {y} stehen an, Upload-PC seit {wann} still (über {st['grenze_std']} Std.)"
    else:
        grund = f"seit {wann} keine Meldung (über {st['grenze_std']} Std. an Werktagen)"
    msg = (f"⚠️ Lohnabrechnung-Upload: {st['rechner'] or 'Upload-PC'} meldet sich nicht – {grund}. "
           f"Bitte prüfen: Laptop an, Laufwerk X: verbunden, Aufgabe \"SEDA24 Lohnabrechnungen Upload\".")
    _melden(msg)
    z["still_gemeldet"] = _ts(jetzt)
    _schreiben(db, z)
    return msg


# ------------------------------------------------------------------ Fehler

def fehler(db, rechner: str, msg: str, jetzt=None) -> bool:
    """Fehlermeldung des PC-Skripts: zaehlt als Lebenszeichen; Telegram nur, wenn derselbe Text nicht schon in den
    letzten 6 Std. gemeldet wurde. Rueckgabe: Telegram gesendet?"""
    jetzt = jetzt or _jetzt()
    msg = (msg or "ohne Text").strip()[:500]
    rechner = (rechner or "PC")[:40]
    gemeldet(db, rechner, jetzt=jetzt)
    z = lesen(db)
    h = hashlib.sha1(msg.lower().encode()).hexdigest()[:16]
    gesendet = {k: v for k, v in (z.get("fehler_gesendet") or {}).items()
                if _dt(v) and jetzt - _dt(v) < FEHLER_PAUSE}
    neu = h not in gesendet
    if neu:
        _melden(f"⚠️ Lohnabrechnung-Upload fehlgeschlagen ({rechner}): {msg}")
        gesendet[h] = _ts(jetzt)
    z["fehler_gesendet"] = gesendet
    z["letzter_fehler"] = {"am": _ts(jetzt), "text": msg}
    _schreiben(db, z)
    return neu


# ------------------------------------------------------------------ Vollstaendig

def komplett_melden(db, y, m):
    """Nach jedem Upload/Zuordnen: Monat jetzt vollstaendig -> einmal Telegram. Fehler hier stoeren den Upload nie."""
    try:
        from app.services import monatsabschluss as ma
        st = ma.lohnabrechnungen_stand(db, y, m)
        k = ma.monat_key(y, m)
        z = lesen(db)
        schon = z.get("komplett_gemeldet") or []
        if not st["komplett"] or not st["erwartet"] or k in schon:
            return None
        msg = f"📄 Lohnabrechnungen {ma.MONATE[m]} {y}: {st['da']} von {st['erwartet']} da"
        _melden(msg)
        z["komplett_gemeldet"] = (schon + [k])[-12:]
        _schreiben(db, z)
        return msg
    except Exception as e:
        logger.error(f"Lohnabrechnungen komplett-Meldung fehlgeschlagen: {e}")
        db.rollback()
        return None
