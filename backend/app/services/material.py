"""Materialmeldung (Drazen 22.11.2026).

- MA-App: "Material melden" nur fuer Objekte mit Dienst heute oder morgen (Dienstplan), Objekt vorausgewaehlt.
  Artikelliste je Objekt mit Menge, dazu "Sonstiges" (1 Zeile, max. 120 Zeichen) und optional 1 Foto.
  Der MA sieht den Status: gemeldet / bestellt / liegt bereit. Ein MA schreibt nie direkt an Kunden.
- Cockpit (Admin + Objektleitung): Liste der Meldungen, Status bestellt/erledigt per Klick, Mengen aenderbar,
  Artikelliste je Objekt pflegbar (Start-Vorlage VORLAGE), Objekt-Einstellung "Material stellt: Kunde | SEDA24"
  mit Kunden-Ansprechpartner. Stellt der Kunde das Material: "An Kunden senden" -> HTML-Mail von SEDA24.
- Telegram an Drazen und Objektleitung bei neuer Meldung (Empfaenger-Kategorie "material"); nicht erledigt nach
  24 h -> jeden Morgen 08:00 eine Erinnerung, bis erledigt. Auf DEV (DISABLE_TELEGRAM) wird nur protokolliert.
- Mail an Kunden: eigener Absender (app_settings "materialmail", nicht lohn@), Testmodus wie die Lohn-Mail (.eml),
  echter Versand an Kunden erst mit MATERIALMAIL_ECHT=1 in backend/.env.
"""
import base64
import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from html import escape

from sqlalchemy import text

logger = logging.getLogger(__name__)

VORLAGE = ["Müllbeutel 60 l", "Müllbeutel 120 l", "Toilettenpapier", "Handtuchrollen", "Falthandtücher", "Seife",
           "Spülmittel", "Glasreiniger", "Allzweckreiniger", "Sanitärreiniger", "Bodenreiniger"]
STATUS = ("gemeldet", "bestellt", "erledigt")
STATUS_MA = {"gemeldet": "gemeldet", "bestellt": "bestellt", "erledigt": "liegt bereit"}
SONSTIGES_MAX = 120
MENGE_MAX = 99
FOTO_MAX_BYTES = 2_500_000
MELDUNGEN_PRO_TAG = 5
ERINNERN_NACH_H = 24
BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ABLAGE = os.path.join(BACKEND, "data", "material")
MAIL_KEY = "materialmail"
MAIL_DEFAULT = {"testmodus": True, "test_an": "dsertic@seda.de", "absender": "info@seda.de",
                "absender_name": "SEDA24 Objektbetreuung", "antwort_an": "", "signatur_mail": "info@seda.de"}
MAIL_RE = re.compile(r"[^@\s,;]+@[^@\s,;]+\.[a-z]{2,}", re.I)


def _q(db, sql, **p):
    return db.execute(text(sql), p).mappings().all()


