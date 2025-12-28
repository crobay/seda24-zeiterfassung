import sys
sys.path.insert(0, '/var/www/vhosts/seda.de/app.seda.de/zeiterfassung/backend')

from app.core.pdf_generator import PDFGenerator
from app.db.database import SessionLocal

db = SessionLocal()
gen = PDFGenerator(db)

# Ruzica Kilometer Dezember 2025
try:
    pdf = gen.generate_kilometer(4, 2025, 12)
    print(f'PDF erstellt: {pdf}')
except Exception as e:
    print(f'FEHLER: {e}')
    import traceback
    traceback.print_exc()
