#!/usr/bin/env python3
"""
SEDA24 Auto-Checkout Script - FINALE VERSION
Läuft täglich um 23:59 Uhr und stempelt alle vergessenen Mitarbeiter aus
"""

import sys
import os
from datetime import datetime, timedelta

# Pfad zum Backend hinzufügen
sys.path.append('/root/zeiterfassung/backend')

from app.db.database import SessionLocal
from app.models.models import TimeEntry, Employee, User, Object, Warning
from sqlalchemy import and_

def auto_checkout_forgotten_entries():
    """
    Findet alle offenen Stempelungen und schließt sie automatisch
    """
    db = SessionLocal()
    results = []
    
    try:
        # Hole alle offenen Stempelungen von heute
        today = datetime.now().date()
        
        open_entries = db.query(TimeEntry).filter(
            and_(
                TimeEntry.check_out == None,
                TimeEntry.check_in != None
            )
        ).all()
        
        for entry in open_entries:
            # Prüfe ob es von heute ist
            if entry.check_in.date() != today:
                continue
                
            # Hole Mitarbeiter-Info
            employee = db.query(Employee).filter(Employee.id == entry.employee_id).first()
            obj = db.query(Object).filter(Object.id == entry.object_id).first()
            
            if not employee:
                continue
            
            # Berechne Ausstempelzeit
            check_in_time = entry.check_in
            now = datetime.now()
            
            # Maximum 14 Stunden
            max_work_time = check_in_time + timedelta(hours=14)
            
            # Standard: 20 Uhr oder 8 Stunden nach Beginn
            default_checkout = check_in_time.replace(hour=20, minute=0, second=0)
            if default_checkout < check_in_time:
                default_checkout = check_in_time + timedelta(hours=8)
            
            checkout_time = min(default_checkout, max_work_time, now)
            
            # Update TimeEntry
            entry.check_out = checkout_time
            if entry.notes:
                entry.notes += " [AUTO-CHECKOUT: Vergessen auszustempeln]"
            else:
                entry.notes = "[AUTO-CHECKOUT: Vergessen auszustempeln]"
            
            # Erstelle Warnung (OHNE severity!)
            warning = Warning(
                employee_id=entry.employee_id,
                warning_type='forgotten_checkout',
                message=f"Vergessen auszustempeln am {check_in_time.strftime('%d.%m.%Y')}. Automatisch ausgestempelt um {checkout_time.strftime('%H:%M')} Uhr.",
                created_at=datetime.now()
            )
            db.add(warning)
            
            results.append({
                'employee': f"{employee.first_name} {employee.last_name}",
                'object': obj.name if obj else "Unbekannt",
                'check_in': check_in_time.strftime('%H:%M'),
                'auto_checkout': checkout_time.strftime('%H:%M'),
                'hours_worked': round((checkout_time - check_in_time).total_seconds() / 3600, 2)
            })
        
        db.commit()
        
        # Log in Datei
        if results:
            log_results(results)
            
        return results
        
    except Exception as e:
        db.rollback()
        print(f"❌ Fehler beim Auto-Checkout: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        db.close()

def check_max_working_time():
    """
    Prüft ob jemand länger als 10 Stunden arbeitet
    """
    db = SessionLocal()
    
    try:
        # Hole alle offenen Stempelungen
        open_entries = db.query(TimeEntry).filter(
            TimeEntry.check_out == None
        ).all()
        
        now = datetime.now()
        
        for entry in open_entries:
            if not entry.check_in:
                continue
                
            hours_worked = (now - entry.check_in).total_seconds() / 3600
            
            if hours_worked > 10:
                employee = db.query(Employee).filter(Employee.id == entry.employee_id).first()
                if employee:
                    print(f"⚠️ WARNUNG: {employee.first_name} {employee.last_name} arbeitet seit {round(hours_worked, 1)} Stunden!")
                    
                    # Prüfe ob Warnung schon existiert
                    existing_warning = db.query(Warning).filter(
                        and_(
                            Warning.employee_id == entry.employee_id,
                            Warning.warning_type == 'excessive_hours',
                            Warning.created_at > datetime.now() - timedelta(hours=2)
                        )
                    ).first()
                    
                    if not existing_warning:
                        # Erstelle Warnung (OHNE severity!)
                        warning = Warning(
                            employee_id=entry.employee_id,
                            warning_type='excessive_hours',
                            message=f"Arbeitet seit über {round(hours_worked, 1)} Stunden ohne Ausstempelung!",
                            created_at=datetime.now()
                        )
                        db.add(warning)
        
        db.commit()
        
    except Exception as e:
        print(f"❌ Fehler bei Arbeitszeitprüfung: {e}")
        db.rollback()
    finally:
        db.close()

def log_results(results):
    """
    Schreibt Ergebnisse in Log-Datei
    """
    log_dir = '/root/zeiterfassung/logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, 'auto_checkout.log')
    
    with open(log_file, 'a') as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"Auto-Checkout am {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
        f.write(f"{'='*50}\n")
        for r in results:
            f.write(f"{r['employee']} - {r['object']}: {r['check_in']} → {r['auto_checkout']} ({r['hours_worked']}h)\n")
        f.write(f"{'='*50}\n")

def test_database_connection():
    """
    Testet ob die Datenbank-Verbindung funktioniert
    """
    db = SessionLocal()
    try:
        # Teste ob wir Employees lesen können
        employee_count = db.query(Employee).count()
        print(f"✅ Datenbank-Verbindung OK! {employee_count} Mitarbeiter gefunden.")
        
        # Teste ob TimeEntry Tabelle existiert
        entry_count = db.query(TimeEntry).count()
        print(f"✅ {entry_count} Zeiteinträge in der Datenbank.")
        
        # Teste ob offene Einträge existieren
        open_count = db.query(TimeEntry).filter(TimeEntry.check_out == None).count()
        if open_count > 0:
            print(f"⚠️  {open_count} offene Stempelungen gefunden.")
        
        return True
    except Exception as e:
        print(f"❌ Datenbank-Fehler: {e}")
        return False
    finally:
        db.close()

def create_test_entry():
    """
    Erstellt einen Test-Eintrag zum Testen des Scripts
    NUR FÜR TESTS - Später löschen!
    """
    db = SessionLocal()
    try:
        # Erstelle einen offenen Eintrag von heute morgen
        test_entry = TimeEntry(
            employee_id=1,
            object_id=1,
            check_in=datetime.now().replace(hour=7, minute=0, second=0),
            check_out=None,  # Nicht ausgestempelt!
            notes="TEST-EINTRAG"
        )
        db.add(test_entry)
        db.commit()
        print("📝 Test-Eintrag erstellt (nicht ausgestempelt)")
        return True
    except Exception as e:
        print(f"❌ Konnte Test-Eintrag nicht erstellen: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print(f"🕐 Auto-Checkout Script gestartet: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("="*50)
    
    # Teste erst die Datenbank
    if not test_database_connection():
        print("❌ Datenbank-Verbindung fehlgeschlagen. Script beendet.")
        sys.exit(1)
    
    print("="*50)
    
    # OPTIONAL: Test-Eintrag erstellen (zum Testen)
    # Entkommentiere die nächste Zeile wenn du testen willst:
    # create_test_entry()
    
    # Prüfe lange Arbeitszeiten
    print("📊 Prüfe auf zu lange Arbeitszeiten...")
    check_max_working_time()
    
    # Führe Auto-Checkout durch
    print("🔄 Suche vergessene Ausstempelungen...")
    results = auto_checkout_forgotten_entries()
    
    if results:
        print(f"✅ {len(results)} Mitarbeiter automatisch ausgestempelt:")
        for r in results:
            print(f"  - {r['employee']}: {r['check_in']} → {r['auto_checkout']} ({r['hours_worked']}h)")
    else:
        print("✅ Keine vergessenen Ausstempelungen gefunden.")
    
    print("="*50)
    print(f"🏁 Script beendet: {datetime.now().strftime('%H:%M:%S')}")
