from app.db.database import SessionLocal
from app.models.models import TimeEntry, User, Employee
from datetime import datetime
import json

db = SessionLocal()

print("\n" + "="*50)
print("🔍 2-STUNDEN-BUG DIAGNOSE")
print("="*50)

# 1. Admin User finden
admin = db.query(User).filter(User.email == "admin@seda24.de").first()
if admin:
    emp = db.query(Employee).filter(Employee.user_id == admin.id).first()
    if emp:
        print(f"\n✅ Admin Employee ID: {emp.id}")
        
        # 2. ALLE Einträge für Admin
        entries = db.query(TimeEntry).filter(TimeEntry.employee_id == emp.id).all()
        print(f"\n📊 Gefundene Einträge: {len(entries)}")
        
        for e in entries:
            age = (datetime.utcnow() - e.check_in).total_seconds() / 3600
            status = "🔴 OFFEN" if not e.check_out else "🟢 GESCHLOSSEN"
            print(f"   ID {e.id}: {age:.1f}h alt - {status}")
            
            if age > 1.5 and age < 3:  # Zwischen 1.5 und 3 Stunden
                print(f"   ⚠️ VERDÄCHTIG! Das könnte der 2h-Geist sein!")
                
        # 3. Offene Einträge
        open_entries = db.query(TimeEntry).filter(
            TimeEntry.employee_id == emp.id,
            TimeEntry.check_out == None
        ).all()
        
        if open_entries:
            print(f"\n⚠️ {len(open_entries)} OFFENE EINTRÄGE GEFUNDEN!")
            for o in open_entries:
                print(f"   Lösche ID {o.id}...")
                db.delete(o)
            db.commit()
            print("   ✅ Gelöscht!")
        else:
            print("\n✅ Keine offenen Einträge")

print("\n" + "="*50)
print("FERTIG!")
print("="*50)
