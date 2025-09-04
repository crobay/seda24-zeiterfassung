#!/usr/bin/env python3
"""Debug-Version um zu sehen was los ist"""

import sys
sys.path.append('/root/zeiterfassung/backend')

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import User, Employee, Schedule, TimeEntry
import os
from dotenv import load_dotenv

load_dotenv('/root/zeiterfassung/backend/.env')

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def debug_check():
    db = SessionLocal()
    
    print("="*60)
    print("DEBUG AUTO-STEMPELUNG")
    print("="*60)
    
    # 1. Aktuelle Zeit
    now = datetime.now()
    weekday = now.isoweekday()
    print(f"\n📅 Jetzt: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Wochentag: {weekday} (1=Mo, 7=So)")
    
    # 2. Kategorie A User
    cat_a_users = db.query(User).filter(User.category == 'A').all()
    print(f"\n👥 Kategorie A User: {len(cat_a_users)}")
    
    for user in cat_a_users:
        print(f"\n--- {user.email} ---")
        
        if not user.employee:
            print("  ❌ Kein Employee-Eintrag!")
            continue
            
        employee = user.employee
        print(f"  ✅ Employee: {employee.first_name} {employee.last_name} (ID: {employee.id})")
        
        # 3. Dienstpläne
        all_schedules = db.query(Schedule).filter(
            Schedule.employee_id == employee.id
        ).all()
        
        print(f"  📋 Alle Dienstpläne: {len(all_schedules)}")
        
        for s in all_schedules:
            print(f"    - Tag {s.weekday}: {s.start_time} - {s.end_time} bei Objekt {s.object_id}")
        
        # 4. Heutiger Dienstplan
        today_schedules = db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.weekday == weekday
        ).all()
        
        if today_schedules:
            print(f"  📍 HEUTE im Dienstplan: JA")
            for s in today_schedules:
                print(f"    - {s.start_time} bis {s.end_time}")
                
                # Zeit-Check
                if s.start_time:
                    # start_time ist ein time Objekt, konvertieren zu datetime
                    start_dt = datetime.combine(now.date(), s.start_time)
                    diff_minutes = (now - start_dt).total_seconds() / 60
                    print(f"    - Start-Differenz: {diff_minutes:.1f} Minuten")
                    
                    if abs(diff_minutes) <= 10:
                        print(f"    ✅ WÜRDE JETZT STEMPELN!")
                    else:
                        print(f"    ⏰ Nicht im 10-Min-Fenster")
        else:
            print(f"  ❌ HEUTE KEIN Dienstplan (Wochentag {weekday})")
        
        # 5. Offene Stempelungen
        open_entries = db.query(TimeEntry).filter(
            TimeEntry.employee_id == employee.id,
            TimeEntry.check_out.is_(None)
        ).all()
        
        print(f"  🕐 Offene Stempelungen: {len(open_entries)}")
        for e in open_entries:
            print(f"    - Check-in: {e.check_in.strftime('%H:%M')} bei Objekt {e.object_id}")
    
    print("\n" + "="*60)
    
    # 6. Nächste Stempel-Zeiten anzeigen
    print("\n🔮 NÄCHSTE AUTO-STEMPEL-ZEITEN:")
    
    for user in cat_a_users:
        if not user.employee:
            continue
            
        schedules = db.query(Schedule).filter(
            Schedule.employee_id == user.employee.id
        ).all()
        
        for s in schedules:
            if s.start_time:
                # Berechne nächsten Zeitpunkt
                start_dt = datetime.combine(now.date(), s.start_time)
                if s.weekday < weekday or (s.weekday == weekday and start_dt < now):
                    # Nächste Woche
                    days_ahead = s.weekday + 7 - weekday
                else:
                    days_ahead = s.weekday - weekday
                    
                next_date = now.date() + timedelta(days=days_ahead)
                next_stamp = datetime.combine(next_date, s.start_time)
                
                if (next_stamp - now).total_seconds() > 0 and (next_stamp - now).days < 2:
                    print(f"  📍 {user.employee.first_name}: {next_stamp.strftime('%a %H:%M')} (in {(next_stamp - now).total_seconds()/3600:.1f}h)")
    
    db.close()

if __name__ == "__main__":
    debug_check()
