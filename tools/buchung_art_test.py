"""NUR DEV: Cockpit "Buchung nachtragen/bearbeiten" mit Art, Taetigkeit, Satz, Fahrt mit KM (Drazen 25.11.2026).
T9999 an Test-Objekt 25, raeumt selbst auf. Aufruf aus backend/: venv/bin/python ../tools/buchung_art_test.py"""
import json, os, subprocess, sys, urllib.request
from datetime import date, timedelta
sys.path.insert(0, os.getcwd())
API = "http://127.0.0.1:8003/api/v1/cockpit"
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
EMP, OBJ = 50, 25
assert sql(f"SELECT is_test FROM employees WHERE id={EMP}") == "t" and sql(f"SELECT is_test FROM objects WHERE id={OBJ}") == "t"
START = int(sql("SELECT coalesce(max(id),0) FROM time_entries")); START_A = int(sql("SELECT coalesce(max(id),0) FROM audit_log"))
tag = (date.today() - timedelta(days=1)).isoformat()
basic = float(sql(f"SELECT hourly_rate_basic FROM employees WHERE id={EMP}"))
try:
    s, r = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}&art=Sonderreinigung")
    chk("Satz-Anzeige Sonder = MA-Sondersatz, Lohnart 0030", s == 200 and r["satz"] == basic and r["lohnart"] == "0030", r)
    s, r = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}")
    chk("Satz-Anzeige Unterhalt, Lohnart 0001", s == 200 and r["lohnart"] == "0001", r)

    print("Nachtragen: Sonderreinigung, Taetigkeit, Fahrt mit KM")
    s, z = call("POST", "/zeiten", {"employee_id": EMP, "object_id": OBJ, "datum": tag, "kommen": "08:00", "gehen": "10:30",
                                    "art": "Sonderreinigung", "taetigkeit": "Fenster", "fahrt": True, "notes": "Test Art"})
    chk("angelegt", s == 200, z if s != 200 else "")
    i = z["id"]
    row = sql(f"SELECT service_type, hourly_rate, taetigkeit, billed_hours FROM time_entries WHERE id={i}")
    chk("service_type/Satz/Taetigkeit gespeichert", row == f"Sonderreinigung|{basic:.2f}|Fenster|2.5", row)
    chk("KM-Zeile angelegt (Fahrt mit KM)", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "1")
    chk("Dialogdaten: art, taetigkeit, fahrt", z["service_type"] == "Sonderreinigung" and z["taetigkeit"] == "Fenster" and z["fahrt"] is True, {k: z.get(k) for k in ("service_type", "hourly_rate", "taetigkeit", "fahrt", "km")} if isinstance(z, dict) else z)

    print("Bearbeiten: nur Zeiten -> Satz bleibt")
    sql(f"UPDATE time_entries SET hourly_rate = 15.50 WHERE id={i}")   # bewusst gesetzter Satz (wie Ljubica 15,50)
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Sonderreinigung", "taetigkeit": "Fenster", "fahrt": True})
    chk("Satz 15,50 bleibt ohne Art-Wechsel", s == 200 and z["hourly_rate"] == 15.5, z.get("hourly_rate") if s == 200 else z)
    chk("KM unveraendert (1 Zeile)", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "1")

    print("Bearbeiten: Taetigkeit aendern, Fahrt aus")
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Sonderreinigung", "taetigkeit": "Grundreinigung", "fahrt": False})
    chk("Taetigkeit geaendert", s == 200 and z["taetigkeit"] == "Grundreinigung", {k: z.get(k) for k in ("service_type", "hourly_rate", "taetigkeit", "fahrt", "km")} if isinstance(z, dict) else z)
    chk("KM-Zeile entfernt", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "0")
    chk("Protokoll: KM aus", sql(f"SELECT count(*) FROM audit_log WHERE id>{START_A} AND action='km_entry_changed' AND entity_id={i} AND details LIKE 'Fahrt mit KM aus%'") == "1")
    a = sql(f"SELECT old_value, new_value FROM audit_log WHERE id>{START_A} AND action='booking_updated' AND entity_id={i} ORDER BY id DESC LIMIT 1")
    chk("Protokoll booking_updated alt/neu Taetigkeit", '"taetigkeit": "Fenster"' in a and '"taetigkeit": "Grundreinigung"' in a, a[:160])

    print("Bearbeiten: Art -> Unterhaltsreinigung, Fahrt an")
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Unterhaltsreinigung", "taetigkeit": "Grundreinigung", "fahrt": True})
    s2, sz = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}")
    chk("Art Unterhalt, Satz = Unterhaltssatz, Taetigkeit leer", s == 200 and z["service_type"] == "Unterhaltsreinigung" and z["hourly_rate"] == sz["satz"] and not z["taetigkeit"], {k: z.get(k) for k in ("service_type", "hourly_rate", "taetigkeit", "fahrt", "km")} if isinstance(z, dict) else z)
    chk("KM wieder da", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "1")

    print("Zeitnachweis")
    sql(f"UPDATE time_entries SET service_type='Sonderreinigung', taetigkeit='Fenster' WHERE id={i}")
    from app.db.database import SessionLocal
    from app.core.pdf_generator import PDFGenerator
    from app.models.models import Employee
    db = SessionLocal()
    try:
        g, emp = PDFGenerator(db), db.get(Employee, EMP)
        e = g._get_time_entries(EMP, int(tag[:4]), int(tag[5:7]))
        html = g._generate_zeitnachweis_html(emp, e, g._calculate_stats(e, emp), int(tag[:4]), int(tag[5:7]))
    finally:
        db.close()
    chk("Zeitnachweis zeigt 'Sonderreinigung: Fenster'", "Sonderreinigung: Fenster" in html)

    print("Ungueltige Art")
    s, z = call("POST", "/zeiten", {"employee_id": EMP, "object_id": OBJ, "datum": tag, "kommen": "12:00", "gehen": "13:00", "art": "Quatsch"})
    chk("abgelehnt (400)", s == 400, {k: z.get(k) for k in ("service_type", "hourly_rate", "taetigkeit", "fahrt", "km")} if isinstance(z, dict) else z)
finally:
    ids = sql(f"SELECT string_agg(id::text, ',') FROM time_entries WHERE employee_id={EMP} AND id>{START}")
    if ids:
        sql(f"DELETE FROM km_daily_entries WHERE time_entry_id IN ({ids}) OR (employee_id={EMP} AND date='{tag}')")
        sql(f"DELETE FROM time_entries WHERE id IN ({ids})")
    sql(f"DELETE FROM audit_log WHERE id>{START_A} AND employee_id={EMP}")
    print(f"  aufgeraeumt: Buchungen {ids or '-'}")
print(f"== {ok} OK, {bad} FAIL"); sys.exit(1 if bad else 0)
