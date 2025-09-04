#!/usr/bin/env python3
# Datei: /root/zeiterfassung/backend/scripts/create_test_schedules.py

import sys
import os
sys.path.append('/root/zeiterfassung/backend')

from datetime import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Employee, Schedule, User
from app.db.database import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def create_test_schedules():
    db = SessionLocal()
    
    # Erst alle alten Schedules löschen
    db.query(Schedule).delete()
    
    # Mitarbeiter-IDs holen
    drazen = db.query(Employee).join(User).filter(User.email == 'dsertic@sertic.de').first()
    andy = db.query(Employee).join(User).filter(User.email == 'andreas.frosch@seda24.de').first()
    sonja = db.query(Employee).join(User).filter(User.email == 'sonja@seda24.de').first()
    ruza = db.query(Employee).join(User).filter(User.email == 'ruzica.sertic@seda24.de').first()
    
    test_schedules = [
        # DRAZEN (Kategorie A) - Objektleiter
        # Montag: SEDA Zentrale 15-18 Uhr (3h)
        Schedule(employee_id=drazen.id, object_id=1, weekday=0, 
                start_time=time(15,0), end_time=time(18,0), planned_hours=3.0),
        # Dienstag: Lidl 6-10 Uhr (4h)
        Schedule(employee_id=drazen.id, object_id=3, weekday=1,
                start_time=time(6,0), end_time=time(10,0), planned_hours=4.0),
        # Mittwoch: Polytec 17-20 Uhr (3h)
        Schedule(employee_id=drazen.id, object_id=13, weekday=2,
                start_time=time(17,0), end_time=time(20,0), planned_hours=3.0),
        # Donnerstag: SEDA Zentrale 8-12 Uhr (4h)
        Schedule(employee_id=drazen.id, object_id=1, weekday=3,
                start_time=time(8,0), end_time=time(12,0), planned_hours=4.0),
        # Freitag: Metalicone 14-19 Uhr (5h)
        Schedule(employee_id=drazen.id, object_id=6, weekday=4,
                start_time=time(14,0), end_time=time(19,0), planned_hours=5.0),
        
        # ANDY (Kategorie B) - Erledigt-Button
        # Montag: Huber Iffezheim 19-22 Uhr (3h)
        Schedule(employee_id=andy.id, object_id=8, weekday=0,
                start_time=time(19,0), end_time=time(22,0), planned_hours=3.0),
        # Mittwoch: Huber Iffezheim 19-22 Uhr (3h)
        Schedule(employee_id=andy.id, object_id=8, weekday=2,
                start_time=time(19,0), end_time=time(22,0), planned_hours=3.0),
        # Freitag: Huber Iffezheim 18-21 Uhr (3h)
        Schedule(employee_id=andy.id, object_id=8, weekday=4,
                start_time=time(18,0), end_time=time(21,0), planned_hours=3.0),
        
        # SONJA (Kategorie C) - Normal mit GPS
        # Samstag: Rytec 12-14 Uhr (2h)
        Schedule(employee_id=sonja.id, object_id=16, weekday=5,
                start_time=time(12,0), end_time=time(14,0), planned_hours=2.0),
        # Sonntag: Rytec 12-14 Uhr (2h)
        Schedule(employee_id=sonja.id, object_id=16, weekday=6,
                start_time=time(12,0), end_time=time(14,0), planned_hours=2.0),
        
        # RUZA (Kategorie C) - Normal
        # Montag-Freitag: Lidl 6-8 Uhr (2h)
        Schedule(employee_id=ruza.id, object_id=3, weekday=0,
                start_time=time(6,0), end_time=time(8,0), planned_hours=2.0),
        Schedule(employee_id=ruza.id, object_id=3, weekday=1,
                start_time=time(6,0), end_time=time(8,0), planned_hours=2.0),
        Schedule(employee_id=ruza.id, object_id=3, weekday=2,
                start_time=time(6,0), end_time=time(8,0), planned_hours=2.0),
        Schedule(employee_id=ruza.id, object_id=3, weekday=3,
                start_time=time(6,0), end_time=time(8,0), planned_hours=2.0),
        Schedule(employee_id=ruza.id, object_id=3, weekday=4,
                start_time=time(6,0), end_time=time(8,0), planned_hours=2.0),
    ]
    
    for schedule in test_schedules:
        db.add(schedule)
    
    # Kategorien setzen
    drazen.category = 'A'
    andy.category = 'B'
    sonja.category = 'C'
    ruza.category = 'C'
    
    db.commit()
    
    print("✅ Test-Dienstpläne erstellt:")
    print(f"  - Drazen (A): Mo-Fr verschiedene Objekte")
    print(f"  - Andy (B): Mo,Mi,Fr Huber Iffezheim")
    print(f"  - Sonja (C): Sa,So Rytec")
    print(f"  - Ruza (C): Mo-Fr Lidl morgens")
    
    db.close()

if __name__ == "__main__":
    create_test_schedules()
