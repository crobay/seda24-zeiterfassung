from app.db.database import SessionLocal, engine
from app.models.models import User, Employee
from app.core.security import get_password_hash
from datetime import datetime
from sqlalchemy import text

db = SessionLocal()

print("=" * 50)
print("🧹 KOMPLETTE DATENBANK-BEREINIGUNG...")
print("=" * 50)

try:
    # Direkt mit SQL arbeiten für sauberes Löschen
    with engine.connect() as conn:
        print("📝 Lösche Daten in richtiger Reihenfolge...")
        
        # WICHTIG: Von "außen nach innen" löschen!
        
        # 1. Correction Requests ZUERST (hängt von time_entries ab)
        result = conn.execute(text("DELETE FROM correction_requests"))
        conn.commit()
        print("   ✅ Correction Requests gelöscht")
        
        # 2. Warnings löschen
        result = conn.execute(text("DELETE FROM warnings"))
        conn.commit()
        print("   ✅ Warnings gelöscht")
        
        # 3. Schedules löschen
        result = conn.execute(text("DELETE FROM schedules"))
        conn.commit()
        print("   ✅ Schedules gelöscht")
        
        # 4. JETZT ERST Time Entries
        result = conn.execute(text("DELETE FROM time_entries"))
        conn.commit()
        print("   ✅ Time Entries gelöscht")
        
        # 5. Employees löschen
        result = conn.execute(text("DELETE FROM employees"))
        conn.commit()
        print("   ✅ Alle Employees gelöscht")
        
        # 6. Users zuletzt
        result = conn.execute(text("DELETE FROM users"))
        conn.commit()
        print("   ✅ Alle Users gelöscht")
        
    print("=" * 50)
    print("✅ DATENBANK SAUBER!")
    print("=" * 50)
    
    # Jetzt Drazen neu anlegen
    print("📝 LEGE DRAZEN NEU AN...")
    print("=" * 50)
    
    # Drazen User
    drazen_user = User(
        email="dsertic@sertic.de",
        password_hash=get_password_hash("drazen123"),
        role="admin",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(drazen_user)
    db.commit()
    db.refresh(drazen_user)
    
    # Drazen Employee
    drazen_employee = Employee(
        user_id=drazen_user.id,
        personal_nr="001",
        first_name="Drazen",
        last_name="Sertic",
        hourly_rate=25.00
    )
    db.add(drazen_employee)
    db.commit()
    
    print("✅ DRAZEN ERFOLGREICH ANGELEGT!")
    print("=" * 50)
    print("📧 Email: dsertic@sertic.de")
    print("🔑 Passwort: drazen123")
    print("👤 Rolle: Admin + Mitarbeiter")
    print("💰 Stundensatz: 25.00€")
    print("📝 Personal-Nr: 001")
    print("=" * 50)
    
    # Test-Admin für Backup
    print("\n📝 Lege Backup-Admin an...")
    admin_user = User(
        email="admin@seda24.de",
        password_hash=get_password_hash("admin123"),
        role="admin",
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
    
    admin_employee = Employee(
        user_id=admin_user.id,
        personal_nr="999",
        first_name="Admin",
        last_name="SEDA24",
        hourly_rate=0.00
    )
    db.add(admin_employee)
    db.commit()
    
    print("✅ Backup-Admin angelegt (admin@seda24.de / admin123)")
    
    print("=" * 50)
    print("🎉 FERTIG! Datenbank ist sauber!")
    print("=" * 50)
    
except Exception as e:
    print(f"❌ FEHLER: {str(e)}")
    db.rollback()
finally:
    db.close()
