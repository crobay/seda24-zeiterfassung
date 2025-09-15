from app.db.database import SessionLocal
from app.models.models import Employee

db = SessionLocal()

# Alle anzeigen
print("\n=== AKTUELLE KATEGORIEN ===")
for emp in db.query(Employee).all():
    print(f"{emp.personal_nr}: {emp.first_name} {emp.last_name} -> {emp.tracking_mode}")

# Kategorien setzen
updates = [
    ("D100", "A"),    # Drazen
    ("D0021", "B"),   # Matej  
    ("D0032", "B"),   # Andreas
    ("D0034", "A"),   # Sonja
    ("D0002", "B"),   # Ruzica
    ("D0004", "B"),   # Ljubica
]

print("\n=== UPDATES ===")
for personal_nr, category in updates:
    emp = db.query(Employee).filter(Employee.personal_nr == personal_nr).first()
    if emp:
        emp.tracking_mode = category
        print(f"✓ {personal_nr} -> Kategorie {category}")
    else:
        print(f"✗ {personal_nr} nicht gefunden")

db.commit()
print("\n✅ Fertig!")
