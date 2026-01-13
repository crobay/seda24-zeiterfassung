#!/usr/bin/env python3
import sys
sys.path.append('/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/backend')
from datetime import datetime, timedelta
import random
from app.db.database import SessionLocal
from app.models.models import Employee, Schedule, TimeEntry
from sqlalchemy import text
from sqlalchemy import and_

def auto_book_category_a():
    db = SessionLocal()
    now = datetime.now()
    current_weekday = now.weekday()
    
    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] Auto-Booking Check...")
    print(f"Wochentag: {current_weekday}, Uhrzeit: {now.strftime('%H:%M')}")
    
    cat_a_employees = db.query(Employee).filter(Employee.tracking_mode == 'A').all()
    
    for emp in cat_a_employees:
        # Alle Schedules für heute (date-based)
        schedules = db.query(Schedule).filter(
            Schedule.employee_id == emp.id,
            Schedule.date == now.date()
        ).all()
        
        for schedule in schedules:
            # Schicht vorbei?
            end_dt = now.replace(hour=schedule.end_time.hour, minute=schedule.end_time.minute, second=0, microsecond=0)
            
            if now >= end_dt:
                # Gibt es schon einen Eintrag?
                existing = db.query(TimeEntry).filter(
                    TimeEntry.employee_id == emp.id,
                    TimeEntry.object_id == schedule.object_id,
                    TimeEntry.check_in >= now.replace(hour=0, minute=0, second=0)
                ).first()
                
                if not existing:
                    # Kleine Variation
                    start_var = random.randint(-3, 3)
                    end_var = random.randint(0, 2)
                    
                    check_in = now.replace(hour=schedule.start_time.hour, minute=schedule.start_time.minute) + timedelta(minutes=start_var)
                    check_out = end_dt + timedelta(minutes=end_var)
                    
                    entry = TimeEntry(
                        employee_id=emp.id,
                        object_id=schedule.object_id,
                        check_in=check_in,
                        check_out=check_out,
                        hourly_rate=emp.hourly_rate,
                        billed_hours=schedule.planned_hours,
                        is_manual_entry=True,
                        notes=f"Auto-Booking Kategorie A"
                    )
                    db.add(entry)
                    db.commit()
                    print(f"✅ Auto-Booking: {emp.first_name} {emp.last_name} - {schedule.planned_hours}h")

# KM-Eintrag mit direktem SQL erstellen
                    km_dist = db.execute(
                        text("SELECT distance_km FROM km_distances WHERE employee_id = :emp AND object_id = :obj"),
                        {"emp": emp.id, "obj": schedule.object_id}
                    ).fetchone()
                    
                    if km_dist and km_dist[0] > 0:
                        db.execute(
                            text("""INSERT INTO km_daily_entries 
                                    (employee_id, object_id, time_entry_id, date, distance_km, amount, is_billable)
                                    VALUES (:emp, :obj, :te, :dt, :dist, :amt, true)
                                    ON CONFLICT (employee_id, date, object_id) DO NOTHING"""),
                            {
                                "emp": emp.id,
                                "obj": schedule.object_id,
                                "te": entry.id,
                                "dt": now.date(),
                                "dist": km_dist[0],
                                "amt": float(km_dist[0]) * 0.30
                            }
                        )
                        db.commit()
                        print(f"   📍 KM: {km_dist[0]} km")
			
    
    db.close()
    print("Check abgeschlossen.\n")

if __name__ == "__main__":
    auto_book_category_a()
