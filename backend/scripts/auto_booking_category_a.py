#!/usr/bin/env python3
import sys
sys.path.append('/root/zeiterfassung/backend')

from datetime import datetime, timedelta
import random
from app.db.database import SessionLocal
from app.models.models import Employee, Schedule, TimeEntry
from sqlalchemy import and_

def auto_book_category_a():
    db = SessionLocal()
    now = datetime.now()
    
    current_weekday = now.weekday()
    if current_weekday != 6:
        current_weekday = current_weekday + 1
    
    print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] Auto-Booking Check...")
    print(f"Wochentag: {current_weekday}, Uhrzeit: {now.strftime('%H:%M')}")
    
    cat_a_employees = db.query(Employee).filter(Employee.tracking_mode == 'A').all()
    
    for emp in cat_a_employees:
        schedules = db.query(Schedule).filter(
            Schedule.employee_id == emp.id,
            Schedule.weekday == current_weekday
        ).all()
        
        for schedule in schedules:
            variation = random.randint(-3, 3)
            target_time = now.replace(hour=schedule.end_time.hour, minute=schedule.end_time.minute, second=0, microsecond=0)
            target_time += timedelta(minutes=variation)
            
            if now >= target_time and now <= target_time + timedelta(minutes=5):
                existing = db.query(TimeEntry).filter(
                    TimeEntry.employee_id == emp.id,
                    TimeEntry.object_id == schedule.object_id,
                    TimeEntry.check_in >= now.replace(hour=0, minute=0, second=0)
                ).first()
                
                if not existing:
                    check_in = now.replace(hour=schedule.start_time.hour, minute=schedule.start_time.minute)
                    entry = TimeEntry(
                        employee_id=emp.id,
                        object_id=schedule.object_id,
                        check_in=check_in,
                        check_out=now,
                        is_manual_entry=True,
                        notes=f"Auto-Booking Kategorie A"
                    )
                    db.add(entry)
                    db.commit()
                    print(f"✅ Auto-Booking: {emp.first_name} {emp.last_name} - {schedule.planned_hours}h")
    
    db.close()
    print("Check abgeschlossen.\n")

if __name__ == "__main__":
    auto_book_category_a()
