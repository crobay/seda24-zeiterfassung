#!/usr/bin/env python3
"""
Stand des Zeiterfassungs-Exports pruefen (nur lesen): export_status.py [JJJJ-MM, Standard Vormonat]

Zeigt Exporttag/Abruf/Kontrolle, die Datei auf dem Server, die Zeilen aus logs/export_zeiterfassung.log
und alle Export-Audit-Eintraege seit dem Exporttag 14:00 (Abruf, Quittung aus Q:, Fehler, abgelehnt).
"""
import hashlib
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BACKEND, '.env'))
sys.path.insert(0, BACKEND)
from app.services.export_termine import (ABRUF_ZEIT, EXPORT_ZEIT, KONTROLLE_ZEIT, exporttag,  # noqa: E402
                                         kontrolltag, vormonat)

monat = sys.argv[1] if len(sys.argv) > 1 else vormonat()
et = exporttag(monat)
seit = datetime.combine(et, EXPORT_ZEIT)
name = f'zeiterfassung_{monat}.csv'
print(f"Monat {monat}: Export {et:%a %d.%m.%Y} {EXPORT_ZEIT:%H:%M} | Abruf ab {ABRUF_ZEIT:%H:%M} | "
      f"Kontrolle {kontrolltag(monat):%a %d.%m.%Y} {KONTROLLE_ZEIT:%H:%M}")

p = os.path.join(BACKEND, 'exports', 'zeiterfassung', name)
if os.path.isfile(p):
    mt = datetime.fromtimestamp(os.path.getmtime(p))
    with open(p, 'rb') as f:
        sha = hashlib.sha256(f.read()).hexdigest()[:12]
    print(f"Server-Datei {name}: {os.path.getsize(p)} Bytes, Stand {mt:%d.%m.%Y %H:%M:%S}, SHA-256 {sha} "
          f"-> {'am Exporttag erzeugt' if mt >= seit else 'NICHT seit dem Exporttag erzeugt'}")
else:
    print(f"Server-Datei {name}: FEHLT")

print("\nlogs/export_zeiterfassung.log (letzte 5):")
try:
    with open(os.path.join(BACKEND, 'logs', 'export_zeiterfassung.log')) as f:
        for z in f.readlines()[-5:]:
            print('  ' + z.rstrip())
except OSError:
    print('  (kein Protokoll)')

print(f"\nAudit seit {seit:%d.%m.%Y %H:%M}:")
eng = create_engine(os.getenv('DATABASE_URL'))
with eng.connect() as c:
    c.execute(text('SET TRANSACTION READ ONLY'))
    rows = c.execute(text("""SELECT id, created_at, action, details, ip_address FROM audit_log
                             WHERE entity_type = 'export' AND created_at >= :s ORDER BY id"""), {'s': seit}).fetchall()
    c.rollback()
for r in rows:
    print(f"  {r[0]} {r[1]:%d.%m. %H:%M:%S} {r[2]:<24} {r[3]}  [{r[4]}]")
ab = [r for r in rows if r[2] == 'export_abruf' and f'Export {name} ' in r[3]]
qu = [r for r in rows if r[2] == 'export_quittung' and f'{name} (' in r[3]]
print(f"\nErgebnis: Abruf {name}: {ab[0][1]:%d.%m. %H:%M:%S}" if ab else f"\nErgebnis: Abruf {name}: noch nicht", end='')
print(f" | in Q: bestaetigt: {qu[0][1]:%d.%m. %H:%M:%S}" if qu else " | in Q: bestaetigt: noch nicht")
