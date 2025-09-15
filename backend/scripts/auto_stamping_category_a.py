#!/usr/bin/env python3
"""
SEDA24 Auto-Stempelung für Kategorie A Mitarbeiter
"""

import sys
import os
import random
from datetime import datetime, timedelta, time
import logging
from pathlib import Path

# Füge den Backend-Pfad hinzu
sys.path.append('/root/zeiterfassung/backend')

from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from app.models.models import Employee, User, TimeEntry, Schedule
from dotenv import load_dotenv

# Lade Umgebungsvariablen
load_dotenv('/root/zeiterfassung/backend/.env')

# Logging Setup
log_dir = Path('/root/zeiterfassung/logs')
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/root/zeiterfassung/logs/auto_stamping.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Datenbankverbindung
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_random_variation():
    """Gibt eine zufällige Variation in Minuten zurück (-4 bis +4)"""
    return random.randint(-4, 4)

def time_to_datetime(time_obj, date_obj=None):
    """Konvertiert time Objekt zu datetime"""
    if date_obj is None:
        date_obj = datetime.now().date()
    return datetime.combine(date_obj, time_obj)

def process_category_a():
    """Hauptfunktion"""
    db = SessionLocal()
    try:
        now = datetime.now()
        weekday = now.isoweekday()
        
        logger.info(f"=== Auto-Stempelung läuft um {now.strftime('%Y-%m-%d %H:%M:%S')} ===")
        
        # Hole alle Kategorie A User
        cat_a_users = db.query(User).filter(
            User.category == 'A',
            User.is_active == True
        ).all()
        
        logger.info(f"Gefundene Kategorie A User: {len(cat_a_users)}")
        
        for user in cat_a_users:
            if not user.employee:
                continue
                
            employee = user.employee
            
            # Hole Dienstplan für heute
            schedules = db.query(Schedule).filter(
                Schedule.employee_id == employee.id,
                Schedule.weekday == weekday
            ).all()
            
            if not schedules:
                logger.info(f"Kein Dienstplan für {employee.first_name} {employee.last_name} heute")
                continue
            
            for schedule in schedules:
                # Check-In Zeit prüfen
                if schedule.start_time:
                    start_dt = time_to_datetime(schedule.start_time)
                    time_diff = abs((now - start_dt).total_seconds() / 60)
                    
                    if time_diff <= 10:  # 10 Minuten Fenster
                        # Prüfe ob schon eingestempelt
                        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                        existing = db.query(TimeEntry).filter(
                            TimeEntry.employee_id == employee.id,
                            TimeEntry.check_in >= today_start
                        ).first()
                        
                        if not existing:
                            variation = get_random_variation()
                            check_in_time = now + timedelta(minutes=variation)
                            
                            entry = TimeEntry(
                                employee_id=employee.id,
                                object_id=schedule.object_id,
                                check_in=check_in_time,
                                is_manual_entry=False,
                                notes=f"Auto-Stempelung Kategorie A (Var: {variation:+d}min)"
                            )
                            db.add(entry)
                            db.commit()
                            logger.info(f"✅ Check-In: {employee.first_name} um {check_in_time.strftime('%H:%M')}")
                
                # Check-Out Zeit prüfen
                if schedule.end_time:
                    end_dt = time_to_datetime(schedule.end_time)
                    time_diff = abs((now - end_dt).total_seconds() / 60)
                    
                    if time_diff <= 15:  # 10 Minuten Fenster
                        # Finde offenen Eintrag
                        open_entry = db.query(TimeEntry).filter(
                            TimeEntry.employee_id == employee.id,
                            TimeEntry.check_out.is_(None)
                        ).first()
                        
                        if open_entry:
                            variation = get_random_variation()
                            check_out_time = now + timedelta(minutes=variation)
                            
                            if check_out_time > open_entry.check_in:
                                open_entry.check_out = check_out_time
                                db.commit()
                                logger.info(f"✅ Check-Out: {employee.first_name} um {check_out_time.strftime('%H:%M')}")
        
        logger.info("=== Auto-Stempelung beendet ===\n")
        
    except Exception as e:
        logger.error(f"Fehler: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    process_category_a()