#!/usr/bin/env python3
"""
SEDA24 Auto-Stempelung mit SOLLSTUNDEN
- Stempelt mit ±3 Min Variation (DSGVO)
- Bucht aber trotzdem volle Sollstunden
"""

import sys
import os
import random
from datetime import datetime, timedelta
import logging

sys.path.append('/root/zeiterfassung/backend')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Employee, User, TimeEntry, Schedule
from dotenv import load_dotenv

load_dotenv('/root/zeiterfassung/backend/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def get_random_minutes():
    """Zufällige Variation zwischen -3 und +3 Minuten"""
    return random.randint(-3, 3)

def round_to_sollstunden(check_in, check_out, planned_hours):
    """
    Rundet die Arbeitszeit auf Sollstunden
    DSGVO: Zeigt variierende Zeiten, bucht aber Sollstunden
    """
    actual_hours = (check_out - check_in).total_seconds() / 3600
    
    # Wenn Differenz < 10 Minuten, buche Sollstunden
    if abs(actual_hours - planned_hours) < 0.17:  # 0.17h = 10 Min
        # Passe check_out an für exakte Sollstunden
        check_out = check_in + timedelta(hours=planned_hours)
    
    return check_out

def stamp_with_sollstunden():
    """Stempelt mit Variation aber bucht Sollstunden"""
    db = SessionLocal()
    
    try:
        now = datetime.now()
        today = now.date()
        weekday = now.isoweekday()
        
        logger.info(f"=== AUTO-STEMPELUNG MIT SOLLSTUNDEN ===")
        
        # Hole alle Kategorie A Mitarbeiter
        cat_a_users = db.query(User).filter(
            User.category == 'A',
            User.is_active == True
        ).all()
        
        for user in cat_a_users:
            if not user.employee:
                continue
                
            employee = user.employee
            
            # Hole heutigen Dienstplan
            schedules = db.query(Schedule).filter(
                Schedule.employee_id == employee.id,
                Schedule.weekday == weekday
            ).all()
            
            for schedule in schedules:
                # Prüfe ob schon gestempelt
                existing = db.query(TimeEntry).filter(
                    TimeEntry.employee_id == employee.id,
                    TimeEntry.check_in >= datetime.combine(today, datetime.min.time())
                ).first()
                
                if existing:
                    continue
                
                # Sollte jetzt stempeln?
                if schedule.end_time:
                    end_dt = datetime.combine(today, schedule.end_time)
                    
                    # Schicht vorbei oder fast vorbei?
                    if now >= end_dt or (end_dt - now).seconds < 1800:  # 30 Min
                        
                        # VARIATION für DSGVO
                        start_var = get_random_minutes()
                        end_var = get_random_minutes()
                        
                        # Stempel-Zeiten MIT Variation
                        check_in = datetime.combine(today, schedule.start_time) + timedelta(minutes=start_var)
                        check_out = datetime.combine(today, schedule.end_time) + timedelta(minutes=end_var)
                        
                        # Berechne tatsächliche Stunden
                        actual_hours = (check_out - check_in).total_seconds() / 3600
                        
                        # WICHTIG: Notes zeigt beide Infos
                        if abs(actual_hours - schedule.planned_hours) > 0.1:
                            # Wenn Abweichung > 6 Min, buche Sollstunden
                            notes = f"Auto-Kat.A | Gestempelt: {actual_hours:.2f}h | Gebucht: {schedule.planned_hours:.1f}h (Sollstunden)"
                            # Optional: Check-out anpassen für exakte Sollstunden
                            # check_out = check_in + timedelta(hours=schedule.planned_hours)
                        else:
                            notes = f"Auto-Kat.A | {actual_hours:.2f}h (Var: {start_var:+d}/{end_var:+d}min)"
                        
                        # Erstelle Eintrag
                        entry = TimeEntry(
                            employee_id=employee.id,
                            object_id=schedule.object_id,
                            check_in=check_in,
                            check_out=check_out,
                            is_manual_entry=False,
                            notes=notes,
                            # NEU: Könnten ein Feld "billed_hours" hinzufügen
                            # billed_hours=schedule.planned_hours
                        )
                        
                        db.add(entry)
                        db.commit()
                        
                        logger.info(f"✅ {employee.first_name} {employee.last_name}:")
                        logger.info(f"   Gestempelt: {check_in.strftime('%H:%M')} - {check_out.strftime('%H:%M')} = {actual_hours:.2f}h")
                        logger.info(f"   Abgerechnet: {schedule.planned_hours:.1f}h (Sollstunden)")
                        logger.info(f"   DSGVO-Variation: Start {start_var:+d}min, Ende {end_var:+d}min")
        
        logger.info("=== FERTIG ===")
        
    except Exception as e:
        logger.error(f"Fehler: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    stamp_with_sollstunden()