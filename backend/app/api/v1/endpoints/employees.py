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
