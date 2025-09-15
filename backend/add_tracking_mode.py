import sys
sys.path.append('/root/zeiterfassung/backend')

from app.db.database import engine
from sqlalchemy import text

# Spalte hinzufügen
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE employees ADD COLUMN tracking_mode VARCHAR(1) DEFAULT 'C'"))
        conn.execute(text("ALTER TABLE employees ADD COLUMN gps_required BOOLEAN DEFAULT FALSE"))
        conn.commit()
        print("✅ Spalten hinzugefügt!")
    except:
        print("Spalten existieren schon")
    
    # Jetzt Kategorien setzen
    conn.execute(text("UPDATE employees SET tracking_mode = 'A' WHERE personal_nr IN ('D001', 'D100')"))  # Drazen
    conn.execute(text("UPDATE employees SET tracking_mode = 'B' WHERE personal_nr IN ('D0021', 'D021', 'D21')"))  # Matej
    conn.execute(text("UPDATE employees SET tracking_mode = 'B' WHERE personal_nr IN ('D0032', 'D032', 'D32')"))  # Andreas
    conn.execute(text("UPDATE employees SET tracking_mode = 'A' WHERE personal_nr IN ('D0034', 'D034', 'D34')"))  # Sonja
    conn.execute(text("UPDATE employees SET tracking_mode = 'B' WHERE personal_nr IN ('D0002', 'D002', 'D2')"))  # Ruzica
    conn.commit()
    
    # Anzeigen
    result = conn.execute(text("SELECT personal_nr, first_name, last_name, tracking_mode FROM employees"))
    print("\n=== MITARBEITER MIT KATEGORIEN ===")
    for row in result:
        print(f"{row[0]}: {row[1]} {row[2]} -> {row[3]}")
