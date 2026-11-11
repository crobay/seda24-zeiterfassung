#!/usr/bin/env python3
"""
Pruefung nach jedem Deploy (wird von deploy.sh aufgerufen, Exit-Code != 0 bricht ab).

  (a) Precache: alle Bundle-Dateien (assets/) stehen in der PRECACHE-Liste des Service Workers
  (b) Nachtrag Kommen/Gehen/Beides vergessen legt einen Antrag an (Trockentest)
  (c) Stempeln Kommen/Gehen klappt, inkl. Offline-Nachsendung mit client_id (Trockentest)
  (d) Kein SQLite-SQL (datetime('now'), strftime(...) usw.) im Backend-Code
  (e) Token-Verlaengerung /auth/refresh liefert einen neuen Token

Trockentest: Ein temporaerer Test-Mitarbeiter mit Kategorie-C-Zuweisung an Objekt 20 und
Dienstplan wird in EINER Transaktion angelegt, alle Anfragen laufen ueber die echten
API-Routen (FastAPI TestClient), am Ende ROLLBACK. Telegram-Meldungen und Log-Dateien
sind abgeschaltet. Es bleiben keine Daten zurueck (nur Sequenz-Nummern werden verbraucht).

Aufruf:  venv/bin/python scripts/post_deploy_check.py --webroot <dist|httpdocs> [--static-only]
"""
import argparse
import logging
import os
import re
import subprocess
import sys
from datetime import date, datetime, time, timedelta

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

results = []


def check(name, ok, info=""):
    results.append((name, bool(ok), info))
    print(f"  [{'OK ' if ok else 'FEHLER'}] {name}{(' - ' + info) if info else ''}")
    return ok


# ---------------------------------------------------------------- (a) Precache
def check_precache(webroot):
    print("(a) Service-Worker-Precache:", webroot)
    sw_path = os.path.join(webroot, "service-worker.js")
    idx_path = os.path.join(webroot, "index.html")
    if not check("service-worker.js und index.html vorhanden",
                 os.path.isfile(sw_path) and os.path.isfile(idx_path)):
        return
    sw = open(sw_path, encoding="utf-8").read()
    idx = open(idx_path, encoding="utf-8").read()
    m = re.search(r"^const PRECACHE = \[(.*?)\];", sw, re.M | re.S)
    if not check("PRECACHE-Liste gefunden", m):
        return
    precache = set(re.findall(r"'([^']+)'", m.group(1)))
    cache_name = re.search(r"^const CACHE_NAME = '([^']+)';", sw, re.M)
    check("CACHE_NAME pro Deploy gesetzt", cache_name and cache_name.group(1) != "seda24-cache-v1",
          cache_name.group(1) if cache_name else "fehlt")
    assets_dir = os.path.join(webroot, "assets")
    files = sorted("/assets/" + f for f in os.listdir(assets_dir)) if os.path.isdir(assets_dir) else []
    check("Bundle-Dateien vorhanden", files, f"{len(files)} Dateien")
    missing = [f for f in files if f not in precache]
    check("alle Bundle-Dateien im Precache", not missing, ", ".join(missing) or f"{len(files)}/{len(files)}")
    referenced = sorted(set(u.split("?")[0] for u in re.findall(r'(?:src|href)="(/assets/[^"]+)"', idx)))
    check("index.html verweist auf Bundles", referenced, ", ".join(referenced))
    check("alle von index.html geladenen Bundles im Precache",
          referenced and all(r in precache for r in referenced))
    stale = [p for p in precache if not os.path.isfile(os.path.join(webroot, p.lstrip("/")))]
    check("keine veralteten Eintraege im Precache", not stale, ", ".join(stale))
    shell = ["index.html", "offline.html", "manifest.json", "icon-192.png", "icon-512.png"]
    miss_shell = [s for s in shell if not os.path.isfile(os.path.join(webroot, s))]
    check("App-Grundgeruest (SHELL) vorhanden", not miss_shell, ", ".join(miss_shell))
    check("alter Cache wird erst nach vollstaendigem Befuellen geloescht",
          "missing.length === 0" in sw and "cache.addAll(ALL_URLS.map(reload))" in sw)
    try:
        r = subprocess.run(["node", "--check", sw_path], capture_output=True, text=True, timeout=30)
        check("service-worker.js Syntax (node --check)", r.returncode == 0, r.stderr.strip()[:200])
    except FileNotFoundError:
        check("service-worker.js Syntax (node --check)", True, "node nicht gefunden, uebersprungen")


