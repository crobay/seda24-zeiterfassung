from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.models.models import Employee, User, UserRole
from app.schemas.employee_schema import EmployeeResponse
from app.core.auth import get_current_user

router = APIRouter()

@router.get("/", response_model=List[EmployeeResponse])
def get_all_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Alle Mitarbeiter abrufen (nur Admin)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Nur Admins dürfen alle Mitarbeiter sehen")
    
    employees = db.query(Employee).join(User).filter(User.role != UserRole.ADMIN).all()
    return employees
    return employees
    } for e in employees]
