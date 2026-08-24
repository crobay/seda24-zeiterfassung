"""
Tests fuer holidays_bw und workday_utils.

Ausfuehren: cd backend && python tests/test_holidays_and_workdays.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import date, timedelta
from app.services.holidays_bw import easter_sunday, get_feiertage_bw, is_feiertag_bw, get_feiertagsname
from app.services.workday_utils import is_working_day, count_working_days, parse_work_days_profile


# ============================================================
# A) Feiertagskalender BW
# ============================================================

def test_easter_sunday_2026():
    assert easter_sunday(2026) == date(2026, 4, 5)

def test_easter_sunday_2027():
    assert easter_sunday(2027) == date(2027, 3, 28)

def test_fronleichnam_2027():
    easter = easter_sunday(2027)
    fronleichnam = easter + timedelta(days=60)
    assert fronleichnam == date(2027, 5, 27)

def test_pfingstmontag_2027():
    easter = easter_sunday(2027)
    pfingstmontag = easter + timedelta(days=50)
    assert pfingstmontag == date(2027, 5, 17)

def test_feiertage_bw_2025_count():
    feiertage = get_feiertage_bw(2025)
    assert len(feiertage) == 12, f"Erwartet 12 Feiertage, bekommen {len(feiertage)}"

def test_feiertage_bw_2026_count():
    feiertage = get_feiertage_bw(2026)
    assert len(feiertage) == 12

def test_neujahr_ist_feiertag():
    assert is_feiertag_bw(date(2026, 1, 1))
    assert is_feiertag_bw(date(2030, 1, 1))

def test_karfreitag_2025():
    assert is_feiertag_bw(date(2025, 4, 18))
    assert get_feiertagsname(date(2025, 4, 18)) == 'Karfreitag'

def test_kein_feiertag():
    assert not is_feiertag_bw(date(2026, 3, 15))

def test_reformationstag_nicht_in_bw():
    assert not is_feiertag_bw(date(2026, 10, 31))

def test_gegentest_alte_liste_2025():
    alte = {
        date(2025, 1, 1), date(2025, 1, 6), date(2025, 4, 18), date(2025, 4, 21),
        date(2025, 5, 1), date(2025, 5, 29), date(2025, 6, 9), date(2025, 6, 19),
        date(2025, 10, 3), date(2025, 11, 1), date(2025, 12, 25), date(2025, 12, 26),
    }
    neue = set(get_feiertage_bw(2025).keys())
    assert alte == neue, f"Differenz: alt-neu={alte-neue}, neu-alt={neue-alte}"

def test_gegentest_alte_liste_2026():
    alte = {
        date(2026, 1, 1), date(2026, 1, 6), date(2026, 4, 3), date(2026, 4, 6),
        date(2026, 5, 1), date(2026, 5, 14), date(2026, 5, 25), date(2026, 6, 4),
        date(2026, 10, 3), date(2026, 11, 1), date(2026, 12, 25), date(2026, 12, 26),
    }
    neue = set(get_feiertage_bw(2026).keys())
    assert alte == neue, f"Differenz: alt-neu={alte-neue}, neu-alt={neue-alte}"


# ============================================================
# B) Arbeitstagsprofil
# ============================================================

def test_parse_default():
    days = parse_work_days_profile(None)
    assert days == {0, 1, 2, 3, 4}

def test_parse_empty():
    days = parse_work_days_profile("")
    assert days == {0, 1, 2, 3, 4}

def test_parse_custom():
    days = parse_work_days_profile("0,2,4")
    assert days == {0, 2, 4}

def test_parse_samstag_only():
    days = parse_work_days_profile("5")
    assert days == {5}


# ============================================================
# C) Zentrale Regel: is_working_day + count_working_days
# ============================================================

def test_normaler_montag():
    # 2026-08-24 ist Montag
    assert is_working_day(date(2026, 8, 24), "0,1,2,3,4")

def test_samstag_nicht_im_profil():
    # 2026-08-29 ist Samstag
    assert not is_working_day(date(2026, 8, 29), "0,1,2,3,4")

def test_samstag_im_profil():
    assert is_working_day(date(2026, 8, 29), "0,1,2,3,4,5")

def test_feiertag_auch_mit_profil_kein_arbeitstag():
    # 2026-01-01 ist Donnerstag (weekday=3)
    assert not is_working_day(date(2026, 1, 1), "0,1,2,3,4")

def test_feiertag_samstag():
    # 2026-10-03 ist Samstag
    assert not is_working_day(date(2026, 10, 3), "0,1,2,3,4,5")

def test_count_eine_woche_mo_fr():
    count = count_working_days(date(2026, 8, 24), date(2026, 8, 28), "0,1,2,3,4")
    assert count == 5

def test_count_mit_wochenende():
    count = count_working_days(date(2026, 8, 24), date(2026, 8, 30), "0,1,2,3,4")
    assert count == 5

def test_count_mit_feiertag():
    # Mo 29.12.2025 - Fr 02.01.2026: Neujahr (Do) abgezogen = 4
    count = count_working_days(date(2025, 12, 29), date(2026, 1, 2), "0,1,2,3,4")
    assert count == 4, f"Erwartet 4, bekommen {count}"

def test_count_teilzeit_nur_mo_mi_fr():
    count = count_working_days(date(2026, 8, 24), date(2026, 8, 30), "0,2,4")
    assert count == 3

def test_count_minijob_nur_samstag():
    count = count_working_days(date(2026, 8, 24), date(2026, 8, 30), "5")
    assert count == 1

def test_count_default_profil():
    count = count_working_days(date(2026, 8, 24), date(2026, 8, 28), None)
    assert count == 5


# ============================================================
# Runner
# ============================================================

if __name__ == '__main__':
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = failed = 0
    for test_fn in tests:
        try:
            test_fn()
            print(f"  PASS  {test_fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test_fn.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*50}")
    print(f"Ergebnis: {passed} bestanden, {failed} fehlgeschlagen von {passed+failed}")
    if failed:
        sys.exit(1)
