from app.db.database import SessionLocal
from app.models.models import User, Employee
from app.core.security import get_password_hash
from datetime import datetime

db = SessionLocal()

# Prüfen ob Drazen schon existiert
existing = db.query(User).filter(User.email == "dsertic@sertic.de").first()
if existing:
    print("❌ Drazen existiert bereits! Lösche alten Eintrag...")
    # Erst Employee löschen falls vorhanden
    emp = db.query(Employee).filter(Employee.user_id == existing.id).first()
    if emp:
        db.delete(emp)
    # Dann User löschen
    db.delete(existing)
    db.commit()
    print("✅ Alter Eintrag gelöscht!")

# Drazen User anlegen
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

# Drazen als Mitarbeiter (zum Stempeln)
drazen_employee = Employee(
    user_id=drazen_user.id,
    personal_nr="001",
    first_name="Drazen",
    last_name="Sertic",
    hourly_rate=25.00
)
db.add(drazen_employee)
db.commit()

print("=" * 50)
print("✅ DRAZEN SERTIC ERFOLGREICH ANGELEGT!")
print("=" * 50)
print("📧 Email: dsertic@sertic.de")
print("🔑 Passwort: drazen123")
print("👤 Rolle: Admin + Mitarbeiter")
print("💰 Stundensatz: 25.00€")
print("📝 Personal-Nr: 001")
print("=" * 50)
print("ℹ️  Du kannst das Passwort später ändern!")
print("=" * 50)

db.close()
