"""NUR DEV: Urlaubstage nach Dienstplan/Vorlage, Feiertage BW zaehlen nie, Urlaubskonten (Drazen 25.11.2026 20:25).
Teil 1 rechnet in einer Transaktion, die zurueckgerollt wird (Test-MA T9999 bekommt dort voruebergehend eine Vorlage).
Teil 2 geht ueber die Urlaubs-API mit T9999 (kein Telegram: T9999 hat keine Chat-ID) und raeumt selbst auf.
Aufruf aus backend/: venv/bin/python ../tools/urlaubstage_test.py"""
import json, os, subprocess, sys, urllib.request
from datetime import date
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(".env")
from sqlalchemy import text
from app.db.database import SessionLocal
from app.services import urlaubstage as ut
from app.services.holidays_bw import is_feiertag_bw

API = "http://127.0.0.1:8003/api/v1/vacation"
TOK = subprocess.run([sys.executable, "../tools/dev_token.py", "admin@seda24.de"], capture_output=True, text=True).stdout.split()[-1]
def sql(q):
    return subprocess.run(["sudo", "-n", "-u", "postgres", "psql", "-d", "dev_cockpit", "-X", "-tA", "-F", "|", "-c", q],
                          capture_output=True, text=True, cwd="/tmp").stdout.strip()
