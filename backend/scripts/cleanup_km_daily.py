#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEDA24 - Taegliche KM-Bereinigung
Laeuft um 23:59 Uhr, setzt alle Fahrten auf 0 km ausser der weitesten.
"""

import sys
sys.path.append('/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/backend')

from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Datenbank-Verbindung
DATABASE_URL = "postgresql://seda24_user:SecurePass2025!@localhost/seda24_zeiterfassung"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def cleanup_km_for_date(target_date):
    """
    Bereinigt KM fuer ein bestimmtes Datum:
    - Findet weiteste Fahrt pro Mitarbeiter
    - Setzt alle anderen auf 0 km
    - Nur weiteste: is_billable = true, is_longest_trip = true
    """
    db = SessionLocal()
    
    try:
        # Hole alle Mitarbeiter die heute gefahren sind
        employees = db.execute(
            text("SELECT DISTINCT employee_id FROM km_daily_entries WHERE date = :dt"),
            {"dt": target_date}
        ).fetchall()
        
        print(f"=== KM-BEREINIGUNG FUER {target_date} ===")
        print(f"Mitarbeiter: {len(employees)}")
        
        for (emp_id,) in employees:
            # Finde weiteste Fahrt dieses Mitarbeiters
            longest = db.execute(
                text("""SELECT id, distance_km, amount 
                       FROM km_daily_entries 
                       WHERE employee_id = :emp AND date = :dt 
                       ORDER BY distance_km DESC LIMIT 1"""),
                {"emp": emp_id, "dt": target_date}
            ).fetchone()
            
            if not longest:
                continue
                
            longest_id, longest_km, longest_amount = longest
            
	 # SPEZIALREGEL: Ljubica (5) & Matej (6) am gleichen Objekt
            if emp_id == 5:  # Ljubica
                # Finde Objekte wo beide waren
                common_objects = db.execute(
                    text("""SELECT DISTINCT object_id FROM km_daily_entries
                           WHERE employee_id = 6 AND date = :dt AND object_id IN (
                               SELECT object_id FROM km_daily_entries WHERE employee_id = 5 AND date = :dt
                           )"""),
                    {"dt": target_date}
                ).fetchall()
                
                if common_objects:
                    for (obj_id,) in common_objects:
                        print(f"  -> Ljubica (5): Fahrt zu Objekt {obj_id} auf 0 km (Matej war auch da)")
                        db.execute(
                            text("""UPDATE km_daily_entries
                                   SET distance_km = 0, amount = 0, is_billable = false, is_longest_trip = false
                                   WHERE employee_id = 5 AND date = :dt AND object_id = :obj"""),
                            {"dt": target_date, "obj": obj_id}
                        )
                    db.commit()
                    
                    # Pruefe ob Ljubica noch andere Fahrten hat
                    remaining = db.execute(
                        text("""SELECT COUNT(*) FROM km_daily_entries
                               WHERE employee_id = 5 AND date = :dt AND distance_km > 0"""),
                        {"dt": target_date}
                    ).fetchone()[0]
                    
                    if remaining == 0:
                        continue  # Alle auf 0, fertig mit Ljubica            
            # Normale Bereinigung: Alle ausser weiteste auf 0
            db.execute(
                text("""UPDATE km_daily_entries 
                       SET distance_km = 0, amount = 0, is_billable = false, is_longest_trip = false
                       WHERE employee_id = :emp AND date = :dt AND id != :longest_id"""),
                {"emp": emp_id, "dt": target_date, "longest_id": longest_id}
            )
            
            # Weiteste Fahrt markieren
            db.execute(
                text("""UPDATE km_daily_entries 
                       SET is_billable = true, is_longest_trip = true
                       WHERE id = :longest_id"""),
                {"longest_id": longest_id}
            )
            
            db.commit()
            
            # Info ausgeben
            emp_name = db.execute(
                text("SELECT first_name, last_name FROM employees WHERE id = :emp"),
                {"emp": emp_id}
            ).fetchone()
            
            print(f"  -> {emp_name[0]} {emp_name[1]}: Weiteste = {longest_km} km ({longest_amount:.2f} Euro)")
        
        print("=== BEREINIGUNG ABGESCHLOSSEN ===")
        
    except Exception as e:
        print(f"FEHLER: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # Fuer heute
    today = date.today()
    cleanup_km_for_date(today)
