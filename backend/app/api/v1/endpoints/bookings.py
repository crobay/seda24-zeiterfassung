from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import verify_admin
from sqlalchemy import text
from datetime import datetime

router = APIRouter()

@router.get("/all")
def get_all_bookings(db: Session = Depends(get_db), admin = Depends(verify_admin)):
    query = text("""
        SELECT 
            te.id, te.employee_id, te.object_id, te.check_in, te.check_out,
            te.billed_hours, te.hourly_rate, te.service_type, te.is_manual_entry, te.notes,
            e.first_name || ' ' || e.last_name as employee_name, o.name as object_name
        FROM time_entries te
        JOIN employees e ON e.id = te.employee_id
        JOIN objects o ON o.id = te.object_id
        ORDER BY te.check_in DESC LIMIT 1000
    """)
    
    result = db.execute(query)
    bookings = []
    for row in result:
        bookings.append({
            "id": row[0], "employee_id": row[1], "object_id": row[2],
            "check_in": row[3].isoformat() if row[3] else None,
            "check_out": row[4].isoformat() if row[4] else None,
            "billed_hours": float(row[5]) if row[5] else 0,
            "hourly_rate": float(row[6]) if row[6] else 0,
            "service_type": row[7], "is_manual_entry": row[8], "notes": row[9],
            "employee_name": row[10], "object_name": row[11]
        })
    return bookings

@router.put("/{booking_id}")
def update_booking(booking_id: int, data: dict, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    check_in = data.get("check_in")
    check_out = data.get("check_out")
    billed_hours = None
    
    if check_in and check_out:
        try:
            start = datetime.fromisoformat(check_in.replace('Z', '+00:00'))
            end = datetime.fromisoformat(check_out.replace('Z', '+00:00'))
            billed_hours = (end - start).total_seconds() / 3600
        except:
            pass
    
    if billed_hours:
        query = text("UPDATE time_entries SET check_in=:ci, check_out=:co, object_id=:oid, notes=:n, billed_hours=:bh WHERE id=:id")
        db.execute(query, {"id": booking_id, "ci": check_in, "co": check_out, "oid": data.get("object_id"), "n": data.get("notes", ""), "bh": billed_hours})
    else:
        query = text("UPDATE time_entries SET check_in=:ci, check_out=:co, object_id=:oid, notes=:n WHERE id=:id")
        db.execute(query, {"id": booking_id, "ci": check_in, "co": check_out, "oid": data.get("object_id"), "n": data.get("notes", "")})
    
    db.commit()
    return {"message": "OK"}

@router.delete("/{booking_id}")
def delete_booking(booking_id: int, db: Session = Depends(get_db), admin = Depends(verify_admin)):
    db.execute(text("DELETE FROM time_entries WHERE id = :id"), {"id": booking_id})
    db.commit()
    return {"message": "OK"}
