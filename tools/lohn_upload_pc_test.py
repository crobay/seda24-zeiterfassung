"""Test Upload-PC Lebenszeichen/Fehler/Vollstaendig (Drazen 26.11.2026 00:41). NUR DEV.
Telegram wird abgefangen (nichts wird gesendet). Stellt app_settings 'lohn_upload_pc' am Ende wieder her,
loescht die eigenen Test-Protokolleintraege. Aufruf aus backend/: venv/bin/python ../tools/lohn_upload_pc_test.py"""
import os, sys, json, subprocess
from datetime import datetime, timedelta
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(".env")
assert "dev_cockpit" in os.environ.get("DATABASE_URL", ""), "nur DEV"
import requests
from sqlalchemy import text
from app.db.database import SessionLocal
from app.services import lohn_upload_pc as lp

BASE = "https://dev.seda.de/api/v1"
gesendet = []
lp._melden = lambda t: gesendet.append(t)
fehler = 0
def ok(name, cond, info=""):
    global fehler
    print(f"  [{'OK ' if cond else 'XX '}] {name}{' - ' + str(info) if info else ''}")
    fehler += 0 if cond else 1

db = SessionLocal()
alt = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": lp.KEY}).scalar()
def leeren():
    db.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": lp.KEY}); db.commit()
