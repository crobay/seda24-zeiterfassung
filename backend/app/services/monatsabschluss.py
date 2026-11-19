"""Monatsabschluss mit einem Klick (PROTOTYP, nur DEV) - ersetzt das PC-Skript seda_lohn_email.py.

Schritt 1  Pruefliste wie bei Lexware: "Hast du ... erledigt?" mit Haken je Punkt. Automatische Pruefungen
           (offene Stempel/Antraege, KM, Plausibilitaet, Minijob-Grenze) muessen gruen sein,
           bevor der Haken gesetzt werden kann. Erst wenn alle Punkte abgehakt sind, geht es weiter.
Schritt 2  "Fuer Lexware erzeugen": EINE Importdatei fuer alle MA (Import-Assistent Lohndaten von Lexware
           lohn+gehalt: ASCII, Semikolon, Dezimalkomma, Felder Jahr;Monat;Personalnummer;Lohnart;Wert;Stundensatz)
           + Zeitnachweis- und KM-PDFs je MA (vorhandener PDF-Generator). Zahlen 1:1 aus der Lohnuebersicht
           (admin.get_lohn_uebersicht) bzw. festgehalt.lexware_lohnarten - an der Gehaltslogik aendert sich nichts.
Schritt 3  Lohnabrechnungen aus Lexware hochladen (ZIP oder PDFs), Zuordnung nach PersNr/Name im Dateinamen.
Schritt 4  Vorschau je MA: Mail-Adresse, Anrede, Anhaenge.
Schritt 5  "Alle versenden" (Graph aus buchhaltung@seda.de, Kopie in "Gesendete Elemente", kein BCC; siehe
           lohnversand.py) + Status je MA +
           einzelnen MA erneut senden + Monat sperren. Testmodus (Schalter): alles geht an Drazen statt an die MA,
           der Monat wird dabei nicht gesperrt.

Regeln aus dem PC-Skript / Drazen 18.11.2026: A*- und TEST*-Konten (und is_test) ueberspringen, D0002 ohne KM
(kein KM-Anhang, kein KM-Geld im Export - Elektro-Dienstwagen), Anrede je MA, 3 Anhaenge (Lohnabrechnung, Zeitnachweis,
KM-Journal), Dateinamen wie Skript v2.5: Lohnabrechnung_{Jahr}_{Monat}_{PersNr}_{Nachname}_{Vorname}.pdf. Dateien liegen unter backend/data/abschluss/JJJJ-MM/ (nicht im Git).
"""
import hashlib
import io
import json
import os
import re
import shutil
import time
import unicodedata
import zipfile
from calendar import monthrange
from datetime import date, datetime

from sqlalchemy import text

from app.services import lohnablage as ablage

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATEN = os.path.join(BACKEND, "data", "abschluss")
OBJ_URLAUB, OBJ_KRANK = 999, 19
OHNE_KM_ANHANG = {"D0002"}                    # kein KM-Anhang und kein KM-Geld im Export (Elektro-Dienstwagen)
LOHNART_KEY = "lexware_lohnarten"
# Nummern aus dem bestehenden XML-Export (13/11/16/14); normal/sonder/km gibt es dort nicht -> Platzhalter (leer),
# Drazen traegt sie aus seinem Lexware-Mandanten ein. Ohne Nummer wird keine Lexware-Datei erzeugt.
LOHNART_DEFAULT = {"normal": None, "sonder": None, "sonntag": 13, "nacht": 11, "feiertag": 16, "urlaub": 14, "km": None,
                   "kopfzeile": True, "persnr": "wie_app", "bestaetigt": False}
MONATE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]


