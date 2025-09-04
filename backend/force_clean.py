import psycopg2
from app.core.config import settings
import os
from dotenv import load_dotenv

load_dotenv()

# Direkte PostgreSQL Verbindung
conn = psycopg2.connect(
    dbname="seda24_zeiterfassung",
    user="seda24_user",
    password="SedaPass2025!",
    host="localhost"
)
cur = conn.cursor()

print("🔨 FORCE CLEAN - Alle Constraints temporär deaktivieren...")

try:
    # Alle Foreign Keys temporär deaktivieren
    cur.execute("SET session_replication_role = 'replica';")
    
    # Jetzt können wir in beliebiger Reihenfolge löschen
    tables = [
        'correction_requests',
        'warnings', 
        'schedules',
        'time_entries',
        'employees',
        'users',
        'customers',
        'objects'
    ]
    
    for table in tables:
        cur.execute(f"DELETE FROM {table};")
        print(f"✅ {table} gelöscht")
    
    # Foreign Keys wieder aktivieren
    cur.execute("SET session_replication_role = 'origin';")
    
    conn.commit()
    print("✅ Datenbank komplett leer!")
    
except Exception as e:
    print(f"❌ Fehler: {e}")
    conn.rollback()
finally:
    cur.close()
    conn.close()

print("Jetzt fix_database.py nochmal ausführen!")
