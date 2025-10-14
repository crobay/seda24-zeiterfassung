from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.database import get_db
from app.models.models import User
from app.core.security import get_current_user

router = APIRouter()

@router.get("/my-category")
def get_my_category(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = text("""
        SELECT e.id, e.personal_nr, e.first_name, e.last_name, e.tracking_mode, e.gps_required
        FROM employees e
        WHERE e.user_id = :user_id
    """)
    
    result = db.execute(query, {"user_id": current_user.id}).fetchone()
    
    if result:
        return {
            "id": result[0],
            "name": f"{result[2]} {result[3]}",
            "personal_nr": result[1],
            "tracking_mode": result[4] if result[4] else "C",
            "gps_required": bool(result[5]) if result[5] else False
        }
    
    return {
        "id": 0,
        "name": "Mitarbeiter",
        "personal_nr": "-",
        "tracking_mode": "C",
        "gps_required": False
    }

@router.get("/my-colleagues-today")
@router.get("/my-colleagues-today")
def get_my_colleagues_today(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kollegen-Feature deaktiviert für v1.0"""
    return []
    
    # Finde Kollegen für HEUTE
    query = text("""
        SELECT DISTINCT e.id, e.first_name, e.last_name, e.personal_nr
        FROM schedules s1
        JOIN schedules s2 ON 
            s1.object_id = s2.object_id 
            AND s1.weekday = s2.weekday
            AND s1.employee_id != s2.employee_id
        JOIN employees e ON s2.employee_id = e.id
        WHERE s1.employee_id = :my_id
            AND s1.weekday = :weekday
        ORDER BY e.first_name
    """)
    
    colleagues = db.execute(query, {
        "my_id": my_employee[0],
        "weekday": today_weekday
    }).fetchall()
    
    return [
        {
            "id": c[0],
            "name": f"{c[1]} {c[2]}",
            "personal_nr": c[3]
        }
        for c in colleagues
    ]
