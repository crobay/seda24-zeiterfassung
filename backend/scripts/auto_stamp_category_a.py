#!/usr/bin/env python3
import sys
import os
sys.path.append('/root/zeiterfassung/backend')

from datetime import datetime, date, timedelta
import random
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Employee, Schedule, TimeEntry
from dotenv import load_dotenv

load_dotenv('/root/zeiterfassung/backend/.env')

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def auto_stamp_category_a():
    """Automatisches Stempeln für Kategorie A Mitarbeiter"""
    db = SessionLocal()
    
    try:
        # Hole alle Kategorie A Mitarbeiter
        category_a_employees = db.query(Employee).filter(
            Employee.tracking_mode == "A"
        ).all()
        
        today = date.today()
        
        for employee in category_a_employees:
            # Hole heutigen Dienstplan
            schedules = db.query(Schedule).filter(
                Schedule.employee_id == employee.id,
                Schedule.date == today
            ).all()
            
            for schedule in schedules:
                # Prüfe ob schon gestempelt
                existing = db.query(TimeEntry).filter(
                    TimeEntry.employee_id == employee.id,
                    TimeEntry.object_id == schedule.object_id,
                    TimeEntry.check_in >= datetime.combine(today, schedule.start_time) - timedelta(hours=1)
                ).first()
                
                if not existing:
                    # Generiere Zeiten mit Variation
                    variation_start = random.randint(3, 6)
                    variation_end = random.randint(3, 6)
                    
                    check_in = datetime.combine(today, schedule.start_time) - timedelta(minutes=variation_start)
                    check_out = datetime.combine(today, schedule.end_time) + timedelta(minutes=variation_end)
                    
                    # Erstelle Eintrag
                    entry = TimeEntry(
                        employee_id=employee.id,
                        object_id=schedule.object_id,
                        check_in=check_in,
                        check_out=check_out,
                        is_manual_entry=True,
                        notes="Auto-Stempelung Kategorie A"
                    )
                    
                    db.add(entry)
                    print(f"Auto-gestempelt: {employee.first_name} {employee.last_name} - {schedule.object_id}")
        
        db.commit()
        print(f"Auto-Stempelung abgeschlossen: {datetime.now()}")
        
    except Exception as e:
        print(f"Fehler: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    auto_stamp_category_a()
