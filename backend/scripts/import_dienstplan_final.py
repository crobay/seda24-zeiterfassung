#!/usr/bin/env python3
"""
SEDA24 - Dienstplan Import FINAL - Mit korrekten Objekt-IDs
Stand: 30.08.2025
"""

import sys
sys.path.append('/root/zeiterfassung/backend')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import Schedule, Employee, User
from dotenv import load_dotenv
from datetime import time
import os

load_dotenv('/root/zeiterfassung/backend/.env')
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# KORREKTE OBJEKT-IDs aus der Datenbank:
# 1: SEDA24 Zentrale
# 3: Lidl Muggensturmer Str
# 4: Lidl Wochenende
# 5: Enfido Sonnenschein
# 6: Metalicone Muggensturm
# 7: JU_RA Baden-Baden
# 8: Huber Iffezheim
# 9: BAD-Treppen
# 11: Leible Rheinmünster
# 12: Zinsfabrik Baden-Baden
# 13: Polytec Rastatt
# 14: Steuerberater Baden-Baden
# 15: Geiger Malsch
# 16: Rytec Baden-Baden

DIENSTPLAENE = {
    'ruzica.sertic@seda24.de': [  # Ruza D002
        (3, 1, '15:00', '20:00', 5.0),  # Mo: Lidl
        (3, 2, '15:00', '20:00', 5.0),  # Di: Lidl
        (3, 3, '15:00', '20:00', 5.0),  # Mi: Lidl
        (4, 6, '11:00', '13:00', 2.0),  # Sa: Lidl WE
        (15, 6, '13:30', '17:30', 4.0), # Sa: Geiger Malsch
    ],
    
    'ljubica.stjepic@seda24.de': [  # Ljubica D003
        (14, 6, '09:00', '15:00', 6.0),  # Sa: Steuerberater BB
        (13, 6, '16:00', '19:00', 3.0),  # Sa: Polytec
    ],
    
    'matej.stjepic@seda24.de': [  # Matej D004
        (5, 3, '17:30', '20:00', 2.5),   # Mi: Enfido
        (14, 6, '09:00', '15:00', 6.0),  # Sa: Steuerberater BB
        (12, 5, '17:00', '19:30', 2.5),  # Fr: Zinsfabrik
        # TODO: alle 2 Wochen ab KW36:
        # (9, 6, '11:00', '12:30', 1.5),  # Sa: BAD-Treppen 
        # (7, 6, '15:00', '18:00', 3.0),  # Sa: JU_RA
    ],
    
    'eldina.mustafic@seda24.de': [  # Eldina D010
        (3, 1, '15:00', '20:00', 4.0),  # Mo: Lidl (SPEZIAL: 4h statt 5h!)
        (3, 2, '15:00', '20:00', 4.0),  # Di: Lidl (SPEZIAL: 4h statt 5h!)
    ],
    
    'jana.bojko@seda24.de': [  # Jana D013
        (6, 6, '18:00', '20:45', 2.75),  # Sa: Metalicone
    ],
    
    'eliane.dasilvatodaro@seda24.de': [  # Eliane D031
        (9, 1, '11:00', '12:30', 1.5),   # Mo: BAD-Treppen
        (9, 2, '11:00', '12:30', 1.5),   # Di: BAD-Treppen
        (1, 5, '11:30', '17:30', 6.0),   # Fr: SEDA24 Zentrale (war ID 9, ist aber ID 1)
        (12, 5, '17:00', '19:30', 2.5),  # Fr: Zinsfabrik
    ],
    
    'andreas.frosch@seda24.de': [  # Andy D032
        (11, 3, '20:45', '23:45', 3.0),  # Mi: Leible Rheinmünster
        (12, 3, '17:00', '19:30', 2.5),  # Mi: Zinsfabrik
    ],
    
    'sonja@seda24.de': [  # Sonja D034
        (16, 5, '11:00', '13:00', 2.0),  # Fr: Rytec
    ],
}

def import_dienstplan():
    db = Session()
    
    print("=== DIENSTPLAN IMPORT ===\n")
    
    # Lösche alte Dienstpläne
    deleted = db.query(Schedule).delete()
    db.commit()  # Wichtig: Commit nach Delete!
    print(f"Gelöscht: {deleted} alte Dienstpläne\n")
    
    total_imported = 0
    
    for email, plaene in DIENSTPLAENE.items():
        # Hole User und Employee
        user = db.query(User).filter(User.email == email).first()
        
        if not user or not user.employee:
            print(f"❌ {email} - Nicht gefunden!")
            continue
        
        employee = user.employee
        
        for objekt_id, wochentag, start, ende, sollstunden in plaene:
            # Konvertiere Zeit-Strings zu time objects
            start_parts = start.split(':')
            end_parts = ende.split(':')
            
            schedule = Schedule(
                employee_id=employee.id,
                object_id=objekt_id,
                weekday=wochentag,
                start_time=time(int(start_parts[0]), int(start_parts[1])),
                end_time=time(int(end_parts[0]), int(end_parts[1])),
                planned_hours=sollstunden
            )
            db.add(schedule)
            total_imported += 1
        
        print(f"✅ {employee.first_name} {employee.last_name}: {len(plaene)} Einträge")
    
    db.commit()
    
    print(f"\n=== IMPORT ABGESCHLOSSEN ===")
    print(f"Gesamt importiert: {total_imported} Dienstplan-Einträge")
    
    # Zeige Übersicht
    print("\n=== ÜBERSICHT ===")
    
    # Zähle pro Wochentag
    for day in range(1, 8):
        count = db.query(Schedule).filter(Schedule.weekday == day).count()
        day_names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
        print(f"{day_names[day-1]}: {count} Einträge")
    
    db.close()

if __name__ == "__main__":
    import_dienstplan()
