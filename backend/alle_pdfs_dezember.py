import sys
sys.path.insert(0, '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/backend')

from app.core.pdf_generator import PDFGenerator
from app.db.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
gen = PDFGenerator(db)

# Alle aktiven Mitarbeiter
employees = db.execute(text("SELECT id, first_name, last_name FROM employees WHERE is_active = true ORDER BY last_name")).fetchall()

print(f"\n=== DEZEMBER 2025 PDF-GENERIERUNG ===\n")

for emp in employees:
    emp_id, first_name, last_name = emp
    name = f"{first_name} {last_name}"
    
    # Zeitnachweis
    try:
        pdf = gen.generate_zeitnachweis(emp_id, 2025, 12)
        print(f"✓ Zeitnachweis {name}: {pdf}")
    except Exception as e:
        print(f"✗ Zeitnachweis {name}: {e}")
    
    # Kilometer
    try:
        pdf = gen.generate_kilometer(emp_id, 2025, 12)
        print(f"✓ Kilometer {name}: {pdf}")
    except Exception as e:
        print(f"✗ Kilometer {name}: {e}")

print(f"\n=== FERTIG ===")
