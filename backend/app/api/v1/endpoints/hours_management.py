from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from app.db.database import get_db
from app.models.models import Employee, Customer, CustomerHours, SpecialRule
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

# Pydantic Models
class CustomerHoursUpdate(BaseModel):
    customer_id: int
    default_hours: float

class SpecialRuleCreate(BaseModel):
    employee_id: int
    customer_id: int
    special_hours: float
    note: Optional[str] = None

class CustomerHoursResponse(BaseModel):
    id: int
    name: str
    hours: float

class SpecialRuleResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    customer_id: int
    customer_name: str
    standard_hours: Optional[float]
    special_hours: float
    note: Optional[str]
    active: bool

# ===== SOLLSTUNDEN ENDPOINTS =====

@router.get("/customer-hours", response_model=List[CustomerHoursResponse])
def get_all_customer_hours(db: Session = Depends(get_db)):
    """Alle Kunden mit ihren Sollstunden"""
    query = text("""
        SELECT c.id, c.name, 
               COALESCE(ch.default_hours, 0) as default_hours
        FROM customers c
        LEFT JOIN customer_hours ch ON c.id = ch.customer_id
        ORDER BY c.name
    """)
    
    result = db.execute(query)
    return [
        CustomerHoursResponse(id=row[0], name=row[1], hours=float(row[2])) 
        for row in result
    ]

@router.put("/customer-hours")
def update_customer_hours(
    data: CustomerHoursUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Sollstunden für einen Kunden ändern (Admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur für Admins")
    
    # Check ob Kunde existiert
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
    
    # Upsert - einfügen oder updaten
    existing = db.query(CustomerHours).filter(
        CustomerHours.customer_id == data.customer_id
    ).first()
    
    if existing:
        existing.default_hours = data.default_hours
    else:
        new_hours = CustomerHours(
            customer_id=data.customer_id,
            default_hours=data.default_hours
        )
        db.add(new_hours)
    
    db.commit()
    return {"message": "Sollstunden aktualisiert", "status": "success"}

# ===== SPEZIALREGELN ENDPOINTS =====

@router.get("/special-rules", response_model=List[SpecialRuleResponse])
def get_all_special_rules(db: Session = Depends(get_db)):
    """Alle aktiven Spezialregeln mit Details"""
    query = text("""
        SELECT 
            sr.id,
            sr.employee_id,
            e.first_name || ' ' || e.last_name as employee_name,
            sr.customer_id,
            c.name as customer_name,
            ch.default_hours as standard_hours,
            sr.special_hours,
            sr.note,
            sr.active
        FROM special_rules sr
        JOIN employees e ON sr.employee_id = e.id
        JOIN customers c ON sr.customer_id = c.id
        LEFT JOIN customer_hours ch ON c.id = ch.customer_id
        WHERE sr.active = true
        ORDER BY c.name, e.first_name
    """)
    
    result = db.execute(query)
    return [
        SpecialRuleResponse(
            id=row[0],
            employee_id=row[1],
            employee_name=row[2],
            customer_id=row[3],
            customer_name=row[4],
            standard_hours=float(row[5]) if row[5] else None,
            special_hours=float(row[6]),
            note=row[7],
            active=row[8]
        )
        for row in result
    ]

@router.post("/special-rules")
def create_special_rule(
    data: SpecialRuleCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Neue Spezialregel anlegen (Admin only)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur für Admins")
    
    # Validierung
    employee = db.query(Employee).filter(Employee.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Kunde nicht gefunden")
    
    # Check ob schon existiert
    existing = db.query(SpecialRule).filter(
        SpecialRule.employee_id == data.employee_id,
        SpecialRule.customer_id == data.customer_id
    ).first()
    
    if existing:
        # Update statt neu anlegen
        existing.special_hours = data.special_hours
        existing.note = data.note
        existing.active = True
    else:
        new_rule = SpecialRule(
            employee_id=data.employee_id,
            customer_id=data.customer_id,
            special_hours=data.special_hours,
            note=data.note
        )
        db.add(new_rule)
    
    db.commit()
    return {"message": "Spezialregel gespeichert", "status": "success"}

@router.delete("/special-rules/{rule_id}")
def delete_special_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Spezialregel deaktivieren (soft delete)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Nur für Admins")
    
    rule = db.query(SpecialRule).filter(SpecialRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")
    
    rule.active = False
    db.commit()
    
    return {"message": "Regel deaktiviert", "status": "success"}

# ===== BERECHNUNG MIT REGELN =====

@router.get("/calculate-hours/{employee_id}/{customer_id}")
def calculate_work_hours(
    employee_id: int, 
    customer_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Berechnet die Sollstunden unter Berücksichtigung von Spezialregeln"""
    
    # 1. Prüfe Spezialregel (z.B. Eldina bei Lidl)
    special_rule = db.query(SpecialRule).filter(
        SpecialRule.employee_id == employee_id,
        SpecialRule.customer_id == customer_id,
        SpecialRule.active == True
    ).first()
    
    if special_rule and special_rule.special_hours:
        return {
            "hours": float(special_rule.special_hours),
            "is_special": True,
            "note": special_rule.note
        }
    
    # 2. Sonst Standard-Sollstunden
    customer_hours = db.query(CustomerHours).filter(
        CustomerHours.customer_id == customer_id
    ).first()
    
    if customer_hours:
        return {
            "hours": float(customer_hours.default_hours),
            "is_special": False,
            "note": None
        }
    
    # 3. Fallback wenn nichts definiert
    return {
        "hours": 8.0,
        "is_special": False,
        "note": "Keine Sollstunden definiert - Standard 8h"
    }

@router.get("/minijob-check/{employee_id}")
def check_minijob_status(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Prüft Minijob-Status und warnt bei Überschreitung"""
    
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    # Skip wenn kein Minijobber
    if employee.employment_type != 'minijob':
        return {
            "is_minijob": False,
            "employment_type": employee.employment_type
        }
    
    # Berechne aktuellen Monat (hier vereinfacht)
    # TODO: Tatsächliche Stunden aus time_entries berechnen
    from datetime import datetime
    from sqlalchemy import func, extract
    
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    # Dummy-Berechnung - müsste mit echten time_entries gemacht werden
    current_amount = 0  # Hier würde die echte Berechnung stehen
    
    max_amount = float(employee.max_monthly_amount) if employee.max_monthly_amount else 556.0
    
    return {
        "is_minijob": True,
        "max_amount": max_amount,
        "current_amount": current_amount,
        "remaining_amount": max_amount - current_amount,
        "warning": current_amount > (max_amount * 0.9),  # Warnung bei 90%
        "critical": current_amount >= max_amount  # Kritisch bei 100%
    }