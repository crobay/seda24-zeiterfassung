from app.db.database import SessionLocal
from app.models.models import User, Employee
from app.core.security import get_password_hash

db = SessionLocal()

# Komplette Mitarbeiter-Liste aus deiner Excel
ALLE_MITARBEITER = [
    {"email": "drazen@seda24.de", "name": "Drazen Sertic", "kurz": "Drazen", "personal_nr": "D100", "stundensatz": 26.00, "admin": True},
    {"email": "ruza@seda24.de", "name": "Ruza Sertic", "kurz": "Ruza", "personal_nr": "D002", "stundensatz": 17.00},
    {"email": "ljubica@seda24.de", "name": "Ljubica Stjepic", "kurz": "Ljubica", "personal_nr": "D003", "stundensatz": 15.00},
    {"email": "matej@seda24.de", "name": "Matej Stjepic", "kurz": "Matko", "personal_nr": "D004", "stundensatz": 15.00},
    {"email": "eldina@seda24.de", "name": "Eldina Mustafic", "kurz": "Eldina", "personal_nr": "D010", "stundensatz": 15.00},
    {"email": "jana@seda24.de", "name": "Jana Bojko", "kurz": "Jana", "personal_nr": "D013", "stundensatz": 15.00},
    {"email": "elia@seda24.de", "name": "Eliane DaSilvaTodaro", "kurz": "Elia", "personal_nr": "D031", "stundensatz": 15.00},
    {"email": "andy@seda24.de", "name": "Andreas Frosch", "kurz": "Andy", "personal_nr": "D032", "stundensatz": 15.00},
]

neu = 0
vorhanden = 0

for ma in ALLE_MITARBEITER:
    # Check ob Email schon existiert
    existing = db.query(User).filter(User.email == ma["email"]).first()
    
    if existing:
        vorhanden += 1
        # Update Stundensatz falls anders
        emp = db.query(Employee).filter(Employee.user_id == existing.id).first()
        if emp and emp.hourly_rate != ma["stundensatz"]:
            emp.hourly_rate = ma["stundensatz"]
            print(f"📝 {ma['name']}: Stundensatz aktualisiert auf {ma['stundensatz']}€")
    else:
        # Neu anlegen
        role = "admin" if ma.get("admin") else "mitarbeiter"
        user = User(
            email=ma["email"],
            password_hash=get_password_hash("seda2025"),
            role=role,
            must_change_password=True  # Markierung für PW-Änderung
        )
        db.add(user)
        db.flush()
        
        # Employee anlegen
        employee = Employee(
            user_id=user.id,
            personal_nr=ma["personal_nr"],
            first_name=ma["kurz"],
            last_name=ma["name"].split()[-1],
            hourly_rate=ma["stundensatz"]
        )
        db.add(employee)
        neu += 1
        print(f"✅ NEU: {ma['name']} ({ma['email']}) - {role}")

db.commit()

print(f"\n=== ERGEBNIS ===")
print(f"✅ {neu} neue Mitarbeiter angelegt")
print(f"📌 {vorhanden} waren schon vorhanden")
print(f"📊 Gesamt: {neu + vorhanden} Mitarbeiter")
print(f"\n🔐 Standard-Passwort: seda2025")
