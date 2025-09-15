#!/usr/bin/env python3
"""
SEDA24 Auto-Stempelung RÜCKWIRKEND
Stempelt vergangene Arbeitszeiten mit Zufallsvariation (DSGVO)
"""

import sys
import os
import random
from datetime import datetime, timedelta
import logging

sys.path.append('/root/zeiterfassung/backend')

from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from app.models.models import Employee, User, TimeEntry, Schedule
from dotenv import load_dotenv

load_dotenv('/root/zeiterfassung/backend/.env')

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

# DB
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_random_minutes():
    """Zufällige Variation zwischen -4 und +4 Minuten"""
    return random.randint(-4, 4)

def stamp_past_schedule():
    """Stempelt rückwirkend basierend auf Dienstplan"""
    db = SessionLocal()
    
    try:
        now = datetime.now()
        today = now.date()
        weekday = now.isoweekday()
        
        logger.info(f"=== RÜCKWIRKENDE AUTO-STEMPELUNG ===")
        logger.info(f"Heute: {today} (Wochentag {weekday})")
        
        # Hole alle Kategorie A Mitarbeiter
        cat_a_users = db.query(User).filter(
            User.category == 'A',
            User.is_active == True
        ).all()
        
        logger.info(f"Kategorie A Mitarbeiter: {len(cat_a_users)}")
        
        for user in cat_a_users:
            if not user.employee:
                continue
                
            employee = user.employee
            logger.info(f"\nVerarbeite: {employee.first_name} {employee.last_name}")
            
            # Hole heutigen Dienstplan
            schedules = db.query(Schedule).filter(
                Schedule.employee_id == employee.id,
                Schedule.weekday == weekday
            ).all()
            
            if not schedules:
                logger.info(f"  Kein Dienstplan für heute")
                continue
            
            for schedule in schedules:
                # Prüfe ob Arbeitszeit schon vorbei ist
                if schedule.end_time:
                    end_datetime = datetime.combine(today, schedule.end_time)
                    
                    # Ist die Schicht schon vorbei oder fast vorbei?
                    if now >= end_datetime or (end_datetime - now).seconds < 600:  # Innerhalb 10 Min
                        
                        # Prüfe ob schon gestempelt wurde heute
                        existing = db.query(TimeEntry).filter(
                            TimeEntry.employee_id == employee.id,
                            TimeEntry.check_in >= datetime.combine(today, datetime.min.time()),
                            TimeEntry.check_in < datetime.combine(today, datetime.max.time())
                        ).first()
                        
                        if existing:
                            logger.info(f"  Bereits gestempelt heute")
                            continue
                        
                        # RÜCKWIRKEND STEMPELN!
                        start_variation = get_random_minutes()
                        end_variation = get_random_minutes()
                        
                        check_in = datetime.combine(today, schedule.start_time) + timedelta(minutes=start_variation)
                        check_out = datetime.combine(today, schedule.end_time) + timedelta(minutes=end_variation)
                        
                        # Sicherstellen dass check_out nach check_in ist
                        if check_out <= check_in:
                            check_out = check_in + timedelta(hours=1)
                        
                        # Erstelle Zeiteintrag
                        entry = TimeEntry(
                            employee_id=employee.id,
                            object_id=schedule.object_id,
                            check_in=check_in,
                            check_out=check_out,
                            is_manual_entry=False,
                            notes=f"Auto-Stempelung Kat.A (rückwirkend, Var: {start_variation:+d}/{end_variation:+d}min)"
                        )
                        
                        db.add(entry)
                        db.commit()
                        
                        work_hours = (check_out - check_in).seconds / 3600
                        logger.info(f"  ✅ RÜCKWIRKEND GESTEMPELT:")
                        logger.info(f"     Check-in:  {check_in.strftime('%H:%M')} (Soll: {schedule.start_time}, Var: {start_variation:+d}min)")
                        logger.info(f"     Check-out: {check_out.strftime('%H:%M')} (Soll: {schedule.end_time}, Var: {end_variation:+d}min)")
                        logger.info(f"     Stunden: {work_hours:.2f}h bei Objekt {schedule.object_id}")
                    else:
                        time_until = (end_datetime - now).seconds // 60
                        logger.info(f"  Schicht läuft noch {time_until} Minuten")
        
        logger.info(f"\n=== FERTIG ===")
        
    except Exception as e:
        logger.error(f"Fehler: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    stamp_past_schedule()