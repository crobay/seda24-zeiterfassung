"""Urlaubskonten eines Jahres anlegen + Antraege nach der neuen Zaehlung (services/urlaubstage.py) nachrechnen
(Drazen 25.11.2026 20:25). Ohne --schreiben nur Vorschau (Transaktion wird zurueckgerollt). Kein Telegram, keine Mail.

  1. Genehmigte Antraege mit Beginn im Jahr: Urlaubstage/-buchungen neu (nur Tage, an denen der MA arbeiten wuerde,
     nie Feiertage), working_days = Anzahl. Offene Antraege ab heute: working_days neu.
  2. Aktive MA (ohne A..., ohne Test-MA) ohne Konto im Jahr: Anspruch wie Vorjahr (ohne dessen Uebertrag),
     Uebertrag = Rest Vorjahr (wie /admin/carry-over), genehmigte Antraege des Jahres sofort abgezogen.

Aufruf aus backend/: venv/bin/python ../tools/urlaub_konten.py 2027 [--schreiben] [--go "GO-Text"]"""
import argparse, os, sys
from datetime import date
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(".env")
from sqlalchemy import text
from app.db.database import SessionLocal
from app.models.models import Employee, VacationRequest, VacationEntitlement
from app.services import urlaubstage as ut
from app.services.booking_service import log_audit
from app.api.v1.endpoints.vacation import _create_vacation_schedules, _revert_vacation_schedules