D = datetime
try:
    print("== Stunden, die zaehlen")
    ok("Fr 22:00 -> Mo 22:00 = 24 Werktagsstunden", lp.betriebsstunden(D(2026, 11, 27, 22), D(2026, 11, 30, 22), False) == 24)
    ok("Fr 22:00 -> Mo 10:00 = 3 Betriebsstunden (07-22)", lp.betriebsstunden(D(2026, 11, 27, 22), D(2026, 11, 30, 10), True) == 3)
    ok("Do 31.12. 12:00 -> Sa 02.01. = 12 (Neujahr zaehlt nicht)", lp.betriebsstunden(D(2026, 12, 31, 12), D(2027, 1, 2, 12), False) == 12)
    ok("Mi 22:00 -> Do 07:00 = 0 Betriebsstunden (Nacht)", lp.betriebsstunden(D(2026, 11, 25, 22), D(2026, 11, 26, 7), True) == 0)

    print("== Lohnphase (Exporttag Vormonat bis Abschluss)")
    st_okt = db.execute(text("SELECT status FROM monatsabschluss WHERE monat = '2026-10'")).scalar()
    ok(f"26.11.2026 -> Oktober nur wenn offen (Exporttag 16.11., Status DEV {st_okt})", lp.lohnphase(db, D(2026, 11, 26).date()) == ("2026-10" if st_okt != "abgeschlossen" else None))
    ok("10.11.2026 -> keine Phase (vor dem Exporttag 16.11.)", lp.lohnphase(db, D(2026, 11, 10).date()) is None)
    ok("01.12.2026 -> November (Exporttag Di 01.12.)", lp.lohnphase(db, D(2026, 12, 1).date()) == "2026-11")
    ok("30.12.2026 -> nichts, wenn noch nie gemeldet", (leeren(), lp.stille_pruefen(db, D(2026, 12, 30, 10)))[1] is None)

    print("== Stille in der Lohnphase November (ab Exporttag Di 01.12., 3 Betriebsstunden)")
    lp.gemeldet(db, "TESTPC", {"2026-11": "12 Dateien"}, "test", jetzt=D(2026, 12, 1, 7, 0))
    ok("Di 01.12. 09:59 (unter 3 Std.) -> still", lp.stille_pruefen(db, D(2026, 12, 1, 9, 59)) is None)
    m = lp.stille_pruefen(db, D(2026, 12, 1, 10, 5))
    ok("Di 10:05 -> Telegram", m and "TESTPC meldet sich nicht" in m and "November 2026" in m, m)
    ok("Di 11:05 -> nicht nochmal (max. 1x je 24 Std.)", lp.stille_pruefen(db, D(2026, 12, 1, 11, 5)) is None)
    ok("Mi 10:06 -> Erinnerung nach 24 Std.", lp.stille_pruefen(db, D(2026, 12, 2, 10, 6)) is not None)
    lp.gemeldet(db, "TESTPC", jetzt=D(2026, 12, 2, 11, 0))
    ok("nach Meldung: Mi 13:00 still", lp.stille_pruefen(db, D(2026, 12, 2, 13, 0)) is None)
    ok("Fr 22:00 -> Mo 07:30: nur 0,5 Betriebsstunden -> still", (lp.gemeldet(db, "TESTPC", jetzt=D(2026, 12, 4, 22)), lp.stille_pruefen(db, D(2026, 12, 7, 7, 30)))[1] is None)
    s = lp.status(db, D(2026, 12, 7, 10, 30))
    ok("Mo 10:30 -> Status ueberfaellig (3,5 Std.)", s["ueberfaellig"] and s["still_std"] == 3.5 and s["phase"] == "2026-11", s)

    print("== Stille ausserhalb der Phase (24 Werktagsstunden)")
    lp.gemeldet(db, "TESTPC", jetzt=D(2026, 11, 6, 20))           # Fr 06.11. 20:00
    ok("Mo 09.11. 10:00 (14 Werktagsstd.) -> still", lp.stille_pruefen(db, D(2026, 11, 9, 10)) is None)
    m = lp.stille_pruefen(db, D(2026, 11, 9, 20, 5))
    ok("Mo 09.11. 20:05 (24 Werktagsstd.) -> Telegram", m and "über 24 Std. an Werktagen" in m, m)

    print("== Zeitplan 1.-15. stuendlich, sonst taeglich 12 Uhr (Drazen 26.11. 07:45)")
    leeren()
    lp.gemeldet(db, "TESTPC", jetzt=D(2026, 11, 30, 12))          # Mo 30.11. 12:00, letzter Tageslauf
    ok("Di 01.12. 07:05 (Exporttag) -> still, Stille zaehlt erst ab 07:00", lp.stille_pruefen(db, D(2026, 12, 1, 7, 5)) is None)
    s = lp.status(db, D(2026, 12, 1, 9, 59))
    ok("Di 01.12. 09:59 -> 2,98 Std., nicht ueberfaellig", not s["ueberfaellig"] and s["grenze_std"] == 3, s)
    m = lp.stille_pruefen(db, D(2026, 12, 1, 10, 5))
    ok("Di 01.12. 10:05 -> Telegram (3 Std. ab Exporttag)", m and "November 2026" in m, m)
    leeren()
    lp.gemeldet(db, "TESTPC", jetzt=D(2026, 12, 15, 22))          # Di 15.12. 22:00, letzter Stundenlauf
    s = lp.status(db, D(2026, 12, 16, 11, 5))
    ok("Mi 16.12. (November noch offen) -> 24-Std.-Regel statt 3 Std.", s["phase"] == "2026-11" and s["grenze_std"] == 24 and not s["ueberfaellig"], s)
    ok("Mi 16.12. 11:05 -> keine Telegram", lp.stille_pruefen(db, D(2026, 12, 16, 11, 5)) is None)
    leeren()
    lp.gemeldet(db, "TESTPC", jetzt=D(2026, 11, 23, 12))          # Mo 23.11. 12:00
    ok("Tageslauf: Di 24.11. 11:59 -> still", lp.stille_pruefen(db, D(2026, 11, 24, 11, 59)) is None)
    lp.gemeldet(db, "TESTPC", jetzt=D(2026, 11, 27, 12))          # Fr 27.11. 12:00
    ok("Tageslauf Fr 12:00 -> Mo 30.11. 11:05: 23 Werktagsstd. -> still", lp.stille_pruefen(db, D(2026, 11, 30, 11, 5)) is None)
    m = lp.stille_pruefen(db, D(2026, 11, 30, 12, 5))
    ok("Mo 30.11. 12:05 ohne Tageslauf -> Telegram (24 Werktagsstd.)", m and "über 24 Std. an Werktagen" in m, m)

    print("== Fehler entprellen (6 Std.)")
    leeren(); gesendet.clear()
    ok("Fehler A -> Telegram", lp.fehler(db, "TESTPC", "Datei X: 503", jetzt=D(2026, 11, 26, 8)))
    ok("Fehler A 1 Std. spaeter -> keine Telegram", not lp.fehler(db, "TESTPC", "Datei X: 503", jetzt=D(2026, 11, 26, 9)))
    ok("Fehler B -> Telegram", lp.fehler(db, "TESTPC", "Datei Y: 413", jetzt=D(2026, 11, 26, 9)))
    ok("Fehler A nach 6 Std. -> wieder Telegram", lp.fehler(db, "TESTPC", "Datei X: 503", jetzt=D(2026, 11, 26, 14, 1)))
    ok("Text 'Lohnabrechnung-Upload fehlgeschlagen (TESTPC): ...'", gesendet[0] == "⚠️ Lohnabrechnung-Upload fehlgeschlagen (TESTPC): Datei X: 503", gesendet[0])
    ok("Fehler zaehlt als Lebenszeichen + letzter Fehler gemerkt", lp.lesen(db)["zuletzt"].startswith("2026-11-26T14:01") and lp.lesen(db)["letzter_fehler"]["text"] == "Datei X: 503")

    print("== Vollstaendig (einmal je Monat)")
    from app.services import monatsabschluss as ma
    st = ma.lohnabrechnungen_stand(db, 2026, 10)
    gesendet.clear()
    m = lp.komplett_melden(db, 2026, 10)
    if st["komplett"]:
        ok(f"Oktober komplett ({st['da']}/{st['erwartet']}) -> Telegram", m == f"📄 Lohnabrechnungen Oktober 2026: {st['da']} von {st['erwartet']} da", m)
        ok("zweites Mal -> keine Telegram", lp.komplett_melden(db, 2026, 10) is None)
    else:
        ok(f"Oktober unvollstaendig ({st['da']}/{st['erwartet']}) -> keine Telegram", m is None)
    st11 = ma.lohnabrechnungen_stand(db, 2026, 11)
    ok(f"November ({st11['da']}/{st11['erwartet']}) unvollstaendig -> keine Telegram", lp.komplett_melden(db, 2026, 11) is None)

    print("== Schnittstellen (ueber https://dev.seda.de, Telegram auf DEV nicht eingerichtet)")
    leeren()
    key = open("secrets/export_api_key").read().strip()
    H = {"X-Export-Key": key, "X-Rechner": "TESTPC"}
    r = requests.post(f"{BASE}/export/lohn-pc/lebenszeichen", headers=H, json={"rechner": "TESTPC", "version": "2026-11-26",
                      "ordner": {"2026-10": "12 Dateien", "2026-11": "Ordner fehlt"}}, timeout=20)
    ok("Lebenszeichen 200", r.status_code == 200, r.status_code)
    db.expire_all(); z = lp.lesen(db)
    ok("Server merkt Rechner, Zeit, Ordner", z.get("rechner") == "TESTPC" and z.get("ordner", {}).get("2026-11") == "Ordner fehlt" and z.get("version") == "2026-11-26", z)
    r = requests.post(f"{BASE}/export/lohn-pc/lebenszeichen", headers={"X-Export-Key": "falsch"}, json={}, timeout=20)
    ok("falscher Schluessel -> 403", r.status_code == 403)
    r1 = requests.post(f"{BASE}/export/lohn-pc/fehler", headers=H, json={"rechner": "TESTPC", "text": "TEST lohn-pc Fehler 1"}, timeout=20).json()
    r2 = requests.post(f"{BASE}/export/lohn-pc/fehler", headers=H, json={"rechner": "TESTPC", "text": "TEST lohn-pc Fehler 1"}, timeout=20).json()
    ok("Fehler 1: Telegram ja, gleich danach nein", r1.get("telegram") is True and r2.get("telegram") is False, (r1, r2))
    r3 = requests.post(f"{BASE}/export/zeiterfassung/fehler", headers=H, json={"rechner": "TESTPC", "text": "Lohnabrechnung-Upload: TEST lohn-pc alt"}, timeout=20).json()
    ok("altes Skript (zeiterfassung/fehler mit Vorsatz) -> Lohn-Weg", r3.get("telegram") is True, r3)
    n = db.execute(text("""SELECT count(*) FROM audit_log WHERE action = 'lohnabrechnung_upload_fehler' AND details LIKE 'Upload-PC TESTPC: TEST lohn-pc%'""")).scalar()
    ok("Protokoll: alle 3 Fehler drin (auch der unterdrueckte)", n == 3, n)
    ok("alter Weg schreibt KEIN export_fehler", db.execute(text("SELECT count(*) FROM audit_log WHERE action = 'export_fehler' AND details LIKE '%TEST lohn-pc%'")).scalar() == 0)
    r = requests.get(f"{BASE}/export/lohnabrechnungen/2026-11", headers=H, timeout=20)
    ok("Stand-Abfrage 200 + zaehlt als Lebenszeichen", r.status_code == 200)
    tok = subprocess.run(["venv/bin/python", "../tools/dev_token.py", "admin@seda24.de"], capture_output=True, text=True).stdout.strip().splitlines()[-1]
    a = requests.get(f"{BASE}/cockpit/abschluss/2026-10", headers={"Authorization": f"Bearer {tok}"}, timeout=30).json()
    pc = a.get("upload_pc") or {"antwort": str(a)[:200]}
    ok("Monatsabschluss liefert upload_pc (Schritt 3)", pc.get("rechner") == "TESTPC" and pc.get("letzter_fehler", {}).get("text") == "TEST lohn-pc alt" and pc.get("ueberfaellig") is False, pc)
finally:
    db.rollback()
    db.execute(text("DELETE FROM audit_log WHERE action = 'lohnabrechnung_upload_fehler' AND details LIKE 'Upload-PC TESTPC: TEST lohn-pc%'"))
    if alt is None:
        db.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": lp.KEY})
    else:
        db.execute(text("UPDATE app_settings SET value = :v WHERE key = :k"), {"k": lp.KEY, "v": alt})
    db.commit(); db.close()
print("ALLES OK" if not fehler else f"FEHLER: {fehler}")
sys.exit(1 if fehler else 0)