def tabellen(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS material_artikel (
        id serial PRIMARY KEY, object_id integer NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
        name varchar(60) NOT NULL, einheit varchar(20), sort integer NOT NULL DEFAULT 0,
        aktiv boolean NOT NULL DEFAULT true, angelegt_am timestamp DEFAULT now())"""))
    db.execute(text("""CREATE TABLE IF NOT EXISTS material_objekt (
        object_id integer PRIMARY KEY REFERENCES objects(id) ON DELETE CASCADE,
        stellt varchar(10) NOT NULL DEFAULT 'seda24', kontakt_anrede varchar(10), kontakt_name varchar(80),
        kontakt_mail varchar(120), updated_at timestamp DEFAULT now(), updated_by integer)"""))
    db.execute(text("""CREATE TABLE IF NOT EXISTS material_meldung (
        id serial PRIMARY KEY, object_id integer NOT NULL REFERENCES objects(id), employee_id integer NOT NULL REFERENCES employees(id),
        erstellt_am timestamp NOT NULL DEFAULT now(), status varchar(10) NOT NULL DEFAULT 'gemeldet',
        status_am timestamp, status_von integer, sonstiges varchar(120), foto_pfad text,
        kunde_gesendet_am timestamp, kunde_gesendet_an varchar(120), kunde_gesendet_von integer, kunde_weg varchar(20),
        erinnert_am timestamp)"""))
    db.execute(text("""CREATE TABLE IF NOT EXISTS material_position (
        id serial PRIMARY KEY, meldung_id integer NOT NULL REFERENCES material_meldung(id) ON DELETE CASCADE,
        artikel_id integer REFERENCES material_artikel(id), name varchar(60) NOT NULL, einheit varchar(20),
        menge integer NOT NULL, menge_gemeldet integer NOT NULL)"""))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_material_meldung_status ON material_meldung (status, erstellt_am)"))


# ------------------------------------------------------------------ Artikel + Objekt-Einstellung

def artikel(db, object_id, nur_aktiv=True):
    """Artikelliste des Objekts; beim ersten Aufruf aus der Start-Vorlage angelegt."""
    tabellen(db)
    if not db.execute(text("SELECT 1 FROM material_artikel WHERE object_id = :o LIMIT 1"), {"o": object_id}).first():
        for i, n in enumerate(VORLAGE):
            db.execute(text("INSERT INTO material_artikel (object_id, name, sort) VALUES (:o, :n, :s)"),
                       {"o": object_id, "n": n, "s": i})
    flt = "AND aktiv" if nur_aktiv else ""
    return [dict(r) for r in _q(db, f"""SELECT id, name, einheit, sort, aktiv FROM material_artikel
                                        WHERE object_id = :o {flt} ORDER BY sort, id""", o=object_id)]


def artikel_speichern(db, object_id, liste, user_id):
    """liste: [{id?, name, einheit?}] in der gewuenschten Reihenfolge. Fehlende bisherige Artikel werden
    ausgeblendet (aktiv=false), nicht geloescht - alte Meldungen behalten ihre Positionen."""
    from app.services.booking_service import log_audit
    alt = artikel(db, object_id)
    if not isinstance(liste, list) or len(liste) > 60:
        raise ValueError("Höchstens 60 Artikel je Objekt")
    gesehen, namen = [], set()
    for i, a in enumerate(liste):
        name = re.sub(r"\s+", " ", str((a or {}).get("name") or "")).strip()
        einheit = re.sub(r"\s+", " ", str((a or {}).get("einheit") or "")).strip()[:20] or None
        if not 2 <= len(name) <= 60:
            raise ValueError("Artikelname: 2 bis 60 Zeichen")
        if name.lower() in namen:
            raise ValueError(f"„{name}“ steht doppelt in der Liste")
        namen.add(name.lower())
        aid = a.get("id")
        if aid:
            n = db.execute(text("""UPDATE material_artikel SET name = :n, einheit = :e, sort = :s, aktiv = true
                                   WHERE id = :i AND object_id = :o"""), {"n": name, "e": einheit, "s": i, "i": aid, "o": object_id}).rowcount
            if not n:
                raise ValueError("Artikel gehört nicht zu diesem Objekt")
        else:
            aid = db.execute(text("""INSERT INTO material_artikel (object_id, name, einheit, sort) VALUES (:o, :n, :e, :s)
                                     RETURNING id"""), {"o": object_id, "n": name, "e": einheit, "s": i}).scalar()
        gesehen.append(aid)
    db.execute(text("UPDATE material_artikel SET aktiv = false WHERE object_id = :o AND NOT (id = ANY(:ids))"),
               {"o": object_id, "ids": gesehen or [0]})
    neu = artikel(db, object_id)
    log_audit(db, user_id, None, "material_artikel_geaendert", entity_type="object", entity_id=object_id,
              old_value=[a["name"] for a in alt], new_value=[a["name"] for a in neu],
              details=f"Materialliste Objekt {object_id}: {len(neu)} Artikel")
    db.commit()
    return neu


def einstellung(db, object_id):
    tabellen(db)
    r = db.execute(text("SELECT * FROM material_objekt WHERE object_id = :o"), {"o": object_id}).mappings().first()
    return {"stellt": (r and r["stellt"]) or "seda24", "kontakt_anrede": (r and r["kontakt_anrede"]) or "",
            "kontakt_name": (r and r["kontakt_name"]) or "", "kontakt_mail": (r and r["kontakt_mail"]) or ""}


def einstellung_speichern(db, object_id, werte, user_id):
    from app.services.booking_service import log_audit
    alt = einstellung(db, object_id)
    neu = dict(alt)
    if "stellt" in werte:
        if werte["stellt"] not in ("seda24", "kunde"):
            raise ValueError("Material stellt: Kunde oder SEDA24")
        neu["stellt"] = werte["stellt"]
    if "kontakt_anrede" in werte:
        if (werte["kontakt_anrede"] or "") not in ("", "Frau", "Herr"):
            raise ValueError("Anrede: Frau, Herr oder leer")
        neu["kontakt_anrede"] = werte["kontakt_anrede"] or ""
    if "kontakt_name" in werte:
        v = re.sub(r"\s+", " ", str(werte["kontakt_name"] or "")).strip()
        if len(v) > 80 or re.search(r'[<>"@]', v):
            raise ValueError("Name: höchstens 80 Zeichen, ohne < > \" @")
        neu["kontakt_name"] = v
    if "kontakt_mail" in werte:
        v = str(werte["kontakt_mail"] or "").strip().lower()
        if v and not MAIL_RE.fullmatch(v):
            raise ValueError("Mail-Adresse des Ansprechpartners ist ungültig")
        neu["kontakt_mail"] = v
    db.execute(text("""INSERT INTO material_objekt (object_id, stellt, kontakt_anrede, kontakt_name, kontakt_mail, updated_at, updated_by)
                       VALUES (:o, :s, :a, :n, :m, now(), :u)
                       ON CONFLICT (object_id) DO UPDATE SET stellt = :s, kontakt_anrede = :a, kontakt_name = :n,
                       kontakt_mail = :m, updated_at = now(), updated_by = :u"""),
               {"o": object_id, "s": neu["stellt"], "a": neu["kontakt_anrede"] or None, "n": neu["kontakt_name"] or None,
                "m": neu["kontakt_mail"] or None, "u": user_id})
    log_audit(db, user_id, None, "material_objekt_geaendert", entity_type="object", entity_id=object_id,
              old_value=alt, new_value=neu,
              details=f"Material Objekt {object_id}: stellt {'Kunde' if neu['stellt'] == 'kunde' else 'SEDA24'}")
    db.commit()
    return neu


# ------------------------------------------------------------------ MA-App

def ma_objekte(db, employee_id, jetzt=None):
    """Objekte mit Dienst heute oder morgen (Dienstplan, ohne Urlaub/Krank/Abwesend), frueheste Schicht zuerst.
    vorauswahl = laufende bzw. naechste Schicht heute, sonst die erste."""
    jetzt = jetzt or datetime.now()
    heute = jetzt.date()
    rows = _q(db, """SELECT s.object_id, o.name, s.date, s.start_time, s.end_time FROM schedules s
                     JOIN objects o ON o.id = s.object_id
                     WHERE s.employee_id = :e AND s.date BETWEEN :a AND :b AND coalesce(s.status, 'normal') IN ('normal', 'vertretung')
                       AND o.is_active AND NOT coalesce(o.is_test, false) AND o.name NOT IN ('Krank', 'Urlaub')
                     ORDER BY s.date, s.start_time NULLS LAST""", e=employee_id, a=heute, b=heute + timedelta(days=1))
    out, ids = [], set()
    for r in rows:
        if r["object_id"] in ids:
            continue
        ids.add(r["object_id"])
        out.append({"object_id": r["object_id"], "name": r["name"], "tag": "heute" if r["date"] == heute else "morgen",
                    "zeit": f"{r['start_time']:%H:%M}" if r["start_time"] else None})
    vor = None
    for r in rows:      # laufende oder naechste Schicht heute
        if r["date"] == heute and (r["end_time"] is None or r["end_time"] >= jetzt.time()):
            vor = r["object_id"]
            break
    return {"objekte": out, "vorauswahl": vor or (out[0]["object_id"] if out else None)}


def _foto_pruefen(data_url):
    m = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/=]+)", (data_url or "").strip())
    if not m:
        raise ValueError("Foto bitte als JPG oder PNG")
    roh = base64.b64decode(m.group(2), validate=True)
    if len(roh) > FOTO_MAX_BYTES:
        raise ValueError("Foto zu groß")
    if not (roh[:3] == b"\xff\xd8\xff" or roh[:8] == b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Kein gültiges Foto")
    return roh, ("jpg" if roh[:3] == b"\xff\xd8\xff" else "png")


def melden(db, employee_id, object_id, positionen, sonstiges="", foto=None, jetzt=None):
    from app.services.booking_service import log_audit
    tabellen(db)
    erlaubt = {o["object_id"] for o in ma_objekte(db, employee_id, jetzt)["objekte"]}
    if object_id not in erlaubt:
        raise ValueError("Material kannst du nur für Objekte melden, in denen du heute oder morgen Dienst hast")
    n_heute = db.execute(text("""SELECT count(*) FROM material_meldung WHERE employee_id = :e AND erstellt_am::date = current_date"""),
                         {"e": employee_id}).scalar()
    if n_heute >= MELDUNGEN_PRO_TAG:
        raise ValueError(f"Heute schon {n_heute} Meldungen – bitte die Objektleitung anrufen")
    art = {a["id"]: a for a in artikel(db, object_id)}
    pos = []
    for p in positionen or []:
        try:
            aid, menge = int(p.get("artikel_id")), int(p.get("menge") or 0)
        except (TypeError, ValueError, AttributeError):
            raise ValueError("Ungültige Position")
        if menge <= 0:
            continue
        if aid not in art:
            raise ValueError("Artikel gehört nicht zu diesem Objekt")
        if menge > MENGE_MAX:
            raise ValueError(f"Menge höchstens {MENGE_MAX}")
        pos.append((art[aid], menge))
    sonstiges = re.sub(r"\s+", " ", str(sonstiges or "")).strip()
    if len(sonstiges) > SONSTIGES_MAX:
        raise ValueError(f"Sonstiges: höchstens {SONSTIGES_MAX} Zeichen")
    if not pos and not sonstiges:
        raise ValueError("Bitte mindestens einen Artikel mit Menge oder „Sonstiges“ angeben")
    foto_roh = _foto_pruefen(foto) if foto else None
    mid = db.execute(text("""INSERT INTO material_meldung (object_id, employee_id, sonstiges) VALUES (:o, :e, :s) RETURNING id"""),
                     {"o": object_id, "e": employee_id, "s": sonstiges or None}).scalar()
    for a, menge in pos:
        db.execute(text("""INSERT INTO material_position (meldung_id, artikel_id, name, einheit, menge, menge_gemeldet)
                           VALUES (:m, :a, :n, :e, :q, :q)"""), {"m": mid, "a": a["id"], "n": a["name"], "e": a["einheit"], "q": menge})
    if foto_roh:
        from app.services.lohnablage import schreiben
        os.makedirs(ABLAGE, mode=0o700, exist_ok=True)
        pfad = schreiben(os.path.join(ABLAGE, f"meldung_{mid}_foto.{foto_roh[1]}"), foto_roh[0])
        db.execute(text("UPDATE material_meldung SET foto_pfad = :p WHERE id = :m"), {"p": pfad, "m": mid})
    log_audit(db, None, employee_id, "material_gemeldet", entity_type="material", entity_id=mid,
              new_value={"objekt": object_id, "positionen": [f"{q}× {a['name']}" for a, q in pos], "sonstiges": sonstiges,
                         "foto": bool(foto_roh)},
              details=f"Materialmeldung #{mid}: {len(pos)} Artikel" + (" + Sonstiges" if sonstiges else "") + (" + Foto" if foto_roh else ""))
    db.commit()
    try:
        benachrichtigen_neu(db, mid)
    except Exception as e:      # Meldung ist gespeichert, Telegram darf sie nicht kippen
        logger.error(f"Material-Telegram #{mid} fehlgeschlagen: {e}")
    return meldung(db, mid)


def ma_meldungen(db, employee_id, tage=30):
    tabellen(db)
    ids = [r["id"] for r in _q(db, """SELECT id FROM material_meldung WHERE employee_id = :e
                                      AND erstellt_am >= now() - make_interval(days => :t) ORDER BY id DESC LIMIT 30""",
                               e=employee_id, t=tage)]
    out = []
    for i in ids:
        m = meldung(db, i)
        out.append({k: m[k] for k in ("id", "objekt", "erstellt_am", "status", "status_ma", "status_am", "positionen", "sonstiges", "foto")})
    return out


# ------------------------------------------------------------------ Cockpit

def meldung(db, mid):
    r = db.execute(text("""SELECT m.*, o.name AS objekt, e.first_name || ' ' || e.last_name AS ma, e.personal_nr
                           FROM material_meldung m JOIN objects o ON o.id = m.object_id JOIN employees e ON e.id = m.employee_id
                           WHERE m.id = :i"""), {"i": mid}).mappings().first()
    if not r:
        raise LookupError("Meldung nicht gefunden")
    pos = [dict(p) for p in _q(db, """SELECT id, artikel_id, name, einheit, menge, menge_gemeldet FROM material_position
                                       WHERE meldung_id = :i ORDER BY id""", i=mid)]
    ein = einstellung(db, r["object_id"])
    iso = lambda d: d.isoformat(timespec="minutes") if d else None  # noqa: E731
    return {"id": r["id"], "object_id": r["object_id"], "objekt": r["objekt"], "employee_id": r["employee_id"], "ma": r["ma"],
            "personal_nr": r["personal_nr"], "erstellt_am": iso(r["erstellt_am"]), "status": r["status"],
            "status_ma": STATUS_MA.get(r["status"], r["status"]), "status_am": iso(r["status_am"]),
            "positionen": pos, "sonstiges": r["sonstiges"] or "", "foto": bool(r["foto_pfad"]),
            "stellt": ein["stellt"], "kontakt": ein if ein["stellt"] == "kunde" else None,
            "kunde_gesendet_am": iso(r["kunde_gesendet_am"]), "kunde_gesendet_an": r["kunde_gesendet_an"], "kunde_weg": r["kunde_weg"],
            "alter_h": round((datetime.now() - r["erstellt_am"]).total_seconds() / 3600, 1)}


def liste(db, nur_offen=True):
    tabellen(db)
    flt = "WHERE status <> 'erledigt'" if nur_offen else "WHERE erstellt_am >= now() - interval '60 days'"
    ids = [r["id"] for r in _q(db, f"SELECT id FROM material_meldung {flt} ORDER BY erstellt_am DESC LIMIT 200")]
    offen = db.execute(text("SELECT count(*) FROM material_meldung WHERE status <> 'erledigt'")).scalar()
    return {"meldungen": [meldung(db, i) for i in ids], "offen": offen}


def status_setzen(db, mid, status, user_id):
    from app.services.booking_service import log_audit
    if status not in STATUS:
        raise ValueError("Status: gemeldet, bestellt oder erledigt")
    alt = meldung(db, mid)
    db.execute(text("UPDATE material_meldung SET status = :s, status_am = now(), status_von = :u WHERE id = :i"),
               {"s": status, "u": user_id, "i": mid})
    log_audit(db, user_id, alt["employee_id"], "material_status", entity_type="material", entity_id=mid,
              old_value={"status": alt["status"]}, new_value={"status": status},
              details=f"Materialmeldung #{mid} ({alt['objekt']}): {alt['status']} -> {status}")
    db.commit()
    return meldung(db, mid)


def mengen_aendern(db, mid, positionen, user_id):
    """positionen: [{id, menge}] - Menge 0 = entfaellt (bleibt sichtbar)."""
    from app.services.booking_service import log_audit
    alt = meldung(db, mid)
    vorher = {p["id"]: p for p in alt["positionen"]}
    aenderung = []
    for p in positionen or []:
        try:
            pid, menge = int(p["id"]), int(p["menge"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Ungültige Menge")
        if pid not in vorher:
            raise ValueError("Position gehört nicht zu dieser Meldung")
        if not 0 <= menge <= MENGE_MAX:
            raise ValueError(f"Menge 0 bis {MENGE_MAX}")
        if menge != vorher[pid]["menge"]:
            db.execute(text("UPDATE material_position SET menge = :q WHERE id = :i"), {"q": menge, "i": pid})
            aenderung.append(f"{vorher[pid]['name']} {vorher[pid]['menge']} -> {menge}")
    if aenderung:
        log_audit(db, user_id, alt["employee_id"], "material_menge", entity_type="material", entity_id=mid,
                  old_value={str(k): v["menge"] for k, v in vorher.items()},
                  new_value={str(p["id"]): int(p["menge"]) for p in positionen},
                  details=f"Materialmeldung #{mid}: " + ", ".join(aenderung))
    db.commit()
    return meldung(db, mid)


def foto(db, mid):
    r = db.execute(text("SELECT foto_pfad FROM material_meldung WHERE id = :i"), {"i": mid}).scalar()
    if not r:
        raise LookupError("Kein Foto")
    from app.services.lohnablage import lesen
    return lesen(r), ("image/png" if r.endswith(".png.enc") or r.endswith(".png") else "image/jpeg")


# ------------------------------------------------------------------ Telegram

def _telegram(text_):
    """Telegram an Drazen + Objektleitung (Empfaenger-Kategorie "material"). DEV: nur protokollieren."""
    if os.getenv("DISABLE_TELEGRAM"):
        logger.info(f"Telegram aus (DISABLE_TELEGRAM): {text_[:100]}")
        return False
    from app.services.telegram_bot import notify_admin
    notify_admin(text_, category="material")
    return True


SENDE_TELEGRAM = _telegram   # austauschbar fuer Tests


def _pos_text(m):
    zeilen = [f"• {p['menge']}× {p['name']}" for p in m["positionen"] if p["menge"] > 0]
    if m["sonstiges"]:
        zeilen.append(f"• Sonstiges: {m['sonstiges']}")
    return "\n".join(zeilen)


def benachrichtigen_neu(db, mid):
    m = meldung(db, mid)
    wer = "Kunde stellt das Material" if m["stellt"] == "kunde" else "SEDA24 stellt das Material"
    return SENDE_TELEGRAM(f"📦 Materialmeldung {m['objekt']}\nvon {m['ma']}, {m['erstellt_am'][11:16]} Uhr\n{_pos_text(m)}"
                          + ("\n📷 mit Foto" if m["foto"] else "") + f"\n({wer} – im Cockpit unter Material)")


def erinnerung(db, jetzt=None):
    """Job 08:00: offene Meldungen aelter als 24 h -> eine Telegram-Sammelmeldung, jeden Morgen bis erledigt."""
    tabellen(db)
    jetzt = jetzt or datetime.now()
    ids = [r["id"] for r in _q(db, """SELECT id FROM material_meldung WHERE status <> 'erledigt'
                                      AND erstellt_am <= :g ORDER BY erstellt_am""", g=jetzt - timedelta(hours=ERINNERN_NACH_H))]
    if not ids:
        return {"erinnert": 0}
    ms = [meldung(db, i) for i in ids]
    zeilen = [f"• {m['objekt']} ({m['erstellt_am'][8:10]}.{m['erstellt_am'][5:7]}., {m['ma']}): {m['status']}" for m in ms]
    SENDE_TELEGRAM(f"⏰ {len(ms)} Materialmeldung{'en' if len(ms) > 1 else ''} seit über 24 Std. nicht erledigt:\n"
                   + "\n".join(zeilen) + "\nBitte im Cockpit unter Material auf „erledigt“ setzen.")
    db.execute(text("UPDATE material_meldung SET erinnert_am = :j WHERE id = ANY(:ids)"), {"j": jetzt, "ids": ids})
    db.commit()
    return {"erinnert": len(ms)}


# ------------------------------------------------------------------ Mail an den Kunden

def echt_erlaubt():
    return os.getenv("MATERIALMAIL_ECHT", "") == "1"


def mail_einstellungen(db):
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": MAIL_KEY}).fetchone()
    try:
        g = json.loads(r[0]) if r else {}
    except (TypeError, ValueError):
        g = {}
    return {k: g.get(k, v) for k, v in MAIL_DEFAULT.items()}


def mail_einstellungen_speichern(db, werte, user_id):
    from app.services.booking_service import log_audit
    from app.services.lohnversand import ABSENDER_DOMAIN
    alt = mail_einstellungen(db)
    neu = dict(alt)
    if "testmodus" in werte:
        neu["testmodus"] = bool(werte["testmodus"])
    for k, leer_ok in (("test_an", False), ("antwort_an", True), ("signatur_mail", False)):
        if k in werte:
            v = str(werte[k] or "").strip().lower()
            if (v or not leer_ok) and not MAIL_RE.fullmatch(v):
                raise ValueError(f"{k.replace('_', ' ').capitalize()}: keine gültige Mail-Adresse")
            neu[k] = v
    if "absender" in werte:
        v = str(werte["absender"] or "").strip().lower()
        if not MAIL_RE.fullmatch(v) or not v.endswith(ABSENDER_DOMAIN):
            raise ValueError(f"Absender: eine Adresse {ABSENDER_DOMAIN}")
        if v == "lohn@seda.de":
            raise ValueError("Material-Mails nicht über lohn@seda.de – bitte eigenen Absender (z. B. info@seda.de)")
        neu["absender"] = v
    if "absender_name" in werte:
        v = re.sub(r"\s+", " ", str(werte["absender_name"] or "")).strip()
        if not 2 <= len(v) <= 80 or re.search(r'[<>"@]', v):
            raise ValueError("Anzeigename: 2 bis 80 Zeichen, ohne < > \" @")
        neu["absender_name"] = v
    if not neu["testmodus"] and not echt_erlaubt():
        raise ValueError("Echter Versand an Kunden ist auf diesem Server nicht freigeschaltet (nur Testmodus)")
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": MAIL_KEY, "v": json.dumps(neu), "u": user_id})
    log_audit(db, user_id, None, "materialmail_einstellung", entity_type="einstellung", old_value=alt, new_value=neu,
              details=f"Material-Mail: {neu['absender_name']} <{neu['absender']}>, " + ("Testmodus an " + neu["test_an"] if neu["testmodus"] else "ECHTER Versand an Kunden"))
    db.commit()
    return neu


def _anrede(k):
    if k.get("kontakt_anrede") in ("Frau", "Herr") and k.get("kontakt_name"):
        nach = k["kontakt_name"].split()[-1]
        return f"Guten Tag {k['kontakt_anrede']} {nach}"
    return f"Guten Tag {k['kontakt_name']}" if k.get("kontakt_name") else "Guten Tag"


BETREFF = "Materialbedarf für Ihr Objekt – SEDA24"


def kundenmail(m, einst, vorspann=""):
    """(betreff, text, html) fuer die Meldung m (nur Positionen mit Menge > 0)."""
    from app.services import mail_signatur as ms
    k = m["kontakt"] or {}
    zeilen = [(f"{p['menge']} × {p['name']}" + (f" ({p['einheit']})" if p.get("einheit") else "")) for p in m["positionen"] if p["menge"] > 0]
    if m["sonstiges"]:
        zeilen.append(m["sonstiges"])
    titel, sig_mail = einst["absender_name"], einst["signatur_mail"]
    txt = (f"{_anrede(k)},\n\nfür Ihre Reinigung ({m['objekt']}) wird folgendes Material benötigt:\n\n"
           + "\n".join(f"- {z}" for z in zeilen) + "\n\nVielen Dank vorab.\n\nMit freundlichen Grüßen\n\n" + ms.text(titel, sig_mail))
    liste_html = (f'<ul style="{ms.F}font-size:14px;line-height:1.5;color:{ms.INK};margin:0 0 14px;padding-left:22px;">'
                  + "".join(f"<li>{escape(z)}</li>" for z in zeilen) + "</ul>")
    inhalt = (ms.absatz(f"{_anrede(k)},") + ms.absatz(f"für Ihre Reinigung ({m['objekt']}) wird folgendes Material benötigt:")
              + liste_html + ms.absatz("Vielen Dank vorab."))
    return BETREFF, txt, ms.dokument(inhalt, titel, sig_mail, vorspann)


def an_kunden_senden(db, mid, user_id):
    from app.services import lohnversand as lv, mail_signatur as ms
    from app.services.booking_service import log_audit
    m = meldung(db, mid)
    if m["stellt"] != "kunde":
        raise ValueError("Bei diesem Objekt stellt SEDA24 das Material – keine Mail an den Kunden")
    k = m["kontakt"]
    if not k or not MAIL_RE.fullmatch(k.get("kontakt_mail") or ""):
        raise ValueError("Beim Objekt fehlt die Mail-Adresse des Kunden-Ansprechpartners")
    if not any(p["menge"] > 0 for p in m["positionen"]) and not m["sonstiges"]:
        raise ValueError("Die Meldung enthält kein Material mehr")
    einst = mail_einstellungen(db)
    test = einst["testmodus"] or not echt_erlaubt()
    an = einst["test_an"] if test else k["kontakt_mail"]
    vorspann = f"TESTMODUS – diese Mail ginge an: {k['kontakt_name'] or ''} <{k['kontakt_mail']}>" if test else ""
    betreff, txt, html = kundenmail(m, einst, vorspann)
    if test:
        betreff = f"[TEST – an {k['kontakt_mail']}] " + betreff
        txt = vorspann + "\n\n" + txt
    absender = {"adresse": einst["absender"], "name": einst["absender_name"], "antwort_an": einst["antwort_an"] or einst["absender"]}
    weg = lv.weg(test)
    ordner = os.path.join(ABLAGE, f"meldung_{mid}")
    conn = lv.verbinden(test, ordner, einst["test_an"], absender)
    try:
        conn.senden(lv.nachricht(an, betreff, txt, [], absender, html=html, inline=ms.bilder()))
    finally:
        conn.schliessen()
    db.execute(text("""UPDATE material_meldung SET kunde_gesendet_am = now(), kunde_gesendet_an = :a, kunde_gesendet_von = :u,
                       kunde_weg = :w WHERE id = :i"""), {"a": an, "u": user_id, "w": weg, "i": mid})
    log_audit(db, user_id, m["employee_id"], "material_an_kunden", entity_type="material", entity_id=mid,
              new_value={"an": an, "kunde": k["kontakt_mail"], "test": test, "weg": weg},
              details=f"Materialmeldung #{mid} ({m['objekt']}) an Kunden " + (f"(TEST an {an})" if test else an))
    db.commit()
    return {**meldung(db, mid), "test": test, "weg": weg}


def testmail(mid):
    """Die zuletzt als .eml erzeugte Test-Mail dieser Meldung (entschluesselt)."""
    from app.services.lohnablage import lesen
    d = os.path.join(ABLAGE, f"meldung_{mid}", "testversand")
    dateien = sorted(os.listdir(d)) if os.path.isdir(d) else []
    if not dateien:
        raise LookupError("Keine Test-Mail vorhanden")
    return lesen(os.path.join(d, dateien[-1])), f"Materialbedarf_{mid}.eml"
