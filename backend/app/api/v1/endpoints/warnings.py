from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.models.models import Warning, Employee
from app.schemas.warning_schema import WarningResponse
from app.api.v1.endpoints.auth import get_current_user
from app.core.validation_service import ValidationService

router = APIRouter()

@router.get("/", response_model=List[WarningResponse])
def get_all_warnings(
    skip: int = 0,
    limit: int = 100,
    only_unresolved: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Alle Warnungen abrufen (nur Admin)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Admins können alle Warnungen sehen")
    
    query = db.query(Warning)
    if only_unresolved:
        query = query.filter(Warning.is_resolved == False)
    
    warnings = query.order_by(Warning.created_at.desc()).offset(skip).limit(limit).all()
    return warnings

@router.get("/my", response_model=List[WarningResponse])
def get_my_warnings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Eigene Warnungen abrufen"""
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []
    
    warnings = db.query(Warning).filter(
        Warning.employee_id == employee.id,
        Warning.is_resolved == False
    ).order_by(Warning.created_at.desc()).all()
    
    return warnings

@router.post("/check-all")
def run_all_checks(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Alle Validierungen manuell ausführen (Admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Admins")
    
    results = {
        "missing_checkouts": ValidationService.check_missing_checkout(db),
        "no_shows": ValidationService.check_no_show(db)
    }
    
    return {"message": "Prüfungen durchgeführt", "results": results}

@router.put("/{warning_id}/resolve")
def resolve_warning(
    warning_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Warnung als erledigt markieren"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Admins")
    
    warning = db.query(Warning).filter(Warning.id == warning_id).first()
    if not warning:
        raise HTTPException(status_code=404, detail="Warnung nicht gefunden")
    
    warning.is_resolved = True
    warning.resolved_at = datetime.now()
    db.commit()
    
    return {"message": "Warnung als erledigt markiert"}
