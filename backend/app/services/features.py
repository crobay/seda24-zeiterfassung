"""Schalter fuer Cockpit-Teile, die etappenweise auf LIVE gehen (Drazen 19.11.2026).

Gesetzt in backend/.env, Standard AUS. DEV setzt alle auf 1; LIVE schaltet sie mit der jeweiligen Etappe frei:
    COCKPIT_ABSCHLUSS=1    Monatsabschluss (Seite + /api/v1/cockpit/abschluss)        -> Etappe 2
    COCKPIT_FIXUM_JOBS=1   Scheduler: Do 18:00 Fixum-Entwurf, Fr 09:00 Plan-Erinnerung -> spaeter
    COCKPIT_OBJEKT_LOGO=1  Objekt-Logo/Kuerzel bearbeiten + gross in der Stempeluhr    -> spaeter
Die Monatssperre ist kein Schalter: sie wirkt erst, wenn migrations/monatssperre.sql eingespielt ist (Etappe 2).
"""
import os


def an(name: str) -> bool:
    return os.getenv(f"COCKPIT_{name}", "") == "1"
