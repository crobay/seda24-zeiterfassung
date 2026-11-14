"""
Termine fuer den monatlichen Zeiterfassungs-Export (scripts/export_zeiterfassung.py).

- Exporttag: 1. Werktag des Folgemonats (Mo-Fr, ohne gesetzliche Feiertage BW), Export um 14:00.
- Abruf von Drazens PC (seda24_export_abruf.ps1) ab 15:00 am Exporttag.
- Kontrollmeldung (Datei nicht erzeugt / nicht abgeholt): 2 Werktage nach dem Exporttag um 12:00.
- SONDERTERMINE: einmalig abweichender Exporttag fuer einen Monat (danach gilt wieder die Regel).
"""
from datetime import date, datetime, time, timedelta

from app.services.holidays_bw import is_feiertag_bw

EXPORT_ZEIT = time(14, 0)
ABRUF_ZEIT = time(15, 0)
KONTROLLE_ZEIT = time(12, 0)
KONTROLLE_WERKTAGE = 2
# Generalprobe (GO Drazen): Oktober 2026 einmalig am Mo 16.11.2026 neu exportieren, Abruf ab 15:00,
# Kontrolle Mi 18.11. 12:00. Naechster regulaerer Export: Di 01.12.2026 (November).
SONDERTERMINE = {'2026-10': date(2026, 11, 16)}


def ist_werktag(d: date) -> bool:
    return d.weekday() < 5 and not is_feiertag_bw(d)


def plus_werktage(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if ist_werktag(d):
            n -= 1
    return d


def exporttag(monat: str) -> date:
    """Exporttag fuer den Monat 'JJJJ-MM' = 1. Werktag des Folgemonats."""
    if monat in SONDERTERMINE:
        return SONDERTERMINE[monat]
    first = datetime.strptime(monat, '%Y-%m').date()
    d = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return d if ist_werktag(d) else plus_werktage(d, 1)


def vormonat(heute: date = None) -> str:
    heute = heute or date.today()
    return (heute.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')


def kontrolltag(monat: str) -> date:
    return plus_werktage(exporttag(monat), KONTROLLE_WERKTAGE)
