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

print("\n=== PRÜFE MITARBEITER ===")
neu = 0
vorhanden = 0

for ma in MITARBEITER:
    # Prüfe ob Personal-Nr schon existiert
    existing_emp = db.query(Employee).filter(Employee.personal_nr == ma["personal_nr"]).first()
    
    if existing_emp:
        print(f"✓ {ma['personal_nr']} - {ma['kurz']} existiert bereits")
        vorhanden += 1
        continue
    
    # Prüfe ob Email schon existiert
    existing_user = db.query(User).filter(User.email == ma["email"]).first()
    
    if not existing_user:
        # User anlegen
        user = User(
            email=ma["email"],
            password_hash=get_password_hash("seda2025"),
            role="mitarbeiter"
        )
        db.add(user)
        db.flush()
        user_id = user.id
    else:
        user_id = existing_user.id
    
    # Employee anlegen
    employee = Employee(
        user_id=user_id,
        personal_nr=ma["personal_nr"],
        first_name=ma["kurz"],
        last_name=ma["name"].split()[-1],
        hourly_rate=ma["stundensatz"]
    )
    db.add(employee)
    print(f"✅ NEU: {ma['personal_nr']} - {ma['kurz']} ({ma['stundensatz']}€/Std)")
    neu += 1

db.commit()

print(f"\n=== ERGEBNIS ===")
print(f"✅ {neu} neue Mitarbeiter")
print(f"📌 {vorhanden} waren schon da")
print(f"📊 Gesamt: {neu + vorhanden} Mitarbeiter")
