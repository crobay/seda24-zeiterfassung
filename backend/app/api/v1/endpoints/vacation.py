from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.models import User
from sqlalchemy import text

router = APIRouter()

@router.get("/my-vacation")
async def get_my_vacation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = db.execute(text("""
        SELECT 
            v.days_entitled,
            v.days_taken,
            v.days_remaining,
            v.vacation_rate,
            e.first_name,
            e.last_name
        FROM vacation_entitlements v
        JOIN employees e ON v.employee_id = e.id
        WHERE e.user_id = :user_id AND v.year = 2025
    """), {"user_id": current_user.id})
    
    vacation = result.fetchone()
    if not vacation:
        return {
            "days_entitled": 0,
            "days_taken": 0,
            "days_remaining": 0,
            "vacation_rate": 0
        }
    
    return {
        "days_entitled": vacation[0],
        "days_taken": vacation[1],
        "days_remaining": vacation[2],
        "vacation_rate": vacation[3],
        "name": f"{vacation[4]} {vacation[5]}"
    }
