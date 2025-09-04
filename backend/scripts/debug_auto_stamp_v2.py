#!/usr/bin/env python3
"""Debug V2 - Zeigt genau was passiert"""

import sys
sys.path.append('/root/zeiterfassung/backend')

from datetime import datetime, timedelta
from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from app.models.models import User, Employee, Schedule, TimeEntry
import os
from dotenv import load_dotenv

load_dotenv('/root/zeiterfassung/backend/.env')

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def debug_auto_stamp():
    db = SessionLocal()
    
    print("="*60)
    print("DEBUG AUTO-STEMPEL V2")
    print("="*60)
    
    now = datetime.now()
    weekday = now.isoweekday()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"\n⏰ Aktuelle Zeit: {now.strftime('%H:%M:%S')}")
    print(f"📅 Wochentag: {weekday}")
    
    # Hole Drazen
    user = db.query(User).filter(User.email == 'dsertic@sertic.de').first()
    if not user or not user.employee:
        print("❌ Drazen nicht gefunden!")
        return
        
    employee = user.employee
    print(f"\n👤 Mitarbeiter: {employee.first_name} {employee.last_name}")
    print(f"   Category: {user.category}")
    
    # Dienstplan für heute
    schedules = db.query(Schedule).filter(
        Schedule.employee_id == employee.id,
        Schedule.weekday == weekday
    ).all()
    
    print(f"\n📋 Dienstpläne heute: {len(schedules)}")
    
    for schedule in schedules:
        print(f"\n   Dienstplan ID {schedule.id}:")
        print(f"   - Start: {schedule.start_time}")
        print(f"   - Ende: {schedule.end_time}")
        print(f"   - Objekt: {schedule.object_id}")
        
        # Check-In Logik
        if schedule.start_time:
            start_dt = datetime.combine(now.date(), schedule.start_time)
            time_diff = (now - start_dt).total_seconds() / 60
            
            print(f"\n   CHECK-IN PRÜFUNG:")
            print(f"   - Soll-Zeit: {start_dt.strftime('%H:%M')}")
            print(f"   - Jetzt: {now.strftime('%H:%M')}")
            print(f"   - Differenz: {time_diff:.1f} Minuten")
            
            if abs(time_diff) <= 10:
                print(f"   ✅ Im 10-Minuten-Fenster!")
                
                # Prüfe ob schon eingestempelt heute
                existing = db.query(TimeEntry).filter(
                    TimeEntry.employee_id == employee.id,
                    TimeEntry.check_in >= today_start
                ).all()
                
                print(f"   - Heutige Stempelungen: {len(existing)}")
                
                if existing:
                    print(f"   ❌ BLOCKIERT: Schon {len(existing)} Stempelung(en) heute:")
                    for e in existing:
                        print(f"      • {e.check_in.strftime('%H:%M')} bei Objekt {e.object_id}")
                else:
                    print(f"   ✅ WÜRDE JETZT STEMPELN!")
            else:
                print(f"   ⏰ Nicht im Zeitfenster (>10 Min Differenz)")
        
        # Check-Out Logik
        if schedule.end_time:
            end_dt = datetime.combine(now.date(), schedule.end_time)
            time_diff = (now - end_dt).total_seconds() / 60
            
            print(f"\n   CHECK-OUT PRÜFUNG:")
            print(f"   - Soll-Zeit: {end_dt.strftime('%H:%M')}")
            print(f"   - Differenz: {time_diff:.1f} Minuten")
            
            if abs(time_diff) <= 10:
                print(f"   ✅ Im 10-Minuten-Fenster!")
                
                # Prüfe offene Einträge
                open_entry = db.query(TimeEntry).filter(
                    TimeEntry.employee_id == employee.id,
                    TimeEntry.check_out.is_(None)
                ).first()
                
                if open_entry:
                    print(f"   ✅ Offener Eintrag gefunden von {open_entry.check_in.strftime('%H:%M')}")
                    print(f"   ✅ WÜRDE JETZT AUSSTEMPELN!")
                else:
                    print(f"   ❌ Kein offener Eintrag zum Schließen")
    
    db.close()

if __name__ == "__main__":
    debug_auto_stamp()
