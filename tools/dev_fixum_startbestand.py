"""NUR DEV: Startbestand der Vorlage (Fixum) aus der LIVE-Planung KW 48/2026 (Schichten 2000-2022, Drazen 18.11.2026)
ueber denselben Weg wie das Haekchen "fix" (plan_vorlage.fix_setzen, mit Aenderungsprotokoll).
- Matej D0021 und Ljubica D0004 samstags: alle 2 Wochen ("lange Woche": Sa 28.11. ja, 05.12. nein).
- NICHT fix: Ruzica Do 26.11. Lidl (2023, einmalig zusaetzlich), Andreas (kein fester Termin).
- Ruzica Sonntage: nicht in der Vorlage - dafuer gibt es die eigene Sonntags-Automatik (ab 01.01.2027).
Aufruf (aus backend/): venv/bin/python ../tools/dev_fixum_startbestand.py
"""
import os
import sys

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv  # noqa: E402
load_dotenv(".env")
assert "dev_cockpit" in os.environ["DATABASE_URL"], "nur DEV"
from sqlalchemy import text  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.services import plan_vorlage as pv  # noqa: E402

db = SessionLocal()
admin = db.execute(text("SELECT id FROM users WHERE email = 'admin@seda24.de'")).scalar()
rows = db.execute(text("""SELECT s.id, s.date, e.personal_nr FROM schedules s JOIN employees e ON e.id = s.employee_id
                          WHERE s.id BETWEEN 2000 AND 2022 AND s.date BETWEEN '2026-11-23' AND '2026-11-29'
                          ORDER BY s.date, s.start_time""")).mappings().all()
for r in rows:
    zwei = r["personal_nr"] in ("D0021", "D0004") and r["date"].weekday() == 5
    x = pv.fix_setzen(db, r["id"], True, zwei, admin)
    print(f"  {r['date']:%a %d.%m.} {r['personal_nr']} Schicht {r['id']} -> Vorlage {x['vorlage_id']} ({x['rhythmus']})")
n = db.execute(text("SELECT count(*) FROM master_schedule_entries WHERE coalesce(is_active, true)")).scalar()
print(f"Vorlage aktiv: {n} Eintraege")
db.close()
