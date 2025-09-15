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
        "tracking_mode": employee.tracking_mode or "C",,,
        "gps_required": employee.gps_required or False
    }
        "gps_required": employee.gps_required or False
    }
        "gps_required": employee.gps_required or False
    }

@router.post("/")
def create_employee(
    employee_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Neuen Mitarbeiter anlegen"""
    # Check ob Personal-Nr schon existiert
    existing = db.query(Employee).filter(
        Employee.personal_nr == employee_data.get("personal_nr")
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Personal-Nr existiert bereits")
    
    # Neuen User für den Mitarbeiter anlegen
    import random
    import string
    from app.models.models import User
    
    # Temporäres Passwort generieren
    temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # User erstellen
    new_user = User(
        email=employee_data.get("email"),
        hashed_password=temp_password,  # In Produktion hashen!
        role="user",
        is_active=True
    )
    db.add(new_user)
    db.flush()
    
    # Employee erstellen
    new_employee = Employee(
        personal_nr=employee_data.get("personal_nr"),
        first_name=employee_data.get("first_name"),
        last_name=employee_data.get("last_name"),
        hourly_rate=float(employee_data.get("hourly_rate", 15.0)),
        user_id=new_user.id,
        tracking_mode=employee_data.get("tracking_mode", "C"),
        address=employee_data.get("address", ""),
        kuerzel=employee_data.get("kuerzel", "")
    )
    
    db.add(new_employee)
    db.commit()
    
    return {
        "message": "Mitarbeiter erfolgreich angelegt",
        "personal_nr": new_employee.personal_nr,
        "temp_password": temp_password
    }
