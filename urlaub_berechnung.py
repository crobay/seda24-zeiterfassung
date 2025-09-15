#!/usr/bin/env python3
import sys
sys.path.append('/root/zeiterfassung/backend')
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://seda24_user:SedaPass2025!@localhost/seda24_zeiterfassung"
engine = create_engine(DATABASE_URL)
db = sessionmaker(bind=engine)()

print("\n*** URLAUBSBERECHNUNG SEDA24 ***")
print("="*60)

result = db.execute(text("""
    SELECT 
        e.id,
        e.first_name || ' ' || e.last_name as name,
        e.hourly_rate,
        COUNT(DISTINCT s.weekday) as tage_pro_woche,
        SUM(EXTRACT(EPOCH FROM (s.end_time - s.start_time))/3600) as stunden_pro_woche
    FROM employees e
    LEFT JOIN schedules s ON e.id = s.employee_id
    WHERE e.is_active = true AND e.role != 'admin'
    GROUP BY e.id, e.first_name, e.last_name, e.hourly_rate
    ORDER BY e.first_name
"""))

print("Name\t\t\tTage/W\tUrlaub\tSatz/Tag")
print("-"*60)

for row in result:
    tage = int(row.tage_pro_woche) if row.tage_pro_woche else 0
    stunden = float(row.stunden_pro_woche) if row.stunden_pro_woche else 0
    stundenlohn = float(row.hourly_rate) if row.hourly_rate else 15.0
    
    if tage > 0:
        urlaubstage = tage * 4
        stunden_pro_tag = stunden / tage
        urlaubssatz = stunden_pro_tag * stundenlohn
        
        name = row.name[:20].ljust(20)
        print(f"{name}\t{tage}\t{urlaubstage}\t{urlaubssatz:.2f}€")

db.close()
