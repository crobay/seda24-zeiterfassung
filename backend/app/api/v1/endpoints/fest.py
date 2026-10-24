"""Sommerfest-Umfrage Endpoints (oeffentlich, kein Login noetig)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.database import SessionLocal
from app.models.models import Employee
from sqlalchemy import text
from datetime import datetime

router = APIRouter()


class FestAntwort(BaseModel):
    personal_nr: str
    termin_wahl: str
    begleitung: str


@router.get("/info/{personal_nr}")
def get_fest_info(personal_nr: str):
    """Oeffentlich: MA-Vorname + bestehende Antwort laden."""
    db = SessionLocal()
    try:
        emp = db.query(Employee).filter(Employee.personal_nr == personal_nr, Employee.is_active == True).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

        row = db.execute(
            text("SELECT termin_wahl, begleitung FROM fest_antworten WHERE employee_id = :eid"),
            {"eid": emp.id}
        ).fetchone()

        return {
            "first_name": emp.first_name,
            "personal_nr": personal_nr,
            "existing_answer": {
                "termin_wahl": row[0],
                "begleitung": row[1]
            } if row else None
        }
    finally:
        db.close()


@router.post("/antwort")
def submit_fest_antwort(data: FestAntwort):
    """Oeffentlich: Antwort speichern/aktualisieren (UPSERT)."""
    if data.termin_wahl not in ('25_07', '01_08', 'beide', 'keiner'):
        raise HTTPException(status_code=400, detail="Ungueltige Terminwahl")
    if data.begleitung not in ('allein', 'zu_zweit'):
        raise HTTPException(status_code=400, detail="Ungueltige Begleitung")

    db = SessionLocal()
    try:
        emp = db.query(Employee).filter(Employee.personal_nr == data.personal_nr, Employee.is_active == True).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

        existing = db.execute(
            text("SELECT id FROM fest_antworten WHERE employee_id = :eid"),
            {"eid": emp.id}
        ).fetchone()

        if existing:
            db.execute(text(
                "UPDATE fest_antworten SET termin_wahl = :tw, begleitung = :bg, updated_at = :now WHERE employee_id = :eid"
            ), {"tw": data.termin_wahl, "bg": data.begleitung, "now": datetime.now(), "eid": emp.id})
        else:
            db.execute(text(
                "INSERT INTO fest_antworten (employee_id, personal_nr, termin_wahl, begleitung) VALUES (:eid, :pnr, :tw, :bg)"
            ), {"eid": emp.id, "pnr": data.personal_nr, "tw": data.termin_wahl, "bg": data.begleitung})

        db.commit()
        return {"status": "ok", "message": "Danke fuer deine Antwort!"}
    finally:
        db.close()


@router.delete("/admin/antwort/{personal_nr}")
def delete_fest_antwort(personal_nr: str):
    """Admin: Antwort eines MA loeschen."""
    db = SessionLocal()
    try:
        emp = db.query(Employee).filter(Employee.personal_nr == personal_nr).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
        db.execute(text("DELETE FROM fest_antworten WHERE employee_id = :eid"), {"eid": emp.id})
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@router.get("/admin/overview")
def get_fest_overview():
    """Admin: Uebersicht aller Antworten + fehlende MAs."""
    db = SessionLocal()
    try:
        answers = db.execute(text(
            "SELECT fa.personal_nr, e.first_name, e.last_name, fa.termin_wahl, fa.begleitung, fa.updated_at "
            "FROM fest_antworten fa JOIN employees e ON e.id = fa.employee_id ORDER BY e.first_name"
        )).fetchall()

        # D0001/D0002/D0032 = Organisatoren, keine Umfrage-Teilnehmer
        all_active = db.execute(text(
            "SELECT e.personal_nr, e.first_name, e.last_name FROM employees e "
            "WHERE e.is_active = true AND e.personal_nr NOT LIKE 'A%%' "
            "AND e.personal_nr NOT IN ('D0001','D0002','D0032') ORDER BY e.first_name"
        )).fetchall()

        answered_pnrs = {a[0] for a in answers}
        not_answered = [{"personal_nr": m[0], "first_name": m[1], "last_name": m[2]}
                        for m in all_active if m[0] not in answered_pnrs]

        personen_25_07 = 0
        personen_01_08 = 0
        for a in answers:
            tw, bg = a[3], a[4]
            p = 2 if bg == 'zu_zweit' else 1
            if tw in ('25_07', 'beide'):
                personen_25_07 += p
            if tw in ('01_08', 'beide'):
                personen_01_08 += p

        return {
            "answers": [{"personal_nr": a[0], "first_name": a[1], "last_name": a[2],
                          "termin_wahl": a[3], "begleitung": a[4], "updated_at": str(a[5])} for a in answers],
            "not_answered": not_answered,
            "stats": {
                "personen_25_07": personen_25_07,
                "personen_01_08": personen_01_08,
                "total_answered": len(answers),
                "total_not_answered": len(not_answered)
            }
        }
    finally:
        db.close()
