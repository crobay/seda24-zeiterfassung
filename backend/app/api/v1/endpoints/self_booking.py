"""
SEDA24 – MA-Selbstbuchung mit Genehmigung.
Mitarbeiter reichen Buchungen ein, Admin genehmigt/lehnt ab.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, date, timedelta
from app.db.database import get_db
from app.models.models import Employee, User
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.get("/my-objects")
def get_my_assigned_objects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Gibt nur die Objekte zurueck, die dem MA in employee_object_assignments zugewiesen sind."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []

    result = db.execute(text("""
        SELECT eoa.object_id, eoa.is_driver, o.name, o.address
        FROM employee_object_assignments eoa
        JOIN objects o ON o.id = eoa.object_id
        WHERE eoa.employee_id = :emp_id
          AND (eoa.is_active = true OR eoa.is_active IS NULL)
          AND o.is_active = true
        ORDER BY o.name
    """), {"emp_id": employee.id})

    objects = []
    for row in result:
        objects.append({
            "id": row.object_id,
            "name": row.name,
            "address": row.address or "",
            "is_driver": row.is_driver or False,
        })
    return objects


@router.post("/submit")
def submit_self_booking(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """MA reicht eine Buchung zur Genehmigung ein."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")

    if current_user.category == 'A':
        raise HTTPException(status_code=403, detail="Kategorie A bucht automatisch")

    object_id = data.get("object_id")
    booking_date = data.get("date")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    service_type = data.get("service_type", "Unterhaltsreinigung")
    is_driver = data.get("is_driver", False)
    notes = data.get("notes", "")

    if not all([object_id, booking_date, start_time, end_time]):
        raise HTTPException(status_code=400, detail="Objekt, Datum, Von und Bis erforderlich")

    # Datum validieren: heute bis max 3 Tage zurueck
    try:
        bdate = date.fromisoformat(booking_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungueltiges Datum")

    today = date.today()
    if bdate > today:
        raise HTTPException(status_code=400, detail="Buchung in der Zukunft nicht erlaubt")
    if bdate < today - timedelta(days=3):
        raise HTTPException(status_code=400, detail="Maximal 3 Tage zurueck erlaubt")

    # Pruefen ob Objekt dem MA zugewiesen ist
    assignment = db.execute(text("""
        SELECT id FROM employee_object_assignments
        WHERE employee_id = :emp_id AND object_id = :obj_id
          AND (is_active = true OR is_active IS NULL)
    """), {"emp_id": employee.id, "obj_id": object_id}).fetchone()

    if not assignment:
        raise HTTPException(status_code=403, detail="Objekt nicht zugewiesen")

    # Stunden berechnen
    try:
        st = datetime.strptime(start_time, "%H:%M").time()
        et = datetime.strptime(end_time, "%H:%M").time()
        hours = round((datetime.combine(bdate, et) - datetime.combine(bdate, st)).total_seconds() / 3600, 2)
        if hours <= 0:
            raise HTTPException(status_code=400, detail="Endzeit muss nach Startzeit liegen")
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungueltiges Zeitformat (HH:MM)")

    # Doppelte Einreichung pruefen
    existing = db.execute(text("""
        SELECT id FROM pending_bookings
        WHERE employee_id = :emp_id AND object_id = :obj_id AND date = :dt
          AND status = 'offen'
    """), {"emp_id": employee.id, "obj_id": object_id, "dt": booking_date}).fetchone()

    if existing:
        raise HTTPException(status_code=400, detail="Fuer dieses Objekt/Datum ist bereits eine Buchung eingereicht")

    db.execute(text("""
        INSERT INTO pending_bookings
        (employee_id, object_id, date, start_time, end_time, service_type, is_driver, requested_hours, notes, status)
        VALUES (:emp_id, :obj_id, :dt, :st, :et, :stype, :driver, :hours, :notes, 'offen')
    """), {
        "emp_id": employee.id,
        "obj_id": object_id,
        "dt": booking_date,
        "st": start_time,
        "et": end_time,
        "stype": service_type,
        "driver": is_driver,
        "hours": hours,
        "notes": notes,
    })
    db.commit()
    return {"status": "ok", "message": "Buchung eingereicht", "hours": hours}


@router.get("/my-bookings")
def get_my_pending_bookings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """MA sieht eigene eingereichte Buchungen (letzte 30 Tage)."""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []

    result = db.execute(text("""
        SELECT pb.id, pb.date, pb.start_time, pb.end_time, pb.service_type,
               pb.is_driver, pb.requested_hours, pb.status, pb.created_at,
               pb.approved_hours, pb.admin_notes, pb.approved_at,
               o.name as object_name
        FROM pending_bookings pb
        JOIN objects o ON o.id = pb.object_id
        WHERE pb.employee_id = :emp_id
          AND pb.created_at >= NOW() - INTERVAL '30 days'
        ORDER BY pb.created_at DESC
    """), {"emp_id": employee.id})

    bookings = []
    for row in result:
        bookings.append({
            "id": row.id,
            "date": str(row.date),
            "start_time": str(row.start_time)[:5],
            "end_time": str(row.end_time)[:5],
            "service_type": row.service_type,
            "is_driver": row.is_driver,
            "requested_hours": float(row.requested_hours) if row.requested_hours else 0,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "approved_hours": float(row.approved_hours) if row.approved_hours else None,
            "admin_notes": row.admin_notes,
            "approved_at": row.approved_at.isoformat() if row.approved_at else None,
            "object_name": row.object_name,
        })
    return bookings
