"""
Feiertagskalender Baden-Wuerttemberg - programmatisch berechnet.

Berechnet alle gesetzlichen Feiertage in BW fuer ein beliebiges Jahr
ueber die Gausssche Osterformel. Keine hartcodierte Liste noetig.

Feste Feiertage BW:
  01.01. Neujahr
  06.01. Heilige Drei Koenige
  01.05. Tag der Arbeit
  03.10. Tag der Deutschen Einheit
  01.11. Allerheiligen
  25.12. Weihnachten
  26.12. 2. Weihnachtsfeiertag

Bewegliche Feiertage (abhaengig von Ostern):
  Karfreitag        = Ostersonntag - 2
  Ostermontag       = Ostersonntag + 1
  Christi Himmelfahrt = Ostersonntag + 39
  Pfingstmontag     = Ostersonntag + 50
  Fronleichnam      = Ostersonntag + 60

NICHT in BW: Buss- und Bettag, Reformationstag.
"""
from datetime import date, timedelta
from functools import lru_cache
from typing import Dict


def easter_sunday(year: int) -> date:
    """Gausssche Osterformel (Meeus/Jones/Butcher-Algorithmus)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=32)
def get_feiertage_bw(year: int) -> Dict[date, str]:
    """Gibt alle gesetzlichen Feiertage in BW fuer das angegebene Jahr zurueck.

    Returns:
        Dict mit date -> Feiertagsname
    """
    easter = easter_sunday(year)

    return {
        # Feste Feiertage
        date(year, 1, 1): 'Neujahr',
        date(year, 1, 6): 'Heilige Drei Koenige',
        date(year, 5, 1): 'Tag der Arbeit',
        date(year, 10, 3): 'Tag der Deutschen Einheit',
        date(year, 11, 1): 'Allerheiligen',
        date(year, 12, 25): 'Weihnachten',
        date(year, 12, 26): '2. Weihnachtsfeiertag',
        # Bewegliche Feiertage
        easter - timedelta(days=2): 'Karfreitag',
        easter + timedelta(days=1): 'Ostermontag',
        easter + timedelta(days=39): 'Christi Himmelfahrt',
        easter + timedelta(days=50): 'Pfingstmontag',
        easter + timedelta(days=60): 'Fronleichnam',
    }


def is_feiertag_bw(d: date) -> bool:
    """Prueft ob ein Datum ein gesetzlicher Feiertag in BW ist."""
    return d in get_feiertage_bw(d.year)


def get_feiertagsname(d: date) -> str:
    """Gibt den Namen des Feiertags zurueck, oder leeren String."""
    return get_feiertage_bw(d.year).get(d, '')
