"""Urlaubstage zaehlen und Urlaubskonten (Drazen 25.11.2026 20:25).

Regel (Drazen wortlich): "sie kriegt es, wie wenn sie arbeitet. Wenn ein Minijobber dienstags, donnerstags arbeitet und
nimmt 2 Tage Urlaub, dann ist der dazwischen der Tag interessiert nicht. Bei Teilzeit- und Vollzeitkraeften ist es so."

Ein Tag ist Urlaubstag, wenn der MA an dem Tag arbeiten wuerde:
  1. Woche schon im Dienstplan (echte Schichten des MA in der Woche) -> nur Tage mit Schicht
  2. sonst Vorlage (master_schedule_entries, Rhythmus wie die Plan-Erzeugung)
  3. sonst Arbeitstagsprofil (employees.work_days_profile)
  4. sonst Wochentage frueherer Schichten, zuletzt Mo-Fr
Gesetzliche Feiertage BW zaehlen nie (workday_utils / holidays_bw): kein Urlaubstag, keine Urlaubsbuchung.
Gilt fuer Antrag (App/Telegram), Aendern, Genehmigen und Admin-Eintrag. Krankmeldungen zaehlen weiter wie bisher.
"""
from datetime import date, timedelta

from sqlalchemy import text

from app.services.holidays_bw import is_feiertag_bw
from app.services.workday_utils import DEFAULT_WORK_DAYS, parse_work_days_profile

ARBEIT = ("normal", "vertretung")


def _platzhalter(s):
    """Vom Urlaub/Abwesenheit selbst angelegte Zeile (keine echte Schicht) -> sagt nichts ueber den Plan."""
    return s["status"] in ("urlaub", "abwesend") and not (s["planned_hours"] or 0) > 0


def tage(db, employee_id, start: date, end: date, req_id=None):
    """Liste der Urlaubstage im Zeitraum (sortiert). req_id: beim Neuberechnen eines genehmigten Antrags zaehlen
    dessen in 'urlaub' umgewandelte echte Schichten weiter als Arbeitstag."""
    if not start or not end or end < start:
        return []
    db.flush()   # eben zurueckgesetzte/geloeschte Urlaubs-Schichten (Aendern) mitzaehlen
    mo, so = start - timedelta(days=start.weekday()), end + timedelta(days=6 - end.weekday())
    plan = db.execute(text("""SELECT date, status, planned_hours, notes FROM schedules
                               WHERE employee_id = :e AND date BETWEEN :a AND :b"""),
                      {"e": employee_id, "a": mo, "b": so}).mappings().all()
    eigen = f"Urlaubsantrag #{req_id}" if req_id else None
    arbeit, wochen = set(), set()
    for s in plan:
        if _platzhalter(s):
            continue
        wochen.add(s["date"] - timedelta(days=s["date"].weekday()))
        if s["status"] in ARBEIT or (eigen and s["status"] == "urlaub" and s["notes"] == eigen):
            arbeit.add(s["date"])

    vorlage = db.execute(text("""SELECT weekday, rhythm, month_week FROM master_schedule_entries
                                  WHERE employee_id = :e AND coalesce(is_active, true)"""), {"e": employee_id}).mappings().all()
    profil = wtage = None
    if not vorlage:
        p = db.execute(text("SELECT work_days_profile FROM employees WHERE id = :e"), {"e": employee_id}).scalar()
        if p and p.strip():
            profil = parse_work_days_profile(p)
        else:
            wtage = {r[0] for r in db.execute(text("""SELECT DISTINCT weekday FROM schedules WHERE employee_id = :e
                                                       AND status IN ('normal', 'vertretung')"""), {"e": employee_id})} \
                or set(DEFAULT_WORK_DAYS)

    from app.services.plan_vorlage import rhythmus_passt
    out, d = [], start
    while d <= end:
        if not is_feiertag_bw(d):
            if d - timedelta(days=d.weekday()) in wochen:
                ja = d in arbeit
            elif vorlage:
                ja = any(v["weekday"] == d.weekday() and rhythmus_passt(v["rhythm"], v["month_week"], v["weekday"], d)
                         for v in vorlage)
            else:
                ja = d.weekday() in (profil if profil is not None else wtage)
            if ja:
                out.append(d)
        d += timedelta(days=1)
    return out


def anzahl(db, employee_id, start, end, req_id=None) -> float:
    return float(len(tage(db, employee_id, start, end, req_id)))


# ------------------------------------------------------------------ Urlaubskonten

def genehmigt_summe(db, employee_id, jahr) -> float:
    """Genehmigte Urlaubstage eines Jahres (Zuordnung wie bisher ueber das Startdatum des Antrags)."""
    return float(db.execute(text("""SELECT coalesce(sum(working_days), 0) FROM vacation_requests
                                     WHERE employee_id = :e AND status = 'approved' AND coalesce(type, 'urlaub') = 'urlaub'
                                       AND extract(year FROM start_date) = :y"""), {"e": employee_id, "y": jahr}).scalar())


def anspruch_vorjahr(db, employee_id, jahr):
    """Anspruch wie im Vorjahr, ohne den Uebertrag, der im Vorjahr dazukam (None = kein Vorjahreskonto)."""
    r = db.execute(text("""SELECT days_entitled - coalesce(days_carried, 0) FROM vacation_entitlements
                            WHERE employee_id = :e AND year = :y"""),
                   {"e": employee_id, "y": jahr - 1}).scalar()
    return float(r) if r is not None else None


def konto_neu(db, employee_id, jahr, anspruch=None, **extra):
    """Neues Urlaubskonto: Anspruch (Standard wie Vorjahr, sonst 0), bereits genehmigte Antraege des Jahres sind
    sofort abgezogen. Gibt das (noch nicht committete) VacationEntitlement zurueck."""
    from app.models.models import VacationEntitlement
    if anspruch is None:
        anspruch = anspruch_vorjahr(db, employee_id, jahr) or 0.0
    genommen = genehmigt_summe(db, employee_id, jahr)
    ent = VacationEntitlement(employee_id=employee_id, year=jahr, days_entitled=float(anspruch),
                              days_taken=genommen, days_remaining=float(anspruch) - genommen, **extra)
    db.add(ent)
    return ent
