#!/usr/bin/env python3
import sys
sys.path.append('/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/backend')

from datetime import date, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://seda24_user:SecurePass2025!@localhost/seda24_zeiterfassung"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def cleanup_km_for_date(target_date):
    db = SessionLocal()
    try:
        employees = db.execute(
            text("SELECT DISTINCT employee_id FROM km_daily_entries WHERE date = :dt"),
            {"dt": target_date}
        ).fetchall()

        for (emp_id,) in employees:
            longest = db.execute(
                text("""SELECT id, distance_km, amount
                       FROM km_daily_entries
                       WHERE employee_id = :emp AND date = :dt
                       ORDER BY distance_km DESC LIMIT 1"""),
                {"emp": emp_id, "dt": target_date}
            ).fetchone()

            if not longest:
                continue

            longest_id, longest_km, longest_amount = longest

            # SPEZIALREGEL: Ljubica (5) & Matej (6)
            if emp_id == 5:
                common_objects = db.execute(
                    text("""SELECT DISTINCT object_id FROM km_daily_entries
                           WHERE employee_id = 6 AND date = :dt AND object_id IN (
                               SELECT object_id FROM km_daily_entries WHERE employee_id = 5 AND date = :dt
                           )"""),
                    {"dt": target_date}
                ).fetchall()

                if common_objects:
                    for (obj_id,) in common_objects:
                        db.execute(
                            text("""UPDATE km_daily_entries
                                   SET distance_km = 0, amount = 0, is_billable = false, is_longest_trip = false
                                   WHERE employee_id = 5 AND date = :dt AND object_id = :obj"""),
                            {"dt": target_date, "obj": obj_id}
                        )
                    db.commit()

                    remaining = db.execute(
                        text("""SELECT COUNT(*) FROM km_daily_entries
                               WHERE employee_id = 5 AND date = :dt AND distance_km > 0"""),
                        {"dt": target_date}
                    ).fetchone()[0]

                    if remaining == 0:
                        continue

            # Alle anderen auf 0
            db.execute(
                text("""UPDATE km_daily_entries
                       SET distance_km = 0, amount = 0, is_billable = false, is_longest_trip = false
                       WHERE employee_id = :emp AND date = :dt AND id != :longest_id"""),
                {"emp": emp_id, "dt": target_date, "longest_id": longest_id}
            )

            # Weiteste markieren
            db.execute(
                text("""UPDATE km_daily_entries
                       SET is_billable = true, is_longest_trip = true
                       WHERE id = :longest_id"""),
                {"longest_id": longest_id}
            )

            db.commit()

    except Exception as e:
        print(f"FEHLER {target_date}: {e}")
        db.rollback()
    finally:
        db.close()

# GANZER JANUAR
start = date(2026, 1, 1)
end = date(2026, 1, 31)
current = start
while current <= end:
    print(f"Bereinige {current}...")
    cleanup_km_for_date(current)
    current += timedelta(days=1)

print("✅ JANUAR FERTIG!")
