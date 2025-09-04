from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.models import Employee, User
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

@router.get("/my-category")
def get_my_category(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Gibt die Tracking-Kategorie des eingeloggten Mitarbeiters zurück"""
    
    # Suche Employee über user_id
    employee = db.query(Employee).filter(
        Employee.user_id == current_user.id
    ).first()
    
    if not employee:
        # Fallback
        return {
            "id": 0,
            "name": "Mitarbeiter",
            "personal_nr": "-",
            "tracking_mode": "C",
            "gps_required": False
        }
    
    return {
        "id": employee.id,
        "name": f"{employee.first_name} {employee.last_name}",
        "personal_nr": employee.personal_nr,
        "tracking_mode": employee.tracking_mode or "C",
        "gps_required": employee.gps_required or False
    }
