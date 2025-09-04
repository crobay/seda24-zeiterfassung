from app.db.database import SessionLocal
from app.models.models import User, Employee
from app.core.security import get_password_hash

db = SessionLocal()

# Alle deine Mitarbeiter
MITARBEITER = [
    {"email": "d100@seda24.de", "name": "Drazen Sertic", "kurz": "Drazen", "personal_nr": "D100", "stundensatz": 26.00},
    {"email": "d002@seda24.de", "name": "Ruza Sertic", "kurz": "Ruza", "personal_nr": "D002", "stundensatz": 17.00},
    {"email": "d003@seda24.de", "name": "Ljubica Stjepic", "kurz": "Ljubica", "personal_nr": "D003", "stundensatz": 15.00},
    {"email": "d004@seda24.de", "name": "Matej Stjepic", "kurz": "Matko", "personal_nr": "D004", "stundensatz": 15.00},
    {"email": "d010@seda24.de", "name": "Eldina Mustafic", "kurz": "Eldina", "personal_nr": "D010", "stundensatz": 15.00},
    {"email": "d013@seda24.de", "name": "Jana Bojko", "kurz": "Jana", "personal_nr": "D013", "stundensatz": 15.00},
    {"email": "d031@seda24.de", "name": "Eliane DaSilvaTodaro", "kurz": "Elia", "personal_nr": "D031", "stundensatz": 15.00},
    {"email": "d032@seda24.de", "name": "Andreas Frosch", "kurz": "Andy", "personal_nr": "D032", "stundensatz": 15.00},
]

print("\n=== MITARBEITER ANLEGEN ===")
for ma in MITARBEITER:
    # Prüfen ob schon da
    existing = db.query(User).filter(User.email == ma["email"]).first()
    if existing:
        print(f"✓ {ma['kurz']} existiert bereits")
        continue
    
    # User anlegen
    user = User(
        email=ma["email"],
        password_hash=get_password_hash("seda2025"),
        role="mitarbeiter"
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
    print(f"✅ {ma['kurz']} angelegt - {ma['stundensatz']}€/Std")

db.commit()
print("\n🎉 FERTIG!")
print("Login: personal-nr@seda24.de")
print("Passwort: seda2025")