def tabellen(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS monatsabschluss (
        monat varchar(7) PRIMARY KEY, status varchar(20) NOT NULL DEFAULT 'offen', haken text NOT NULL DEFAULT '{}',
        erzeugt_am timestamp, erzeugt_von integer, gesperrt_am timestamp, gesperrt_von integer)"""))
    db.execute(text("""CREATE TABLE IF NOT EXISTS monatsabschluss_dokument (
        id serial PRIMARY KEY, monat varchar(7) NOT NULL, employee_id integer REFERENCES employees(id),
        art varchar(20) NOT NULL, dateiname text NOT NULL, pfad text NOT NULL, groesse integer, sha256 varchar(64),
        zuordnung varchar(20), am timestamp DEFAULT now(), von integer)"""))
    db.execute(text("""CREATE TABLE IF NOT EXISTS monatsabschluss_versand (
        id serial PRIMARY KEY, monat varchar(7) NOT NULL, employee_id integer, an text, betreff text, anhaenge text,
        status varchar(20) NOT NULL, fehler text, am timestamp DEFAULT now(), von integer)"""))


def _q(db, sql, **p):
    return db.execute(text(sql), p).mappings().all()


def _grenzen(y, m):
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def monat_key(y, m):
    return f"{y}-{m:02d}"


def zustand(db, y, m):
    tabellen(db)
    k = monat_key(y, m)
    r = _q(db, "SELECT * FROM monatsabschluss WHERE monat = :k", k=k)
    if not r:
        db.execute(text("INSERT INTO monatsabschluss (monat) VALUES (:k) ON CONFLICT DO NOTHING"), {"k": k})
        r = _q(db, "SELECT * FROM monatsabschluss WHERE monat = :k", k=k)
    z = dict(r[0])
    z["haken"] = json.loads(z["haken"] or "{}")
    return z


def gesperrt(db, y, m) -> bool:
    """Durchgesetzt wird die Sperre in der Datenbank (migrations/monatssperre.sql, Trigger auf allen Lohndaten)."""
    return zustand(db, y, m)["status"] == "abgeschlossen"


def lohnarten(db):
    r = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": LOHNART_KEY}).fetchone()
    try:
        return {**LOHNART_DEFAULT, **(json.loads(r[0]) if r else {})}
    except (TypeError, ValueError):
        return dict(LOHNART_DEFAULT)


def lohnarten_speichern(db, werte: dict, user_id):
    from app.services.booking_service import log_audit
    alt = lohnarten(db)
    neu = {**alt}
    for k in ("normal", "sonder", "sonntag", "nacht", "feiertag", "urlaub", "km"):
        if k in werte:
            if werte[k] in (None, ""):
                neu[k] = None
                continue
            v = int(werte[k])
            if not 1 <= v <= 9999:
                raise ValueError(f"Lohnart {k}: 1 bis 9999")
            neu[k] = v
    if "kopfzeile" in werte:
        neu["kopfzeile"] = bool(werte["kopfzeile"])
    if werte.get("persnr") in ("wie_app", "nur_ziffern"):
        neu["persnr"] = werte["persnr"]
    neu["bestaetigt"] = bool(werte.get("bestaetigt", alt["bestaetigt"]))
    db.execute(text("""INSERT INTO app_settings (key, value, updated_at, updated_by) VALUES (:k, :v, now(), :u)
                       ON CONFLICT (key) DO UPDATE SET value = :v, updated_at = now(), updated_by = :u"""),
               {"k": LOHNART_KEY, "v": json.dumps(neu), "u": user_id})
    log_audit(db, user_id, None, "lexware_lohnarten_geaendert", entity_type="einstellung", old_value=alt, new_value=neu,
              details="Lexware-Lohnarten fuer den Monatsabschluss geaendert")
    db.commit()
    return neu


# ------------------------------------------------------------------ Mitarbeiter im Abschluss

def ueberspringen(pnr: str, is_test: bool) -> bool:
    p = (pnr or "").upper()
    return is_test or p.startswith("A") or p.startswith("TEST") or p == "T9999"


def lohnzeilen(db, y, m):
    """Zeilen der Lohnuebersicht (gleiche Zahlen wie Cockpit > Abrechnung), ohne A*/TEST*/Test-MA."""
    from types import SimpleNamespace
    from app.api.v1.endpoints.admin import get_lohn_uebersicht
    rows = get_lohn_uebersicht(y, m, db=db, current_user=SimpleNamespace(role=SimpleNamespace(value="admin")))
    test = {r["id"] for r in _q(db, "SELECT id FROM employees WHERE coalesce(is_test, false)")}
    return [r for r in rows if not ueberspringen(r.get("personal_nr"), r["employee_id"] in test)]


def _hat_lohn(r):
    return any((r.get(k) or 0) for k in ("normal_hours", "sonder_hours", "urlaub_hours", "km_amount", "gesamt")) or r.get("festgehalt")


# ------------------------------------------------------------------ Schritt 1: Pruefliste

def _punkt(key, frage, ok, detail="", link=None, info=None):
    return {"key": key, "frage": frage, "auto": ok, "detail": detail, "link": link, "info": info}


def pruefliste(db, y, m):
    """Je Punkt: auto = True (gruen) / False (rot, Haken gesperrt) / None (nur von Hand abzuhaken)."""
    m0, m1 = _grenzen(y, m)
    mk = monat_key(y, m)
    rows = [r for r in lohnzeilen(db, y, m) if _hat_lohn(r)]
    ids = [r["employee_id"] for r in rows]
    name = {r["employee_id"]: r["name"] for r in rows}
    out = []

    # Punkt "Haben alle MA ihren Monat bestaetigt?" entfernt (18.11.2026, Drazen: Monatsbestaetigung wird nicht genutzt)

    offen = _q(db, """SELECT t.id, e.first_name || ' ' || e.last_name AS n, t.check_in FROM time_entries t
                      JOIN employees e ON e.id = t.employee_id
                      WHERE t.check_out IS NULL AND t.check_in::date BETWEEN :a AND :b AND NOT coalesce(e.is_test, false)""", a=m0, b=m1)
    out.append(_punkt("offene_stempel", "Sind alle Stempelungen geschlossen (kein offenes Gehen)?", not offen,
                      ", ".join(f"{r['n']} {r['check_in']:%d.%m.}" for r in offen[:6]) if offen else "keine offenen Einträge",
                      f"/cockpit/zeiten?monat={mk}"))

    antr = []
    antr += [f"Mehrzeit #{r['id']}" for r in _q(db, """SELECT id FROM pending_bookings WHERE coalesce(status, 'offen') NOT IN
             ('genehmigt', 'abgelehnt', 'erledigt') AND date BETWEEN :a AND :b""", a=m0, b=m1)]
    antr += [f"Urlaub #{r['id']}" for r in _q(db, """SELECT id FROM vacation_requests WHERE status = 'pending'
             AND start_date <= :b AND end_date >= :a""", a=m0, b=m1)]
    antr += [f"Korrektur #{r['id']}" for r in _q(db, """SELECT id FROM correction_requests WHERE coalesce(status, 'pending') IN
             ('pending', 'offen') AND created_at::date BETWEEN :a AND :b""", a=m0, b=m1)]
    out.append(_punkt("antraege", "Sind alle Anträge entschieden (Mehrzeit, Urlaub, Korrekturen)?", not antr,
                      ", ".join(antr[:8]) if antr else "keine offenen Anträge", "/cockpit"))

    km_offen = _q(db, """SELECT DISTINCT k.employee_id, k.date FROM km_daily_entries k
                         WHERE k.date BETWEEN :a AND :b AND k.is_billable AND k.is_longest_trip IS NULL""", a=m0, b=m1)
    out.append(_punkt("km", "Ist das KM-Journal vollständig (Tagesbereinigung für alle Tage gelaufen)?", not km_offen,
                      f"{len(km_offen)} Tag(e) noch nicht bereinigt" if km_offen else "alle Tage bereinigt"))

    pl = _q(db, """SELECT e.first_name || ' ' || e.last_name AS n, t.check_in, CASE
                      WHEN t.check_out < t.check_in THEN 'Gehen vor Kommen am selben Tag'
                      WHEN t.billed_hours < 0 THEN 'negative Stunden'
                      WHEN t.billed_hours > 10 THEN 'über 10 Std. an einem Tag'
                      ELSE 'Urlaub/Krank und Arbeit am selben Tag' END AS grund
                   FROM time_entries t JOIN employees e ON e.id = t.employee_id
                   WHERE t.check_in::date BETWEEN :a AND :b AND NOT coalesce(e.is_test, false) AND (
                         -- Gehen an frueherem TAG = nachgebucht (Kommen-Datum = Buchungstag), wie im Zeiterfassungs-Export erlaubt
                         (t.check_out < t.check_in AND t.check_out::date = t.check_in::date) OR t.billed_hours < 0
                      OR (t.billed_hours > 10 AND t.object_id NOT IN (999, 19))
                      OR (t.object_id NOT IN (999, 19) AND EXISTS (SELECT 1 FROM time_entries u WHERE u.employee_id = t.employee_id
                          AND u.object_id IN (999, 19) AND u.check_in::date = t.check_in::date)))
                   ORDER BY t.check_in""", a=m0, b=m1)
    out.append(_punkt("plausibel", "Sind die Zeiten plausibel?", not pl,
                      "; ".join(f"{r['n']} {r['check_in']:%d.%m.}: {r['grund']}" for r in pl[:5]) + (" …" if len(pl) > 5 else "")
                      if pl else "keine Auffälligkeiten", f"/cockpit/zeiten?pruef=alle&monat={mk}"))

    try:
        from app.services.minijob import grenze
        g = float(grenze(db, m1))
    except Exception:                       # Service noch nicht da -> Punkt nur von Hand
        g = None
    if g:
        typ = {r["id"]: r["t"] for r in _q(db, "SELECT id, coalesce(employment_type, '') AS t FROM employees")}
        drueber = [f"{r['name']} {r['gesamt'] - (r.get('km_amount') or 0):.2f} €".replace(".", ",") for r in rows
                   if typ.get(r["employee_id"]) == "minijob" and (r["gesamt"] or 0) - (r.get("km_amount") or 0) > g]
        out.append(_punkt("minijob", f"Bleiben alle Minijobber unter der Grenze ({g:.0f} €)?", not drueber,
                          ", ".join(drueber) if drueber else "alle unter der Grenze (ohne KM-Geld)"))
    else:
        out.append(_punkt("minijob", "Hast du die Minijob-Grenze geprüft?", None, "Grenze noch nicht hinterlegt – bitte von Hand prüfen"))

    krank = _q(db, """SELECT count(DISTINCT (employee_id, check_in::date)) AS n FROM time_entries
                      WHERE object_id = 19 AND check_in::date BETWEEN :a AND :b""", a=m0, b=m1)[0]["n"]
    out.append(_punkt("krank", "Hast du alle Krankmeldungen (AU) und Urlaube eingetragen?", None,
                      f"im System: {krank} Krankheitstag(e)"))
    neu = _q(db, """SELECT first_name || ' ' || last_name AS n FROM employees WHERE created_at::date BETWEEN :a AND :b
                    AND is_active AND NOT coalesce(is_test, false) AND personal_nr !~* '^(A|TEST)'""", a=m0, b=m1) if _spalte(db, "employees", "created_at") else []
    out.append(_punkt("stammdaten", "Sind neue Mitarbeiter, Austritte und Lohnänderungen auch in Lexware gepflegt?", None,
                      ("neu im Monat: " + ", ".join(r["n"] for r in neu)) if neu else "keine neuen Mitarbeiter im Monat"))
    out.append(_punkt("vorschuss", "Hast du Vorschüsse und Sonderzahlungen erfasst?", None, ""))

    haken = zustand(db, y, m)["haken"]
    for p in out:
        h = haken.get(p["key"])
        p["haken"] = bool(h) and p["auto"] is not False
        p["haken_von"] = h and h.get("von")
        p["gruen"] = p["haken"]
    db.commit()
    return {"monat": mk, "punkte": out, "alle_gruen": all(p["gruen"] for p in out)}


def _spalte(db, tab, sp):
    return bool(_q(db, "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :s", t=tab, s=sp))


def haken_setzen(db, y, m, key, wert: bool, user_id, wer: str):
    from app.services.booking_service import log_audit
    z = zustand(db, y, m)
    if z["status"] == "abgeschlossen":
        raise PermissionError("Der Monat ist abgeschlossen")
    p = next((p for p in pruefliste(db, y, m)["punkte"] if p["key"] == key), None)
    if not p:
        raise KeyError(key)
    if wert and p["auto"] is False:
        raise ValueError("Erst erledigen, dann abhaken: " + p["detail"])
    h = z["haken"]
    if wert:
        h[key] = {"von": wer, "am": datetime.now().isoformat(timespec="minutes")}
    else:
        h.pop(key, None)
    db.execute(text("UPDATE monatsabschluss SET haken = :h WHERE monat = :k"), {"h": json.dumps(h), "k": monat_key(y, m)})
    log_audit(db, user_id, None, "abschluss_haken", entity_type="monat", entity_id=y * 100 + m,
              details=f"Monatsabschluss {m:02d}/{y}: '{p['frage']}' " + ("abgehakt" if wert else "Haken entfernt"))
    db.commit()
    return pruefliste(db, y, m)


# ------------------------------------------------------------------ Schritt 2: Lexware-Datei + PDFs

def _num(x):
    return f"{x:.2f}".replace(".", ",")


def _persnr(p, art):
    return str(int(re.sub(r"\D", "", p) or 0)) if art == "nur_ziffern" else p


def lexware_zeilen(db, y, m):
    """[(persnr, name, lohnart, wert, stundensatz, bezeichnung)] - Werte unveraendert aus der Lohnuebersicht."""
    from app.services import festgehalt
    la = lohnarten(db)
    out = []
    for r in lohnzeilen(db, y, m):
        if not _hat_lohn(r):
            continue
        p, n = r["personal_nr"], r["name"]
        if r.get("festgehalt"):
            emp = db.execute(text("SELECT * FROM employees WHERE id = :i"), {"i": r["employee_id"]}).fetchone()
            fg = festgehalt.active_in_month(db, r["employee_id"], y, m)
            for x in festgehalt.lexware_lohnarten(db, emp, fg, y, m):
                out.append((p, n, x["lohnart"], x.get("stunden") if x.get("stunden") is not None else x.get("betrag"), None, x["bezeichnung"]))
        else:
            for k, bez in (("normal_hours", "normal"), ("nacht_hours", "nacht"), ("sonntag_hours", "sonntag"),
                           ("feiertag_hours", "feiertag"), ("urlaub_hours", "urlaub")):
                if r.get(k):
                    out.append((p, n, la[bez], round(r[k], 2), None, {"normal": "Stunden", "nacht": "Nachtzuschlag",
                               "sonntag": "Sonntagszuschlag", "feiertag": "Feiertagszuschlag", "urlaub": "Urlaubsstunden"}[bez]))
            if r.get("sonder_hours"):
                satz = round((r.get("sonder_amount") or 0) / r["sonder_hours"], 2) if r["sonder_hours"] else None
                out.append((p, n, la["sonder"], round(r["sonder_hours"], 2), satz, "Sonderstunden"))
        if r.get("km_amount") and p not in OHNE_KM_ANHANG:
            out.append((p, n, la["km"], round(r["km_amount"], 2), None, "Fahrtkosten (KM-Geld)"))
    return out


def fehlende_lohnarten(db, y, m):
    """Bezeichnungen, fuer die im Monat Werte anfallen, aber noch keine Lexware-Lohnart-Nummer eingetragen ist."""
    return sorted({z[5] for z in lexware_zeilen(db, y, m) if z[2] in (None, "")})


def lexware_datei(db, y, m) -> bytes:
    la = lohnarten(db)
    fehlt = fehlende_lohnarten(db, y, m)
    if fehlt:
        raise ValueError("Lexware-Lohnart-Nummer fehlt für: " + ", ".join(fehlt) + " (Schritt 2 › Lohnarten eintragen)")
    zeilen = []
    if la["kopfzeile"]:
        zeilen.append("Jahr;Monat;Personalnummer;Lohnart;Wert;Stundensatz")
    for p, _n, nr, wert, satz, _b in lexware_zeilen(db, y, m):
        zeilen.append(f"{y};{m};{_persnr(p, la['persnr'])};{nr};{_num(wert)};{_num(satz) if satz else ''}")
    return ("\r\n".join(zeilen) + "\r\n").encode("cp1252", errors="replace")


def _datei_teil(s):
    s = (s or "").strip()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-") or "x"


ANH_PRAEFIX = {"lohnabrechnung": "Lohnabrechnung", "zeitnachweis": "Zeitnachweis", "km": "KM-Journal"}


def anhang_name(art, y, m, pnr, nachname, vorname):
    """Wie Skript v2.5: Lohnabrechnung_{Jahr}_{Monat}_{PersNr}_{Nachname}_{Vorname}.pdf (Zeitnachweis/KM-Journal analog)."""
    return f"{ANH_PRAEFIX[art]}_{y}_{m:02d}_{_datei_teil(pnr)}_{_datei_teil(nachname)}_{_datei_teil(vorname)}.pdf"


def ordner(y, m):
    d = os.path.join(DATEN, monat_key(y, m))
    os.makedirs(d, exist_ok=True)
    return d


def erzeugen(db, y, m, user_id):
    """Lexware-Datei + Zeitnachweis-/KM-PDFs je MA in den Monatsordner, alles zusaetzlich als ZIP."""
    from app.core.pdf_generator import PDFGenerator
    from app.services.booking_service import log_audit
    if not pruefliste(db, y, m)["alle_gruen"]:
        raise ValueError("Erst alle Punkte der Prüfliste abhaken")
    z = zustand(db, y, m)
    if z["status"] == "abgeschlossen":
        raise PermissionError("Der Monat ist abgeschlossen")
    d = ordner(y, m)
    lex = f"Lexware_Lohndaten_{monat_key(y, m)}.txt"
    ablage.schreiben(os.path.join(d, lex), lexware_datei(db, y, m))
    gen = PDFGenerator(db)
    # Eigener Ausgabeordner: /tmp/seda24_pdfs teilen sich LIVE und DEV; dort koennen alte (fremde) Dateien liegen,
    # die wkhtmltopdf nicht ueberschreiben kann -> sonst landen veraltete PDFs im Paket.
    gen.output_dir = os.path.join(d, ".erzeugen")
    shutil.rmtree(gen.output_dir, ignore_errors=True)
    os.makedirs(gen.output_dir)
    start = datetime.now().timestamp() - 1
    for r in _q(db, "SELECT pfad FROM monatsabschluss_dokument WHERE monat = :k AND art IN ('zeitnachweis', 'km')", k=monat_key(y, m)):
        if r["pfad"] and os.path.exists(r["pfad"]):
            os.remove(r["pfad"])
    db.execute(text("DELETE FROM monatsabschluss_dokument WHERE monat = :k AND art IN ('zeitnachweis', 'km')"), {"k": monat_key(y, m)})
    fehler = []
    for r in lohnzeilen(db, y, m):
        if not _hat_lohn(r):
            continue
        for art, fn in (("zeitnachweis", gen.generate_zeitnachweis), ("km", gen.generate_kilometer)):
            if art == "km" and (r["personal_nr"] in OHNE_KM_ANHANG or not r.get("km_amount")):
                continue
            try:
                quelle = fn(r["employee_id"], y, m)
                if os.path.dirname(quelle) != gen.output_dir or os.path.getmtime(quelle) < start:
                    raise RuntimeError("PDF nicht frisch erzeugt")
                name = anhang_name(art, y, m, r["personal_nr"], *_namen(db, r["employee_id"]))
                with open(quelle, "rb") as f:
                    daten = f.read()
                os.remove(quelle)
                _dok(db, y, m, r["employee_id"], art, name, ablage.schreiben(os.path.join(d, name), daten), "automatisch",
                     user_id, daten)
            except Exception as e:  # einzelner MA bricht den Lauf nicht ab
                fehler.append(f"{r['name']} {art}: {e}")
    shutil.rmtree(gen.output_dir, ignore_errors=True)
    db.execute(text("UPDATE monatsabschluss SET status = 'erzeugt', erzeugt_am = now(), erzeugt_von = :u WHERE monat = :k"),
               {"u": user_id, "k": monat_key(y, m)})
    log_audit(db, user_id, None, "abschluss_erzeugt", entity_type="monat", entity_id=y * 100 + m,
              details=f"Monatsabschluss {m:02d}/{y}: Lexware-Datei und PDFs erzeugt" + (f", {len(fehler)} Fehler" if fehler else ""))
    db.commit()
    return {"lexware_datei": lex, "zeilen": len(lexware_zeilen(db, y, m)), "fehler": fehler, **dokumente(db, y, m)}


def _namen(db, eid):
    r = db.execute(text("SELECT last_name, first_name FROM employees WHERE id = :i"), {"i": eid}).fetchone()
    return (r[0], r[1]) if r else ("", "")


def paket_zip(db, y, m) -> bytes:
    """ZIP fuer Drazens PC: Lexware-Datei + alle Zeitnachweis-/KM-PDFs."""
    d = ordner(y, m)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        lex = os.path.join(d, f"Lexware_Lohndaten_{monat_key(y, m)}.txt")
        for p in (lex + ".enc", lex):
            if os.path.exists(p):
                zf.writestr(os.path.basename(lex), ablage.lesen(p))
                break
        for r in _q(db, "SELECT pfad, dateiname, art FROM monatsabschluss_dokument WHERE monat = :k AND art IN ('zeitnachweis', 'km')",
                    k=monat_key(y, m)):
            if r["pfad"] and os.path.exists(r["pfad"]):
                zf.writestr(f"{r['art']}/{r['dateiname']}", ablage.lesen(r["pfad"]))
    return buf.getvalue()


def _dok(db, y, m, eid, art, name, pfad, zuordnung, user_id, b: bytes):
    return db.execute(text("""INSERT INTO monatsabschluss_dokument (monat, employee_id, art, dateiname, pfad, groesse, sha256, zuordnung, von)
                              VALUES (:k, :e, :a, :n, :p, :g, :s, :z, :u) RETURNING id"""),
                      {"k": monat_key(y, m), "e": eid, "a": art, "n": name, "p": pfad, "g": len(b),
                       "s": hashlib.sha256(b).hexdigest(), "z": zuordnung, "u": user_id}).scalar()


def dokumente(db, y, m):
    tabellen(db)
    rows = _q(db, """SELECT d.id, d.employee_id, d.art, d.dateiname, d.groesse, d.zuordnung, e.personal_nr,
                            e.first_name || ' ' || e.last_name AS name
                       FROM monatsabschluss_dokument d LEFT JOIN employees e ON e.id = d.employee_id
                      WHERE d.monat = :k ORDER BY d.art, e.personal_nr NULLS LAST, d.dateiname""", k=monat_key(y, m))
    return {"dokumente": [dict(r) for r in rows], "lohnabrechnungen": lohnabrechnungen_stand(db, y, m, rows)}


def lohnabrechnungen_stand(db, y, m, rows=None):
    """'12 von 12 Lohnabrechnungen da': erwartet = alle MA mit Lohn im Monat (wie Versand-Vorschau)."""
    if rows is None:
        rows = _q(db, "SELECT employee_id, art FROM monatsabschluss_dokument WHERE monat = :k", k=monat_key(y, m))
    da_ids = {r["employee_id"] for r in rows if r["art"] == "lohnabrechnung" and r["employee_id"]}
    erwartet = [r for r in lohnzeilen(db, y, m) if _hat_lohn(r)]
    fehlen = [{"employee_id": r["employee_id"], "personal_nr": r["personal_nr"], "name": r["name"]}
              for r in erwartet if r["employee_id"] not in da_ids]
    offen = sum(1 for r in rows if r["art"] == "lohnabrechnung" and not r["employee_id"])
    return {"erwartet": len(erwartet), "da": len(erwartet) - len(fehlen), "fehlen": fehlen, "nicht_zugeordnet": offen,
            "komplett": not fehlen and not offen}


# ------------------------------------------------------------------ Schritt 3: Lohnabrechnungen hochladen

def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def zuordnen_name(db, dateiname, kandidaten=None):
    """MA zu einem Dateinamen: zuerst PersNr (D0040 / 0040), sonst Vor- und Nachname, sonst eindeutiger Nachname."""
    ma = kandidaten or [dict(r) for r in _q(db, """SELECT id, personal_nr, first_name, last_name FROM employees
                                                    WHERE NOT coalesce(is_test, false)""")]
    n = _norm(os.path.splitext(os.path.basename(dateiname))[0])
    pm = re.search(r"\b([a-z])?0*(\d{1,4})\b", n.replace("_", " "))
    for r in ma:
        p = (r["personal_nr"] or "").lower()
        if p and re.search(rf"(^|\s){re.escape(p)}(\s|$)", n):
            return r["id"], "persnr"
    toks = set(n.split())
    voll = [r for r in ma if set(_norm(r["last_name"]).split()) <= toks and set(_norm(r["first_name"]).split()[:1]) <= toks]
    if len(voll) == 1:
        return voll[0]["id"], "name"
    nach = [r for r in ma if set(_norm(r["last_name"]).split()) <= toks]
    if len(nach) == 1:
        return nach[0]["id"], "nachname"
    if pm and pm.group(2):
        nr = int(pm.group(2))
        treffer = [r for r in ma if re.sub(r"\D", "", r["personal_nr"] or "x") and int(re.sub(r"\D", "", r["personal_nr"])) == nr]
        if len(treffer) == 1:
            return treffer[0]["id"], "persnr"
    return None, None


def _pdf_seiten_text(b: bytes):
    try:
        from pypdf import PdfReader
        return [(p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages]
    except Exception:
        return None


def _ma_im_text(textstueck, ma):
    """MA, dessen Vor- UND Nachname (oder PersNr D0040) im Seitentext steht - nur wenn genau einer passt."""
    n = " " + _norm(textstueck) + " "
    treffer = {r["id"] for r in ma if r["personal_nr"] and f" {r['personal_nr'].lower()} " in n}
    if len(treffer) != 1:
        treffer = {r["id"] for r in ma if f" {_norm(r['last_name'])} " in n and f" {_norm(r['first_name']).split()[0]} " in n}
    return treffer.pop() if len(treffer) == 1 else None


def _aufteilen(b: bytes, ma):
    """[(employee_id|None, pdf_bytes, seiten)] - eine Sammel-PDF aus Lexware wird je MA aufgeteilt.
    Seiten ohne erkennbaren MA gehoeren zum vorherigen (Folgeseiten)."""
    seiten = _pdf_seiten_text(b)
    if not seiten:
        return [(None, b, None)]
    je = []
    for i, t in enumerate(seiten):
        eid = _ma_im_text(t, ma)
        if je and (eid is None or eid == je[-1][0]):
            je[-1][1].append(i)
        else:
            je.append([eid, [i]])
    if len({e for e, _ in je if e}) <= 1:
        return [(je[0][0] if len(je) == 1 or all(e in (None, je[0][0]) for e, _ in je) else None, b, None)]
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(io.BytesIO(b))
    out = []
    for eid, idx in je:
        w = PdfWriter()
        for i in idx:
            w.add_page(r.pages[i])
        buf = io.BytesIO()
        w.write(buf)
        out.append((eid, buf.getvalue(), [i + 1 for i in idx]))
    return out


def lohnabrechnungen_aufnehmen(db, y, m, pdfs, user_id, quelle="Cockpit"):
    """pdfs: [(dateiname, bytes)]. Speichert verschluesselt, ordnet zu (PersNr/Name im Dateinamen, sonst im PDF-Text;
    Sammel-PDFs werden je MA aufgeteilt). Gleicher Inhalt (sha256) wird nicht doppelt gespeichert.
    Rueckgabe je Datei: Quittung mit sha256, Zuordnung, ggf. 'doppelt'."""
    from app.services.booking_service import log_audit
    if zustand(db, y, m)["status"] == "abgeschlossen":
        raise PermissionError("Der Monat ist abgeschlossen")
    ma = [dict(r) for r in _q(db, "SELECT id, personal_nr, first_name, last_name FROM employees WHERE NOT coalesce(is_test, false)")]
    namen = {r["id"]: f"{r['first_name']} {r['last_name']}" for r in ma}
    d = os.path.join(ordner(y, m), "lohnabrechnungen")
    os.makedirs(d, exist_ok=True)
    vorhanden = {r["sha256"]: r for r in _q(db, """SELECT sha256, employee_id FROM monatsabschluss_dokument
                                                  WHERE monat = :k AND art = 'lohnabrechnung'""", k=monat_key(y, m))}
    quittung = []
    for name, b in pdfs:
        sha = hashlib.sha256(b).hexdigest()
        q = {"datei": name, "sha256": sha, "groesse": len(b), "teile": []}
        quittung.append(q)
        if not b.startswith(b"%PDF"):
            q["status"] = "kein PDF"
            continue
        if sha in vorhanden:
            q["status"] = "doppelt"
            q["teile"].append({"employee_id": vorhanden[sha]["employee_id"], "name": namen.get(vorhanden[sha]["employee_id"])})
            continue
        teile = _aufteilen(b, ma)
        q["status"] = "gespeichert"
        for eid, daten, seiten in teile:
            wie = "PDF-Text" if eid else None
            if len(teile) == 1:
                eid_name, wie_name = zuordnen_name(db, name, ma)
                if eid_name and eid and eid_name != eid:
                    eid, wie = None, "Widerspruch"   # Dateiname sagt X, Inhalt Y: lieber von Hand zuordnen
                elif eid_name:
                    eid, wie = eid_name, wie_name
            if eid:
                nach, vor = _namen(db, eid)
                pnr = next((r["personal_nr"] for r in ma if r["id"] == eid), "")
                ablage_name = anhang_name("lohnabrechnung", y, m, pnr, nach, vor)
            else:
                ablage_name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:110]
            if seiten:
                ablage_name = ablage_name.replace(".pdf", "") + f"_S{seiten[0]}.pdf" if not eid else ablage_name
            pfad = ablage.schreiben(os.path.join(d, f"{sha[:12]}_{len(q['teile'])}_{ablage_name}"), daten)
            dok = _dok(db, y, m, eid, "lohnabrechnung", ablage_name, pfad, wie or "offen", user_id, daten)
            vorhanden[sha] = {"employee_id": eid}
            q["teile"].append({"dok_id": dok, "employee_id": eid, "name": namen.get(eid), "zuordnung": wie or "offen",
                               "seiten": seiten})
    neu = sum(len(q["teile"]) for q in quittung if q.get("status") == "gespeichert")
    if neu or any(q.get("status") != "doppelt" for q in quittung):
        log_audit(db, user_id, None, "abschluss_upload", entity_type="monat", entity_id=y * 100 + m,
                  details=f"Monatsabschluss {m:02d}/{y}: {neu} Lohnabrechnung(en) aufgenommen ({quelle})"
                          + "".join(f"; {q['datei']}: {q['status']}" for q in quittung if q.get("status") != "gespeichert"))
    db.commit()
    return quittung


def hochladen(db, y, m, dateien, user_id):
    """dateien: [(name, bytes)] - PDFs oder ZIPs mit PDFs (Notweg im Cockpit; regulaer kommt alles vom PC-Skript)."""
    pdfs = []
    for name, b in dateien:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(b)) as zf:
                for i in zf.infolist():
                    if not i.is_dir() and i.filename.lower().endswith(".pdf") and i.file_size < 10_000_000:
                        pdfs.append((os.path.basename(i.filename), zf.read(i)))
        elif name.lower().endswith(".pdf"):
            pdfs.append((os.path.basename(name), b))
    q = lohnabrechnungen_aufnehmen(db, y, m, pdfs, user_id)
    return {"neu": sum(len(x["teile"]) for x in q if x.get("status") == "gespeichert"),
            "doppelt": sum(1 for x in q if x.get("status") == "doppelt"), **dokumente(db, y, m)}


def dokument_zuordnen(db, y, m, dok_id, employee_id, user_id):
    if zustand(db, y, m)["status"] == "abgeschlossen":
        raise PermissionError("Der Monat ist abgeschlossen")
    db.execute(text("""UPDATE monatsabschluss_dokument SET employee_id = :e, zuordnung = 'von Hand'
                       WHERE id = :i AND monat = :k AND art = 'lohnabrechnung'"""), {"e": employee_id, "i": dok_id, "k": monat_key(y, m)})
    db.commit()
    return dokumente(db, y, m)


def dokument_loeschen(db, y, m, dok_id):
    r = _q(db, "SELECT pfad FROM monatsabschluss_dokument WHERE id = :i AND monat = :k AND art = 'lohnabrechnung'", i=dok_id, k=monat_key(y, m))
    if r:
        db.execute(text("DELETE FROM monatsabschluss_dokument WHERE id = :i"), {"i": dok_id})
        if os.path.exists(r[0]["pfad"]):
            os.remove(r[0]["pfad"])
    db.commit()
    return dokumente(db, y, m)


# ------------------------------------------------------------------ Schritt 4: Vorschau je MA

def anrede(vorname, gender):
    g = (gender or "").upper()
    return f"Liebe {vorname}" if g in ("W", "F") else f"Lieber {vorname}" if g == "M" else f"Hallo {vorname}"


def vorschau(db, y, m):
    docs = _q(db, "SELECT employee_id, art, dateiname FROM monatsabschluss_dokument WHERE monat = :k", k=monat_key(y, m))
    je = {}
    for d in docs:
        je.setdefault(d["employee_id"], []).append(d)
    info = {r["id"]: r for r in _q(db, """SELECT e.id, e.first_name, e.gender, u.email FROM employees e
                                          LEFT JOIN users u ON u.id = e.user_id""")}
    out = []
    for r in lohnzeilen(db, y, m):
        if not _hat_lohn(r):
            continue
        i = info[r["employee_id"]]
        d = je.get(r["employee_id"], [])
        anh = [{"art": x["art"], "datei": x["dateiname"]} for x in sorted(d, key=lambda x: ["lohnabrechnung", "zeitnachweis", "km"].index(x["art"]))]
        fehlt = []
        if not any(x["art"] == "lohnabrechnung" for x in d):
            fehlt.append("Lohnabrechnung")
        if not any(x["art"] == "zeitnachweis" for x in d):
            fehlt.append("Zeitnachweis")
        mail = (i["email"] or "").strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", mail, re.I):
            fehlt.append("Mail-Adresse")
        out.append({"employee_id": r["employee_id"], "personal_nr": r["personal_nr"], "name": r["name"], "email": mail or None,
                    "anrede": anrede(i["first_name"], i["gender"]), "betreff": betreff(y, m),
                    "text": mailtext(i["first_name"], i["gender"], y, m), "anhaenge": anh, "fehlt": fehlt,
                    "ohne_km": r["personal_nr"] in OHNE_KM_ANHANG, "bereit": not fehlt})
    lose = [dict(x) for x in _q(db, """SELECT id, dateiname FROM monatsabschluss_dokument WHERE monat = :k AND art = 'lohnabrechnung'
                                       AND employee_id IS NULL""", k=monat_key(y, m))]
    return {"monat": monat_key(y, m), "mitarbeiter": out, "nicht_zugeordnet": lose,
            "bereit": sum(1 for x in out if x["bereit"]), "gesamt": len(out)}


def betreff(y, m):
    return f"SEDA24 – deine Lohnabrechnung {MONATE[m]} {y}"


def mailtext(vorname, gender, y, m):
    return (f"{anrede(vorname, gender)},\n\nanbei deine Lohnabrechnung für {MONATE[m]} {y} mit Zeitnachweis"
            f" (und Kilometer-Nachweis, falls du gefahren bist).\nBei Fragen melde dich gern bei uns.\n\n"
            f"Viele Grüße\nDein SEDA24-Team")


# ------------------------------------------------------------------ Schritt 5: versenden + sperren

def _anhaenge(db, y, m, eid, pnr):
    """[(Dateiname fuer die Mail, Pfad)] in der Reihenfolge Lohnabrechnung, Zeitnachweis, KM-Journal."""
    nach, vor = _namen(db, eid)
    docs = _q(db, """SELECT art, pfad FROM monatsabschluss_dokument WHERE monat = :k AND employee_id = :e
                     ORDER BY array_position(ARRAY['lohnabrechnung','zeitnachweis','km']::varchar[], art), id""",
              k=monat_key(y, m), e=eid)
    out, gesehen = [], set()
    for d in docs:
        if d["art"] in gesehen or (d["art"] == "km" and pnr in OHNE_KM_ANHANG):
            continue
        if not os.path.exists(d["pfad"]):
            raise RuntimeError(f"Datei fehlt auf dem Server ({ANH_PRAEFIX[d['art']]})")
        gesehen.add(d["art"])
        out.append((anhang_name(d["art"], y, m, pnr, nach, vor), d["pfad"]))
    return out


def _senden(db, y, m, user_id, mas):
    """Schickt die Mails fuer die Vorschau-Eintraege mas mit EINER Anmeldung. Status je MA sofort gespeichert."""
    from app.services import lohnversand as lv
    einst = lv.einstellungen(db)
    test = einst["testmodus"] or not lv.echt_erlaubt()
    try:
        conn = lv.verbinden(test, ordner(y, m), einst["test_an"])
    except Exception as e:
        raise ValueError(f"Mail-Server nicht erreichbar: {type(e).__name__} {str(e)[:150]}")
    ergebnis = {"gesendet": 0, "fehler": 0, "testmodus": test, "weg": lv.weg(test)}
    try:
        for i, x in enumerate(mas):
            an_ma = x["email"]
            an = einst["test_an"] if test else an_ma
            betreff = (f"[TEST – an {x['name']} <{an_ma}>] " if test else "") + x["betreff"]
            koerper = (f"TESTMODUS – diese Mail ginge an: {x['name']} <{an_ma}>\n\n" if test else "") + x["text"]
            status, fehler, namen = ("test" if test else "gesendet"), None, []
            try:
                anh = _anhaenge(db, y, m, x["employee_id"], x["personal_nr"])
                namen = [n for n, _ in anh]
                conn.senden(lv.nachricht(an, betreff, koerper, anh))
                ergebnis["gesendet"] += 1
            except Exception as e:      # ein MA bricht den Lauf nicht ab
                status, fehler = "fehler", f"{type(e).__name__}: {str(e)[:200]}"
                ergebnis["fehler"] += 1
            db.execute(text("""INSERT INTO monatsabschluss_versand (monat, employee_id, an, betreff, anhaenge, status, fehler, von)
                               VALUES (:k, :e, :an, :b, :a, :s, :f, :u)"""),
                       {"k": monat_key(y, m), "e": x["employee_id"], "an": an, "b": betreff,
                        "a": json.dumps(namen), "s": status, "f": fehler, "u": user_id})
            db.commit()
            if i < len(mas) - 1:
                time.sleep(lv.PAUSE_S)
    finally:
        conn.schliessen()
    return ergebnis


def versenden(db, y, m, user_id):
    """Alle MA verschicken. Echter Versand sperrt danach den Monat (auch wenn einzelne fehlschlagen - die werden
    einzeln erneut gesendet). Im Testmodus geht alles an Drazen und der Monat bleibt offen."""
    from app.services import lohnversand as lv
    from app.services.booking_service import log_audit
    z = zustand(db, y, m)
    test = lv.einstellungen(db)["testmodus"] or not lv.echt_erlaubt()
    if z["status"] == "abgeschlossen" and not test:
        raise PermissionError("Der Monat ist bereits abgeschlossen – einzelne Mitarbeiter über „Erneut senden“")
    if not pruefliste(db, y, m)["alle_gruen"]:
        raise ValueError("Erst alle Punkte der Prüfliste abhaken")
    v = vorschau(db, y, m)
    if v["bereit"] < v["gesamt"] or v["nicht_zugeordnet"]:
        raise ValueError(f"Noch nicht alle bereit: {v['gesamt'] - v['bereit']} Mitarbeiter, {len(v['nicht_zugeordnet'])} Datei(en) ohne Zuordnung")
    erg = _senden(db, y, m, user_id, v["mitarbeiter"])
    if not test:
        db.execute(text("UPDATE monatsabschluss SET status = 'abgeschlossen', gesperrt_am = now(), gesperrt_von = :u WHERE monat = :k"),
                   {"u": user_id, "k": monat_key(y, m)})
    log_audit(db, user_id, None, "abschluss_versand", entity_type="monat", entity_id=y * 100 + m,
              details=f"Monatsabschluss {m:02d}/{y}: " + (f"TESTVERSAND an {lv.einstellungen(db)['test_an']}: " if test else "")
              + f"{erg['gesendet']} gesendet, {erg['fehler']} Fehler" + ("" if test else ", Monat gesperrt"))
    db.commit()
    return {**protokoll(db, y, m), "ergebnis": erg}


def erneut_senden(db, y, m, employee_id, user_id):
    """Einen MA (erneut) schicken - z. B. nach Fehler oder falscher Adresse. Geht auch im gesperrten Monat."""
    from app.services.booking_service import log_audit
    if zustand(db, y, m)["status"] not in ("erzeugt", "abgeschlossen"):
        raise ValueError("Erst Schritt 2 (Für Lexware erzeugen)")
    x = next((x for x in vorschau(db, y, m)["mitarbeiter"] if x["employee_id"] == employee_id), None)
    if not x:
        raise ValueError("Mitarbeiter ist in diesem Monat nicht im Abschluss")
    if not x["bereit"]:
        raise ValueError("Noch nicht bereit: " + ", ".join(x["fehlt"]))
    erg = _senden(db, y, m, user_id, [x])
    log_audit(db, user_id, employee_id, "abschluss_erneut_gesendet", entity_type="monat", entity_id=y * 100 + m,
              details=f"Monatsabschluss {m:02d}/{y}: {x['name']} erneut gesendet" + (" (Test)" if erg["testmodus"] else "")
              + (" – FEHLER" if erg["fehler"] else ""))
    db.commit()
    return {**protokoll(db, y, m), "ergebnis": erg}


def protokoll(db, y, m):
    from app.services import lohnversand as lv
    rows = _q(db, """SELECT v.id, v.employee_id, e.personal_nr, e.first_name || ' ' || e.last_name AS name, v.an, v.anhaenge,
                            v.status, v.fehler, v.am FROM monatsabschluss_versand v LEFT JOIN employees e ON e.id = v.employee_id
                      WHERE v.monat = :k ORDER BY v.am, v.id""", k=monat_key(y, m))
    z = zustand(db, y, m)
    versand = [{**dict(r), "anhaenge": json.loads(r["anhaenge"] or "[]"), "am": r["am"].isoformat(timespec="minutes")} for r in rows]
    je_ma = {}
    for r in versand:          # letzter Stand je MA
        je_ma[r["employee_id"]] = r
    return {"monat": monat_key(y, m), "status": z["status"],
            "gesperrt_am": z["gesperrt_am"] and z["gesperrt_am"].isoformat(timespec="minutes"),
            "versand": versand, "je_ma": sorted(je_ma.values(), key=lambda r: r["personal_nr"] or ""),
            "einstellungen": lv.einstellungen(db), "versandweg": lv.status_versand(), "nachtraege": nachtraege(db, y, m)}


def sperren(db, y, m, user_id):
    """Monat (wieder) sperren ohne neuen Versand - z. B. nach einer Korrektur im wieder geoeffneten Monat."""
    from app.services.booking_service import log_audit
    if zustand(db, y, m)["status"] != "erzeugt":
        raise ValueError("Sperren geht erst nach Schritt 2 (Für Lexware erzeugen)")
    db.execute(text("UPDATE monatsabschluss SET status = 'abgeschlossen', gesperrt_am = now(), gesperrt_von = :u WHERE monat = :k"),
               {"u": user_id, "k": monat_key(y, m)})
    log_audit(db, user_id, None, "abschluss_gesperrt", entity_type="monat", entity_id=y * 100 + m,
              details=f"Monatsabschluss {m:02d}/{y} gesperrt (ohne Versand)")   # offene Oeffnung schliesst der DB-Trigger
    db.commit()
    return protokoll(db, y, m)


def wieder_oeffnen(db, y, m, user, grund, pin):
    """Abgeschlossenen Monat oeffnen - nur mit Super-PIN (services/superpin.py) und Grund. Die Oeffnung, jede Aenderung
    an Lohndaten in dem Monat und das erneute Sperren schreibt die Datenbank selbst unveraenderbar ins Protokoll
    (monatsabschluss_oeffnung/-_aenderung, migrations/monatssperre.sql) - auch bei Aenderungen ausserhalb der App."""
    from app.db.database import APP_BENUTZER
    from app.services import superpin
    from app.services.booking_service import log_audit
    grund = (grund or "").strip()
    if len(grund) < 10:
        raise ValueError("Bitte einen Grund angeben (mindestens 10 Zeichen) – er steht dauerhaft im Protokoll")
    if zustand(db, y, m)["status"] != "abgeschlossen":
        raise ValueError("Der Monat ist nicht gesperrt")
    superpin.pruefen(db, user, pin)
    db.execute(text("""INSERT INTO monatsabschluss_oeffnung (monat, grund, geoeffnet_von, app_benutzer)
                       VALUES (:k, :g, :u, :a)"""), {"k": monat_key(y, m), "g": grund[:1000], "u": user.id, "a": APP_BENUTZER.get()})
    db.execute(text("UPDATE monatsabschluss SET status = 'erzeugt', gesperrt_am = NULL, gesperrt_von = NULL WHERE monat = :k"),
               {"k": monat_key(y, m)})
    log_audit(db, user.id, None, "abschluss_wieder_offen", entity_type="monat", entity_id=y * 100 + m,
              details=f"Monatsabschluss {m:02d}/{y} mit Super-PIN wieder geöffnet: {grund[:200]}")
    db.commit()
    return protokoll(db, y, m)


TABELLEN_TEXT = {"time_entries": "Zeitbuchung", "break_entries": "Pause", "km_daily_entries": "KM-Tag",
                 "km_monthly_reports": "KM-Monat", "sick_notes": "Krankmeldung", "zeitkonto": "Zeitkonto",
                 "monthly_carryovers": "Übertrag", "vacation_requests": "Urlaubsantrag",
                 "correction_requests": "Korrekturantrag", "pending_bookings": "Nachbuchung"}
AKTION_TEXT = {"INSERT": "neu", "UPDATE": "geändert", "DELETE": "gelöscht", "GEOEFFNET": "geöffnet", "GESPERRT": "wieder gesperrt"}
UNWICHTIG = {"updated_at", "created_at"}
FELD_TEXT = {"check_in": "Kommen", "check_out": "Gehen", "notes": "Notiz", "billed_hours": "Std. abgerechnet",
             "object_id": "Objekt", "employee_id": "Mitarbeiter", "status": "Status", "date": "Datum", "start_date": "von",
             "end_date": "bis", "start_time": "Beginn", "end_time": "Ende", "distance_km": "KM", "amount": "Betrag",
             "hourly_rate": "Stundensatz", "is_billable": "abrechenbar", "is_longest_trip": "längste Fahrt", "type": "Art",
             "duration_minutes": "Minuten", "reason": "Grund"}


def _wer_text(db, app_benutzer, user_id, db_benutzer):
    r = None
    if user_id or app_benutzer:
        r = db.execute(text("""SELECT coalesce(e.first_name || ' ' || e.last_name, u.email) FROM users u
                               LEFT JOIN employees e ON e.user_id = u.id WHERE u.id = :i OR u.email = :a LIMIT 1"""),
                       {"i": user_id or -1, "a": app_benutzer or ""}).scalar()
    return r or app_benutzer or f"System/Skript ({db_benutzer})"


def nachtraege(db, y, m):
    """'Nachtraegliche Aenderungen' fuer den Monatsabschluss: je Oeffnung Grund, wer/wann, alle Aenderungen alt -> neu,
    erneutes Sperren. Dazu die Pruefung der Hash-Kette des Protokolls."""
    k = monat_key(y, m)
    if not db.execute(text("SELECT to_regclass('monatsabschluss_oeffnung') IS NOT NULL")).scalar():
        return {"oeffnungen": [], "kette_ok": None, "zeilen": 0}
    oeff = _q(db, "SELECT * FROM monatsabschluss_oeffnung WHERE monat = :k ORDER BY id", k=k)
    zeilen = _q(db, "SELECT * FROM monatsabschluss_aenderung WHERE monat = :k ORDER BY id", k=k)
    kette = db.execute(text("SELECT * FROM monatsabschluss_kette_pruefen()")).mappings().first()
    erg = []
    for o in oeff:
        aend = []
        for z in (z for z in zeilen if z["oeffnung_id"] == o["id"] and z["aktion"] in ("INSERT", "UPDATE", "DELETE")):
            alt, neu = z["alt"] or {}, z["neu"] or {}
            felder = [{"feld": FELD_TEXT.get(f, f), "alt": alt.get(f), "neu": neu.get(f)} for f in sorted(set(alt) | set(neu))
                      if f not in UNWICHTIG and alt.get(f) != neu.get(f)]
            if z["aktion"] != "UPDATE":    # neu/geloescht: nur die aussagekraeftigen Felder
                felder = [f for f in felder if f["alt"] is not None or f["neu"] is not None]
            ma_id = (neu or alt).get("employee_id")
            aend.append({"id": z["id"], "am": z["am"].isoformat(timespec="seconds"), "tabelle": TABELLEN_TEXT.get(z["tabelle"], z["tabelle"]),
                         "aktion": AKTION_TEXT.get(z["aktion"], z["aktion"]), "datensatz_id": z["datensatz_id"],
                         "mitarbeiter": ma_id and db.execute(text("SELECT first_name || ' ' || last_name FROM employees WHERE id = :i"),
                                                              {"i": ma_id}).scalar(),
                         "wer": _wer_text(db, z["app_benutzer"], None, z["db_benutzer"]), "felder": felder})
        erg.append({"id": o["id"], "grund": o["grund"], "geoeffnet_am": o["geoeffnet_am"].isoformat(timespec="seconds"),
                    "geoeffnet_von": _wer_text(db, o["app_benutzer"], o["geoeffnet_von"], o["db_benutzer"]),
                    "gesperrt_am": o["gesperrt_am"] and o["gesperrt_am"].isoformat(timespec="seconds"),
                    "gesperrt_von": o["gesperrt_am"] and _wer_text(db, None, o["gesperrt_von"], "?"),
                    "offen": o["gesperrt_am"] is None, "aenderungen": aend})
    return {"oeffnungen": erg, "kette_ok": kette["erste_fehlerhafte"] is None, "zeilen": kette["zeilen"]}


def testversand_zip(y, m) -> bytes:
    """Die .eml-Dateien des letzten Testlaufs (Versandweg 'Datei') als ZIP."""
    d = os.path.join(ordner(y, m), "testversand")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if n.endswith(".eml.enc"):
                zf.writestr(n[:-4], ablage.lesen(os.path.join(d, n)))
    return buf.getvalue()