# ---------------------------------------------------------------- (d) SQLite-Reste
SQLITE_PATTERNS = [
    r"datetime\(\s*'now'", r"date\(\s*'now'", r"(?<![.\w])strftime\(\s*'%", r"julianday\(",
    r"'localtime'", r"'unixepoch'", r"INSERT\s+OR\s+(IGNORE|REPLACE)", r"last_insert_rowid",
    r"func\.strftime", r"func\.julianday", r"func\.datetime\(",
]


def check_sqlite():
    print("(d) SQLite-Reste im Backend-Code")
    hits = []
    for root, dirs, files in os.walk(os.path.join(BACKEND, "app")):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            for n, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
                if any(re.search(pat, line, re.I) for pat in SQLITE_PATTERNS):
                    hits.append(f"{os.path.relpath(p, BACKEND)}:{n}")
    check("kein SQLite-SQL in app/", not hits, ", ".join(hits[:10]))


# ---------------------------------------------------------------- (b)(c)(e) Trockentest
def dry_api_tests():
    print("(b)(c)(e) Trockentest ueber die API-Routen (Rollback)")
    # Keine Log-Dateien anfassen (bie2_stempel.log, auth.log), keine Telegram-Meldungen
    logging.FileHandler = lambda *a, **k: logging.NullHandler()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from app.db.database import engine, get_db
    from app.models.models import User, Employee, Schedule, EmployeeObjectAssignment, UserRole
    from app.core.security import create_access_token, get_password_hash
    from app.api.v1.endpoints import auth, time_entries
    import app.services.telegram_bot as tg
    tg.notify_admin = lambda *a, **k: None
    for name in dir(tg):
        if name.startswith(("notify", "send")) and callable(getattr(tg, name)):
            setattr(tg, name, lambda *a, **k: None)
    time_entries.log_bie2 = lambda *a, **k: None

    conn = engine.connect()
    trans = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        email = f"deploycheck-{stamp}@seda.invalid"
        u = User(email=email, password_hash=get_password_hash(os.urandom(16).hex()),
                 role=UserRole.MITARBEITER, category="C", is_active=True, must_change_password=False)
        db.add(u)
        db.flush()
        e = Employee(user_id=u.id, personal_nr=f"TCHK{stamp[-8:]}", first_name="Deploy", last_name="Check",
                     hourly_rate=0.01, tracking_mode="B", is_active=True, enforce_min_duration=True)
        db.add(e)
        db.flush()
        db.add(EmployeeObjectAssignment(employee_id=e.id, object_id=20, is_active=True, tracking_category="C"))
        yday = date.today() - timedelta(days=1)
        db.add(Schedule(employee_id=e.id, object_id=20, date=yday, weekday=yday.weekday(),
                        start_time=time(8, 0), end_time=time(11, 0), planned_hours=3.0, status="normal"))
        db.commit()   # nur Sicherungspunkt freigeben, die aeussere Transaktion bleibt offen (Rollback am Ende)

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/v1/auth")
        app.include_router(time_entries.router, prefix="/api/v1/time-entries")
        app.dependency_overrides[get_db] = lambda: db
        _client = TestClient(app, raise_server_exceptions=False)

        class _Client:
            # Nach einem Serverfehler nur den Sicherungspunkt zuruecksetzen, damit die
            # folgenden Pruefungen unabhaengig weiterlaufen
            def _wrap(self, fn, *a, **k):
                r = fn(*a, **k)
                if r.status_code >= 500:
                    db.rollback()
                return r

            def post(self, *a, **k):
                return self._wrap(_client.post, *a, **k)

            def get(self, *a, **k):
                return self._wrap(_client.get, *a, **k)

        client = _Client()
        h = {"Authorization": f"Bearer {create_access_token(data={'sub': email})}"}
        T = "/api/v1/time-entries"

        def pending(kind):
            return db.execute(__import__("sqlalchemy").text(
                "SELECT count(*) FROM pending_bookings WHERE employee_id=:e AND catch_up_type=:k AND status='offen'"),
                {"e": e.id, "k": kind}).scalar()

        today = date.today().isoformat()
        # (b) Kommen vergessen (mit Gehen-Zeit) -> Antrag
        r = client.post(f"{T}/catch-up", headers=h, json={"object_id": 20, "catch_up_type": "kommen_vergessen",
                        "date": today, "time": "06:00", "time_end": "07:00", "reason": "technisch",
                        "notes": "deploy-check"})
        check("Nachtrag 'Kommen vergessen' -> Antrag", r.status_code == 200 and pending("kommen_vergessen") == 1,
              f"HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
        # (b) Beides vergessen -> Antrag
        body = {"object_id": 20, "catch_up_type": "beides_vergessen", "date": today,
                "time": "09:00", "time_end": "10:30", "reason": "technisch", "notes": "deploy-check"}
        r = client.post(f"{T}/catch-up", headers=h, json=body)
        check("Nachtrag 'Beides vergessen' -> Antrag", r.status_code == 200 and pending("beides_vergessen") == 1,
              f"HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
        r = client.post(f"{T}/catch-up", headers=h, json=body)
        check("Doppelter Nachtrag innerhalb 60 s abgewiesen (PostgreSQL-Zeitpruefung)",
              r.status_code == 400 and "bereits" in r.text and pending("beides_vergessen") == 1,
              f"HTTP {r.status_code}")

        # (c) KOMMEN wie aus der Offline-Queue (client_id + Handy-Zeit von gestern 08:00)
        cid_in = f"chk-{stamp}-in"
        ts_in = datetime.combine(yday, time(8, 0)).isoformat()
        r = client.post(f"{T}/check-in", headers=h, json={"object_id": 20, "notes": "Bie2 Kommen",
                        "client_id": cid_in, "client_timestamp": ts_in})
        ok_in = r.status_code == 200 and r.json().get("check_in", "").startswith(ts_in[:16])
        check("Stempeln KOMMEN (offline nachgesendet, Handy-Zeit uebernommen)", ok_in,
              f"HTTP {r.status_code} {r.text[:120] if not ok_in else ''}")
        entry_id = r.json().get("id") if r.status_code == 200 else None
        r = client.post(f"{T}/check-in", headers=h, json={"object_id": 20, "client_id": cid_in,
                        "client_timestamp": ts_in})
        check("KOMMEN doppelt gesendet -> kein zweiter Eintrag",
              r.status_code == 200 and r.json().get("id") == entry_id, f"HTTP {r.status_code}")

        # (b) Gehen vergessen (offene Schicht) -> Antrag
        r = client.post(f"{T}/catch-up", headers=h, json={"object_id": 20, "catch_up_type": "gehen_vergessen",
                        "date": yday.isoformat(), "time": "11:00", "reason": "technisch", "notes": "deploy-check"})
        check("Nachtrag 'Gehen vergessen' -> Antrag", r.status_code == 200 and pending("gehen_vergessen") == 1,
              f"HTTP {r.status_code} {r.text[:120] if r.status_code != 200 else ''}")

        # (c) GEHEN wie aus der Offline-Queue
        cid_out = f"chk-{stamp}-out"
        ts_out = datetime.combine(yday, time(11, 0)).isoformat()
        r = client.post(f"{T}/check-out", headers=h, json={"client_id": cid_out, "client_timestamp": ts_out})
        ok_out = (r.status_code == 200 and r.json().get("id") == entry_id
                  and (r.json().get("check_out") or "").startswith(ts_out[:16])
                  and float(r.json().get("billed_hours") or 0) > 0)
        check("Stempeln GEHEN (offline nachgesendet), Stunden berechnet", ok_out,
              f"HTTP {r.status_code} billed={r.json().get('billed_hours') if r.status_code == 200 else r.text[:120]}")
        r = client.post(f"{T}/check-out", headers=h, json={"client_id": cid_out, "client_timestamp": ts_out})
        check("GEHEN doppelt gesendet -> kein Fehler", r.status_code == 200, f"HTTP {r.status_code}")

        # (e) Token verlaengern
        r = client.post("/api/v1/auth/refresh", headers=h)
        ok_ref = r.status_code == 200 and r.json().get("access_token")
        check("Token-Verlaengerung /auth/refresh", ok_ref, f"HTTP {r.status_code}")
        if ok_ref:
            r2 = client.get(f"{T}/my-catchups", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
            check("neuer Token wird akzeptiert", r2.status_code == 200, f"HTTP {r2.status_code}")
    except Exception as ex:
        check("Trockentest ohne Ausnahme", False, repr(ex)[:300])
    finally:
        db.close()
        trans.rollback()
        conn.close()
    # Nachweis: nichts zurueckgeblieben
    from sqlalchemy import text
    with engine.connect() as c:
        left = c.execute(text("SELECT count(*) FROM users WHERE email LIKE 'deploycheck-%@seda.invalid'")).scalar()
    check("Rollback: keine Testdaten zurueckgeblieben", left == 0, f"{left} Test-Benutzer")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webroot", required=True)
    ap.add_argument("--static-only", action="store_true", help="nur (a) Precache")
    a = ap.parse_args()
    print(f"=== Post-Deploy-Pruefung {datetime.now():%d.%m.%Y %H:%M:%S} ===")
    check_precache(a.webroot)
    if not a.static_only:
        check_sqlite()
        dry_api_tests()
    failed = [r for r in results if not r[1]]
    print(f"=== {len(results) - len(failed)}/{len(results)} OK ===")
    if failed:
        print("FEHLGESCHLAGEN:")
        for n, _, i in failed:
            print(f"  - {n}: {i}")
        sys.exit(1)


if __name__ == "__main__":
    main()
