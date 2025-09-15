#!/usr/bin/env python3
import sys
sys.path.append('/root/zeiterfassung/backend')
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://seda24_user:SedaPass2025!@localhost/seda24_zeiterfassung"
engine = create_engine(DATABASE_URL)
db = sessionmaker(bind=engine)()

print("\n*** URLAUBSBERECHNUNG ***")
print("="*60)

result = db.execute(text("""
    SELECT 
        e.id,
        e.first_name || ' ' || e.last_name as name,
        e.hourly_rate,
        COUNT(DISTINCT s.weekday) as tage,
        SUM(EXTRACT(EPOCH FROM (s.end_time - s.start_time))/3600) as stunden
    FROM employees e
    LEFT JOIN schedules s ON e.id = s.employee_id
    WHERE e.is_active = true
    GROUP BY e.id, e.first_name, e.last_name, e.hourly_rate
    ORDER BY e.first_name
"""))

for row in result:
    if row.tage and row.tage > 0:
        urlaubstage = row.tage * 4
        urlaubssatz = (float(row.stunden) / float(row.tage)) * float(row.hourly_rate or 15)
        print(f"{row.name}: {urlaubstage} Tage, {urlaubssatz:.2f}€/Tag")

db.close()