ap = argparse.ArgumentParser()
ap.add_argument("jahr", type=int)
ap.add_argument("--schreiben", action="store_true")
ap.add_argument("--go", default="")
a = ap.parse_args()
J = a.jahr
db = SessionLocal()
admin = db.execute(text("SELECT id FROM users WHERE email = 'admin@seda24.de'")).scalar()
GO = f" – {a.go}" if a.go else ""
fmt = lambda d: f"{d:%d.%m.%Y}"
try:
    print(f"== 1. Antraege nachrechnen ({'SCHREIBEN' if a.schreiben else 'Vorschau'})")
    gen = db.query(VacationRequest).filter(VacationRequest.status == "approved",
                                           VacationRequest.start_date >= date(J, 1, 1),
                                           VacationRequest.start_date <= date(J, 12, 31)).order_by(VacationRequest.id).all()
    for r in gen:
        emp = db.get(Employee, r.employee_id)
        vorher = db.execute(text("""SELECT string_agg(to_char(date, 'DD.MM.'), ',' ORDER BY date) FROM schedules
                                     WHERE employee_id = :e AND notes = :n"""), {"e": r.employee_id, "n": f"Urlaubsantrag #{r.id}"}).scalar()
        fest = db.execute(text("""SELECT count(*) FROM time_entries WHERE employee_id = :e AND object_id = 999
                                   AND notes LIKE :n AND hourly_rate <> -1"""), {"e": r.employee_id, "n": f"%Urlaubsantrag #{r.id} %"}).scalar()
        if fest:
            print(f"  #{r.id} {emp.first_name} {emp.last_name}: {fest} Urlaubstage schon bewertet -> NICHT angefasst")
            continue
        alt = r.working_days
        _revert_vacation_schedules(db, r)
        _create_vacation_schedules(db, r, emp)
        db.flush()
        neu = db.execute(text("""SELECT string_agg(to_char(date, 'DD.MM.'), ',' ORDER BY date) FROM schedules
                                  WHERE employee_id = :e AND notes = :n"""), {"e": r.employee_id, "n": f"Urlaubsantrag #{r.id}"}).scalar()
        print(f"  #{r.id} {emp.first_name} {emp.last_name} {fmt(r.start_date)}-{fmt(r.end_date)} ({r.type}): "
              f"{alt:g} -> {r.working_days:g} Tage | vorher {vorher or '-'} | jetzt {neu or '-'}")
        if alt != r.working_days or (vorher or "") != (neu or ""):
            log_audit(db, admin, r.employee_id, "vacation_request_updated", "vacation_request", r.id,
                      old_value={"working_days": alt, "tage": vorher}, new_value={"working_days": r.working_days, "tage": neu},
                      details=f"Urlaub {fmt(r.start_date)}-{fmt(r.end_date)} neu gezaehlt (Dienstplan/Vorlage, ohne Feiertage): "
                              f"{alt:g} -> {r.working_days:g} Tage ({emp.first_name} {emp.last_name}){GO}")
    for r in db.query(VacationRequest).filter(VacationRequest.status == "pending", VacationRequest.end_date >= date.today()).all():
        alt, neu = r.working_days, ut.anzahl(db, r.employee_id, r.start_date, r.end_date)
        print(f"  offen #{r.id} MA {r.employee_id} {fmt(r.start_date)}-{fmt(r.end_date)}: {alt:g} -> {neu:g} Tage")
        if alt != neu:
            r.working_days = neu
            log_audit(db, admin, r.employee_id, "vacation_request_updated", "vacation_request", r.id,
                      old_value={"working_days": alt}, new_value={"working_days": neu},
                      details=f"Offener Urlaubsantrag neu gezaehlt: {alt:g} -> {neu:g} Tage{GO}")
    db.flush()

    print(f"\n== 2. Urlaubskonten {J}")
    zeilen = []
    for e in db.query(Employee).filter(Employee.is_active == True).order_by(Employee.personal_nr).all():
        if (e.personal_nr or "").startswith("A") or getattr(e, "is_test", False):
            continue
        ent = db.query(VacationEntitlement).filter_by(employee_id=e.id, year=J).first()
        vj = db.query(VacationEntitlement).filter_by(employee_id=e.id, year=J - 1).first()
        hinweis = ""
        if ent:
            hinweis = "Konto gab es schon - unveraendert"
        else:
            anspruch = ut.anspruch_vorjahr(db, e.id, J)
            if anspruch is None:
                anspruch, hinweis = 0.0, f"kein Konto {J - 1} -> Anspruch 0, bitte setzen"
            ent = ut.konto_neu(db, e.id, J, anspruch=anspruch)
            uebertrag = max(0.0, float(vj.days_remaining or 0)) if vj else 0.0
            ent.days_carried = uebertrag
            ent.days_entitled = anspruch + uebertrag
            ent.days_remaining = ent.days_entitled - ent.days_taken
            db.flush()
            log_audit(db, admin, e.id, "vacation_entitlement_updated", "vacation_entitlement", ent.id,
                      new_value={"jahr": J, "anspruch": anspruch, "uebertrag": uebertrag, "genommen": ent.days_taken},
                      details=f"Urlaubskonto {J} angelegt: {e.first_name} {e.last_name}, Anspruch {anspruch:g} + Uebertrag "
                              f"{uebertrag:g}, genehmigt {ent.days_taken:g}, Rest {ent.days_remaining:g}{GO}")
        car = float(ent.days_carried or 0)
        art = db.execute(text("SELECT employment_type FROM employees WHERE id = :e"), {"e": e.id}).scalar()
        zeilen.append((e.personal_nr, f"{e.first_name} {e.last_name}", art or "", float(ent.days_entitled or 0) - car,
                       car, float(ent.days_taken or 0), float(ent.days_remaining or 0), hinweis))
    print(f"{'Nr':6} {'Name':22} {'Art':9} {'Anspruch':>8} {'Uebertr.':>8} {'genehm.':>8} {'Rest':>6}  Hinweis")
    for z in zeilen:
        print(f"{z[0]:6} {z[1]:22} {z[2]:9} {z[3]:8g} {z[4]:8g} {z[5]:8g} {z[6]:6g}  {z[7]}")
    if a.schreiben:
        db.commit()
        print("\nGESCHRIEBEN")
    else:
        db.rollback()
        print("\nVorschau - nichts gespeichert")
finally:
    db.rollback()
    db.close()
