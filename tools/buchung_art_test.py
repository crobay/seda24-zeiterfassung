"""NUR DEV: Cockpit "Buchung nachtragen/bearbeiten" mit Art (4 Werte), Satz (ueberschreibbar), Sondersatz, Fahrt mit KM (Drazen 25.11.2026 12:20).
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
TMP_M, TMP_S = [], []
F = lambda z: {k: z.get(k) for k in ("service_type", "hourly_rate", "fahrt", "km")} if isinstance(z, dict) else z
try:
    for art in ("Grundreinigung", "Sonderreinigung", "Fensterreinigung"):
        s, r = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}&art={art}")
        chk(f"Vorbelegung {art} = MA-Sondersatz, Lohnart 0030", s == 200 and r["satz"] == basic and r["lohnart"] == "0030", r)
    s, r = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}")
    chk("Vorbelegung Unterhalt, Lohnart 0001", s == 200 and r["lohnart"] == "0001", r)

    print("Sondersatz im Cockpit beim Mitarbeiter")
    s, r = call("PUT", f"/mitarbeiter/{EMP}/sondersatz", {"sondersatz": "17,25"})
    chk("Sondersatz 17,25 gespeichert", s == 200 and sql(f"SELECT hourly_rate_basic FROM employees WHERE id={EMP}") == "17.25", r)
    s, r = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}&art=Grundreinigung")
    chk("Vorbelegung folgt dem Sondersatz", r.get("satz") == 17.25, r)
    s, r = call("GET", f"/mitarbeiter/{EMP}")
    chk("Stammblatt zeigt Sondersatz", r["stamm"].get("sondersatz") == 17.25, r["stamm"].get("sondersatz"))
    chk("Protokoll Sondersatz", sql(f"SELECT count(*) FROM audit_log WHERE id>{START_A} AND entity_type='employee' AND entity_id={EMP} AND details LIKE 'Sondersatz%'") == "1")
    s, r = call("PUT", f"/mitarbeiter/{EMP}/sondersatz", {"sondersatz": "abc"})
    chk("Sondersatz ungueltig -> 400", s == 400, r)
    sql(f"UPDATE employees SET hourly_rate_basic = {basic} WHERE id={EMP}")

    print("Nachtragen: Sonderreinigung mit eigenem Satz 15,50 + Fahrt mit KM")
    s, z = call("POST", "/zeiten", {"employee_id": EMP, "object_id": OBJ, "datum": tag, "kommen": "08:00", "gehen": "10:30",
                                    "art": "Sonderreinigung", "stundensatz": "15,50", "fahrt": True, "notes": "Test Art"})
    chk("angelegt", s == 200, z if s != 200 else "")
    i = z["id"]
    row = sql(f"SELECT service_type, hourly_rate, billed_hours FROM time_entries WHERE id={i}")
    chk("Art + eigener Satz gespeichert", row == "Sonderreinigung|15.50|2.5", row)
    chk("KM-Zeile angelegt (Fahrt mit KM)", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "1")
    chk("Bearbeiten-Daten: Art, Satz, Fahrt", z["service_type"] == "Sonderreinigung" and z["hourly_rate"] == 15.5 and z["fahrt"] is True, F(z))

    print("Bearbeiten: nur Zeiten -> eigener Satz bleibt")
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Sonderreinigung", "fahrt": True})
    chk("Satz 15,50 bleibt ohne Art-Wechsel", s == 200 and z["hourly_rate"] == 15.5, F(z))
    chk("KM unveraendert (1 Zeile)", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "1")

    print("Bearbeiten: Art -> Fensterreinigung (Vorbelegung), Fahrt aus")
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Fensterreinigung", "fahrt": False})
    chk("Fensterreinigung mit Sondersatz", s == 200 and z["service_type"] == "Fensterreinigung" and z["hourly_rate"] == basic, F(z))
    chk("KM-Zeile entfernt", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "0")
    chk("Protokoll: KM aus", sql(f"SELECT count(*) FROM audit_log WHERE id>{START_A} AND action='km_entry_changed' AND entity_id={i} AND details LIKE 'Fahrt mit KM aus%'") == "1")
    a = sql(f"SELECT old_value, new_value FROM audit_log WHERE id>{START_A} AND action='booking_updated' AND entity_id={i} ORDER BY id DESC LIMIT 1")
    chk("Protokoll booking_updated alt/neu Art + Satz", '"Sonderreinigung"' in a and '"Fensterreinigung"' in a and "15.5" in a, a[:200])

    print("Bearbeiten: eigener Satz 18,00 ohne Art-Wechsel")
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Fensterreinigung", "stundensatz": "18", "fahrt": False})
    chk("eigener Satz 18 gespeichert", s == 200 and z["hourly_rate"] == 18.0, F(z))
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Fensterreinigung", "stundensatz": "500"})
    chk("Satz 500 abgelehnt (400)", s == 400, z)

    print("Bearbeiten: Art -> Unterhaltsreinigung, Fahrt an")
    s, z = call("PUT", f"/zeiten/{i}", {"datum": tag, "kommen": "08:00", "gehen": "11:00", "art": "Unterhaltsreinigung", "fahrt": True})
    s2, sz = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}")
    chk("Art Unterhalt, Satz = Unterhaltssatz", s == 200 and z["service_type"] == "Unterhaltsreinigung" and z["hourly_rate"] == sz["satz"], F(z))
    chk("KM wieder da", sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={i}") == "1")

    print("Zeitnachweis + Lohnsplit")
    sql(f"UPDATE time_entries SET service_type='Grundreinigung' WHERE id={i}")
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
    chk("Zeitnachweis zeigt die Art 'Grundreinigung'", "Grundreinigung</small>" in html)

    print("Vorbelegung Kommen/Gehen beim Nachtragen (Dienstplan -> Zuweisung -> Objekt-Standard)")
    Z = lambda o, d: call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={o}&datum={d}")[1].get("zeit")
    z = Z(14, "2026-12-05")
    chk("Objekt-Standard je Wochentag (Steuerberater Sa 09-15)", z and (z["kommen"], z["gehen"], z["quelle"]) == ("09:00", "15:00", "objekt"), z)
    z = Z(7, "2026-12-07")
    chk("Objekt-Zeit (JU_RA Mo 15-18)", z and (z["kommen"], z["gehen"], z["quelle"]) == ("15:00", "18:00", "objekt"), z)
    TMP_M.append(sql(f"""INSERT INTO master_schedule_entries (employee_id, object_id, weekday, start_time, end_time, planned_hours, is_active, rhythm)
                         VALUES ({EMP}, 14, 5, '08:00', '12:00', 4, true, 'weekly') RETURNING id""").split()[0])
    z = Z(14, "2026-12-05")
    chk("Zuweisung (Vorlage) vor Objekt-Standard", z and (z["kommen"], z["gehen"], z["quelle"]) == ("08:00", "12:00", "zuweisung"), z)
    TMP_S.append(sql(f"""INSERT INTO schedules (employee_id, object_id, date, start_time, end_time, status)
                         VALUES ({EMP}, 14, '2026-12-05', '10:00', '11:30', 'normal') RETURNING id""").split()[0])
    z = Z(14, "2026-12-05")
    chk("Dienstplan vor Zuweisung (+ Schicht-Id)", z and (z["kommen"], z["gehen"], z["quelle"]) == ("10:00", "11:30", "dienstplan") and str(z.get("schedule_id")) == TMP_S[0], z)
    sql(f"UPDATE schedules SET status = 'krank' WHERE id = {TMP_S[0]}")
    z = Z(14, "2026-12-05")
    chk("Krank-Schicht zaehlt nicht", z and z["quelle"] == "zuweisung", z)

    print("Fahrt mit KM beim Nachtragen")
    s, r = call("GET", "/zeiten-satz?employee_id=4&object_id=20")
    chk("Ruzica (D0002) ohne KM-Berechtigung", r.get("km_berechtigt") is False, r.get("km_berechtigt"))
    s, r = call("GET", f"/zeiten-satz?employee_id={EMP}&object_id={OBJ}")
    chk("T9999 mit KM-Berechtigung", r.get("km_berechtigt") is True, r.get("km_berechtigt"))
    s, z = call("POST", "/zeiten", {"employee_id": EMP, "object_id": OBJ, "datum": tag, "kommen": "14:00", "gehen": "15:00"})
    chk("ohne Angabe: Fahrt mit KM an", s == 200 and sql(f"SELECT count(*) FROM km_daily_entries WHERE time_entry_id={z['id']}") == "1", F(z))

    print("Ungueltige Art")
    s, z = call("POST", "/zeiten", {"employee_id": EMP, "object_id": OBJ, "datum": tag, "kommen": "12:00", "gehen": "13:00", "art": "Quatsch"})
    chk("abgelehnt (400)", s == 400, z)
    chk("Spalte taetigkeit gibt es nicht mehr", sql("SELECT count(*) FROM information_schema.columns WHERE table_name='time_entries' AND column_name='taetigkeit'") == "0")
finally:
    for i_ in TMP_S:
        sql(f"DELETE FROM schedules WHERE id={i_}")
    for i_ in TMP_M:
        sql(f"DELETE FROM master_schedule_entries WHERE id={i_}")
    ids = sql(f"SELECT string_agg(id::text, ',') FROM time_entries WHERE employee_id={EMP} AND id>{START}")
    if ids:
        sql(f"DELETE FROM km_daily_entries WHERE time_entry_id IN ({ids}) OR (employee_id={EMP} AND date='{tag}')")
        sql(f"DELETE FROM time_entries WHERE id IN ({ids})")
    sql(f"UPDATE employees SET hourly_rate_basic = {basic} WHERE id={EMP}")
    sql(f"DELETE FROM audit_log WHERE id>{START_A} AND employee_id={EMP}")
    print(f"  aufgeraeumt: Buchungen {ids or '-'}")
print(f"== {ok} OK, {bad} FAIL"); sys.exit(1 if bad else 0)
