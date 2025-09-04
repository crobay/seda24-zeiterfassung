import sys
sys.path.append('/root/zeiterfassung/backend')

from app.db.database import SessionLocal
from app.models.models import Employee

db = SessionLocal()

print("\n=== ALLE MITARBEITER IN DB ===")
for emp in db.query(Employee).all():
    print(f"ID: {emp.id} | Pers-Nr: {emp.personal_nr} | Name: {emp.first_name} {emp.last_name} | Kategorie: {emp.tracking_mode}")
