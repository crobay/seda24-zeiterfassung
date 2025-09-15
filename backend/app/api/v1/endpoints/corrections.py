from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.db.database import get_db
from app.models.models import CorrectionRequest, Employee, User, TimeEntry, Object
from app.schemas.correction_schema import (
    CorrectionRequestCreate,
    CorrectionRequestUpdate,
    CorrectionRequestResponse,
    CorrectionRequestList
)
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=CorrectionRequestResponse)
def create_correction_request(
    correction: CorrectionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mitarbeiter erstellt Korrektur-Anfrage"""
    
    # Hole Employee-Daten
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Prüfe ob TimeEntry existiert und dem Mitarbeiter gehört
    time_entry = db.query(TimeEntry).filter(
        TimeEntry.id == correction.time_entry_id,
        TimeEntry.employee_id == employee.id
    ).first()
    
    if not time_entry:
        raise HTTPException(
            status_code=404, 
            detail="Zeiteintrag nicht gefunden oder gehört nicht dir"
        )
    
    # Prüfe ob schon eine offene Korrektur für diesen Eintrag existiert
    existing = db.query(CorrectionRequest).filter(
        CorrectionRequest.time_entry_id == correction.time_entry_id,
        CorrectionRequest.status == "pending"
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Es gibt bereits eine offene Korrektur für diesen Eintrag"
        )
    
    # Erstelle Korrektur-Anfrage
    db_correction = CorrectionRequest(
        employee_id=employee.id,
        time_entry_id=correction.time_entry_id,
        correction_type=correction.correction_type,
        old_value=correction.old_value,
        new_value=correction.new_value,
        reason=correction.reason,
        status="pending"
    )
    
    db.add(db_correction)
    db.commit()
    db.refresh(db_correction)
    
    # Füge Zusatz-Infos hinzu
    response = CorrectionRequestResponse.from_orm(db_correction)
    response.employee_name = f"{employee.first_name} {employee.last_name}"
    
    return response

@router.get("/", response_model=CorrectionRequestList)
def get_all_corrections(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Admin sieht alle Korrekturen, Mitarbeiter nur eigene"""
    
    query = db.query(CorrectionRequest)
    
    # Wenn nicht Admin, nur eigene anzeigen
    if current_user.role != "admin":
        employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
        if employee:
            query = query.filter(CorrectionRequest.employee_id == employee.id)
    
    # Status-Filter wenn gewünscht
    if status_filter:
        query = query.filter(CorrectionRequest.status == status_filter)
    
    corrections = query.order_by(CorrectionRequest.created_at.desc()).all()
    
    # Zähle pending für Admins
    pending_count = 0
    if current_user.role == "admin":
        pending_count = db.query(CorrectionRequest).filter(
            CorrectionRequest.status == "pending"
        ).count()
    
    # Füge Namen hinzu
    result = []
    for corr in corrections:
        response = CorrectionRequestResponse.from_orm(corr)
        response.employee_name = f"{corr.employee.first_name} {corr.employee.last_name}"
        if corr.time_entry.object:
            response.object_name = corr.time_entry.object.name
        result.append(response)
    
    return CorrectionRequestList(
        total=len(corrections),
        pending=pending_count,
        corrections=result
    )

@router.put("/{correction_id}", response_model=CorrectionRequestResponse)
def process_correction(
    correction_id: int,
    update: CorrectionRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Admin genehmigt oder lehnt Korrektur ab"""
    
    # Nur Admins dürfen das
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Nur Admins können Korrekturen bearbeiten"
        )
    
    # Hole Korrektur
    correction = db.query(CorrectionRequest).filter(
        CorrectionRequest.id == correction_id
    ).first()
    
    if not correction:
        raise HTTPException(status_code=404, detail="Korrektur nicht gefunden")
    
    if correction.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Korrektur wurde bereits bearbeitet"
        )
    
    # Update Status
    correction.status = update.status
    correction.admin_response = update.admin_response
    correction.processed_by = current_user.id
    correction.processed_at = datetime.utcnow()
    
    # Wenn genehmigt, führe die Änderung durch
    if update.status == "approved":
        time_entry = correction.time_entry
        
        if correction.correction_type == "check_in":
            time_entry.check_in = datetime.fromisoformat(correction.new_value)
        elif correction.correction_type == "check_out":
            time_entry.check_out = datetime.fromisoformat(correction.new_value)
        elif correction.correction_type == "object":
            time_entry.object_id = int(correction.new_value)
        elif correction.correction_type == "delete":
            db.delete(time_entry)
    
    db.commit()
    db.refresh(correction)
    
    # Response mit Namen
    response = CorrectionRequestResponse.from_orm(correction)
    response.employee_name = f"{correction.employee.first_name} {correction.employee.last_name}"
    
    return response

@router.get("/my", response_model=List[CorrectionRequestResponse])
def get_my_corrections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mitarbeiter sieht nur eigene Korrekturen"""
    
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        return []
    
    corrections = db.query(CorrectionRequest).filter(
        CorrectionRequest.employee_id == employee.id
    ).order_by(CorrectionRequest.created_at.desc()).all()
    
    result = []
    for corr in corrections:
        response = CorrectionRequestResponse.from_orm(corr)
        response.employee_name = f"{employee.first_name} {employee.last_name}"
        result.append(response)
    
    return result
