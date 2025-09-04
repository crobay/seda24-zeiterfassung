#!/usr/bin/env python3
import sys
import os
import random
from datetime import datetime, timedelta

sys.path.append('/root/zeiterfassung/backend')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Employee, User, TimeEntry, Schedule
from dotenv import load_dotenv

load_dotenv('/root/zeiterfassung/backend/.env')

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

def auto_stamp():
    db = Session()
    
    now = datetime.now()
    today = now.date()
    weekday = now.isoweekday()
    
    # Hole Kategorie A User
    cat_a_users = db.query(User).filter(
        User.category == 'A',
        User.is_active == True
    ).all()
    
    for user in cat_a_users:
        if not user.employee:
            continue
            
        employee = user.employee
        
        # Dienstplan heute
        schedules = db.query(Schedule).filter(
            Schedule.employee_id == employee.id,
            Schedule.weekday == weekday
        ).all()
        
        for schedule in schedules:
            # Check ob schon gestempelt
            existing = db.query(TimeEntry).filter(
                TimeEntry.employee_id == employee.id,
                TimeEntry.check_in >= datetime.combine(today, datetime.min.time())
            ).first()
            
            if existing:
                continue
            
            # Schicht vorbei?
            if schedule.end_time:
                end_dt = datetime.combine(today, schedule.end_time)
                
                if now >= end_dt or (end_dt - now).seconds < 1800:
                    
                    # KLEINE Variation: 0-2 Min beim Start, 0-1 Min beim Ende
                    start_var = random.randint(0, 2)
                    end_var = random.randint(0, 1)
                    
                    # Stempel mit Variation
                    check_in = datetime.combine(today, schedule.start_time) + timedelta(minutes=start_var)
                    check_out = datetime.combine(today, schedule.end_time) + timedelta(minutes=end_var)
                    
                    # Erstelle Eintrag - SOLLSTUNDEN werden in der Abrechnung verwendet
                    entry = TimeEntry(
                        employee_id=employee.id,
                        object_id=schedule.object_id,
                        check_in=check_in,
                        check_out=check_out,
                        is_manual_entry=False,
                        notes=f"Soll: {schedule.planned_hours:.1f}h"
                    )
                    
                    db.add(entry)
                    db.commit()
                    
                    print(f"✅ {employee.first_name}: {check_in.strftime('%H:%M')} - {check_out.strftime('%H:%M')}")
    
    db.close()

if __name__ == "__main__":
    auto_stamp()