def call(m, p, body=None):
    r = urllib.request.Request(API + p, method=m, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as x:
            return x.status, json.loads(x.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")
ok = bad = 0
def chk(name, cond, info=""):
    global ok, bad
    print(f"  [{'OK ' if cond else 'XX '}] {name}{' - ' + str(info) if info else ''}"); ok += bool(cond); bad += not cond
D = date.fromisoformat
fmt = lambda l: ",".join(f"{d:%d.%m.}" for d in l)
EMP, OBJ = 50, 25
assert sql(f"SELECT is_test FROM employees WHERE id={EMP}") == "t"
assert sql(f"SELECT telegram_chat_id IS NULL FROM employees WHERE id={EMP}") == "t"

print("Feiertage BW 2027")
for d, n in (("2027-05-17", "Pfingstmontag"), ("2027-05-27", "Fronleichnam"), ("2027-05-06", "Christi Himmelfahrt"), ("2027-01-06", "Hl. Drei Koenige")):
    chk(f"{n} {d} ist Feiertag", is_feiertag_bw(D(d)))

db = SessionLocal()
try:
    def vorlage(tage, rhythm="weekly"):
        db.execute(text("DELETE FROM master_schedule_entries WHERE employee_id = :e"), {"e": EMP})
        for w in tage:
            db.execute(text("""INSERT INTO master_schedule_entries (employee_id, object_id, weekday, start_time, end_time, rhythm)
                               VALUES (:e, :o, :w, '09:00', '12:00', :r)"""), {"e": EMP, "o": OBJ, "w": w, "r": rhythm})
    print("Teil 1: Regel 'wie wenn sie arbeitet' (T9999 mit Vorlage, Wochen ohne Dienstplan)")
    vorlage([1, 3])   # Minijob Di + Do
    l = ut.tage(db, EMP, D("2027-04-13"), D("2027-04-15"))
    chk("Minijob Di/Do, Urlaub Di 13.04.-Do 15.04.2027 = 2 Tage (Mi zaehlt nicht)", len(l) == 2, fmt(l))
    l = ut.tage(db, EMP, D("2027-04-12"), D("2027-04-25"))
    chk("Minijob Di/Do, zwei Wochen = 4 Tage", len(l) == 4, fmt(l))
    l = ut.tage(db, EMP, D("2027-05-24"), D("2027-05-28"))
    chk("Minijob Di/Do, Woche mit Fronleichnam (Do 27.05.) = 1 Tag (nur Di)", fmt(l) == "25.05.", fmt(l))
    vorlage([0, 1, 2])   # Teilzeit Mo-Mi
    l = ut.tage(db, EMP, D("2027-04-12"), D("2027-04-18"))
    chk("Teilzeit Mo-Mi, ganze Woche = 3 Tage", len(l) == 3, fmt(l))
    l = ut.tage(db, EMP, D("2027-05-17"), D("2027-05-23"))
    chk("Teilzeit Mo-Mi, Woche mit Pfingstmontag = 2 Tage", fmt(l) == "18.05.,19.05.", fmt(l))
    vorlage([0, 1, 2, 3, 4])   # Vollzeit Mo-Fr
    l = ut.tage(db, EMP, D("2027-04-12"), D("2027-04-18"))
    chk("Vollzeit Mo-Fr, ganze Woche = 5 Tage (Sa/So zaehlen nicht)", len(l) == 5, fmt(l))
    l = ut.tage(db, EMP, D("2027-05-24"), D("2027-05-28"))
    chk("Vollzeit, 24.-28.05.2027 (Fronleichnam) = 4 Tage", fmt(l) == "24.05.,25.05.,26.05.,28.05.", fmt(l))
    l = ut.tage(db, EMP, D("2027-05-17"), D("2027-05-28"))
    chk("Vollzeit, 17.-28.05.2027 (Pfingstmontag + Fronleichnam) = 8 Tage", len(l) == 8, fmt(l))
    l = ut.tage(db, EMP, D("2026-12-21"), D("2027-01-08"))
    chk("Vollzeit, 21.12.2026-08.01.2027 ohne 24./25./26.12. Feiertage, 01.01., 06.01. = 12 Tage",
        len(l) == 12 and D("2026-12-25") not in l and D("2027-01-01") not in l and D("2027-01-06") not in l, fmt(l))
    vorlage([5], "biweekly_even")   # wie Ljubica: Sa alle 2 Wochen (gerade KW)
    l = ut.tage(db, EMP, D("2027-04-05"), D("2027-04-18"))
    chk("Sa alle 2 Wochen, zwei Wochen = 1 Tag", len(l) == 1 and l[0].isocalendar()[1] % 2 == 0, fmt(l))
    db.execute(text("DELETE FROM master_schedule_entries WHERE employee_id = :e"), {"e": EMP})
    l = ut.tage(db, EMP, D("2027-04-12"), D("2027-04-18"))
    chk("ohne Vorlage/Profil/fruehere Schichten: Mo-Fr = 5", len(l) == 5, fmt(l))

    print("Dienstplan schon da: zaehlen nur geplante Tage")
    db.execute(text("""INSERT INTO schedules (employee_id, object_id, weekday, date, start_time, end_time, planned_hours, status)
                       VALUES (:e, :o, 2, '2027-04-14', '09:00', '12:00', 3, 'normal'),
                              (:e, :o, 3, '2027-05-27', '09:00', '12:00', 3, 'normal')"""), {"e": EMP, "o": OBJ})
    vorlage([0, 1, 2, 3, 4])
    l = ut.tage(db, EMP, D("2027-04-12"), D("2027-04-18"))
    chk("Woche im Plan mit nur Mi-Schicht = 1 Tag (Vorlage zaehlt dann nicht)", fmt(l) == "14.04.", fmt(l))
    l = ut.tage(db, EMP, D("2027-05-24"), D("2027-05-28"))
    chk("Schicht am Fronleichnam: Feiertag zaehlt trotzdem nicht", D("2027-05-27") not in l and len(l) == 0, fmt(l))

    print("Echte Mitarbeiter (nur lesen)")
    l = ut.tage(db, 33, D("2027-05-24"), D("2027-05-28"))
    chk("Helena (Vorlage Mo-Fr) 24.-28.05.2027 = 4", len(l) == 4 and D("2027-05-27") not in l, fmt(l))
    l = ut.tage(db, 33, D("2027-05-17"), D("2027-05-28"))
    chk("Helena 17.-28.05.2027 = 8 (bisher 10)", len(l) == 8, fmt(l))
    l = ut.tage(db, 9, D("2027-04-14"), D("2027-04-16"))
    chk("Eliane (Minijob Vorlage Mi/Fr) Mi 14.-Fr 16.04. = 2 (Do zaehlt nicht)", fmt(l) == "14.04.,16.04.", fmt(l))
    l = ut.tage(db, 16, D("2027-05-24"), D("2027-05-28"))
    chk("Drazen (Profil Mo-Fr, keine Vorlage) Fronleichnam-Woche = 4", len(l) == 4, fmt(l))
finally:
    db.rollback(); db.close()
chk("Teil 1 zurueckgerollt (T9999 ohne Vorlage/Schichten)",
    sql(f"SELECT (SELECT count(*) FROM master_schedule_entries WHERE employee_id={EMP}) + (SELECT count(*) FROM schedules WHERE employee_id={EMP})") == "0")

print("Teil 2: API (Admin-Eintrag, Aendern, Konto, Storno) mit T9999")
START_V = int(sql("SELECT coalesce(max(id),0) FROM vacation_requests"))
ENT_VORHER = sql(f"SELECT count(*) FROM vacation_entitlements WHERE employee_id={EMP} AND year=2027")
try:
    s, r = call("POST", "/admin/create-request", {"employee_id": EMP, "start_date": "2027-05-24", "end_date": "2027-05-28", "type": "urlaub"})
    rid = r.get("request_id") if isinstance(r, dict) else None
    chk("Admin-Eintrag 24.-28.05.2027 = 4 Arbeitstage", s == 200 and r["working_days"] == 4 and "4 Arbeitstage" in r["message"], r)
    tg = sql(f"SELECT string_agg(to_char(date,'DD.MM.'), ',' ORDER BY date) FROM schedules WHERE notes='Urlaubsantrag #{rid}'")
    te = sql(f"SELECT string_agg(to_char(check_in,'DD.MM.'), ',' ORDER BY check_in) FROM time_entries WHERE object_id=999 AND notes LIKE '%Urlaubsantrag #{rid} %'")
    chk("Urlaubstage nur 24./25./26./28.05. (Plan)", tg == "24.05.,25.05.,26.05.,28.05.", tg)
    chk("Urlaubsbuchungen nur 24./25./26./28.05., keine am Fronleichnam", te == "24.05.,25.05.,26.05.,28.05.", te)
    s, r = call("GET", "/admin/calendar?year=2027")
    cal = [d["date"] for e in r if e["employee_id"] == EMP for d in e["days"]] if s == 200 else r
    chk("Jahreskalender zeigt dieselben 4 Tage", cal == ["2027-05-24", "2027-05-25", "2027-05-26", "2027-05-28"], cal)

    s, r = call("PUT", "/admin/entitlement", {"employee_id": EMP, "year": 2027, "days_entitled": 10})
    chk("Konto 2027 spaeter angelegt: genehmigte 4 Tage sofort abgezogen", s == 200 and r["days_taken"] == 4 and r["days_remaining"] == 6, r)

    s, r = call("PUT", f"/admin/requests/{rid}", {"start_date": "2027-05-17", "end_date": "2027-05-28"})
    wd = sql(f"SELECT working_days FROM vacation_requests WHERE id={rid}")
    tg = sql(f"SELECT string_agg(to_char(date,'DD.MM.'), ',' ORDER BY date) FROM schedules WHERE notes='Urlaubsantrag #{rid}'")
    te = sql(f"SELECT count(*) FROM time_entries WHERE object_id=999 AND notes LIKE '%Urlaubsantrag #{rid} %'")
    k = sql(f"SELECT days_taken||'/'||days_remaining FROM vacation_entitlements WHERE employee_id={EMP} AND year=2027")
    chk("Aendern auf 17.-28.05. = 8 Tage (ohne Pfingstmontag/Fronleichnam)", s == 200 and wd == "8" and "17.05." not in tg and "27.05." not in tg, f"{wd}: {tg}")
    chk("Aendern: 8 Urlaubsbuchungen, Konto 8 genommen / Rest 2", te == "8" and k == "8/2", f"{te}, {k}")

    s, r = call("PUT", f"/admin/requests/{rid}", {"status": "cancelled"})
    left = sql(f"SELECT (SELECT count(*) FROM schedules WHERE notes='Urlaubsantrag #{rid}') + (SELECT count(*) FROM time_entries WHERE object_id=999 AND notes LIKE '%Urlaubsantrag #{rid} %')")
    k = sql(f"SELECT days_taken||'/'||days_remaining FROM vacation_entitlements WHERE employee_id={EMP} AND year=2027")
    chk("Storno: Urlaubstage + offene Urlaubsbuchungen weg", s == 200 and left == "0", left)
    chk("Storno: Tage zurueck aufs Konto (0 genommen / Rest 10)", k == "0/10", k)
finally:
    sql(f"""DELETE FROM time_entries WHERE employee_id={EMP} AND object_id=999 AND notes LIKE '%Urlaubsantrag #%';
            DELETE FROM schedules WHERE employee_id={EMP} AND notes LIKE 'Urlaubsantrag #%';
            DELETE FROM vacation_requests WHERE employee_id={EMP} AND id>{START_V};""")
    if ENT_VORHER == "0":
        sql(f"DELETE FROM vacation_entitlements WHERE employee_id={EMP} AND year=2027")
chk("aufgeraeumt", sql(f"SELECT count(*) FROM vacation_requests WHERE employee_id={EMP} AND id>{START_V}") == "0")
print(f"\n{ok} OK, {bad} Fehler")
sys.exit(1 if bad else 0)
