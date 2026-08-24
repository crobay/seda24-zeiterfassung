"""
Zentrale Arbeitstag-Logik fuer Urlaubsberechnung nach BUrlG.

Konvention: Wochentage immer als Python-int (0=Montag .. 6=Sonntag).

Ein Tag ist fuer einen Mitarbeiter KEIN Arbeitstag, wenn:
  1. Der Wochentag nicht in seinem Arbeitstagsprofil liegt, ODER
  2. Der Tag ein gesetzlicher Feiertag in BW ist (§ 3 Abs. 2 BUrlG).

Wird spaeter in der Urlaubsberechnung, Anspruchsermittlung und
ggf. im Auto-Booking verwendet.
"""
from datetime import date, timedelta
from typing import List, Optional, Set

from app.services.holidays_bw import is_feiertag_bw


# Default: Mo-Fr (Python 0-4) - fuer Mitarbeiter ohne konfiguriertes Profil
DEFAULT_WORK_DAYS = {0, 1, 2, 3, 4}


def parse_work_days_profile(profile: Optional[str]) -> Set[int]:
    """Parst den kommaseparierten work_days_profile-String in ein Set von Wochentag-ints.

    Args:
        profile: z.B. "0,1,2,3,4" oder None

    Returns:
        Set von ints (0=Mo..6=So). Bei None/leer wird DEFAULT_WORK_DAYS zurueckgegeben.
    """
    if not profile or not profile.strip():
        return set(DEFAULT_WORK_DAYS)
    return {int(d.strip()) for d in profile.split(',') if d.strip().isdigit()}


def is_working_day(d: date, work_days_profile: Optional[str] = None) -> bool:
    """Prueft ob ein Tag fuer den Mitarbeiter ein Arbeitstag ist.

    Ein Tag ist KEIN Arbeitstag wenn:
      - Der Wochentag nicht im Profil liegt, ODER
      - Es ein gesetzlicher Feiertag in BW ist.

    Args:
        d: Das zu pruefende Datum
        work_days_profile: Kommaseparierter String (Python 0=Mo..6=So), oder None fuer Mo-Fr

    Returns:
        True wenn Arbeitstag, False sonst
    """
    if is_feiertag_bw(d):
        return False
    work_days = parse_work_days_profile(work_days_profile)
    return d.weekday() in work_days


def count_working_days(start_date: date, end_date: date, work_days_profile: Optional[str] = None) -> int:
    """Zaehlt die Arbeitstage in einem Zeitraum (inkl. Start und Ende).

    Beruecksichtigt Arbeitstagsprofil UND Feiertage BW.

    Args:
        start_date: Erster Tag (inklusiv)
        end_date: Letzter Tag (inklusiv)
        work_days_profile: Kommaseparierter String, oder None fuer Mo-Fr

    Returns:
        Anzahl der Arbeitstage im Zeitraum
    """
    if start_date > end_date:
        return 0
    count = 0
    current = start_date
    while current <= end_date:
        if is_working_day(current, work_days_profile):
            count += 1
        current += timedelta(days=1)
    return count
